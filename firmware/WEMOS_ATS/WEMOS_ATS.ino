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

const char* ssid = WIFI_SSID;
const char* password = WIFI_PASS;

// MQTT Broker (Hub)
const char* mqtt_server = MQTT_HOST;
const uint16_t mqtt_port = 1883;
const char* mqtt_topic_data = "hs109rs/ats/data";
const char* mqtt_topic_command = "hs109rs/ats/command";
char device_name[16];  // Derived at boot: ATS-last4ofMAC bounded snprintf
static const char* _HUB_NAME_VAL_FIX = HUB_NAME;
#undef HUB_NAME
const char* HUB_NAME = _HUB_NAME_VAL_FIX;
const char* DEV_TYPE = "ATS";
const char* mqtt_user = MQTT_USER;
const char* mqtt_pass = MQTT_PASS;

WiFiClient espClient;
PubSubClient client(espClient);

// Non-blocking MQTT reconnect backoff
unsigned long lastMqttAttempt = 0;
unsigned long mqttRetryDelay = 3000;
const unsigned long MQTT_RETRY_DELAY_MAX = 30000;

unsigned long lastMsg = 0;
// ############### MQTT #################

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// E: bounded char[65] like PROMINI, no String heap for serial frames
char nowState[32] = "";
bool autoMode = false;
bool emergency = false;
bool rtcOk = false;
bool isOledPresent = false;
char nowDate[16] = "";
char nowTime[16] = "";

unsigned long lastTime = 0;
const unsigned long intervalConnected = 500;
const unsigned long intervalDisconnected = 2000;

double teganganPln = 0;
double teganganGenset = 0;
double teganganAki = 0;

bool isPlnOn = false;
bool isGensetOn = false;
bool isAkiOn = false;
bool isWarmup = false;

long sisaDetik = 0;
long sisaMenit = 0;
long sisaJam = 0;

// E: overflow counter (PROMINI 56-58 style)
unsigned long serialOverflowCount = 0;

// E: WiFi non-blocking retry state (setup_wifi returns immediately)
unsigned long lastWifiAttempt = 0;
unsigned long wifiRetryDelay = 3000;
const unsigned long WIFI_RETRY_MAX = 30000;

void setup_wifi() {
  // E: non-blocking — start connect and return immediately; retry handled in loop()
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  lastWifiAttempt = millis();
}

void callback(char* topic, byte* payload, unsigned int length) {

  Serial.print("Pesan masuk [");
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

  if (strcmp(topic, mqtt_topic_command) == 0) {
    if (doc.containsKey("mode")) {
      const char* mode = doc["mode"];
      if (mode != nullptr) {
        if (strcmp(mode, "auto") == 0) {
          Serial.println("<M,auto>");
        }
        else if (strcmp(mode, "manual") == 0) {
          Serial.println("<M,manual>");
        }
      }
    }

    if (doc.containsKey("start_genset")) {
      // E: SGM guard — PROMINI blocks SGM when autoMode==true; bridge tracks <AUTO_MODE,x>
      // so we log/block here as well. Server pending_commands also validates, this is
      // defense-in-depth; keep behavior aligned with PROMINI 704 autoMode check.
      if (autoMode) {
        Serial.println("<SGM blocked autoMode=1>");
        // still allow server-authoritative path: do not forward <SGM,...> when in AUTO
      } else {
        const char* start_genset = doc["start_genset"];
        if (start_genset != nullptr) {
          if (strcmp(start_genset, "on") == 0) {
            Serial.println("<SGM,on>");
          }
          else if (strcmp(start_genset, "off") == 0) {
            Serial.println("<SGM,off>");
          }
        }
      }
    }

    if (doc.containsKey("reset")) {
      const char* rst = doc["reset"];
      if (rst != nullptr) {
        if (strcmp(rst, "rst") == 0) {
          Serial.println("<RST,rst>");
        }
      }
    }
  }
}

