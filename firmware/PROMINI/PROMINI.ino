#include <ZMPT101B.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "RTClib.h"
#include <EEPROM.h>
#include <avr/wdt.h>

#define SENSITIVITAS_SENSOR_AC 500.0f
#define BATAS_VAC 200.0f
#define BATAS_AKI 12.0f
#define VAC_ON 210.0f
#define VAC_OFF 190.0f
#define AKI_ON 12.5f
#define AKI_OFF 11.5f

LiquidCrystal_I2C lcd(0x27, 16, 2);
bool lcdAvailable = false;
unsigned long serialOverflowCount = 0;

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
DateTime nextWarmup;

// Weekly warmup scheduler (hardware-team v2): warmup setiap hari yang dipilih
const int WARMUP_DAY = 0;   // 0 = Sunday
const int WARMUP_HOUR = 18;

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

const int CMD_BUF_LEN = 64;
char cmdBuffer[CMD_BUF_LEN + 1];
int cmdBufferLen = 0;

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

const int SIZE = 20;
const int LONG_SIZE = 60; //default 120 proofed 10->20 20->60 for 10s/30s vote
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
const int MAX_START_ATTEMPTS = 3; // unified 3 vs fsm 3 (was 5)
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
  MCUSR = 0;
  wdt_disable();
  wdt_reset();

  Serial.begin(9600);

  Wire.begin();
  Wire.beginTransmission(0x27);
  lcdAvailable = (Wire.endTransmission() == 0);
  if (lcdAvailable) { lcd.init(); lcd.backlight(); lcd.setCursor(0,0); lcd.print(F("Hello World!")); }

  // Relay glitch-safe: drive HIGH before OUTPUT
  digitalWrite(emergencyGensetPin, HIGH);
  digitalWrite(relay1, HIGH);
  digitalWrite(relay2, HIGH);
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
    Serial.println(F("<RTC tidak ditemukan! Mode degradasi: warmup countdown nonaktif, FSM tetap jalan>"));
    // Tidak ada while(1); - sistem lanjut operasi normal tanpa RTC
  }
  else {
    rtcAvailable = true;

    // Jika RTC kehilangan power
    if (rtc.lostPower()) {
      Serial.println(F("<RTC kehilangan power, set waktu!>"));

      // SET waktu sesuai waktu compile
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));

      // ATAU set manual:
      // rtc.adjust(DateTime(2026, 4, 18, 19, 39, 0));
    }

    // Muat jadwal warmup mingguan dari EEPROM; jika invalid, hitung & simpan
    if (!loadNextWarmup()) {
      nextWarmup = getNextWarmup(rtc.now());
      saveNextWarmup(nextWarmup);
      Serial.println(F("<Data EEPROM kosong / invalid, jadwal warmup awal disimpan>"));
    }
    else {
      Serial.println(F("<Jadwal warmup berhasil dimuat>"));
    }
  }

  wdt_reset();
  delay(1000);
  wdt_reset();
  wdt_enable(WDTO_8S);
}

