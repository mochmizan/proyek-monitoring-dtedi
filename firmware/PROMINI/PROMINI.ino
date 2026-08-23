#include <ZMPT101B.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "RTClib.h"
#include <EEPROM.h>

#define SENSITIVITAS_SENSOR_AC 500.0f
#define BATAS_VAC 200.0f
#define BATAS_AKI 12.0f

LiquidCrystal_I2C lcd(0x27, 16, 2);

enum State {
  WAIT_AKI,
  CHECK_WAIT_AKI,
  PLN,
  GENSET,
  WAIT, 
  LONG_WAIT,
  CHECK_WAIT,
  CHECK_LONG_WAIT,
  DELAY_AFTER_START_GENSET,
  WAIT_GENSET,
  CHECK_WAIT_GENSET,
  START_GENSET,
  EMERGENCY_GENSET

};

State nowState = WAIT;

enum manualState {
  WAIT_COMMAND,
  GENSET_ON,
  GENSET_OFF
};

manualState nowManualState = WAIT_COMMAND;

enum gensetOnFSM {
  AWAL_ON,
  NYALAKAN_GENSET,
  MULAI_STARTER,
  LEPAS_STARTER,
  TUNGGU_ON
};

gensetOnFSM gensetOnState = AWAL_ON;

enum gensetOffFSM {
  AWAL_OFF,
  LEPAS_ON,
  TUNGGU_OFF
};

gensetOffFSM gensetOffState = AWAL_OFF;

RTC_DS3231 rtc;
ZMPT101B sensorPLN (A1, 50.0);
ZMPT101B sensorGenset (A0, 50.0);
DateTime nowTime;
DateTime lastWarmup;

const unsigned long WARMUP_COUNTDOWN_SEC = 86400UL;

struct warmupCountdown{
  long remSecTotal;
  long remSec;
  long remMin;
  long remHour;
};

const int relay1 = 4;
const int relay2 = 5;
const int akiPin = A2;
const int emergencyGensetPin = 2;
const int BTN_LEFT = 7;
const int BTN_RIGHT = 8;
int menu = 0;
unsigned long debounce_left = 0;
unsigned long debounce_right = 0;

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
const unsigned long TEN_SECONDS = 20000; // delay after start genset
const unsigned long STARTER_INTERVAL = 2000;
const unsigned long FIVE_MIN = 300000;

int gensetStartAttempts = 0;
const int MAX_START_ATTEMPTS = 5;
bool emergencyNotified = false;

void nyalakan_genset(){
  digitalWrite(relay1, LOW);
}

void matikan_genset(){
  digitalWrite(relay1, HIGH);
}

void mulai_starter_genset(){
  digitalWrite(relay2, LOW);
}

void lepas_starter_genset(){
  digitalWrite(relay2, HIGH);
}

void nyalakan_lampu_emergency(){
  digitalWrite(emergencyGensetPin, LOW);
}

void matikan_lampu_emergency(){
  digitalWrite(emergencyGensetPin, HIGH);
}

void setup() {

  Serial.begin(9600);

  Wire.begin();

  lcd.init();
  lcd.backlight();

  lcd.setCursor(0,0);
  lcd.print("Hello World!");

  pinMode(BTN_LEFT, INPUT_PULLUP);
  pinMode(BTN_RIGHT, INPUT_PULLUP);

  pinMode(emergencyGensetPin, OUTPUT);
  pinMode(relay1, OUTPUT);
  pinMode(relay2, OUTPUT);

  matikan_genset();
  lepas_starter_genset();
  matikan_lampu_emergency();

  sensorPLN.setSensitivity(SENSITIVITAS_SENSOR_AC);
  sensorGenset.setSensitivity(SENSITIVITAS_SENSOR_AC);

  if (!rtc.begin()) {
    rtcAvailable = false;
    Serial.println("<RTC tidak ditemukan! Mode degradasi: warmup countdown nonaktif, FSM tetap jalan>");
    // Tidak ada while(1); — sistem lanjut operasi normal tanpa RTC
  }
  else {
    rtcAvailable = true;

    // // Jika RTC kehilangan power
    if (rtc.lostPower()) {
      Serial.println("<RTC kehilangan power, set waktu!>");

      // SET waktu sesuai waktu compile
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));

      // // ATAU set manual:
      // rtc.adjust(DateTime(2026, 4, 18, 19, 39, 0));
    }

    // rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));

  ///////////////////
    unsigned long now = rtc.now().unixtime();
    unsigned long savedTime;

    EEPROM.get(0, savedTime);

    if (savedTime > 1700000000 && savedTime < now) {
      lastWarmup = DateTime(savedTime);
      Serial.println("<Data warmup berhasil dimuat>");
    }
    else {
      Serial.println("<Data EEPROM kosong / invalid>");
      EEPROM.put(0, now);
      lastWarmup = rtc.now(); // fallback
    }
  ///////////////////////
  }

