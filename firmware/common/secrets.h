#pragma once
// secrets.h — LOCAL ONLY, gitignored (firmware/common/secrets.h).
// Copy from secrets.h.example and fill live values for local arduino-cli compile.
// DO NOT commit this file. For Arduino IDE, also copy this file into each sketch folder.
// Live values must be provided via env/deployment, not hardcoded in .ino.

#define WIFI_SSID "smsb-iot"
#define WIFI_PASS "CHANGE_ME"  // <-- replace with live WiFi password for local compile
#define MQTT_USER "hubadmin"
#define MQTT_PASS "CHANGE_ME_32+CHARS"  // <-- replace with live MQTT password (min 32 chars)
#define MQTT_HOST "192.168.72.242"
#define HUB_NAME  "hs109rs-hub-01"
