// ############### MQTT #################
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

// Fleet AP bubble: SSID/password identik di semua room Pi (hidden AP)
const char* NAMA_WIFI = WIFI_SSID;
const char* NAMA_PASSWORD = WIFI_PASS;

// MQTT Broker (Hub)
const char* MQTT_IP = MQTT_HOST;
const uint16_t MQTT_PORT = 1883;
const char* DATA_TOPIC = "hs109rs/ats/data";
const char* COMMAND_TOPIC = "hs109rs/ats/command";
char DEVICE_NAME[9] = "ATS-"; // diisi saat boot: ATS- + 4 hex terakhir MAC (unik per node)
static const char* _HUB_NAME_VAL_ATS = HUB_NAME;
#undef HUB_NAME
const char* HUB_NAME = _HUB_NAME_VAL_ATS;
const char* DEV_TYPE = "ATS";
const char* mqtt_user = MQTT_USER;
const char* mqtt_pass = MQTT_PASS;

WiFiClient wemosClient;
PubSubClient mqtt(wemosClient);
String mqttClientId;

unsigned long lastMsg = 0;

unsigned long lastLoopTime = 0;
const unsigned long loopInterval = 500;
const unsigned long WIFI_CONNECT_TIMEOUT_MS = 15000;
unsigned long lastMqttAttempt = 0;
unsigned long mqttRetryDelay = 3000;
const unsigned long MQTT_RETRY_DELAY_MAX = 30000;

String serialBuffer = "";
String nowState = "";
bool autoMode = false;
bool emergency = false;

bool emergencyNotified = false;

double voltPLN = 0;
double voltGenset = 0;
double voltAki = 0;

long remSec = 0;
long remMin = 0;
long remHour = 0;

void connect_wifi() {
  
  if(WiFi.status() == WL_CONNECTED) return;

  Serial.print("Connecting to ");
  Serial.println(NAMA_WIFI);

  WiFi.begin(NAMA_WIFI, NAMA_PASSWORD);

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_CONNECT_TIMEOUT_MS)
    {
        Serial.println();
        Serial.println("WiFi connect timeout, akan dicoba lagi di loop berikutnya");
        return; // keluar, biar loop() jalan lagi & tidak trigger watchdog reset
    }
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.print("WEMOS IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("WEMOS MAC Address: ");
  Serial.println(WiFi.macAddress());
}

void callback(char* topic, byte* payload, unsigned int length) {

  Serial.print("Pesan masuk: ");
  Serial.print("[");
  Serial.print(topic);
  Serial.print("]");

  if (length >= 200) {
    Serial.println("Payload too large");
    return;
  }

  char msg[200];
  memcpy(msg, payload, length);
  msg[length] = '\0';

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, msg);

  if (error) {
    Serial.print("JSON error: ");
    Serial.println(error.c_str());
    return;
  }

  if (strcmp(topic, COMMAND_TOPIC) == 0) {

    if (doc.containsKey("mode")) {

      const char* mode = doc["mode"];

      if (mode != nullptr) {
        if(strcmp(mode, "manual") == 0) {
          Serial.println("<M,manual>");
        }
        else if (strcmp(mode, "auto") == 0) {
          Serial.println("<M,auto>");
        }
      }

    }

    if (doc.containsKey("start_genset")) {

      const char* start_genset = doc["start_genset"];

      if (start_genset != nullptr) {
        if(strcmp(start_genset, "on") == 0){
          Serial.println("<SGM,on>"); // SGM = Start Genset Manually
        }
        else if (strcmp(start_genset, "off") == 0){
          Serial.println("<SGM,off>"); // preventif check
        }
      }

    }

    if (doc.containsKey("reset")) {

      const char* reset = doc["reset"];

      if (reset != nullptr) {
        if(strcmp(reset, "rst") == 0){
          Serial.println("<RST,rst>");
        }
      }
    }
  }
}