// Last Warmup Kemarin Jam 3

  // DateTime now = rtc.now();

  // // Besok
  // DateTime besok = now - TimeSpan(1, 0, 0, 0);

  // // Besok jam 02:00:00
  // DateTime warmupTime(
  //     besok.year(),
  //     besok.month(),
  //     besok.day(),
  //     15, 0, 0
  // );

// Last Warmup Kemarin Jam 3

  // EEPROM.put(0, warmupTime.unixtime());
  // lastWarmup = warmupTime;

  // EEPROM.get(0, savedTime);

  // if (savedTime > 1700000000 && savedTime < now) {

  //     DateTime t(savedTime);

  //     // Tambah 1 hari
  //     t = t + TimeSpan(1, 0, 0, 0);

  //     // Ubah jam menjadi 04:00
  //     DateTime fixedTime(
  //         t.year(),
  //         t.month(),
  //         t.day(),
  //         4, 0, 0);

  //     EEPROM.put(0, fixedTime.unixtime());
  //     lastWarmup = fixedTime;

  //     Serial.println("EEPROM berhasil diubah.");
  // }

  // EEPROM.put(0, now);
  // lastWarmup = rtc.now(); // fallback

  delay(1000);
}

void processCommand(String msg) {
  
  int commaIndex = msg.indexOf(',');
  int endIndex = msg.indexOf('>');  

  if (commaIndex != -1 && endIndex != -1) {

    String type = msg.substring(1, commaIndex);
    String data = msg.substring(commaIndex + 1, endIndex);

    if (type == "C") {
      
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
        Serial.print(emergencyNotified);
        Serial.println(">");
      }
    }
    else if (type == "RST"){
      emergencyNotified = false;
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

    else if (type == "SGM"){ // SGM = Start Genset Manually

      if (gensetOnState == AWAL_ON && gensetOffState == AWAL_OFF){
        if (data == "off"){
          nowManualState = GENSET_OFF;
        }
        else if (data == "on"){
          nowManualState = GENSET_ON;// start_genset_manually
        }
      }
    }
  }
}

void do_lcd(){
  if (digitalRead(BTN_LEFT) == LOW) {
    if (millis() - debounce_left >= 100) {
      menu--;
      debounce_left = millis();
    }
  }
  else if (digitalRead(BTN_RIGHT) == LOW) {
    if (millis() - debounce_right >= 100) {
      menu++;
      debounce_right = millis();
    }
  }

  lcd.clear();

  if (emergencyNotified == false){
    if (menu <= 0) {
      menu = 0;
      lcd.setCursor(0,0);
      lcd.print("STATE:");
      lcd.setCursor(0, 1);
      lcd.print(stateToString(nowState));
    }
    else if (menu == 1) {
      lcd.setCursor(0, 0);
      lcd.print("PLN: ");
      lcd.setCursor(5, 0);
      lcd.print(teganganPln, 0);

      lcd.setCursor(8, 0);
      lcd.print("AKI: ");
      lcd.setCursor(13, 0);
      lcd.print(teganganAki, 0);

      lcd.setCursor(0, 1);
      lcd.print("GENSET: ");
      lcd.setCursor(8, 1);
      lcd.print(teganganGenset, 0);
    }
    else if (menu == 2) {
      
      lcd.setCursor(0, 0);
      lcd.print("Warmup Rem. Time");

      char line2[17];

      sprintf(line2, "%02ld:%02ld:%02ld",
              sisaJam,
              sisaMenit,
              sisaDetik
              );
      lcd.setCursor(0, 1);
      lcd.print(line2);

    }
    else if (menu >= 3) {
      menu = 3;

      if (!rtcAvailable) {
        lcd.setCursor(0, 0);
        lcd.print("RTC offline");
      }
      else {
        char line1[17];
        char line2[17];

        sprintf(line1, "D:%02d/%02d/%02d",
                nowTime.day(),
                nowTime.month(),
                nowTime.year() % 100);   // hanya 2 digit tahun

        sprintf(line2, "T:%02d:%02d:%02d",
                nowTime.hour(),
                nowTime.minute(),
                nowTime.second());

        lcd.setCursor(0, 0);
        lcd.print(line1);

        lcd.setCursor(0, 1);
        lcd.print(line2);
      }
    }
  }
  else if (emergencyNotified == true){
    lcd.setCursor(2, 0);
    lcd.print("EMERGENCY!");
    lcd.setCursor(0, 0);
    lcd.print("GENSET FAILURE!");
  }
}

