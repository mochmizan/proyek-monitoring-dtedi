#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_SHT31.h>

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
// WiFi Config
//========================
const char* NAMA_WIFI     = "ABC";
const char* NAMA_PASSWORD = "Admin123";

//========================
// MQTT Broker Config (Hub)
//========================
const char* MQTT_IP     = "192.168.72.242";   // IP Raspberry Pi Hub
const int   MQTT_PORT   = 1883;
const char* DATA_TOPIC  = "hs109rs/ts/data";

//========================
// Device Identification
//========================
const char* DEV_NAME  = "hs109-ts-01";
const char* DEV_TYPE  = "TS";              // Temperature Sensor Node
const char* HUB_NAME  = "hs109rs-hub-01";    // Target Hub Name
const char* MQTT_USER = "hubadmin";
const char* MQTT_PASS = "414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1";

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

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
String       mqttClientId;

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
        Serial.println(F("WARNING: No I2C devices found! Check wiring: SDA=D2 (GPIO4), SCL=D1 (GPIO5), VCC=3.3V, GND"));
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
        display.println(F("WEMOS TS Init"));
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
void connectWiFi()
{
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.print(F("Connecting WiFi"));
    WiFi.mode(WIFI_STA);
    WiFi.begin(NAMA_WIFI, NAMA_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED)
    {
        if (millis() - start > WIFI_CONNECT_TIMEOUT_MS)
        {
            Serial.println();
            Serial.println(F("WiFi connect timeout, akan dicoba lagi di loop berikutnya"));
            return;
        }
        delay(250);
        Serial.print(F("."));
    }

    Serial.println();
    Serial.println(F("WiFi Connected"));
    Serial.print(F("IP : "));
    Serial.println(WiFi.localIP());
}

//========================
// Connect MQTT (Non-blocking with Backoff)
//========================
void connectMQTT()
{
    if (mqtt.connected()) return;
    if (WiFi.status() != WL_CONNECTED) return;

    if (millis() - lastMqttAttempt < mqttRetryDelay) return;
    lastMqttAttempt = millis();

    Serial.print(F("[MQTT] connecting... "));

    if (mqtt.connect(mqttClientId.c_str(), MQTT_USER, MQTT_PASS))
    {
        Serial.println(F("connected"));
        mqttRetryDelay = 3000; // Reset backoff
    }
    else
    {
        Serial.print(F("failed rc="));
        Serial.println(mqtt.state());
        mqttRetryDelay = min(mqttRetryDelay * 2, MQTT_RETRY_DELAY_MAX);
    }
}

//========================
// JSON Payload Builder
//========================
void buildPayload(char *buffer, size_t bufferSize)
{
    JsonDocument doc;

    doc["HUB_NAME"] = HUB_NAME;
    doc["DEV_ID"]   = WiFi.macAddress();
    doc["DEV_NAME"] = DEV_NAME;
    doc["DEV_TYPE"] = DEV_TYPE;
    doc["TEMP"]     = serialized(String(temperature, 1));
    doc["HUMID"]    = serialized(String(humidity, 1));

    serializeJson(doc, buffer, bufferSize);
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
    Serial.println(F("  WEMOS Temperature Sensor Node Boot    "));
    Serial.println(F("========================================"));

    // Wemos D1 Mini I2C: SDA=D2 (GPIO4), SCL=D1 (GPIO5)
    Wire.begin(D2, D1);
    Wire.setClock(100000); // 100 kHz standard mode for maximum reliability

    scanAndInitI2C();

    mqttClientId = String(DEV_NAME) + "-" + WiFi.macAddress();

    connectWiFi();

    mqtt.setServer(MQTT_IP, MQTT_PORT);
    mqtt.setKeepAlive(30);
    mqtt.setSocketTimeout(5);

    Serial.print(F("MAC Address: "));
    Serial.println(WiFi.macAddress());
}

//========================
// Loop (Strictly Throttled & Non-Blocking)
//========================
void loop()
{
    connectWiFi();
    connectMQTT();
    mqtt.loop();

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

    // 2. Strictly Throttled OLED Rendering (Prevents Soft WDT Resets)
    if (isOledPresent && (now - lastOLED >= OLED_INTERVAL_MS))
    {
        lastOLED = now;
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);

        if (WiFi.status() != WL_CONNECTED)
        {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println(F("WiFi Status"));
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 20);
            display.println(F("WiFi"));
            display.println(F("Connecting"));
        }
        else if (!mqtt.connected())
        {
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
        else if (sensorError)
        {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println(F("Sensor Status"));
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 20);
            display.println(F("Sensor"));
            display.println(F("Error"));
        }
        else
        {
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println(F("SHT30 Sensor"));
            display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            display.setTextSize(2);
            display.setCursor(0, 18);
            display.print(F("T:"));
            display.print(temperature, 1);
            display.print(F(" C"));

            display.setCursor(0, 45);
            display.print(F("H:"));
            display.print(humidity, 1);
            display.print(F(" %"));
        }

        display.display();
    }

    // 3. Throttled Publish to MQTT Hub
    if (now - lastPublish >= PUBLISH_INTERVAL_MS)
    {
        lastPublish = now;

        if (sensorError)
        {
            Serial.println(F("Skip publish: sensor read failure (NaN/absent)"));
        }
        else if (mqtt.connected())
        {   
            char payload[256];
            buildPayload(payload, sizeof(payload));

            Serial.print(F("[PUB] "));
            Serial.println(payload);

            if (mqtt.publish(DATA_TOPIC, payload))
            {
                Serial.println(F("Publish Success"));
            }
            else
            {
                Serial.println(F("Publish Failed"));
            }
        }
        else
        {
            Serial.println(F("Skip publish, MQTT belum terkoneksi"));
        }
    }
}