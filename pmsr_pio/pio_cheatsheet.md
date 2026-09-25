# PlatformIO CLI Cheatsheet

## Daftar Isi

1. [Project](#1-project)
2. [Build / Compile](#2-build--compile)
3. [Clean Build](#3-clean-build)
4. [Upload](#4-upload)
5. [Serial Monitor](#5-serial-monitor)
6. [Melihat Device yang Terhubung](#6-melihat-device-yang-terhubung)
7. [Library](#7-library)
8. [Platform](#8-platform)
9. [Multi-Environment](#9-multi-environment)
10. [Command yang Paling Sering Dipakai](#10-command-yang-paling-sering-dipakai)
11. [Workflow Harian](#11-workflow-harian)
12. [Pola Dasar PlatformIO](#12-pola-dasar-platformio)

---

## 1. Project

### Membuat project

```bash
pio project init
```

### Melihat konfigurasi project

```bash
pio project config
```

### Melihat metadata project

```bash
pio project metadata
```

---

## 2. Build / Compile

### Build semua environment

```bash
pio run
```

### Build environment tertentu

```bash
pio run -e wemos1
```

Contoh:

```bash
pio run -e wemos_sensor
pio run -e wemos_actuator
pio run -e promini
```

---

## 3. Clean Build

### Clean default environment

```bash
pio run -t clean
```

### Clean environment tertentu

```bash
pio run -e wemos1 -t clean
```

Berguna jika terdapat masalah cache atau hasil build sebelumnya.

---

## 4. Upload

### Compile + upload

```bash
pio run -e wemos1 -t upload
```

Contoh:

```bash
pio run -e wemos_sensor -t upload
pio run -e promini -t upload
```

PlatformIO akan otomatis melakukan:

```text
Source
   ↓
Compile
   ↓
Link
   ↓
Firmware
   ↓
Upload
```

Jika hasil build sudah up-to-date, PlatformIO tidak perlu mengompilasi ulang bagian yang tidak berubah.

---

## 5. Serial Monitor

### Membuka Serial Monitor

```bash
pio device monitor
```

### Dengan environment tertentu

```bash
pio device monitor -e wemos1
```

### Menentukan baudrate

```bash
pio device monitor -b 115200
```

Contoh:

```bash
pio device monitor -e wemos1 -b 115200
```

Keluar dari Serial Monitor:

```text
Ctrl + C
```

---

## 6. Melihat Device yang Terhubung

```bash
pio device list
```

Contoh output:

```text
/dev/ttyUSB0
/dev/ttyUSB1
```

Berguna ketika terdapat beberapa board yang terhubung.

---

## 7. Library

### Melihat library yang terinstall

```bash
pio pkg list
```

### Mencari library

```bash
pio pkg search "nama library"
```

Contoh:

```bash
pio pkg search "BME280"
```

### Install library

```bash
pio pkg install --library "nama/library"
```

Contoh:

```bash
pio pkg install --library "adafruit/Adafruit BME280 Library"
```

### Update library

```bash
pio pkg update
```

---

## 8. Platform

### Melihat platform

```bash
pio platform list
```

### Install platform

```bash
pio platform install espressif8266
```

### Update platform

```bash
pio platform update
```

---

# 9. Multi-Environment

Misalnya `platformio.ini` memiliki:

```ini
[platformio]
default_envs = wemos1
src_dir = firmware


[env:wemos1]
platform = espressif8266
board = d1_mini
framework = arduino
build_src_filter = +<wemos1/main.cpp>


[env:wemos2]
platform = espressif8266
board = d1_mini
framework = arduino
build_src_filter = +<wemos2/main.cpp>


[env:wemos3]
platform = espressif8266
board = d1_mini
framework = arduino
build_src_filter = +<wemos3/main.cpp>


[env:promini]
platform = atmelavr
board = pro16MHzatmega328
framework = arduino
build_src_filter = +<promini/main.cpp>
```

### Build

```bash
pio run -e wemos1
pio run -e wemos2
pio run -e wemos3
pio run -e promini
```

### Upload

```bash
pio run -e wemos1 -t upload
pio run -e wemos2 -t upload
pio run -e wemos3 -t upload
pio run -e promini -t upload
```

### Serial Monitor

```bash
pio device monitor -e wemos1
pio device monitor -e wemos2
pio device monitor -e wemos3
pio device monitor -e promini
```

---

# 10. Command yang Paling Sering Dipakai

| Kebutuhan                    | Command                           |
| ---------------------------- | --------------------------------- |
| Build                        | `pio run`                         |
| Build environment            | `pio run -e ENV`                  |
| Upload                       | `pio run -e ENV -t upload`        |
| Clean                        | `pio run -e ENV -t clean`         |
| Serial Monitor               | `pio device monitor`              |
| Serial Monitor + environment | `pio device monitor -e ENV`       |
| Lihat device                 | `pio device list`                 |
| Lihat library                | `pio pkg list`                    |
| Cari library                 | `pio pkg search "..."`            |
| Install library              | `pio pkg install --library "..."` |
| Update library               | `pio pkg update`                  |

---

# 11. Workflow Harian

Untuk development normal:

```bash
# 1. Build
pio run -e wemos1

# 2. Upload
pio run -e wemos1 -t upload

# 3. Monitor
pio device monitor -e wemos1
```

Atau langsung **build + upload**:

```bash
pio run -e wemos1 -t upload
```

Jika build bermasalah:

```bash
# Clean
pio run -e wemos1 -t clean

# Build ulang
pio run -e wemos1
```

Untuk board lain tinggal mengganti `ENV`:

```bash
pio run -e wemos2 -t upload
pio run -e wemos3 -t upload
pio run -e promini -t upload
```

---

# 12. Pola Dasar PlatformIO

```text
pio
│
├── project
│   ├── init
│   ├── config
│   └── metadata
│
├── run
│   ├── build
│   ├── clean
│   └── upload
│
├── device
│   ├── list
│   └── monitor
│
├── pkg
│   ├── list
│   ├── search
│   ├── install
│   └── update
│
└── platform
    ├── list
    ├── install
    └── update
```

### Yang paling penting dihafal

```bash
pio run -e ENV
```

→ **Compile / Build**

```bash
pio run -e ENV -t upload
```

→ **Compile + Upload**

```bash
pio device monitor -e ENV
```

→ **Serial Monitor**

```bash
pio device list
```

→ **Lihat board yang terhubung**