void loop() {

  if (rtcAvailable) {
    nowTime = rtc.now();
  }

  warmupCountdown countdown = getWarmupCountdown();

  sisaDetik = countdown.remSec;
  sisaMenit = countdown.remMin;
  sisaJam = countdown.remHour;

  teganganPln = readVAC(sensorPLN);
  teganganGenset = readVAC(sensorGenset);
  teganganAki = readVDC(akiPin);

  isPlnOn = checkVolt(teganganPln, BATAS_VAC);
  isGensetOn = checkVolt(teganganGenset, BATAS_VAC);
  isAkiOn = checkVolt(teganganAki, BATAS_AKI);

  while (Serial.available()) {
    char c = Serial.read();

    if (c == '<'){
      buffer = "";
      buffer += c;
    }
    else if (c == '>') {
      buffer += c;
      processCommand(buffer);
      buffer = "";
    }
    else {
      if (buffer.length() < 64) buffer += c;
      else buffer = "";
    }
  }

  unsigned long waktuGlobal = millis();

  if (autoMode) {

    if (lastMode == false) {
      lepas_starter_genset();
      lastMode = autoMode;
      indexTegangan = 0;
      nowState = WAIT;
    }

    if ( waktuGlobal - waktuGlobal_last1 >= LOOP_INTERVAL ) {
      
      waktuGlobal_last1 = waktuGlobal;

      if (nowState == PLN){
        
        matikan_genset();

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

      else if (nowState == DELAY_AFTER_START_GENSET){

          if (waktuGlobal - waktuGlobal_last2 >= TEN_SECONDS) {
            gensetStartAttempts++;
            waktuGlobal_last2 = waktuGlobal;
            nowState = WAIT_GENSET;
          }
      }

      else if (nowState == CHECK_WAIT_GENSET) {

        waktuGlobal_last2 = waktuGlobal;
        relayOrder = 0;

        if ( hasilWait == true ) {
          nowState = GENSET;

        }
        else {
          if (gensetStartAttempts >= MAX_START_ATTEMPTS) {
            nowState = EMERGENCY_GENSET;
            emergencyNotified = true;
          }
          else {
            nowState = START_GENSET;
          }

          matikan_genset();
          lepas_starter_genset();
        }
      }

      else if (nowState == START_GENSET) {

        if (relayOrder == 0) {

          if (waktuGlobal - waktuGlobal_last2 >= THREE_SECONDS) {

            waktuGlobal_last2 = waktuGlobal;
            nyalakan_genset();
            relayOrder++;

          }

        }

        else if (relayOrder == 1) {

          if (waktuGlobal - waktuGlobal_last2 >= THREE_SECONDS) {

            waktuGlobal_last2 = waktuGlobal;
            mulai_starter_genset();
            relayOrder++;

          }

        }

        else {

          if (waktuGlobal - waktuGlobal_last2 >= STARTER_INTERVAL) {
            waktuGlobal_last2 = waktuGlobal;
            lepas_starter_genset();
            nowState = DELAY_AFTER_START_GENSET;
          }

        }
      }

      else if (nowState == EMERGENCY_GENSET){
        matikan_genset();
        lepas_starter_genset();
        if (emergencyNotified == false){
          gensetStartAttempts = 0;
          indexTegangan = 0;
          nowState = WAIT;
          waktuGlobal_last2 = millis();
          matikan_lampu_emergency();
          Serial.println("<RESET_OK,Emergency direset, sistem kembali normal>");
        }
        else if (emergencyNotified == true){
          Serial.println("EMERGENCY,Genset gagal start setelah 5x percobaan. Cek kondisi fisik & kirim RST,confirm untuk reset");
          nyalakan_lampu_emergency();
        }
      }

      else if (nowState == GENSET){

        nyalakan_genset();

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

    }
  }
  else {
    Serial.print("<Manual Mode>");

    if (lastMode == true){
      lastMode = autoMode;
      waktuGlobal_last2 = waktuGlobal;
      nowManualState = WAIT_COMMAND;

      gensetOnState = AWAL_ON;
      gensetOffState = AWAL_OFF;
      lepas_starter_genset();
    }

    if (nowManualState == WAIT_COMMAND){
      Serial.println("Waiting for command!");
      waktuGlobal_last2 = waktuGlobal;
    }

    else if (nowManualState == GENSET_ON){
      if (gensetOnState == AWAL_ON){
        Serial.println("Memulai aktifkan genset!");
        wait_next_genset_on_state(waktuGlobal, NYALAKAN_GENSET);
      }
      else if (gensetOnState == NYALAKAN_GENSET){

        nyalakan_genset();

        wait_next_genset_on_state(waktuGlobal, MULAI_STARTER);
      }
      else if (gensetOnState == MULAI_STARTER){

        mulai_starter_genset();
        wait_next_genset_on_state(waktuGlobal, LEPAS_STARTER);
      }
      else if (gensetOnState == LEPAS_STARTER){
        lepas_starter_genset();
        wait_next_genset_on_state(waktuGlobal, TUNGGU_ON);
      }
      else if (gensetOnState == TUNGGU_ON){
        gensetOnState = AWAL_ON;
        nowManualState = WAIT_COMMAND;
      }
    }

    else if (nowManualState == GENSET_OFF){
      if (gensetOffState == AWAL_OFF){
        Serial.println("Memulai matikan genset!");
        wait_next_genset_off_state(waktuGlobal, LEPAS_ON);
        lepas_starter_genset(); // preventif check
      }
      else if (gensetOffState == LEPAS_ON){
        matikan_genset();
        wait_next_genset_off_state(waktuGlobal, TUNGGU_OFF);
      }
      else if (gensetOffState == TUNGGU_OFF){
        gensetOffState = AWAL_OFF;
        nowManualState = WAIT_COMMAND;
      }
    }
  }

  do_lcd();
}

void wait_next_genset_on_state(unsigned long waktuGlobal, gensetOnFSM state) {
  if (waktuGlobal - waktuGlobal_last2 >= THREE_SECONDS) {
      gensetOnState = state;
      waktuGlobal_last2 = waktuGlobal;
  }
}

void wait_next_genset_off_state(unsigned long waktuGlobal, gensetOffFSM state) {
  if (waktuGlobal - waktuGlobal_last2 >= THREE_SECONDS) {
      gensetOffState = state;
      waktuGlobal_last2 = waktuGlobal;
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
    case DELAY_AFTER_START_GENSET: return "DELAY_AFTER_START_GENSET";
    case WAIT_GENSET: return "WAIT_GENSET";
    case CHECK_WAIT_GENSET: return "CHECK_WAIT_GENSET";
    case START_GENSET: return "START_GENSET";
    case EMERGENCY_GENSET: return "EMERGENCY_GENSET";
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
    // Mode degradasi: warmup dianggap selesai, FSM langsung lanjut tanpa RTC
    return {0, 0, 0, 0};
  }

  TimeSpan diff = nowTime - lastWarmup;

  long rem_sec_total = WARMUP_COUNTDOWN_SEC - diff.totalseconds();

  if (rem_sec_total < 0) rem_sec_total = 0;

  long rem_hour = (rem_sec_total - (rem_sec_total % 3600)) / 3600;

  long hour_in_sec = rem_hour * 3600;

  long rem_sec = (rem_sec_total - hour_in_sec) % 60;

  long rem_min = ((rem_sec_total - hour_in_sec) - rem_sec) / 60;

  return {rem_sec_total, rem_sec, rem_min, rem_hour};
}
