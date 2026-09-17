// ############### MQTT #################
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Secrets configuration:
// 1. Sketch-local secrets.h (preferred for Arduino IDE out-of-the-box compile)
// 2. Monorepo common/secrets.h (for CLI / multi-sketch builds)
#if __has_include("secrets.h")
#include "secrets.h"
#elif __has_include("../common/secrets.h")
#include "../common/secrets.h"
#elif __has_include("common/secrets.h")
#include "common/secrets.h"
#else
#error "secrets.h missing. Ensure secrets.h exists in this sketch folder or in firmware/common/."
#endif
#ifndef WIFI_PASS
#error "WIFI_PASS not defined. Check secrets.h."
#endif

const char* ssid = WIFI_SSID;
const char* password = WIFI_PASS;

// MQTT Broker (Hub)
const char* mqtt_server = MQTT_HOST;
#ifdef MQTT_PORT
const uint16_t mqtt_port = MQTT_PORT;
#undef MQTT_PORT
#else
const uint16_t mqtt_port = 1883;
#endif
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

//========================
// Timing & Cadence (ms)
//========================
const unsigned long STEADY_PUBLISH_INTERVAL_MS = 60000; // 60s steady-state heartbeat
const unsigned long BURST_PUBLISH_INTERVAL_MS  = 2000;  // 2.0s burst interval
const unsigned long BURST_DURATION_MS          = 60000; // 60s burst duration
const unsigned long MIN_PUBLISH_INTERVAL_MS    = 2000;  // 2s rate-limit

const unsigned long intervalConnected          = 500;   // 500ms serial poll when connected
const unsigned long intervalDisconnected       = 2000;  // 2000ms serial poll when disconnected

//========================
// Deadband Thresholds
//========================
const double DEADBAND_PLN_V = 1.0; // delta_pln >= 1.0V
const double DEADBAND_GEN_V = 1.0; // delta_gen >= 1.0V
const double DEADBAND_AKI_V = 0.1; // delta_aki >= 0.1V

unsigned long lastSerialPoll = 0;
unsigned long lastPublish = 0;
unsigned long burstUntil = 0;

// E: bounded char[65] like PROMINI, no String heap for serial frames
char nowState[32] = "";
bool autoMode = false;
bool emergency = false;
bool rtcOk = false;
bool isOledPresent = false;
char nowDate[16] = "";
char nowTime[16] = "";

double teganganPln = 0;
double teganganGenset = 0;
double teganganAki = 0;

bool isPlnOn = false;
bool isGensetOn = false;
bool isAkiOn = false;
bool isWarmup = false;
bool isAlarm = false;

long sisaDetik = 0;
long sisaMenit = 0;
long sisaJam = 0;

// Last published values for deadband & state change detection
char lastPublishedState[32] = "";
bool lastPublishedAutoMode = false;
bool lastPublishedEmergency = false;
bool lastPublishedPlnRelay = false;
bool lastPublishedGenRelay = false;
bool lastPublishedAlarm = false;
double lastPublishedPln = -999.0;
double lastPublishedGenset = -999.0;
double lastPublishedAki = -999.0;
bool hasPublishedOnce = false;

// E: overflow counter (PROMINI 56-58 style)
unsigned long serialOverflowCount = 0;