void connectMQTT() {
  if (client.connected()) return;
  if (WiFi.status() != WL_CONNECTED) return;

  if (millis() - lastMqttAttempt < mqttRetryDelay) return;
  lastMqttAttempt = millis();

  Serial.print("Connecting to MQTT...");

  // E: bounded snprintf instead of String heap for clientId
  char clientId[32];
  String mac = WiFi.macAddress();
  snprintf(clientId, sizeof(clientId), "ESP-%s", mac.c_str());
  if (client.connect(clientId, mqtt_user, mqtt_pass)) {
    Serial.println("connected");
    client.subscribe(mqtt_topic_command);
    mqttRetryDelay = 3000;
  } else {
    Serial.print("failed, rc=");
    Serial.println(client.state());
    unsigned long next = mqttRetryDelay * 2;
    if (next > MQTT_RETRY_DELAY_MAX) next = MQTT_RETRY_DELAY_MAX;
    mqttRetryDelay = next;
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(13, OUTPUT);
  digitalWrite(13, LOW);

  String bootMac = WiFi.macAddress();
  // bounded snprintf device_name[16] ATS-XXXX (last 4 hex chars of MAC)
  snprintf(device_name, sizeof(device_name), "%s-%c%c%c%c", DEV_TYPE,
           bootMac[12], bootMac[13], bootMac[15], bootMac[16]);

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setBufferSize(512);

  Wire.begin(D2, D1);
  Wire.beginTransmission(0x3C);
  if (Wire.endTransmission() == 0) {
    isOledPresent = true;
  }

  if (isOledPresent) {
    if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
      Serial.println("OLED initialization failed");
      isOledPresent = false;
    } else {
      display.clearDisplay();
      display.setTextSize(1);
      display.setTextColor(SSD1306_WHITE);
    }
  } else {
    Serial.println("OLED tidak ditemukan");
  }
}

void loop() {

  // E: non-blocking WiFi retry with millis backoff 3000->30000
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifiAttempt >= wifiRetryDelay) {
      lastWifiAttempt = millis();
      Serial.println("WiFi reconnect...");
      WiFi.begin(ssid, password);
      unsigned long next = wifiRetryDelay * 2;
      if (next > WIFI_RETRY_MAX) next = WIFI_RETRY_MAX;
      wifiRetryDelay = next;
    }
  } else {
    wifiRetryDelay = 3000;
  }

  connectMQTT();
  if (client.connected()) {
    client.loop();
  }
  yield();

  // E: gate <C,GET> behind client.connected() or throttle 2s when disconnected
  unsigned long curInterval = client.connected() ? intervalConnected : intervalDisconnected;
  if (millis() - lastTime >= curInterval){
    lastTime = millis();
    // throttle serial poll when MQTT disconnected: still poll but at 2s, not 500ms
    Serial.println("<C,GET>");
    if (client.connected()) {
      publishData();
    }
  }

  static char buf[65];
  static uint8_t len = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '<') {
      len = 0;
      if (len < 64) buf[len++] = c;
      buf[len] = '\0';
    } else if (c == '>') {
      if (len < 64) buf[len++] = c;
      buf[len] = '\0';
      processData(buf);
      len = 0;
      buf[0] = '\0';
    } else {
      if (len < 64) {
        buf[len++] = c;
        buf[len] = '\0';
      } else {
        // E: overflow — reset and count like PROMINI
        serialOverflowCount++;
        len = 0;
        buf[0] = '\0';
        Serial.print("<ERR,overflow,");
        Serial.print(serialOverflowCount);
        Serial.println(">");
      }
    }
  }
}


