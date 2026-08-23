// ############### MQTT #################
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Ganti sesuai WiFi kamu
const char* ssid = "ABC";
const char* password = "Admin123";

// MQTT Broker (Hub)
const char* mqtt_server = "192.168.72.242";
const uint16_t mqtt_port = 1883;
const char* mqtt_topic_data = "hs109rs/ats/data";
const char* mqtt_topic_command = "hs109rs/ats/command";
const char* device_name = "hs109-ats-01";
const char* HUB_NAME = "hs109rs-hub-01";
const char* DEV_TYPE = "ATS";
const char* mqtt_user = "hubadmin";
const char* mqtt_pass = "414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1";

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

String buffer = "";
String nowState = "";
bool autoMode = false;
bool emergency = false;
bool isOledPresent = false;
String nowDate = "";
String nowTime = "";

unsigned long lastTime = 0;
const unsigned long interval = 500;

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

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.print("IP ESP8266: ");
  Serial.println(WiFi.localIP());
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

  String clientId = String("ESP-") + WiFi.macAddress();
  if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {
    Serial.println("connected");
    client.subscribe(mqtt_topic_command);
    mqttRetryDelay = 3000;
  } else {
    Serial.print("failed, rc=");
    Serial.println(client.state());
    mqttRetryDelay = min(mqttRetryDelay * 2, MQTT_RETRY_DELAY_MAX);
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(13, OUTPUT);
  digitalWrite(13, LOW);
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

  connectMQTT();
  if (client.connected()) {
    client.loop();
  }

  if (millis() - lastTime >= interval){
    lastTime = millis();
    Serial.println("<C,GET>");
    publishData();
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '<') {
      buffer = "";
      buffer += c;
    }
    else if (c == '>') {
      buffer += c;
      processData(buffer);
      buffer = "";
    }
    else {
      buffer += c;
    }
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
      teganganPln = data.toFloat();
    }
    else if (type == "GENSET") {
      teganganGenset = data.toFloat();
    }
    else if (type == "AKI") {
      teganganAki = data.toFloat();
    }
    else if (type == "IS_PLN_ON") {
      isPlnOn = data.toInt();
    }
    else if (type == "IS_GENSET_ON") {
      isGensetOn = data.toInt();
    }
    else if (type == "IS_AKI_ON") {
      isAkiOn = data.toInt();
    }
    else if (type == "IS_WARMUP") {
      isWarmup = data.toInt();
    }
    else if (type == "REM_SEC") {
      sisaDetik = data.toInt();
    }
    else if (type == "REM_MIN") {
      sisaMenit = data.toInt();
    }
    else if (type == "REM_HOUR") {
      sisaJam = data.toInt();
    }
    else if (type == "AUTO_MODE") {
      autoMode = data.toInt();
    }
    else if (type == "EMERGENCY") {
      emergency = data.toInt();
    }
    else if (type == "DATE") {
      nowDate = data;
    }
    else if (type == "TIME") {
      nowTime = data;
    }
  }
  else if (commaIndex == -1 && endIndex != -1) {
    String txt = msg.substring(1, endIndex);
    if (isOledPresent) {
      display.clearDisplay();
      display.setCursor(0, 10);
      display.println(txt);
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

