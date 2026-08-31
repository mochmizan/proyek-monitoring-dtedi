#include <ZMPT101B.h>
#include <Wire.h>
#include "RTClib.h"
#include <EEPROM.h>
#include <avr/wdt.h>

#define SENSITIVITAS_SENSOR_AC 500.0f
#define BATAS_VAC 200.0f
#define BATAS_AKI 12.0f

const int EMERGENCY_RETRY_LIMIT = 3;
int failedStartAttempts = 0;
bool emergencyNotified = false;

enum State {
  WAIT_AKI,
  CHECK_WAIT_AKI,
  PLN,
  GENSET,
  WAIT, 
  LONG_WAIT,
  CHECK_WAIT,
  CHECK_LONG_WAIT,
  WAIT_GENSET,
  CHECK_WAIT_GENSET,
  START_GENSET

};

State nowState = WAIT;

RTC_DS3231 rtc;
ZMPT101B sensorPLN (A1, 50.0);
ZMPT101B sensorGenset (A0, 50.0);
DateTime nowTime;
DateTime lastWarmup;

const unsigned int WARMUP_COUNTDOWN_SEC = 86400;

struct warmupCountdown{
  long remSecTotal;
  long remSec;
  long remMin;
  long remHour;
};

const int relay1 = 2;
const int relay2 = 3;
const int akiPin = A2;

String buffer = "";

bool autoMode = true;
bool lastMode = autoMode;
bool isPlnOn = false;
bool isGensetOn = false;
bool isAkiOn = false;
bool hasilWait = false;
bool isWarmup = false;
bool warmupStarted = false;
bool rtcAvailable = false;
unsigned int relayOrder = 0;

double teganganPln = 0;
double teganganGenset = 0;
double teganganAki = 0;

long sisaDetik = 0;
long sisaMenit = 0;
long sisaJam = 0;

const int SIZE = 10;
const int LONG_SIZE = 20; //default 120
bool dataTegangan[SIZE];
bool dataTegangan_long[LONG_SIZE];
int indexTegangan = 0;

unsigned long waktuGlobal_last1 = 0;
unsigned long waktuGlobal_last2 = 0;
unsigned long waktuGlobal_warmup = 0;

const unsigned long LOOP_INTERVAL = 500; // Siklus loop setiap 0.5 detik
const unsigned long THREE_SECONDS = 3000;
const unsigned long STARTER_INTERVAL = 2000;
const unsigned long FIVE_MIN = 300000;

void setup() {
  MCUSR = 0;
  wdt_disable();

  Serial.begin(9600);

  Wire.begin();
  
  pinMode(relay1, OUTPUT);
  pinMode(relay2, OUTPUT);
  pinMode(13, OUTPUT);

  digitalWrite(relay1, HIGH);
  digitalWrite(relay2, HIGH);

  sensorPLN.setSensitivity(SENSITIVITAS_SENSOR_AC);
  sensorGenset.setSensitivity(SENSITIVITAS_SENSOR_AC);

  if (!rtc.begin()) {
    rtcAvailable = false;
    Serial.println(F("<RTC tidak ditemukan! Mode degradasi: warmup countdown nonaktif, FSM tetap jalan>"));
    // Tidak ada while(1); - sistem lanjut operasi normal tanpa RTC (mirror PROMINI.ino:181)
  } else {
    rtcAvailable = true;

    // Jika RTC kehilangan power
    if (rtc.lostPower()) {
      Serial.println(F("<RTC kehilangan power, set waktu!>"));

      // SET waktu sesuai waktu compile
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));

      // ATAU set manual:
      // rtc.adjust(DateTime(2026, 4, 18, 19, 39, 0));
    }

    unsigned long now = rtc.now().unixtime();
    unsigned long savedTime;

    EEPROM.get(0, savedTime);

    if (savedTime > 1700000000 && savedTime < now) {
      lastWarmup = DateTime(savedTime);
      Serial.println(F("<Data warmup berhasil dimuat>"));
    }
    else {
      Serial.println(F("<Data EEPROM kosong / invalid>"));
      EEPROM.put(0, now);
      lastWarmup = rtc.now(); // fallback
    }
  }

  delay(1000);
  wdt_enable(WDTO_8S);
}