void connect_mqtt() {
  if(mqtt.connected()) return;
  if(WiFi.status() != WL_CONNECTED) return;

  // batasi percobaan reconnect agar tidak spam
  if (millis() - lastMqttAttempt < mqttRetryDelay) return;
  lastMqttAttempt = millis();

  Serial.print("[MQTT] connecting... ");

  if (mqtt.connect(mqttClientId.c_str(), mqtt_user, mqtt_pass))
  {
      mqtt.subscribe(COMMAND_TOPIC);
      Serial.println("connected");
      mqttRetryDelay = 3000; // reset backoff setelah sukses
  }
  else
  {
      Serial.print("failed rc=");
      Serial.println(mqtt.state());

      // exponential backoff, dibatasi maksimum
      mqttRetryDelay = min(mqttRetryDelay * 2, MQTT_RETRY_DELAY_MAX);

  }
}

void publishData(){
  if (!mqtt.connected()) return;

  StaticJsonDocument<512> doc;
  doc["HUB_NAME"] = HUB_NAME;
  doc["DEV_ID"] = WiFi.macAddress();
  doc["DEV_NAME"] = DEVICE_NAME;
  doc["DEV_TYPE"] = DEV_TYPE;
  doc["STATE"] = nowState;
  doc["PLN"] = voltPLN;
  doc["GENSET"] = voltGenset;
  doc["AKI"] = voltAki;
  doc["REM_SEC"] = remSec; 
  doc["REM_MIN"] = remMin;
  doc["REM_HOUR"] = remHour;
  doc["AUTO_MODE"] = (bool)autoMode;
  doc["EMERGENCY"] = (bool)emergency;

  char buffer_json[512];
  serializeJson(doc, buffer_json);

  if (mqtt.publish(DATA_TOPIC, buffer_json))
  {
      Serial.println("Publish Success");
  }
  else
  {
      Serial.println("Publish Failed");
  }
}

void processData(String msg) {
  
  int commaIndex = msg.indexOf(',');
  int endIndex = msg.indexOf('>');  

  if (commaIndex != -1 && endIndex != -1) {

    String type = msg.substring(1, commaIndex);
    String data = msg.substring(commaIndex + 1, endIndex);

    if (type == "STATE") {
      nowState = data;
    }
    else if (type == "PLN") {
      voltPLN = data.toFloat();
    }
    else if (type == "GENSET") {
      voltGenset = data.toFloat();
    }
    else if (type == "AKI") {
      voltAki = data.toFloat();
    }
    else if (type == "REM_SEC") {
      remSec = data.toInt();
    }
    else if (type == "REM_MIN") {
      remMin = data.toInt();
    }
    else if (type == "REM_HOUR") {
      remHour = data.toInt();
    }
    else if (type == "AUTO_MODE") {
      autoMode = data.toInt();
    }
    else if (type == "EMERGENCY") {
      emergency = data.toInt();
    }
  }
}

void setup() {
  Serial.begin(9600);

  String mac = WiFi.macAddress();
  snprintf(DEVICE_NAME, sizeof(DEVICE_NAME), "ATS-%c%c%c%c",
           toupper(mac[12]), toupper(mac[13]), toupper(mac[15]), toupper(mac[16]));
  Serial.print("DEV_NAME: ");
  Serial.println(DEVICE_NAME);

  mqttClientId = String(DEVICE_NAME) + "-" + WiFi.macAddress();
  connect_wifi();
  mqtt.setServer(MQTT_IP, MQTT_PORT);
  mqtt.setCallback(callback);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);      // detik, sesuaikan kalau jaringan lambat
  mqtt.setSocketTimeout(5);   // detik

}

void loop() {

  connect_wifi();

  connect_mqtt();

  if (mqtt.connected()) {
    mqtt.loop();
  }

  if (millis() - lastLoopTime >= loopInterval){
    lastLoopTime = millis();
    Serial.println("<C,GET>");
    publishData();
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '<') {
      serialBuffer = "";
      serialBuffer += c;
    }
    else if (c == '>') {
      serialBuffer += c;
      processData(serialBuffer);
      serialBuffer = "";
    }
    else {
      if (serialBuffer.length() < 64) serialBuffer += c;
      else serialBuffer = "";
    }
  }
}

