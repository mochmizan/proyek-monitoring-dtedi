#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_SHT31.h>
#include <EEPROM.h>

#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRsend.h>
#include <ir_Gree.h>

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Secrets (gitignored) — copy firmware/common/secrets.h.example to firmware/common/secrets.h
// For Arduino IDE: copy firmware/common/secrets.h into this sketch folder and use #include "secrets.h"
#if __has_include("../common/secrets.h")
#include "../common/secrets.h"
#elif __has_include("secrets.h")
#include "secrets.h"
#else
#error "copy firmware/common/secrets.h.example to firmware/common/secrets.h and set WIFI_PASS/MQTT_PASS"
#endif
#ifndef WIFI_PASS
#error "copy firmware/common/secrets.h.example to firmware/common/secrets.h and set WIFI_PASS/MQTT_PASS"
#endif

//========================
// OLED Display Config
//========================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
Adafruit_SHT31 sht30 = Adafruit_SHT31();

// Supported I2C addresses for auto-probing
const uint8_t OLED_CANDIDATES[] = {0x3C, 0x3D};
const uint8_t SHT_CANDIDATES[]  = {0x44, 0x45};

uint8_t detectedOledAddr = 0;
uint8_t detectedShtAddr  = 0;

bool isOledPresent = false;
bool isShtPresent  = false;

//========================
// IR Transmitter Pins
//========================
const uint16_t IR1_PIN = D5;
const uint16_t IR2_PIN = D6;

//========================
// WiFi Config
//========================
const char* NAMA_WIFI     = WIFI_SSID;
const char* NAMA_PASSWORD = WIFI_PASS;

//========================
// MQTT Broker Config (Hub)
//========================
const char*     MQTT_IP       = MQTT_HOST;   // IP Raspberry Pi Hub (from secrets.h)
const uint16_t  MQTT_PORT     = 1883;
const char*     DATA_TOPIC    = "hs109rs/ac/data";
const char*     COMMAND_TOPIC = "hs109rs/ac/command";

//========================
// Device Identification
//========================
char DEV_NAME[16];                         // Derived at boot: AC-last4ofMAC
const char* DEV_TYPE  = "AC";
// HUB_NAME / MQTT_USER / MQTT_PASS are #defined in secrets.h — capture then undef to avoid macro collision
static const char* _HUB_NAME_VAL = HUB_NAME;
static const char* _MQTT_USER_VAL = MQTT_USER;
static const char* _MQTT_PASS_VAL = MQTT_PASS;
#undef HUB_NAME
#undef MQTT_USER
#undef MQTT_PASS
const char* HUB_NAME  = _HUB_NAME_VAL;  // Target Hub Name
const char* MQTT_USER = _MQTT_USER_VAL;
const char* MQTT_PASS = _MQTT_PASS_VAL;

//========================
// Timing & Intervals (ms)
//========================
const unsigned long PUBLISH_INTERVAL_MS = 5000;
unsigned long lastPublish = 0;

const unsigned long OLED_INTERVAL_MS = 1000;
unsigned long lastOLED = 0;

const unsigned long SENSOR_INTERVAL_MS = 1000;
unsigned long lastSensorRead = 0;

const unsigned long WIFI_CONNECT_TIMEOUT_MS = 15000;
unsigned long mqttRetryDelay = 3000;
const unsigned long MQTT_RETRY_DELAY_MAX = 30000;
unsigned long lastMqttAttempt = 0;

float temperature = NAN;
float humidity    = NAN;

String mqttClientId;

WiFiClient wemosClient;
PubSubClient client(wemosClient);

IRGreeAC ac1(IR1_PIN);
IRGreeAC ac2(IR2_PIN);

const uint8_t EEPROM_MAGIC = 0xAC;

//========================
// EEPROM State Persistence
//========================
void saveACStateToEEPROM(int unitIndex, IRGreeAC& ac)
{
    EEPROM.write(0, EEPROM_MAGIC);
    int offset = (unitIndex == 1) ? 1 : 9;
    const uint8_t* raw = ac.getRaw();
    for (int i = 0; i < kGreeStateLength; i++)
    {
        EEPROM.write(offset + i, raw[i]);
    }
    EEPROM.commit();
    Serial.print(F("Saved AC"));
    Serial.print(unitIndex);
    Serial.println(F(" state to EEPROM."));
}