void processCommand(String msg) {
  
  int commaIndex = msg.indexOf(',');
  int endIndex = msg.indexOf('>');  

  if (commaIndex != -1 && endIndex != -1) {

    String type = msg.substring(1, commaIndex);
    String data = msg.substring(commaIndex + 1, endIndex);

    if (type == "C") {
      if (autoMode == false) {
        if (data == "LED_ON") {
          digitalWrite(13, HIGH);
        }
        else if (data == "LED_OFF") {
          digitalWrite(13, LOW);
        }
        else if (data == "R1_ON") {
          digitalWrite(relay1, LOW);
        }
        else if (data == "R1_OFF") {
          digitalWrite(relay1, HIGH);
        }
        else if (data == "R2_ON") {
          digitalWrite(relay2, LOW);
        }
        else if (data == "R2_OFF") {
          digitalWrite(relay2, HIGH);
        }
      }

      if (data == "GET") {
        Serial.print("<STATE,");
        Serial.print(stateToString(nowState));
        Serial.println(">");

        Serial.print("<PLN,");
        Serial.print(teganganPln);
        Serial.println(">");
        Serial.print("<GENSET,");
        Serial.print(teganganGenset);
        Serial.println(">");
        Serial.print("<AKI,");
        Serial.print(teganganAki);
        Serial.println(">");

        Serial.print("<IS_PLN_ON,");
        Serial.print(isPlnOn);
        Serial.println(">");
        Serial.print("<IS_GENSET_ON,");
        Serial.print(isGensetOn);
        Serial.println(">");
        Serial.print("<IS_AKI_ON,");
        Serial.print(isAkiOn);
        Serial.println(">");
        Serial.print("<IS_WARMUP,");
        Serial.print(isWarmup);
        Serial.println(">");

        Serial.print("<REM_SEC,");
        Serial.print(sisaDetik);
        Serial.println(">");
        Serial.print("<REM_MIN,");
        Serial.print(sisaMenit);
        Serial.println(">");
        Serial.print("<REM_HOUR,");
        Serial.print(sisaJam);
        Serial.println(">");

        Serial.print("<AUTO_MODE,");
        Serial.print(autoMode);
        Serial.println(">");

        Serial.print("<EMERGENCY,");
        Serial.print(emergencyNotified ? 1 : 0);
        Serial.println(">");

        Serial.print("<DATE,");
        Serial.print(nowTime.day());
        Serial.print("/");
        Serial.print(nowTime.month());
        Serial.print("/");
        Serial.print(nowTime.year());
        Serial.println(">");

        Serial.print("<TIME,");
        Serial.print(nowTime.hour());
        Serial.print(":");
        Serial.print(nowTime.minute());
        Serial.print(":");
        Serial.print(nowTime.second());
        Serial.println(">");
      }
    }
    else if (type == "SGM") {
      if (autoMode == false) {
        if (data == "on") {
          digitalWrite(relay2, LOW);
        }
        else if (data == "off") {
          digitalWrite(relay2, HIGH);
        }
      }
    }
    else if (type == "RST") {
      if (data == "rst") {
        emergencyNotified = false;
        failedStartAttempts = 0;
      }
    }
    else if (type == "M" ) {
      lastMode = autoMode;
      if (data == "auto") {
        autoMode = true;
      }
      else if (data == "manual") {
        autoMode = false;
      }
    }
  }
}