void processCommand(const char* msg) {

  const char* comma = strchr(msg, ',');
  const char* end = strchr(msg, '>');

  if (comma != NULL && end != NULL) {

    int typeLen = comma - msg - 1;
    int dataLen = end - comma - 1;
    const char* type = msg + 1;
    const char* data = comma + 1;

    if (typeLen == 1 && type[0] == 'C' && dataLen == 3 && strncmp(data, "GET", 3) == 0) {
        Serial.print(F("<STATE,"));
        Serial.print(stateToString(nowState));
        Serial.println(F(">"));

        Serial.print(F("<PLN,"));
        Serial.print(teganganPln);
        Serial.println(F(">"));
        Serial.print(F("<GENSET,"));
        Serial.print(teganganGenset);
        Serial.println(F(">"));
        Serial.print(F("<AKI,"));
        Serial.print(teganganAki);
        Serial.println(F(">"));

        Serial.print(F("<REM_SEC,"));
        Serial.print(sisaDetik);
        Serial.println(F(">"));
        Serial.print(F("<REM_MIN,"));
        Serial.print(sisaMenit);
        Serial.println(F(">"));
        Serial.print(F("<REM_HOUR,"));
        Serial.print(sisaJam);
        Serial.println(F(">"));

        Serial.print(F("<AUTO_MODE,"));
        Serial.print(autoMode);
        Serial.println(F(">"));

        Serial.print(F("<EMERGENCY,"));
        Serial.print(emergencyNotified);
        Serial.println(F(">"));

        Serial.print(F("<RTC_OK,"));
        Serial.print(rtcAvailable ? 1 : 0);
        Serial.println(F(">"));
    }
    else if (typeLen == 3 && strncmp(type, "RST", 3) == 0 && dataLen == 3 && strncmp(data, "rst", 3) == 0){
      emergencyNotified = false;
      gensetStartAttempts = 0;
    }
    else if (typeLen == 1 && type[0] == 'T') {
      unsigned long t = atol(data);
      if (t > 1700000000UL && t < 4100000000UL) {
        rtc.adjust(DateTime(t));
        rtcAvailable = true;
      }
    }
    else if (typeLen == 1 && type[0] == 'M') {
      lastMode = autoMode;
      if (dataLen == 4 && strncmp(data, "auto", 4) == 0) {
        autoMode = true;
      }
      else if (dataLen == 6 && strncmp(data, "manual", 6) == 0) {
        autoMode = false;
      }
    }

    else if (typeLen == 3 && strncmp(type, "SGM", 3) == 0){ // SGM = Start Genset Manually
      if (autoMode) { Serial.println(F("<SGM blocked autoMode=1>")); return; }
      if (gensetOnState == AWAL_ON && gensetOffState == AWAL_OFF){
        if (dataLen == 3 && strncmp(data, "off", 3) == 0){
          nowManualState = GENSET_OFF;
        }
        else if (dataLen == 2 && strncmp(data, "on", 2) == 0){
          nowManualState = GENSET_ON;// start_genset_manually
        }
      }
    }
  }
}