void loadOrInitACStates()
{
    if (EEPROM.read(0) == EEPROM_MAGIC)
    {
        Serial.println(F("EEPROM valid state found. Restoring AC states..."));
        uint8_t raw1[kGreeStateLength];
        uint8_t raw2[kGreeStateLength];
        for (int i = 0; i < kGreeStateLength; i++)
        {
            raw1[i] = EEPROM.read(1 + i);
            raw2[i] = EEPROM.read(9 + i);
        }
        ac1.setRaw(raw1);
        ac1.send();
        ac2.setRaw(raw2);
        ac2.send();
        Serial.println(F("AC1 and AC2 states restored and IR sent."));
    }
    else
    {
        Serial.println(F("EEPROM uninitialized or magic mismatch. Setting default OFF baseline..."));
        ac1.off();
        ac1.setMode(kGreeCool);
        ac1.setTemp(24);
        ac1.setFan(kGreeFanAuto);
        ac1.send();

        ac2.off();
        ac2.setMode(kGreeCool);
        ac2.setTemp(24);
        ac2.setFan(kGreeFanAuto);
        ac2.send();

        saveACStateToEEPROM(1, ac1);
        saveACStateToEEPROM(2, ac2);
        Serial.println(F("Default baseline saved to EEPROM."));
    }
}

//========================
// I2C Bus Diagnostic Scanner & Auto-Probe
//========================
void scanAndInitI2C()
{
    Serial.println();
    Serial.println(F("--- [I2C Bus Diagnostics] ---"));
    byte count = 0;
    for (byte addr = 1; addr < 127; ++addr) {
        Wire.beginTransmission(addr);
        byte error = Wire.endTransmission();
        if (error == 0) {
            Serial.print(F("Found I2C device at 0x"));
            if (addr < 16) Serial.print(F("0"));
            Serial.print(addr, HEX);

            if (addr == 0x3C || addr == 0x3D) Serial.print(F(" (SSD1306 OLED candidate)"));
            if (addr == 0x44 || addr == 0x45) Serial.print(F(" (SHT30/31 Sensor candidate)"));
            Serial.println();
            count++;
        }
    }
    if (count == 0) {
        Serial.println(F("WARNING: No I2C devices found! Check wiring: SDA=D2, SCL=D1, VCC=3.3V, GND"));
    }
    Serial.println(F("-----------------------------"));

    // 1. Auto-probe OLED display (0x3C, then 0x3D)
    for (size_t i = 0; i < sizeof(OLED_CANDIDATES) / sizeof(OLED_CANDIDATES[0]); i++) {
        uint8_t addr = OLED_CANDIDATES[i];
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            if (display.begin(SSD1306_SWITCHCAPVCC, addr)) {
                isOledPresent = true;
                detectedOledAddr = addr;
                Serial.printf("[OLED] Successfully initialized at 0x%02X\n", addr);
                break;
            }
        }
    }
    if (!isOledPresent) {
        Serial.println(F("[OLED] NOT DETECTED or failed to init (continuing headless)"));
    }

    // 2. Auto-probe SHT30/31 sensor (0x44, then 0x45)
    for (size_t i = 0; i < sizeof(SHT_CANDIDATES) / sizeof(SHT_CANDIDATES[0]); i++) {
        uint8_t addr = SHT_CANDIDATES[i];
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            if (sht30.begin(addr)) {
                isShtPresent = true;
                detectedShtAddr = addr;
                Serial.printf("[SHT30] Successfully initialized at 0x%02X\n", addr);
                break;
            }
        }
    }
    if (!isShtPresent) {
        Serial.println(F("[SHT30] NOT DETECTED or failed to init"));
    }

    // Initial Splash on OLED
    if (isOledPresent) {
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);
        display.setTextSize(1);
        display.setCursor(0, 0);
        display.println(F("WEMOS AC Init"));
        display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

        display.setCursor(0, 16);
        display.printf("OLED: 0x%02X [OK]\n", detectedOledAddr);

        display.setCursor(0, 28);
        if (isShtPresent) {
            display.printf("SHT:  0x%02X [OK]\n", detectedShtAddr);
        } else {
            display.println(F("SHT:  [FAIL]"));
        }

        display.setCursor(0, 42);
        display.println(F("Connecting WiFi..."));
        display.display();
        delay(1000);
    }
}

//========================
// Connect WiFi (Non-blocking with Timeout)
//========================
void connect_wifi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.print(F("Connecting to "));
    Serial.println(NAMA_WIFI);
    WiFi.mode(WIFI_STA);
    WiFi.begin(NAMA_WIFI, NAMA_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println();
            Serial.println(F("WiFi connect timeout, akan dicoba lagi di loop berikutnya"));
            return;
        }
        delay(250);
        Serial.print(F("."));
    }

    Serial.println(F("\nWiFi connected"));
    Serial.print(F("WEMOS IP: "));
    Serial.println(WiFi.localIP());
    Serial.print(F("WEMOS MAC Address: "));
    Serial.println(WiFi.macAddress());
}