void loop() {
  wdt_reset();

  if (rtcAvailable) {
    nowTime = rtc.now();
  }

  auto countdown = getWarmupCountdown();

  sisaDetik = countdown.remSec;
  sisaMenit = countdown.remMin;
  sisaJam = countdown.remHour;

  teganganPln = readVAC(sensorPLN);
  teganganGenset = readVAC(sensorGenset);
  teganganAki = readVDC(akiPin);

  isPlnOn = checkVolt(teganganPln, BATAS_VAC);
  isGensetOn = checkVolt(teganganGenset, BATAS_VAC);
  isAkiOn = checkVolt(teganganAki, BATAS_AKI);

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
      processCommand(String(buf));
      len = 0;
      buf[0] = '\0';
    } else {
      if (len < 64) {
        buf[len++] = c;
        buf[len] = '\0';
      }
    }
  }

  unsigned long waktuGlobal = millis();

  if (autoMode) {

    if (lastMode == false) {
      digitalWrite(relay2, HIGH);
      lastMode = autoMode;
      indexTegangan = 0;
      nowState = WAIT;
    }

    if ( waktuGlobal - waktuGlobal_last1 >= LOOP_INTERVAL ) {
      
      waktuGlobal_last1 = waktuGlobal;

      if (nowState == PLN){
        
        digitalWrite(relay1, HIGH);

        if (countdown.remSecTotal <= 0){

          nowState = WAIT_GENSET;
          waktuGlobal_last2 = waktuGlobal;
          isWarmup = true;

        }
        else if (isAkiOn == false) {

          nowState = WAIT_AKI;

        }
        else if (isPlnOn == false) {

          nowState = WAIT;

        }
      }

      else if (nowState == WAIT) {

        if ( indexTegangan < SIZE ) {

          dataTegangan[indexTegangan] = isPlnOn;
          indexTegangan++;

        }
        else {

          hasilWait = cariModus(dataTegangan, SIZE);
          indexTegangan = 0;
          nowState = CHECK_WAIT;

        }

      }

      else if (nowState == CHECK_WAIT) {

        if ( hasilWait == true ) {

          nowState = PLN;

        }
        else {

          nowState = LONG_WAIT;

        }

      }

      else if (nowState == LONG_WAIT) {

        if ( indexTegangan < LONG_SIZE ) {

          dataTegangan_long[indexTegangan] = isPlnOn;
          indexTegangan++;

        }
        else {

          hasilWait = cariModus(dataTegangan_long, LONG_SIZE);
          indexTegangan = 0;
          nowState = CHECK_LONG_WAIT;

        }

      }

      else if (nowState == CHECK_LONG_WAIT) {

        if ( hasilWait == true ) {

          nowState = PLN;

        }
        else {

          nowState = WAIT_GENSET;
          waktuGlobal_last2 = waktuGlobal;
        }

      }

      else if (nowState == WAIT_AKI) {

        if ( indexTegangan < SIZE ) {

          dataTegangan[indexTegangan] = isAkiOn;
          indexTegangan++;

        }
        else {

          hasilWait = cariModus(dataTegangan, SIZE);
          indexTegangan = 0;
          nowState = CHECK_WAIT_AKI;

        }

      }

      else if (nowState == CHECK_WAIT_AKI) {

        if ( hasilWait == true ) {

          nowState = PLN;

        }
        else {

          nowState = WAIT_GENSET;
          isWarmup = true;

        }

      }    
      else if (nowState == WAIT_GENSET) {

        if ( indexTegangan < SIZE ) {

          dataTegangan[indexTegangan] = isGensetOn;
          indexTegangan++;

        }
        else {

          hasilWait = cariModus(dataTegangan, SIZE);
          indexTegangan = 0;
          nowState = CHECK_WAIT_GENSET;

        }

      }

      else if (nowState == CHECK_WAIT_GENSET) {

        waktuGlobal_last2 = waktuGlobal;
        relayOrder = 0;

        if ( hasilWait == true ) {
          nowState = GENSET;
          failedStartAttempts = 0;
        }
        else {
          if (failedStartAttempts < EMERGENCY_RETRY_LIMIT) {
            failedStartAttempts++;
          }
          if (failedStartAttempts >= EMERGENCY_RETRY_LIMIT) {
            emergencyNotified = true;
          }

          if (!emergencyNotified) {
            nowState = START_GENSET;
            digitalWrite(relay1, HIGH);
          }
        }
      }

      else if (nowState == START_GENSET) {

        if (relayOrder == 0) {

          if (waktuGlobal - waktuGlobal_last2 >= THREE_SECONDS) {

            waktuGlobal_last2 = waktuGlobal;
            digitalWrite(relay1, LOW);
            relayOrder++;

          }

        }

        else if (relayOrder == 1) {

          if (waktuGlobal - waktuGlobal_last2 >= THREE_SECONDS) {

            waktuGlobal_last2 = waktuGlobal;
            digitalWrite(relay2, LOW);
            relayOrder++;

          }

        }

        else {

          if (waktuGlobal - waktuGlobal_last2 >= STARTER_INTERVAL) {
            waktuGlobal_last2 = waktuGlobal;
            digitalWrite(relay2, HIGH);
            nowState = WAIT_GENSET;
          }

        }
      }

      else if (nowState == GENSET){

        digitalWrite(relay1, LOW);

        if (isGensetOn == false) {
          nowState = WAIT_GENSET;
        }
        else if (isWarmup == true){

          if (warmupStarted == true) {
            if (waktuGlobal - waktuGlobal_warmup >= FIVE_MIN) {

              isWarmup = false;
              warmupStarted = false;

              if (rtcAvailable) {
                unsigned long now = rtc.now().unixtime();
                EEPROM.put(0, now);
                lastWarmup = rtc.now();
              }

            }
          }
          else {
            warmupStarted = true;
            waktuGlobal_warmup = waktuGlobal;
          }

        }
        else if (isPlnOn == true) {
          nowState = LONG_WAIT;
        }
      }

      Serial.print("<State: ");
      Serial.print(stateToString(nowState));
      Serial.println(">");

      Serial.print("<EMERGENCY,");
      Serial.print(emergencyNotified ? 1 : 0);
      Serial.println(">");

    }
  }
  else {
    if (lastMode == true){
      lastMode = autoMode;
      digitalWrite(relay2, HIGH);
    }
    Serial.print("<Manual Mode>");
  }
}