void do_lcd(){
  if (!lcdAvailable) return;
  wdt_reset();
  static int lastMenu = -1; static bool lastEmerg = false; static unsigned long lastBlink = 0;
  if (digitalRead(BTN_LEFT) == LOW) {
    if (millis() - debounce_left >= 100) { menu--; debounce_left = millis(); }
  } else if (digitalRead(BTN_RIGHT) == LOW) {
    if (millis() - debounce_right >= 100) { menu++; debounce_right = millis(); }
  }
  bool blink = (millis() / 1000) % 2;
  if (lastMenu==menu && lastEmerg==emergencyNotified && !blink) { /* throttle */ }
  lastMenu=menu; lastEmerg=emergencyNotified;
  lcd.clear();

  if (emergencyNotified == false){
    if (menu <= 0) {
      menu = 0;
      lcd.setCursor(0,0);
      lcd.print(F("STATE:"));
      lcd.setCursor(0, 1);
      lcd.print(stateToString(nowState));
    }
    else if (menu == 1) {
      lcd.setCursor(0, 0);
      lcd.print(F("PLN: "));
      lcd.setCursor(5, 0);
      lcd.print(teganganPln, 0);

      lcd.setCursor(8, 0);
      lcd.print(F("AKI: "));
      lcd.setCursor(13, 0);
      lcd.print(teganganAki, 0);

      lcd.setCursor(0, 1);
      lcd.print(F("GENSET: "));
      lcd.setCursor(8, 1);
      lcd.print(teganganGenset, 0);
    }
    else if (menu == 2) {
      
      lcd.setCursor(0, 0);
      lcd.print(F("Warmup Rem. Time"));

      char line2[17];

      long jamCap = sisaJam > 99 ? 99 : sisaJam;
      sprintf(line2, "%02ld:%02ld:%02ld", jamCap, sisaMenit, sisaDetik);
      lcd.setCursor(0, 1);
      lcd.print(line2);

    }
    else if (menu >= 3) {
      menu = 3;

      if (!rtcAvailable) {
        lcd.setCursor(0, 0);
        lcd.print(F("RTC offline"));
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
    if ((millis()/1000)%2==0){
      lcd.setCursor(2,0); lcd.print(F("EMERGENCY!"));
      lcd.setCursor(0,1); lcd.print(F("GENSET FAILURE!"));
    } else {
      lcd.setCursor(0,0); lcd.print(F("STATE:")); lcd.setCursor(0,1); lcd.print(stateToString(nowState));
    }
  }
}

void loop() {

  wdt_reset();

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

  isPlnOn = isPlnOn ? (teganganPln >= VAC_OFF) : (teganganPln >= VAC_ON);
  isGensetOn = isGensetOn ? (teganganGenset >= VAC_OFF) : (teganganGenset >= VAC_ON);
  isAkiOn = isAkiOn ? (teganganAki >= 11.5f) : (teganganAki >= 12.5f);

  while (Serial.available()) {
    char c = Serial.read();

    if (c == '<'){
      cmdBufferLen = 0;
      cmdBuffer[cmdBufferLen++] = c;
    }
    else if (c == '>') {
      if (cmdBufferLen < CMD_BUF_LEN) cmdBuffer[cmdBufferLen++] = c;
      cmdBuffer[cmdBufferLen] = '\0';
      processCommand(cmdBuffer);
      cmdBufferLen = 0;
    }
    else {
      if (cmdBufferLen < CMD_BUF_LEN) cmdBuffer[cmdBufferLen++] = c;
      else { serialOverflowCount++; Serial.print(F("<ERR,overflow,")); Serial.print(serialOverflowCount); Serial.println(F(">")); cmdBufferLen = 0; }
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
          if (rtcAvailable) { // persist at start to avoid retrigger on brownout
            DateTime n = rtc.now();
            DateTime nxt = getNextWarmup(n);
            unsigned long cur; EEPROM.get(0, cur);
            if (cur != nxt.unixtime()) saveNextWarmup(nxt);
          }
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
          Serial.println(F("<RESET_OK,Emergency direset, sistem kembali normal>"));
        }
        else if (emergencyNotified == true){
          Serial.println(F("EMERGENCY,Genset gagal start setelah 3x percobaan. Cek kondisi fisik & kirim RST,rst untuk reset"));
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

              // Warmup selesai: jadwalkan siklus mingguan berikutnya
              if (rtcAvailable) {
                DateTime now = rtc.now();
                nextWarmup = getNextWarmup(now);
                saveNextWarmup(nextWarmup);
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

      Serial.print(F("<State: "));
      Serial.print(stateToString(nowState));
      Serial.println(F(">"));

    }
  }
  else {
    Serial.print(F("<Manual Mode>"));

    if (lastMode == true){
      lastMode = autoMode;
      waktuGlobal_last2 = waktuGlobal;
      nowManualState = WAIT_COMMAND;

      gensetOnState = AWAL_ON;
      gensetOffState = AWAL_OFF;
      lepas_starter_genset();
    }

    if (nowManualState == WAIT_COMMAND){
      Serial.println(F("Waiting for command!"));
      waktuGlobal_last2 = waktuGlobal;
    }

    else if (nowManualState == GENSET_ON){
      if (gensetOnState == AWAL_ON){
        Serial.println(F("Memulai aktifkan genset!"));
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
        Serial.println(F("Memulai matikan genset!"));
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

const __FlashStringHelper* stateToString(State s) {
  switch (s) {
    case WAIT_AKI: return F("WAIT_AKI");
    case CHECK_WAIT_AKI: return F("CHECK_WAIT_AKI");
    case PLN: return F("PLN");
    case GENSET: return F("GENSET");
    case WAIT: return F("WAIT");
    case LONG_WAIT: return F("LONG_WAIT");
    case CHECK_WAIT: return F("CHECK_WAIT");
    case CHECK_LONG_WAIT: return F("CHECK_LONG_WAIT");
    case DELAY_AFTER_START_GENSET: return F("DELAY_AFTER_START_GENSET");
    case WAIT_GENSET: return F("WAIT_GENSET");
    case CHECK_WAIT_GENSET: return F("CHECK_WAIT_GENSET");
    case START_GENSET: return F("START_GENSET");
    case EMERGENCY_GENSET: return F("EMERGENCY_GENSET");
    default: return F("UNKNOWN");
  }
}

// fungsi untuk mencari modus - tie keep previous hasilWait
bool cariModus(bool arr[], int size) {
  int countTrue = 0;
  int countFalse = 0;
  for (int i = 0; i < size; i++) { if (arr[i]) countTrue++; else countFalse++; }
  if (countTrue > countFalse) return true;
  if (countFalse > countTrue) return false;
  return hasilWait; // tie keep previous
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
  double a = VAC.getRmsVoltage(); delay(10);
  double b = VAC.getRmsVoltage(); delay(10);
  double c = VAC.getRmsVoltage();
  // median 3
  if ((a <= b && b <= c) || (c <= b && b <= a)) return b;
  if ((b <= a && a <= c) || (c <= a && a <= b)) return a;
  return c;
}

double readVDC(int pin){
  int v1 = analogRead(pin); delay(10);
  int v2 = analogRead(pin); delay(10);
  int v3 = analogRead(pin);
  // median map
  int m;
  if ((v1 <= v2 && v2 <= v3) || (v3 <= v2 && v2 <= v1)) m = v2;
  else if ((v2 <= v1 && v1 <= v3) || (v3 <= v1 && v1 <= v2)) m = v1;
  else m = v3;
  double vdc = map(m, 0, 1023, 0, 2500);
  vdc /= 100;
  return vdc;
}

warmupCountdown getWarmupCountdown(){

  if (!rtcAvailable) {
    // Mode degradasi: warmup dianggap selesai, FSM langsung lanjut tanpa RTC
    return {0, 0, 0, 0};
  }

  long rem_sec_total = (long)nextWarmup.unixtime() - (long)nowTime.unixtime();

  if (rem_sec_total < 0) rem_sec_total = 0;

  long rem_hour = (rem_sec_total - (rem_sec_total % 3600)) / 3600;

  long hour_in_sec = rem_hour * 3600;

  long rem_sec = (rem_sec_total - hour_in_sec) % 60;

  long rem_min = ((rem_sec_total - hour_in_sec) - rem_sec) / 60;

  return {rem_sec_total, rem_sec, rem_min, rem_hour};
}

// Hitung kejadian WARMUP_DAY jam WARMUP_HOUR berikutnya yang > now
DateTime getNextWarmup(DateTime now) {
  DateTime candidate(now.year(), now.month(), now.day(), WARMUP_HOUR, 0, 0);

  int daysAhead = (WARMUP_DAY - candidate.dayOfTheWeek() + 7) % 7;
  candidate = candidate + TimeSpan(daysAhead, 0, 0, 0);

  if (candidate.unixtime() <= now.unixtime()) {
    candidate = candidate + TimeSpan(7, 0, 0, 0);
  }

  return candidate;
}

void saveNextWarmup(DateTime dt) {
  EEPROM.put(0, dt.unixtime());
}

bool loadNextWarmup() {
  unsigned long savedTime;
  EEPROM.get(0, savedTime);
  if (savedTime > 1700000000UL) {
    if (rtcAvailable) {
      unsigned long now = rtc.now().unixtime();
      if (savedTime < now + 8UL*86400UL && savedTime > now - 86400UL) {
        nextWarmup = DateTime(savedTime);
        return true;
      }
    } else {
      nextWarmup = DateTime(savedTime);
      return true;
    }
  }
  return false;
}
