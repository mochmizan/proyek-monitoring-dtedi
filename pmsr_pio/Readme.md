# PMSR — PlatformIO Project

Repository ini berisi firmware untuk sistem **PMSR (Power Management / Monitoring System)** yang sebelumnya dikembangkan menggunakan **Arduino IDE**, kemudian dimigrasikan ke **PlatformIO** agar proses pengembangan lebih terstruktur, dependency lebih mudah dikelola, dan beberapa jenis board dapat dikelola dalam satu project.

Project ini menggunakan beberapa target hardware:

* **Wemos D1 Mini / ESP8266**
* **Arduino Pro Mini / ATmega328P**

## Daftar Isi

- [1. Mengapa Migrasi dari Arduino IDE ke PlatformIO?](#1-mengapa-migrasi-dari-arduino-ide-ke-platformio)
- [2. Struktur Project](#2-struktur-project)
- [3. Karakteristik PlatformIO pada Project Ini](#3-karakteristik-platformio-pada-project-ini)
- [4. `platformio.ini`](#4-platformioini)
- [5. Konsep Environment](#5-konsep-environment)
- [6. `default_envs` Bukan Berarti Semua Board](#6-default_envs-bukan-berarti-semua-board)
- [7. Mengapa Source Dipisah ke `firmware/`?](#7-mengapa-source-dipisah-ke-firmware)
- [8. Perbedaan Arduino IDE `.ino` dan PlatformIO `.cpp`](#8-perbedaan-arduino-ide-ino-dan-platformio-cpp)
- [9. Function Prototype yang Ditambahkan](#9-function-prototype-yang-ditambahkan)
- [10. Library Management](#10-library-management)
- [11. ZMPT101B 1.0.1](#11-zmpt101b-101)
- [12. Jangan Duplikasi Library Tanpa Alasan](#12-jangan-duplikasi-library-tanpa-alasan)
- [13. Dependency Wemos](#13-dependency-wemos)
- [14. ArduinoJson Version](#14-arduinojson-version)
- [15. IntelliSense dan Red Squiggles](#15-intellisense-dan-red-squiggles)
- [16. Mengapa IntelliSense Bisa Salah?](#16-mengapa-intellisense-bisa-salah)
- [17. Solusi IntelliSense](#17-solusi-intellisense)
- [18. Jangan Edit `c_cpp_properties.json` Secara Manual](#18-jangan-edit-c_cpp_propertiesjson-secara-manual)
- [19. Mengapa Library di `lib/` Terlihat Lebih Mudah oleh IntelliSense?](#19-mengapa-library-di-lib-terlihat-lebih-mudah-oleh-intellisense)
- [20. `avr/wdt.h` Tidak Perlu Disalin](#20-avrwdth-tidak-perlu-disalin)
- [21. Build Project](#21-build-project)
- [22. Upload Firmware](#22-upload-firmware)
- [23. Serial Monitor](#23-serial-monitor)
- [24. Upload Port](#24-upload-port)
- [25. PlatformIO udev Rules pada Linux](#25-platformio-udev-rules-pada-linux)
- [26. Apakah udev Rules Wajib Jika Upload Sudah Berhasil?](#26-apakah-udev-rules-wajib-jika-upload-sudah-berhasil)
- [27. Banyak File `.rules` dengan Nomor `99`](#27-banyak-file-rules-dengan-nomor-99)
- [28. `.gitignore`](#28-gitignore)
- [29. Nested `.gitignore`](#29-nested-gitignore)
- [30. Jangan Ignore `lib/`](#30-jangan-ignore-lib)
- [31. `secrets.h`](#31-secretsh)
- [32. Jika `secrets.h` Sudah Pernah Di-Track](#32-jika-secretsh-sudah-pernah-di-track)
- [33. Troubleshooting](#33-troubleshooting)
- [34. Clean Build](#34-clean-build)
- [35. Melihat Dependency](#35-melihat-dependency)
- [36. Memeriksa Library yang Sebenarnya Digunakan](#36-memeriksa-library-yang-sebenarnya-digunakan)
- [37. Workflow Development yang Direkomendasikan](#37-workflow-development-yang-direkomendasikan)
- [38. Workflow Git](#38-workflow-git)
- [39. Hal yang Perlu Diingat Saat Menambah Board Baru](#39-hal-yang-perlu-diingat-saat-menambah-board-baru)
- [40. Ringkasan Konsep](#40-ringkasan-konsep)
- [41. Prinsip Utama Project](#41-prinsip-utama-project)
- [42. Status Migrasi](#42-status-migrasi)

---

## 1. Mengapa Migrasi dari Arduino IDE ke PlatformIO?

Pada Arduino IDE, setiap program umumnya dikelola sebagai sketch:

```text
project/
└── project.ino
```

Arduino IDE memberikan beberapa kemudahan otomatis, salah satunya adalah pembuatan **function prototype** untuk fungsi yang didefinisikan setelah `setup()` atau `loop()`.

PlatformIO menggunakan struktur project yang lebih dekat dengan project C/C++ pada umumnya:

```text
project/
├── platformio.ini
├── src/
├── include/
├── lib/
└── test/
```

Keuntungan utama migrasi:

1. Dependency dapat didefinisikan secara eksplisit.
2. Beberapa board dapat berada dalam satu repository.
3. Build dapat dilakukan berdasarkan environment.
4. Library dapat menggunakan versi tertentu.
5. Struktur source code lebih terorganisasi.
6. Project lebih mudah direproduksi pada komputer lain.
7. Integrasi dengan VS Code dan IntelliSense lebih baik.
8. Build dan upload dapat dilakukan melalui command line.

---

# 2. Struktur Project

Struktur utama project saat ini:

```text
pmsr_pio/
├── firmware/
│   ├── promini_ats/
│   │   └── main.cpp
│   │
│   ├── wemos_ac/
│   │   └── main.cpp
│   │
│   ├── wemos_ats/
│   │   └── main.cpp
│   │
│   └── wemos_ts/
│       └── main.cpp
│
├── include/
│   ├── README
│   └── secrets.h
│
├── lib/
│   ├── LiquidCrystal_I2C/
│   └── ZMPT101B/
│
├── platformio.ini
├── src/
│   └── main.cpp
│
└── test/
    └── README
```

> `secrets.h` berisi konfigurasi lokal/credential dan **tidak boleh di-commit** apabila mengandung password, token, atau credential asli. Gunakan `secrets.example.h` sebagai template.

---

# 3. Karakteristik PlatformIO pada Project Ini

Project ini tidak menggunakan satu board saja. Terdapat dua platform hardware utama:

| Environment | Board            | Platform   | Framework |
| ----------- | ---------------- | ---------- | --------- |
| `wemos_ac`  | Wemos D1 Mini    | ESP8266    | Arduino   |
| `wemos_ts`  | Wemos D1 Mini    | ESP8266    | Arduino   |
| `wemos_ats` | Wemos D1 Mini    | ESP8266    | Arduino   |
| `promini`   | Arduino Pro Mini | ATmega328P | Arduino   |

Perbedaan platform sangat penting.

ESP8266 menggunakan:

```ini
platform = espressif8266
board = d1_mini
framework = arduino
```

sedangkan Pro Mini menggunakan:

```ini
platform = atmelavr
board = pro16MHzatmega328
framework = arduino
```

Walaupun keduanya menggunakan Arduino framework, **toolchain, header, compiler, dan library system-nya berbeda**.

Contohnya:

```cpp
#include <ESP8266WiFi.h>
```

hanya relevan untuk ESP8266.

Sedangkan:

```cpp
#include <avr/wdt.h>
```

berasal dari environment AVR dan digunakan oleh Pro Mini.

---

# 4. `platformio.ini`

Konfigurasi utama project berada di:

```text
platformio.ini
```

Contoh struktur:

```ini
[platformio]
default_envs = wemos_ac
src_dir = firmware


[common_esp8266]
platform = espressif8266
board = d1_mini
framework = arduino
monitor_speed = 115200

lib_deps =
    knolleary/PubSubClient@2.8.0
    bblanchon/ArduinoJson@6.21.5
    adafruit/Adafruit GFX Library@1.11.11
    adafruit/Adafruit SSD1306@2.5.13
    adafruit/Adafruit SHT31 Library@2.2.2
    crankyoldgit/IRremoteESP8266@2.8.6


[env:wemos_ac]
extends = common_esp8266
build_src_filter = +<wemos_ac/main.cpp>


[env:wemos_ts]
extends = common_esp8266
build_src_filter = +<wemos_ts/main.cpp>


[env:wemos_ats]
extends = common_esp8266
build_src_filter = +<wemos_ats/main.cpp>


[env:promini]
platform = atmelavr
board = pro16MHzatmega328
framework = arduino
monitor_speed = 115200
build_src_filter = +<promini_ats/main.cpp>
```

---

# 5. Konsep Environment

PlatformIO menggunakan istilah **environment**.

Contohnya:

```text
wemos_ac
wemos_ts
wemos_ats
promini
```

Environment menentukan:

* board
* platform
* framework
* compiler/toolchain
* dependency
* source file yang digunakan
* konfigurasi upload
* konfigurasi serial monitor

Untuk melihat environment yang tersedia:

```bash
pio project config
```

atau langsung lihat:

```bash
cat platformio.ini
```

---

# 6. `default_envs` Bukan Berarti Semua Board

Contoh:

```ini
[platformio]
default_envs = wemos_ac
```

Artinya ketika menjalankan:

```bash
pio run
```

PlatformIO akan menggunakan:

```text
wemos_ac
```

bukan seluruh environment.

Jika ingin compile Pro Mini:

```bash
pio run -e promini
```

Jika ingin compile Wemos ATS:

```bash
pio run -e wemos_ats
```

Jika ingin compile beberapa environment:

```bash
pio run -e wemos_ac -e wemos_ts -e wemos_ats -e promini
```

### Mengapa tidak memasukkan semuanya ke `default_envs`?

Secara teknis bisa:

```ini
default_envs = wemos_ac,wemos_ts,wemos_ats,promini
```

tetapi tidak selalu ideal.

Karena ESP8266 dan AVR menggunakan toolchain yang berbeda, konfigurasi IntelliSense juga dapat menjadi ambigu.

Praktik yang digunakan pada project ini adalah:

```text
default_envs
    ↓
environment yang sedang aktif dikembangkan
```

Misalnya sedang mengembangkan Pro Mini:

```ini
default_envs = promini
```

Jika sedang mengembangkan Wemos:

```ini
default_envs = wemos_ac
```

Environment lain tetap dapat di-build secara eksplisit menggunakan `-e`.

---

# 7. Mengapa Source Dipisah ke `firmware/`?

Project ini menggunakan:

```ini
src_dir = firmware
```

sehingga PlatformIO menganggap:

```text
firmware/
```

sebagai source directory.

Source setiap board kemudian dipisahkan:

```text
firmware/
├── promini_ats/
├── wemos_ac/
├── wemos_ats/
└── wemos_ts/
```

Masing-masing environment memilih file yang sesuai menggunakan:

```ini
build_src_filter = +<wemos_ac/main.cpp>
```

atau:

```ini
build_src_filter = +<promini_ats/main.cpp>
```

Dengan demikian satu repository dapat menyimpan beberapa firmware tanpa semua `main.cpp` dikompilasi bersamaan.

---

# 8. Perbedaan Arduino IDE `.ino` dan PlatformIO `.cpp`

Ini merupakan salah satu masalah utama ketika migrasi.

Pada Arduino IDE, kode biasanya:

```text
main.ino
```

Arduino IDE melakukan beberapa preprocessing sebelum compiler C++ menjalankan kode.

Salah satunya adalah membuat function prototype secara otomatis.

Contoh Arduino IDE:

```cpp
void setup()
{
    processCommand("TEST");
}

void processCommand(const char* msg)
{
    // ...
}
```

Arduino IDE dapat membuat prototype secara otomatis.

---

## PlatformIO

Pada PlatformIO, source digunakan sebagai C++ biasa:

```text
main.cpp
```

Jika fungsi dipanggil sebelum deklarasinya diketahui compiler:

```cpp
void setup()
{
    processCommand("TEST");
}

void processCommand(const char* msg)
{
}
```

compiler dapat menghasilkan error:

```text
'processCommand' was not declared in this scope
```

Solusinya adalah menambahkan prototype:

```cpp
void processCommand(const char* msg);

void setup()
{
    processCommand("TEST");
}

void processCommand(const char* msg)
{
}
```

---

# 9. Function Prototype yang Ditambahkan

Pada firmware Pro Mini, beberapa prototype perlu ditambahkan di bagian atas file.

Contohnya:

```cpp
void processCommand(const char* msg);
void do_lcd();

void wait_next_genset_on_state(
    unsigned long waktuGlobal,
    gensetOnFSM state
);

void wait_next_genset_off_state(
    unsigned long waktuGlobal,
    gensetOffFSM state
);

const __FlashStringHelper* stateToString(State s);

bool cariModus(bool arr[], int size);
bool checkVolt(double volt, double batas);

double readVAC(ZMPT101B &VAC);
double readVDC(int pin);

warmupCountdown getWarmupCountdown();

DateTime getNextWarmup(DateTime now);

void saveNextWarmup(DateTime dt);

bool loadNextWarmup();
```

Prototype tersebut **tidak merusak kompatibilitas dengan Arduino IDE**.

Arduino IDE tetap dapat meng-compile kode tersebut karena function prototype adalah bagian normal dari C++.

---

# 10. Library Management

PlatformIO memiliki dua cara utama yang digunakan project ini untuk mendapatkan library.

## 10.1 `lib_deps`

Library normal sebaiknya didefinisikan di:

```ini
lib_deps =
    knolleary/PubSubClient@2.8.0
    bblanchon/ArduinoJson@6.21.5
```

PlatformIO kemudian menginstall dependency tersebut ke:

```text
.pio/libdeps/
```

Directory ini **tidak perlu di-commit**.

---

## 10.2 Library Lokal di `lib/`

Project juga menggunakan:

```text
lib/
├── LiquidCrystal_I2C/
└── ZMPT101B/
```

Library lokal digunakan ketika library tertentu perlu versi khusus atau tidak tersedia dengan mudah dari registry PlatformIO.

Contoh penting adalah:

```text
ZMPT101B 1.0.1
```

Library ZMPT101B yang digunakan oleh project Arduino sebelumnya memiliki API tertentu:

```cpp
setSensitivity(...)
getVoltageRMS(...)
```

Ketika PlatformIO mengambil versi lain dari registry, terjadi perbedaan API seperti:

```text
'class ZMPT101B' has no member named 'setSensitivity'
```

dan:

```text
'class ZMPT101B' has no member named 'getRmsVoltage'
```

---

# 11. ZMPT101B 1.0.1

Versi yang digunakan project Arduino sebelumnya adalah:

```text
ZMPT101B 1.0.1
```

Versi tersebut tidak berhasil diperoleh dengan:

```bash
pio pkg install --library "fmgambino/ZMPT101B@1.0.1"
```

sehingga library dari Arduino IDE dipindahkan secara lokal ke:

```text
lib/ZMPT101B/
```

Dengan cara ini PlatformIO menggunakan library lokal:

```text
lib/ZMPT101B
```

bukan library registry dengan versi berbeda.

Verbose build dapat digunakan untuk memastikan:

```bash
pio run -e promini -v
```

dan mencari:

```text
ZMPT101B @ 1.0.1
```

---

# 12. Jangan Duplikasi Library Tanpa Alasan

Jika sebuah library sudah berada di:

```text
lib/
```

jangan sekaligus menginstall versi lain melalui:

```ini
lib_deps
```

kecuali memang ada alasan khusus.

Contoh yang tidak ideal:

```text
lib/ZMPT101B/
```

dan sekaligus:

```ini
lib_deps =
    ...
    ZMPT101B
```

Hal tersebut dapat menyebabkan kebingungan versi atau dependency resolution.

Untuk project ini:

```text
ZMPT101B 1.0.1
    → lib/
```

sedangkan library umum dapat menggunakan:

```text
lib_deps
```

---

# 13. Dependency Wemos

Environment ESP8266 menggunakan dependency seperti:

```ini
lib_deps =
    knolleary/PubSubClient@2.8.0
    bblanchon/ArduinoJson@6.21.5
    adafruit/Adafruit GFX Library@1.11.11
    adafruit/Adafruit SSD1306@2.5.13
    adafruit/Adafruit SHT31 Library@2.2.2
    crankyoldgit/IRremoteESP8266@2.8.6
```

Framework ESP8266 juga menyediakan library seperti:

```text
ESP8266WiFi
Wire
EEPROM
```

yang tidak perlu disalin manual ke `lib/`.

---

# 14. ArduinoJson Version

Project ini menggunakan:

```text
ArduinoJson 6.21.5
```

Salah satu masalah yang muncul adalah kode menggunakan:

```cpp
JsonDocument doc;
```

Sementara API yang digunakan adalah ArduinoJson 6.

Untuk ArduinoJson 6 digunakan:

```cpp
StaticJsonDocument<512> doc;
```

Contoh:

```cpp
StaticJsonDocument<512> doc;
```

bukan:

```cpp
JsonDocument doc;
```

Perbedaan API library merupakan salah satu alasan penting untuk selalu mengunci versi dependency:

```ini
bblanchon/ArduinoJson@6.21.5
```

---

# 15. IntelliSense dan Red Squiggles

Salah satu masalah yang cukup membingungkan saat migrasi adalah:

> Program berhasil compile, tetapi header di VS Code berwarna merah.

Contohnya:

```cpp
#include <LiquidCrystal_I2C.h>
#include <RTClib.h>
#include <avr/wdt.h>
```

terlihat error di editor, tetapi:

```bash
pio run -e promini
```

berhasil.

Ini berarti masalahnya bukan compiler, melainkan **IntelliSense**.

---

# 16. Mengapa IntelliSense Bisa Salah?

PlatformIO membuat konfigurasi IntelliSense secara otomatis:

```text
.vscode/c_cpp_properties.json
```

File tersebut bergantung pada environment yang digunakan.

Jika:

```ini
default_envs = wemos_ac
```

maka IntelliSense dapat menggunakan:

```text
xtensa-lx106-elf-gcc
```

yang merupakan toolchain ESP8266.

Ketika membuka kode Pro Mini:

```cpp
#include <avr/wdt.h>
```

IntelliSense ESP8266 tentu tidak memiliki environment AVR yang sama.

Akibatnya:

```text
LiquidCrystal_I2C.h
RTClib.h
avr/wdt.h
```

dapat terlihat merah walaupun compiler Pro Mini sebenarnya dapat menemukannya.

---

# 17. Solusi IntelliSense

Ketika mengembangkan Pro Mini:

```ini
[platformio]
default_envs = promini
```

Ketika mengembangkan Wemos:

```ini
[platformio]
default_envs = wemos_ac
```

Setelah mengganti environment, IntelliSense akan menggunakan konfigurasi environment tersebut.

Pada kasus project ini, hanya dengan mengganti:

```ini
default_envs = wemos_ac
```

menjadi:

```ini
default_envs = promini
```

red squiggles pada library AVR menghilang tanpa perlu melakukan compile ulang.

---

# 18. Jangan Edit `c_cpp_properties.json` Secara Manual

File:

```text
.vscode/c_cpp_properties.json
```

adalah file yang dihasilkan PlatformIO.

Biasanya terdapat peringatan:

```text
!!! WARNING !!! AUTO-GENERATED FILE!
PLEASE DO NOT MODIFY IT AND USE "platformio.ini"
```

Karena itu jangan menjadikan edit manual file tersebut sebagai solusi utama.

Gunakan:

```text
platformio.ini
```

untuk menentukan environment.

Jika IntelliSense masih bermasalah, dapat dilakukan:

```text
PlatformIO: Rebuild IntelliSense Index
```

atau:

```text
Developer: Reload Window
```

---

# 19. Mengapa Library di `lib/` Terlihat Lebih Mudah oleh IntelliSense?

Library lokal:

```text
lib/LiquidCrystal_I2C/
lib/ZMPT101B/
```

langsung berada di dalam project sehingga lebih mudah ditemukan oleh IntelliSense.

Sedangkan dependency `lib_deps` berada di:

```text
.pio/libdeps/<environment>/
```

dan path tersebut bergantung pada environment yang aktif.

Karena itu kondisi berikut dapat terjadi:

```text
Compiler
    ↓
berhasil menemukan library

IntelliSense
    ↓
belum menggunakan environment yang benar
    ↓
header merah
```

Ini bukan berarti `lib_deps` gagal.

---

# 20. `avr/wdt.h` Tidak Perlu Disalin

Header:

```cpp
#include <avr/wdt.h>
```

berasal dari AVR toolchain/framework.

Jangan melakukan:

```text
lib/avr/wdt.h
```

atau menyalin file system header ke project.

Jika:

```bash
pio run -e promini
```

berhasil menemukan:

```cpp
#include <avr/wdt.h>
```

maka environment AVR sudah benar.

---

# 21. Build Project

Build Wemos AC:

```bash
pio run -e wemos_ac
```

Build Wemos TS:

```bash
pio run -e wemos_ts
```

Build Wemos ATS:

```bash
pio run -e wemos_ats
```

Build Pro Mini:

```bash
pio run -e promini
```

Build menggunakan default environment:

```bash
pio run
```

---

# 22. Upload Firmware

Upload Wemos:

```bash
pio run -e wemos_ac -t upload
```

Upload Pro Mini:

```bash
pio run -e promini -t upload
```

PlatformIO dapat melakukan auto-detection serial port.

Contoh:

```text
Auto-detected: /dev/ttyUSB0
```

Untuk melihat device:

```bash
pio device list
```

---

# 23. Serial Monitor

Karena environment menggunakan:

```ini
monitor_speed = 115200
```

serial monitor dapat dijalankan:

```bash
pio device monitor -b 115200
```

atau:

```bash
pio run -e wemos_ac -t monitor
```

---

# 24. Upload Port

Tidak selalu perlu menentukan port secara manual.

Jika PlatformIO berhasil melakukan:

```text
Auto-detected: /dev/ttyUSB0
```

biarkan PlatformIO melakukan auto-detection.

Jika terdapat beberapa device dan perlu menentukan port:

```ini
upload_port = /dev/ttyUSB0
```

Namun konfigurasi tersebut sebaiknya hanya digunakan jika memang diperlukan, karena nama `/dev/ttyUSB0` dapat berubah ketika perangkat dicabut/dipasang kembali.

---

# 25. PlatformIO udev Rules pada Linux

Pada Linux, PlatformIO dapat memberikan peringatan:

```text
Warning! Please install `99-platformio-udev.rules`.
```

Aturan udev membantu Linux mengatur akses dan identifikasi perangkat USB/serial.

Install:

```bash
curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules \
| sudo tee /etc/udev/rules.d/99-platformio-udev.rules
```

Kemudian:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Setelah itu cabut dan pasang kembali board.

Cek:

```bash
pio device list
```

---

# 26. Apakah udev Rules Wajib Jika Upload Sudah Berhasil?

Tidak selalu.

Pada kasus ini upload tetap berhasil meskipun PlatformIO awalnya memberikan warning.

Contohnya:

```text
Auto-detected: /dev/ttyUSB0
...
Hash of data verified.
Hard resetting via RTS pin
[SUCCESS]
```

Artinya akses device sudah bekerja.

Namun tetap disarankan memasang udev rules agar konfigurasi Linux sesuai dengan rekomendasi PlatformIO dan mengurangi masalah permission/access di kemudian hari.

---

# 27. Banyak File `.rules` dengan Nomor `99`

Dalam:

```text
/etc/udev/rules.d/
```

dapat terdapat:

```text
99-my-cameras.rules
99-platformio-udev.rules
```

Ini **bukan konflik otomatis**.

Nomor:

```text
99
```

menentukan urutan pemrosesan relatif.

Kedua file tetap merupakan file berbeda dan keduanya diproses.

Yang perlu diperhatikan hanya apabila kedua rule sama-sama cocok terhadap device tertentu dan mengatur property yang bertentangan.

Jangan menghapus:

```text
99-my-cameras.rules
```

hanya karena ada:

```text
99-platformio-udev.rules
```

---

# 28. `.gitignore`

Project PlatformIO menghasilkan banyak file sementara dan hasil build.

File seperti:

```text
.pio/
```

tidak perlu dimasukkan ke Git.

Contoh `.gitignore` khusus `pmsr_pio`:

```gitignore
# PlatformIO
.pio/
.piolibdeps/
.pioenvs/

# VS Code
.vscode/

# Build artifacts
*.o
*.elf
*.hex
*.bin
*.map

# Temporary files
*.swp
*.swo
*~

# Local secrets
include/secrets.h
```

---

# 29. Nested `.gitignore`

Repository utama dapat memiliki:

```text
proyek-monitoring-dtedi/
├── .gitignore
└── pmsr_pio/
    └── .gitignore
```

`.gitignore` yang berada di dalam `pmsr_pio` **tetap berlaku** walaupun Git repository berada satu level di atas.

Git membaca aturan `.gitignore` secara hierarkis.

Dengan demikian:

```text
root/.gitignore
        +
pmsr_pio/.gitignore
```

keduanya dapat bekerja bersama.

Ini berguna karena aturan khusus PlatformIO tidak perlu dimasukkan seluruhnya ke `.gitignore` repository utama.

---

# 30. Jangan Ignore `lib/`

Untuk project ini:

```text
lib/
├── LiquidCrystal_I2C/
└── ZMPT101B/
```

jangan di-ignore.

Library tersebut merupakan bagian dari source/dependency project, terutama:

```text
ZMPT101B 1.0.1
```

yang sengaja disimpan secara lokal karena versi yang dibutuhkan berbeda dengan dependency registry PlatformIO.

---

# 31. `secrets.h`

Jika file:

```text
include/secrets.h
```

mengandung:

```cpp
#define WIFI_PASSWORD "password"
#define MQTT_PASSWORD "password"
```

jangan commit file tersebut ke repository public.

Buat template:

```text
include/secrets.example.h
```

Contoh:

```cpp
#pragma once

#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

#define MQTT_SERVER "YOUR_MQTT_SERVER"
#define MQTT_USER "YOUR_MQTT_USER"
#define MQTT_PASSWORD "YOUR_MQTT_PASSWORD"
```

Kemudian setiap developer membuat:

```text
include/secrets.h
```

berdasarkan template tersebut.

---

# 32. Jika `secrets.h` Sudah Pernah Di-Track

`.gitignore` tidak otomatis menghentikan Git dari tracking file yang sudah pernah di-commit.

Cek:

```bash
git ls-files pmsr_pio/include/secrets.h
```

Jika muncul:

```text
pmsr_pio/include/secrets.h
```

hapus dari Git index:

```bash
git rm --cached pmsr_pio/include/secrets.h
```

File lokal tetap ada, tetapi Git tidak lagi melacaknya.

---

# 33. Troubleshooting

## 33.1 Header Merah Tetapi Build Berhasil

Contoh:

```cpp
#include <RTClib.h>
```

merah di VS Code tetapi:

```bash
pio run -e promini
```

berhasil.

### Penyebab

Environment IntelliSense tidak sesuai dengan source yang sedang dibuka.

### Solusi

Pastikan:

```ini
default_envs = promini
```

kemudian:

```text
PlatformIO: Rebuild IntelliSense Index
```

Jika perlu:

```text
Developer: Reload Window
```

---

## 33.2 `was not declared in this scope`

Contoh:

```text
'processCommand' was not declared in this scope
```

### Penyebab

Kode `.ino` Arduino IDE sebelumnya mengandalkan auto-generated prototype.

### Solusi

Tambahkan prototype:

```cpp
void processCommand(const char* msg);
```

di bagian atas file.

---

## 33.3 `ZMPT101B has no member named ...`

Contoh:

```text
'class ZMPT101B' has no member named 'setSensitivity'
```

### Penyebab

Versi ZMPT101B yang digunakan PlatformIO berbeda dengan versi yang digunakan Arduino IDE.

### Solusi

Gunakan versi library yang sama.

Pada project ini:

```text
ZMPT101B 1.0.1
```

disimpan di:

```text
lib/ZMPT101B/
```

Pastikan verbose build menunjukkan library tersebut:

```bash
pio run -e promini -v
```

---

## 33.4 `JsonDocument` Error

Jika muncul error berkaitan dengan:

```cpp
JsonDocument doc;
```

periksa versi ArduinoJson.

Project ini menggunakan:

```text
ArduinoJson 6.21.5
```

Gunakan:

```cpp
StaticJsonDocument<512> doc;
```

sesuai API ArduinoJson 6.

---

## 33.5 Upload Tidak Menemukan Board

Cek:

```bash
pio device list
```

Pastikan board terdeteksi.

Cek device Linux:

```bash
ls /dev/ttyUSB*
```

atau:

```bash
ls /dev/ttyACM*
```

Kemudian cabut/pasang board dan coba kembali.

---

## 33.6 Permission Serial

Jika device terdeteksi tetapi tidak dapat digunakan, periksa:

```bash
ls -l /dev/ttyUSB0
```

Cek group user:

```bash
groups
```

Pada sistem Linux tertentu, user perlu berada pada group:

```text
dialout
```

Contoh:

```bash
sudo usermod -aG dialout $USER
```

Kemudian logout/login kembali.

---

## 33.7 udev Warning

Jika muncul:

```text
Warning! Please install `99-platformio-udev.rules`.
```

install rule:

```bash
curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules \
| sudo tee /etc/udev/rules.d/99-platformio-udev.rules
```

Kemudian:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Cabut dan pasang kembali board.

---

# 34. Clean Build

Jika terjadi masalah build yang tidak jelas, bersihkan hasil build:

```bash
pio run -t clean
```

kemudian:

```bash
pio run -e promini
```

Untuk environment tertentu:

```bash
pio run -e wemos_ac -t clean
```

---

# 35. Melihat Dependency

Untuk melihat dependency yang digunakan:

```bash
pio pkg list
```

Untuk environment tertentu:

```bash
pio pkg list -e promini
```

Dependency Pro Mini yang digunakan pada project ini antara lain:

```text
ZMPT101B
LiquidCrystal_I2C
RTClib
EEPROM
Wire
```

Sedangkan Wemos menggunakan dependency ESP8266 seperti:

```text
PubSubClient
ArduinoJson
Adafruit GFX
Adafruit SSD1306
Adafruit SHT31
IRremoteESP8266
```

---

# 36. Memeriksa Library yang Sebenarnya Digunakan

Gunakan verbose build:

```bash
pio run -e promini -v
```

Ini sangat berguna ketika terdapat lebih dari satu library dengan nama/header yang sama.

Cari bagian seperti:

```text
-Ilib/ZMPT101B/src
```

atau:

```text
.pio/libdeps/promini/...
```

Dengan demikian dapat diketahui apakah compiler menggunakan library lokal atau dependency PlatformIO.

---

# 37. Workflow Development yang Direkomendasikan

### Mengembangkan Pro Mini

Set:

```ini
default_envs = promini
```

Compile:

```bash
pio run
```

atau:

```bash
pio run -e promini
```

Upload:

```bash
pio run -e promini -t upload
```

Monitor:

```bash
pio device monitor -b 115200
```

---

### Mengembangkan Wemos

Set:

```ini
default_envs = wemos_ac
```

Compile:

```bash
pio run
```

Upload:

```bash
pio run -e wemos_ac -t upload
```

Monitor:

```bash
pio device monitor -b 115200
```

---

# 38. Workflow Git

Sebelum commit:

```bash
git status
```

Periksa perubahan:

```bash
git diff
```

Tambahkan:

```bash
git add pmsr_pio/
```

Periksa staged files:

```bash
git status
```

Commit:

```bash
git commit -m "Migrate PMSR firmware to PlatformIO"
```

Push:

```bash
git push
```

Jangan melakukan:

```bash
git add .
```

secara membabi buta sebelum memeriksa `git status`, terutama untuk memastikan:

* `secrets.h` tidak ikut
* `.pio/` tidak ikut
* file sementara tidak ikut
* file library yang memang diperlukan tetap ikut

---

# 39. Hal yang Perlu Diingat Saat Menambah Board Baru

Jika board baru ditambahkan, buat environment baru di:

```text
platformio.ini
```

Contoh:

```ini
[env:new_board]
platform = ...
board = ...
framework = arduino
build_src_filter = +<new_board/main.cpp>
```

Kemudian:

```text
firmware/
└── new_board/
    └── main.cpp
```

Jika board menggunakan dependency khusus, tambahkan pada environment atau common environment yang sesuai.

Jangan memasukkan dependency ESP8266 ke environment AVR hanya karena library tersebut digunakan oleh environment lain.

---

# 40. Ringkasan Konsep

Secara sederhana, arsitektur project ini adalah:

```text
                    Git Repository
                          │
                          ▼
                     pmsr_pio/
                          │
                ┌─────────┴─────────┐
                │                   │
         platformio.ini         firmware/
                │                   │
                │          ┌────────┼─────────┐
                │          │        │         │
                ▼          ▼        ▼         ▼
          Environment    Wemos    Wemos     Pro Mini
          configuration    AC       ATS
                │
                ▼
        PlatformIO Build System
                │
       ┌────────┴────────┐
       │                 │
       ▼                 ▼
   ESP8266            ATmega328P
   toolchain           toolchain
       │                 │
       ▼                 ▼
   Wemos D1 Mini      Pro Mini
```

---

# 41. Prinsip Utama Project

Beberapa prinsip yang digunakan dalam migrasi ini:

### 1. Source code tetap dipisahkan berdasarkan hardware

```text
firmware/wemos_ac/
firmware/wemos_ts/
firmware/wemos_ats/
firmware/promini_ats/
```

### 2. Environment menentukan compiler dan board

```text
ESP8266 → espressif8266
ATmega328P → atmelavr
```

### 3. Library umum menggunakan `lib_deps`

```ini
lib_deps =
    ...
```

### 4. Library dengan versi khusus dapat disimpan di `lib/`

Contohnya:

```text
lib/ZMPT101B/
```

### 5. Jangan memasukkan hasil build ke Git

```text
.pio/
```

### 6. Jangan menyimpan credential asli

```text
include/secrets.h
```

### 7. Jangan mengedit konfigurasi IntelliSense secara manual

Gunakan:

```text
platformio.ini
```

dan pilih `default_envs` sesuai firmware yang sedang dikembangkan.

### 8. `.ino` dan `.cpp` tidak sepenuhnya sama

Kode yang sebelumnya bergantung pada preprocessing Arduino IDE mungkin membutuhkan:

```cpp
function_prototype();
```

ketika dipindahkan ke PlatformIO.

---

# 42. Status Migrasi

Migrasi dari Arduino IDE ke PlatformIO untuk project ini telah berhasil dilakukan.

Status environment:

| Environment           | Status                            |
| --------------------- | --------------------------------- |
| `wemos_ac`            | ✅ Build berhasil                  |
| `wemos_ts`            | ✅ PlatformIO environment tersedia |
| `wemos_ats`           | ✅ PlatformIO environment tersedia |
| `promini`             | ✅ Build berhasil                  |
| Wemos upload          | ✅ Berhasil                        |
| ZMPT101B 1.0.1        | ✅ Library lokal                   |
| ArduinoJson 6         | ✅ Dependency dikunci              |
| IntelliSense Pro Mini | ✅ Setelah memilih environment AVR |
| PlatformIO udev       | ✅ Rule tersedia                   |

Contoh hasil build Pro Mini:

```text
RAM:   [====      ] 40.3% (used 826 bytes from 2048 bytes)
Flash: [======    ] 61.8% (used 18976 bytes from 30720 bytes)

SUCCESS
```

Contoh hasil build Wemos:

```text
RAM:   [====      ] 36.5% (used 29916 bytes from 81920 bytes)
Flash: [===       ] 30.0% (used 312823 bytes from 1044464 bytes)

SUCCESS
```

Dengan demikian, project sudah dapat dikembangkan dan di-build menggunakan PlatformIO tanpa kehilangan struktur firmware yang sebelumnya digunakan pada Arduino IDE.