const char* stateToString(State s) {
  switch (s) {
    case WAIT_AKI: return "WAIT_AKI";
    case CHECK_WAIT_AKI: return "CHECK_WAIT_AKI";
    case PLN: return "PLN";
    case GENSET: return "GENSET";
    case WAIT: return "WAIT";
    case LONG_WAIT: return "LONG_WAIT";
    case CHECK_WAIT: return "CHECK_WAIT";
    case CHECK_LONG_WAIT: return "CHECK_LONG_WAIT";
    case WAIT_GENSET: return "WAIT_GENSET";
    case CHECK_WAIT_GENSET: return "CHECK_WAIT_GENSET";
    case START_GENSET: return "START_GENSET";
    default: return "UNKNOWN";
  }
}

// fungsi untuk mencari modus
bool cariModus(bool arr[], int size) {
  int countTrue = 0;
  int countFalse = 0;

  for (int i = 0; i < size; i++) {
    if (arr[i]) {
      countTrue++;
    } else {
      countFalse++;
    }
  }

  // tentukan hasil
  if (countTrue > countFalse) {
    return true;
  } else {
    return false;
  }
}

bool checkVolt (double volt, double batas){
  bool status;

  if (volt < batas) {
    status = false;
  }
  else {
    status = true;
  }
  return status;
}

double readVAC(ZMPT101B &VAC) {
  double vac = VAC.getRmsVoltage();
  return vac;
}

double readVDC(int pin){
  int value = analogRead(pin);
  double vdc = map(value, 0, 1023, 0, 2500);
  vdc /= 100;
  return vdc;
}

warmupCountdown getWarmupCountdown(){

  if (!rtcAvailable) {
    // Mode degradasi: warmup dianggap selesai, FSM langsung lanjut tanpa RTC (mirror PROMINI.ino:848)
    return {0, 0, 0, 0};
  }

  TimeSpan diff = nowTime - lastWarmup;

  long rem_sec_total = WARMUP_COUNTDOWN_SEC - diff.totalseconds();

  long rem_hour = (rem_sec_total - (rem_sec_total % 3600)) / 3600;

  long hour_in_sec = rem_hour * 3600;

  long rem_sec = (rem_sec_total - hour_in_sec) % 60;

  long rem_min = ((rem_sec_total - hour_in_sec) - rem_sec) / 60;

  return {rem_sec_total, rem_sec, rem_min, rem_hour};
}
