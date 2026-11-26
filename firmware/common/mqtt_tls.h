#pragma once
// mqtt_tls.h — MQTT over TLS (port 8883) untuk node ESP8266 (TS / ATS / AC).
//
// Cara kerja: broker Mosquitto di Pi pakai server.crt; firmware mem-PIN public key broker
// (setKnownKey), jadi:
//   - trafik terenkripsi TLS 1.2 (username/password MQTT dan payload tidak lagi plaintext)
//   - ESP menolak broker palsu (rogue AP / MITM) karena public key harus cocok
//   - TIDAK butuh NTP / jam (Pi tanpa RTC & tanpa internet)
// File mqtt_tls_pin.h dibuat oleh tools/gen_mqtt_tls.sh (taruh di folder include/ ini).

#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>

#if __has_include("mqtt_tls_pin.h")
#include "mqtt_tls_pin.h"
#elif __has_include("../common/mqtt_tls_pin.h")
#include "../common/mqtt_tls_pin.h"
#elif __has_include("common/mqtt_tls_pin.h")
#include "common/mqtt_tls_pin.h"
#else
#error "mqtt_tls_pin.h belum ada. Jalankan tools/gen_mqtt_tls.sh lalu copy mqtt_tls_pin.h ke firmware/common/ (atau folder sketch)."
#endif

#define MQTT_TLS_PORT 8883

// Dipanggil sekali di setup(), SEBELUM mqtt.setServer()/connect().
inline void mqttTlsConfigure(BearSSL::WiFiClientSecure &c)
{
    static BearSSL::PublicKey pinnedKey(MQTT_SERVER_PUBKEY_PEM);
    c.setKnownKey(&pinnedKey);
    c.setBufferSizes(1024, 512);   // hemat RAM (default 16 KB + 512 B); cukup untuk payload < 512 B
}