// E: WiFi non-blocking retry state (setup_wifi returns immediately)
unsigned long lastWifiAttempt = 0;
unsigned long wifiRetryDelay = 3000;
// Forward declarations
void setup_wifi();
void connectMQTT();
void processData(const char* msg);
bool publishData();
void checkAndPublishTelemetry(unsigned long now);

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

  unsigned long now = millis();

  // 1. Serial polling of Pro Mini (<C,GET>)
  unsigned long curInterval = client.connected() ? intervalConnected : intervalDisconnected;
  if (now - lastSerialPoll >= curInterval){
    lastSerialPoll = now;
    // throttle serial poll when MQTT disconnected: still poll but at 2s, not 500ms
    Serial.println("<C,GET>");
  }

  // 2. Bounded serial packet reception & parsing
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

  // 3. Cadenced / Dynamic Burst / Deadband Telemetry Publishing
  checkAndPublishTelemetry(now);
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
    else if ((typeLen == 9 && strncmp(type, "IS_PLN_ON", 9) == 0) ||
             (typeLen == 9 && strncmp(type, "PLN_RELAY", 9) == 0)) {
      isPlnOn = (tmp[0] == '1');
    }
    else if ((typeLen == 12 && strncmp(type, "IS_GENSET_ON", 12) == 0) ||
             (typeLen == 9 && strncmp(type, "GEN_RELAY", 9) == 0)) {
      isGensetOn = (tmp[0] == '1');
    }
    else if (typeLen == 9 && strncmp(type, "IS_AKI_ON", 9) == 0) {
      isAkiOn = (tmp[0] == '1');
    }
    else if (typeLen == 9 && strncmp(type, "IS_WARMUP", 9) == 0) {
      isWarmup = (tmp[0] == '1');
    }
    else if (typeLen == 5 && strncmp(type, "ALARM", 5) == 0) {
      isAlarm = (tmp[0] == '1');
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

bool publishData(){
  if (!client.connected()) return false;

  StaticJsonDocument<512> doc;
  doc["HUB_NAME"] = HUB_NAME;
  doc["DEV_ID"] = WiFi.macAddress();
  doc["DEV_NAME"] = device_name;
  doc["DEV_TYPE"] = DEV_TYPE;
  doc["STATE"] = nowState;
  doc["PLN"] = teganganPln;
  doc["GENSET"] = teganganGenset;
  doc["AKI"] = teganganAki;
  doc["PLN_RELAY"] = (bool)isPlnOn;
  doc["GEN_RELAY"] = (bool)isGensetOn;
  doc["ALARM"] = (bool)isAlarm;
  doc["REM_SEC"] = sisaDetik; 
  doc["REM_MIN"] = sisaMenit;
  doc["REM_HOUR"] = sisaJam;
  doc["AUTO_MODE"] = (bool)autoMode;
  doc["EMERGENCY"] = (bool)emergency;
  doc["RTC_OK"] = (bool)rtcOk;

  char buffer_json[512];
  serializeJson(doc, buffer_json);

  if (client.publish(mqtt_topic_data, buffer_json))
  {
      Serial.println(F("Publish Success"));
      lastPublish = millis();
      hasPublishedOnce = true;
      strncpy(lastPublishedState, nowState, sizeof(lastPublishedState) - 1);
      lastPublishedState[sizeof(lastPublishedState) - 1] = '\0';
      lastPublishedAutoMode  = autoMode;
      lastPublishedEmergency = emergency;
      lastPublishedPlnRelay  = isPlnOn;
      lastPublishedGenRelay  = isGensetOn;
      lastPublishedAlarm     = isAlarm;
      lastPublishedPln       = teganganPln;
      lastPublishedGenset    = teganganGenset;
      lastPublishedAki       = teganganAki;
      return true;
  }
  else
  {
      Serial.println(F("Publish Failed"));
      return false;
  }
}

void checkAndPublishTelemetry(unsigned long now) {
  if (!client.connected()) return;
  // Don't publish before first valid state read from Pro Mini
  if (nowState[0] == '\0' && !hasPublishedOnce) return;

  // 1. Check for Discrete State Changes (0ms instant forward + triggers 60s burst)
  bool stateChanged = false;
  if (hasPublishedOnce) {
    if (strncmp(nowState, lastPublishedState, sizeof(nowState)) != 0 ||
        autoMode != lastPublishedAutoMode ||
        emergency != lastPublishedEmergency ||
        isPlnOn != lastPublishedPlnRelay ||
        isGensetOn != lastPublishedGenRelay ||
        isAlarm != lastPublishedAlarm) {
      stateChanged = true;
    }
  }

  if (stateChanged) {
    // Dynamic burst mode (2.0s interval for 60s)
    burstUntil = now + BURST_DURATION_MS;
    Serial.println(F("[ATS] Discrete state change: instant forward & 60s burst mode active"));
    publishData();
    return;
  }

  // 2. Dynamic Burst Mode (2.0s interval for 60s)
  bool inBurst = (now < burstUntil);
  if (inBurst) {
    if (now - lastPublish >= BURST_PUBLISH_INTERVAL_MS) {
      publishData();
    }
    return;
  }

  // 3. Steady-State Mode (Deadbands & 60s heartbeat)
  bool minIntervalElapsed = (!hasPublishedOnce || (now - lastPublish >= MIN_PUBLISH_INTERVAL_MS));
  if (!minIntervalElapsed) return;

  bool heartbeatExpired = (!hasPublishedOnce || (now - lastPublish >= STEADY_PUBLISH_INTERVAL_MS));

  bool deadbandExceeded = false;
  if (fabs(teganganPln - lastPublishedPln) >= DEADBAND_PLN_V ||
      fabs(teganganGenset - lastPublishedGenset) >= DEADBAND_GEN_V ||
      fabs(teganganAki - lastPublishedAki) >= DEADBAND_AKI_V) {
    deadbandExceeded = true;
  }

  if (heartbeatExpired || deadbandExceeded) {
    publishData();
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
