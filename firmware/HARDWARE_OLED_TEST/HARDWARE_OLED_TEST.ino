#include <ESP8266WiFi.h>
#include <Wire.h>

#define LED_PIN 2  // Onboard LED on Wemos D1 Mini (D4 / GPIO2)
#define SDA_PIN D2 // GPIO 4
#define SCL_PIN D1 // GPIO 5

void i2cBusClear() {
    pinMode(SDA_PIN, INPUT_PULLUP);
    pinMode(SCL_PIN, OUTPUT);
    for (int i = 0; i < 10; i++) {
        digitalWrite(SCL_PIN, HIGH);
        delayMicroseconds(10);
        digitalWrite(SCL_PIN, LOW);
        delayMicroseconds(10);
    }
    pinMode(SDA_PIN, INPUT);
    pinMode(SCL_PIN, INPUT);
}

void sendOledCommand(uint8_t addr, uint8_t cmd) {
    Wire.beginTransmission(addr);
    Wire.write(0x00); // Co = 0, D/C# = 0 (Command)
    Wire.write(cmd);
    Wire.endTransmission();
}

void setup() {
    // 1. Disable WiFi to save power and prevent interference
    WiFi.mode(WIFI_OFF);
    WiFi.forceSleepBegin();

    // 2. Setup Onboard LED indicator
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW); // Turn LED ON

    // 3. Serial Debug Output
    Serial.begin(115200);
    delay(500);

    Serial.println();
    Serial.println(F("=============================================="));
    Serial.println(F("    WEMOS D1 MINI - OLED HARDWARE DIAGNOSTIC  "));
    Serial.println(F("=============================================="));

    // 4. Force I2C bus recovery
    i2cBusClear();
    delay(50);

    // 5. Initialize I2C at standard 100kHz
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);
    delay(100);

    // 6. Scan I2C Bus
    Serial.println(F("[*] Scanning I2C Bus for connected devices..."));
    int deviceCount = 0;
    uint8_t foundOledAddr = 0;

    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        byte error = Wire.endTransmission();
        if (error == 0) {
            Serial.printf("  [+] Found I2C Device at: 0x%02X", addr);
            if (addr == 0x3C || addr == 0x3D) {
                Serial.print(F(" <--- (OLED Display)"));
                foundOledAddr = addr;
            } else if (addr == 0x44 || addr == 0x45) {
                Serial.print(F(" <--- (SHT30 Temperature/Humidity Sensor)"));
            }
            Serial.println();
            deviceCount++;
        }
    }

    if (deviceCount == 0) {
        Serial.println(F("  [!] ERROR: No I2C devices responded! Check physical shield header."));
    } else {
        Serial.printf("[*] Total I2C devices responding: %d\n", deviceCount);
    }

    // 7. Force Hardware OLED Initialization on both 0x3C and 0x3D
    uint8_t testAddrs[] = {0x3C, 0x3D};
    for (int i = 0; i < 2; i++) {
        uint8_t a = testAddrs[i];
        Serial.printf("[*] Sending Raw Hardware Wakeup & Charge Pump to 0x%02X...\n", a);
        
        sendOledCommand(a, 0xAE); // Display OFF
        sendOledCommand(a, 0xD5); // Set Display Clock
        sendOledCommand(a, 0x80);
        sendOledCommand(a, 0xA8); // Set Multiplex
        sendOledCommand(a, 0x3F); // 64 MUX
        sendOledCommand(a, 0xD3); // Display Offset
        sendOledCommand(a, 0x00);
        sendOledCommand(a, 0x40); // Start Line 0
        sendOledCommand(a, 0x8D); // Enable Charge Pump (CRITICAL FOR OLED POWER)
        sendOledCommand(a, 0x14); // 7.5V Pump ON
        sendOledCommand(a, 0x81); // Set Contrast Max
        sendOledCommand(a, 0xFF);
        sendOledCommand(a, 0xA1); // Segment Remap
        sendOledCommand(a, 0xC8); // COM Output Scan Direction
        sendOledCommand(a, 0xDA); // Set COM Pins
        sendOledCommand(a, 0x12);
        sendOledCommand(a, 0xAF); // DISPLAY ON!
        sendOledCommand(a, 0xA5); // ENTIRE DISPLAY ALL-PIXELS-ON TEST
    }

    Serial.println(F("[*] Hardware Wakeup commands sent. Display should glow solid bright now."));
    Serial.println(F("=============================================="));
}

void loop() {
    // Fast Blink LED to confirm CPU is actively looping
    digitalWrite(LED_PIN, LOW);  // LED ON
    delay(200);
    digitalWrite(LED_PIN, HIGH); // LED OFF
    delay(200);
}