//========================
// Connect MQTT (Non-blocking with Backoff)
//========================
void connect_mqtt() {
    if (client.connected()) return;
    if (WiFi.status() != WL_CONNECTED) return;

    if (millis() - lastMqttAttempt < mqttRetryDelay) return;
    lastMqttAttempt = millis();

    Serial.print(F("[MQTT] connecting... "));

    if (client.connect(mqttClientId.c_str(), MQTT_USER, MQTT_PASS)) {   
        client.subscribe(COMMAND_TOPIC);
        Serial.println(F("connected"));
        mqttRetryDelay = 3000; // Reset backoff
    } else {
        Serial.print(F("failed rc="));
        Serial.println(client.state());
        mqttRetryDelay = min(mqttRetryDelay * 2, MQTT_RETRY_DELAY_MAX);
    }
}

void printHelp()
{
    Serial.println();
    Serial.println(F("========== COMMAND =========="));
    Serial.println(F("AC1 ON"));
    Serial.println(F("AC1 OFF"));
    Serial.println(F("AC1 TEMP 16"));
    Serial.println(F("============================="));
}

void publishACStatus(const IRGreeAC *ac1_inst, const IRGreeAC *ac2_inst)
{
    if (!isShtPresent || isnan(temperature) || isnan(humidity))
    {
        Serial.println(F("Skip publish: sensor read failure (NaN/absent)"));
        return;
    }

    JsonDocument doc;
    doc["HUB_NAME"]  = HUB_NAME;
    doc["DEV_ID"]    = WiFi.macAddress();
    doc["DEV_NAME"]  = DEV_NAME;
    doc["DEV_TYPE"]  = DEV_TYPE;
    doc["AC1_POWER"] = ac1_inst->getPower() ? "ON" : "OFF";
    doc["AC1_TEMP"]  = ac1_inst->getTemp();
    doc["AC2_POWER"] = ac2_inst->getPower() ? "ON" : "OFF";
    doc["AC2_TEMP"]  = ac2_inst->getTemp();
    doc["TEMP"]      = serialized(String(temperature, 1));
    doc["HUMID"]     = serialized(String(humidity, 1));

    char buffer[256];
    serializeJson(doc, buffer, sizeof(buffer));

    if (client.publish(DATA_TOPIC, buffer))
    {
        Serial.print(F("[PUB] "));
        Serial.println(buffer);
    }
    else
    {
        Serial.println(F("Publish Failed"));
    }
}

//========================
// MQTT Downlink Command Callback
//========================
void callback(char* topic, byte* payload, unsigned int length)
{
    if (strcmp(topic, COMMAND_TOPIC) != 0) return;

    Serial.print(F("Pesan masuk: ["));
    Serial.print(topic);
    Serial.println(F("]"));

    char msg[256];
    if (length >= sizeof(msg)) {
        Serial.println(F("Payload too large"));
        return;
    }

    memcpy(msg, payload, length);
    msg[length] = '\0';

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, msg);
    if (error) {
        Serial.print(F("JSON error: "));
        Serial.println(error.c_str());
        return;
    }

    const char* target = doc["target"];
    const char* action = doc["action"];

    IRGreeAC* ac = NULL;
    int unitIndex = 0;

    if (target) {
        if (strcmp(target, "AC1") == 0) {
            ac = &ac1;
            unitIndex = 1;
        } else if (strcmp(target, "AC2") == 0) {
            ac = &ac2;
            unitIndex = 2;
        }
    }

    if (!ac) {
        Serial.println(F("Unknown target AC"));
        return;
    }

    if (action) {
        if (strcmp(action, "ON") == 0) {
            ac->on();
        } else if (strcmp(action, "OFF") == 0) {
            ac->off();
        } else if (strcmp(action, "SET_TEMP") == 0) {
            int temp = doc["temp"] | 24;
            if (temp >= 16 && temp <= 30) {
                ac->setTemp(temp);
            }
        }
        ac->send();
        saveACStateToEEPROM(unitIndex, *ac);
        Serial.printf("Executed MQTT cmd for AC%d: %s\n", unitIndex, action);
        publishACStatus(&ac1, &ac2);
    }
}