void processData(const char* msg) {
  const char* comma = strchr(msg, ',');
  const char* end = strchr(msg, '>');

  if (comma != NULL && end != NULL) {
    int typeLen = comma - msg - 1;
    int dataLen = end - comma - 1;
    const char* type = msg + 1;
    const char* data = comma + 1;

    // bounded copy for string values (null-terminated temp)
    char tmp[32];
    int copyLen = dataLen < (int)sizeof(tmp)-1 ? dataLen : (int)sizeof(tmp)-1;
    memcpy(tmp, data, copyLen);
    tmp[copyLen] = '\0';

    if (typeLen == 5 && strncmp(type, "STATE", 5) == 0) {
      // bounded
      int n = copyLen < (int)sizeof(nowState)-1 ? copyLen : (int)sizeof(nowState)-1;
      memcpy(nowState, data, n);
      nowState[n] = '\0';
    }
    else if (typeLen == 3 && strncmp(type, "PLN", 3) == 0) {
      teganganPln = atof(tmp);
    }
    else if (typeLen == 6 && strncmp(type, "GENSET", 6) == 0) {
      teganganGenset = atof(tmp);
    }
    else if (typeLen == 3 && strncmp(type, "AKI", 3) == 0) {
      teganganAki = atof(tmp);
    }
    else if (typeLen == 9 && strncmp(type, "IS_PLN_ON", 9) == 0) {
      isPlnOn = (tmp[0] == '1');
    }
    else if (typeLen == 12 && strncmp(type, "IS_GENSET_ON", 12) == 0) {
      isGensetOn = (tmp[0] == '1');
    }
    else if (typeLen == 9 && strncmp(type, "IS_AKI_ON", 9) == 0) {
      isAkiOn = (tmp[0] == '1');
    }
    else if (typeLen == 9 && strncmp(type, "IS_WARMUP", 9) == 0) {
      isWarmup = (tmp[0] == '1');
    }
    else if (typeLen == 7 && strncmp(type, "REM_SEC", 7) == 0) {
      sisaDetik = atol(tmp);
    }
    else if (typeLen == 7 && strncmp(type, "REM_MIN", 7) == 0) {
      sisaMenit = atol(tmp);
    }
    else if (typeLen == 8 && strncmp(type, "REM_HOUR", 8) == 0) {
      sisaJam = atol(tmp);
    }
    else if (typeLen == 9 && strncmp(type, "AUTO_MODE", 9) == 0) {
      autoMode = (tmp[0] == '1');
    }
    else if (typeLen == 9 && strncmp(type, "EMERGENCY", 9) == 0) {
      emergency = (tmp[0] == '1');
    }
    else if (typeLen == 6 && strncmp(type, "RTC_OK", 6) == 0) {
      rtcOk = (tmp[0] == '1');
    }
    else if (typeLen == 4 && strncmp(type, "DATE", 4) == 0) {
      int n = copyLen < (int)sizeof(nowDate)-1 ? copyLen : (int)sizeof(nowDate)-1;
      memcpy(nowDate, data, n);
      nowDate[n] = '\0';
    }
    else if (typeLen == 4 && strncmp(type, "TIME", 4) == 0) {
      int n = copyLen < (int)sizeof(nowTime)-1 ? copyLen : (int)sizeof(nowTime)-1;
      memcpy(nowTime, data, n);
      nowTime[n] = '\0';
    }
  }
  else if (comma == NULL && end != NULL) {
    // no comma: display raw text
    int txtLen = end - msg - 1;
    if (isOledPresent) {
      display.clearDisplay();
      display.setCursor(0, 10);
      // bounded display write
      int n = txtLen < 32 ? txtLen : 32;
      char line[33];
      memcpy(line, msg + 1, n);
      line[n] = '\0';
      display.println(line);
      display.display();
    }
  }
}

void publishData(){
  if (!client.connected()) return;

  StaticJsonDocument<512> doc;
  doc["HUB_NAME"] = HUB_NAME;
  doc["DEV_ID"] = WiFi.macAddress();
  doc["DEV_NAME"] = device_name;
  doc["DEV_TYPE"] = DEV_TYPE;
  doc["STATE"] = nowState;
  doc["PLN"] = teganganPln;
  doc["GENSET"] = teganganGenset;
  doc["AKI"] = teganganAki;
  // doc["IS_PLN_ON"] = isPlnOn;
  // doc["IS_GENSET_ON"] = isGensetOn;
  // doc["IS_AKI_ON"] = isAkiOn;
  // doc["IS_WARMUP"] = isWarmup;
  doc["REM_SEC"] = sisaDetik; 
  doc["REM_MIN"] = sisaMenit;
  doc["REM_HOUR"] = sisaJam;
  doc["AUTO_MODE"] = (bool)autoMode;
  doc["EMERGENCY"] = (bool)emergency;
  doc["RTC_OK"] = (bool)rtcOk;
  // doc["DATE"] = nowDate;
  // doc["TIME"] = nowTime;

  char buffer_json[512];
  serializeJson(doc, buffer_json);

  if (client.publish(mqtt_topic_data, buffer_json))
  {
      Serial.println("Publish Success");
  }
  else
  {
      Serial.println("Publish Failed");
  }
}


// String buffer2 = "";

  // while (Serial.available()) {
  //   char c = Serial.read();
  //   if (c == '\n') {
  //     buffer2.trim();
  //     Serial.println(buffer2);
  //     buffer2 = "";
  //   } else {
  //     buffer2 += c;
  //   }
  // }