//========================
// Serial CLI Command Processor
//========================
void processSerialCommand(String cmd)
{
    cmd.trim();
    cmd.toUpperCase();

    IRGreeAC* ac = NULL;
    int unitIndex = 0;

    if (cmd.startsWith("AC1")) {
        ac = &ac1;
        unitIndex = 1;
        cmd = cmd.substring(3);
    } else if (cmd.startsWith("AC2")) {
        ac = &ac2;
        unitIndex = 2;
        cmd = cmd.substring(3);
    } else {
        Serial.println(F("Format: AC1/AC2 ON|OFF|TEMP <val>"));
        return;
    }

    cmd.trim();

    if (cmd == "ON") {
        ac->on();
    } else if (cmd == "OFF") {
        ac->off();
    } else if (cmd.startsWith("TEMP")) {
        int temp = cmd.substring(4).toInt();
        if (temp >= 16 && temp <= 30) {
            ac->setTemp(temp);
        } else {
            Serial.println(F("Temperature must be 16-30"));
            return;
        }
    } else {
        Serial.println(F("Unknown Command"));
        return;
    }

    ac->send();
    saveACStateToEEPROM(unitIndex, *ac);
    Serial.printf("Executed Serial cmd for AC%d\n", unitIndex);
    publishACStatus(&ac1, &ac2);
}

//========================
// Setup
//========================
void setup()
{
    Serial.begin(115200);
    delay(200);

    Serial.println();
    Serial.println(F("========================================"));
    Serial.println(F("    WEMOS AC/IR Controller Node Boot    "));
    Serial.println(F("========================================"));

    EEPROM.begin(32);

    Wire.begin(D2, D1);
    Wire.setClock(100000);

    scanAndInitI2C();

    String bootMac = WiFi.macAddress();
    snprintf(DEV_NAME, sizeof(DEV_NAME), "%s-%c%c%c%c", DEV_TYPE,
             bootMac[12], bootMac[13], bootMac[15], bootMac[16]);

    mqttClientId = String(DEV_NAME) + "-" + WiFi.macAddress();

    connect_wifi();

    client.setServer(MQTT_IP, MQTT_PORT);
    client.setCallback(callback);
    client.setKeepAlive(30);
    client.setSocketTimeout(5);
    
    ac1.begin();
    ac2.begin();
    loadOrInitACStates();

    printHelp();
}

//========================
// Loop
//========================
void loop()
{   
    connect_wifi();
    connect_mqtt();
    client.loop();

    unsigned long now = millis();

    // 1. Throttled Sensor Reading
    if (now - lastSensorRead >= SENSOR_INTERVAL_MS)
    {
        lastSensorRead = now;
        if (isShtPresent) {
            float t = sht30.readTemperature();
            float h = sht30.readHumidity();
            if (!isnan(t) && !isnan(h)) {
                temperature = t;
                humidity    = h;
            } else {
                temperature = NAN;
                humidity    = NAN;
            }
        }
    }

    bool sensorError = (isnan(temperature) || isnan(humidity) || !isShtPresent);

    // 2. Strictly Throttled OLED Updates (1 Hz)
    if (isOledPresent && (now - lastOLED >= OLED_INTERVAL_MS)) {
        lastOLED = now;
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);

        if (WiFi.status() != WL_CONNECTED) {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println(F("WiFi Status"));
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 20);
            display.println(F("WiFi"));
            display.println(F("Connecting"));
        }
        else if (!client.connected()) {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.print(F("IP: "));
            display.println(WiFi.localIP());
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 20);
            display.println(F("MQTT"));
            display.println(F("Connecting"));
        }
        else if (sensorError) {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println(F("Sensor Status"));
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 20);
            display.println(F("Sensor"));
            display.println(F("Error"));
        }
        else {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println(F("AC Node Monitor"));
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 18);
            display.print(F("T:"));
            display.print(temperature, 1);
            display.print(F("C"));

            display.setCursor(0, 45);
            display.print(F("H:"));
            display.print(humidity, 1);
            display.print(F("%"));
        }

        display.display();
    }
    else if (!isOledPresent && (now - lastOLED >= OLED_INTERVAL_MS)) {
        lastOLED = now;
        if (sensorError) {
            Serial.println(F("Gagal membaca sensor!"));
        } else {
            Serial.print(F("Temperature : "));
            Serial.print(temperature, 1);
            Serial.println(F(" C"));
            Serial.print(F("Humidity    : "));
            Serial.print(humidity, 1);
            Serial.println(F(" %"));
            Serial.println();
        }
    }

    // 3. Throttled Publish to MQTT Hub
    if (now - lastPublish >= PUBLISH_INTERVAL_MS)
    {
        lastPublish = now;

        if (sensorError)
        {
            Serial.println(F("Skip publish: sensor read failure (NaN/absent)"));
        }
        else if (client.connected())
        {
            publishACStatus(&ac1, &ac2);
        }
        else
        {
            Serial.println(F("Skip publish, MQTT belum terkoneksi"));
        }
    }

    // 4. Serial CLI Commands
    if (Serial.available())
    {
        String cmd = Serial.readStringUntil('\n');
        processSerialCommand(cmd);
    }
}
