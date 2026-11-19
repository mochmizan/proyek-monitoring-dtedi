#include "sensing/sensing.h"
#include "lcd/lcd.h"
#include "command/command.h"
#include "actuator/actuator.h"
#include <Wire.h>
#include "rtc/rtc.h"
#include <avr/wdt.h>

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

bool autoMode = true;
bool lastMode = autoMode;
bool hasilWait = false;
bool isWarmup = false;
bool warmupStarted = false;
bool rtcAvailable = false;
unsigned int relayOrder = 0;

long sisaDetik = 0;
long sisaMenit = 0;
long sisaJam = 0;

double teganganPln = 0;
double teganganGenset = 0;
double teganganAki = 0;

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

// ==================== FUNCTION PROTOTYPES ====================

void wait_next_genset_on_state(unsigned long waktuGlobal, gensetOnFSM state);
void wait_next_genset_off_state(unsigned long waktuGlobal, gensetOffFSM state);

const __FlashStringHelper* stateToString(State s);

bool cariModus(bool arr[], int size);
bool checkVolt(double volt, double batas);

// =================================================================

void setup() {
  MCUSR = 0;
  wdt_disable();
  wdt_reset();

  Serial.begin(9600);
  commandInit();

  Wire.begin();

  lcdInit();

  // Relay glitch-safe: drive HIGH before OUTPUT

  actuatorInit();

  sensingInit();

  rtcAvailable = rtcInit();

  wdt_reset();
  delay(1000);
  wdt_reset();
  wdt_enable(WDTO_8S);
}


void loop() {

  wdt_reset();

  rtcTask();

  WarmupCountdown countdown = getWarmupCountdown();

  sisaDetik = countdown.remSec;
  sisaMenit = countdown.remMin;
  sisaJam = countdown.remHour;

  sensingTask();

  const SensingData& sensing = getSensingData();

  teganganPln = sensing.pln;
  teganganGenset = sensing.genset;
  teganganAki = sensing.aki;

  bool isPlnOn = sensing.plnOn;
  bool isGensetOn = sensing.gensetOn;
  bool isAkiOn = sensing.akiOn;

  CommandStatus commandStatus = {
    stateToString(nowState),
    teganganPln,
    teganganGenset,
    teganganAki,
    sisaDetik,
    sisaMenit,
    sisaJam,
    autoMode,
    emergencyNotified,
    rtcAvailable,
    gensetOnState == AWAL_ON,
    gensetOffState == AWAL_OFF
  };

  CommandResult commandResult = commandTask(commandStatus);

  switch (commandResult.action) {

    case CMD_RESET_EMERGENCY:

        emergencyNotified = false;
        gensetStartAttempts = 0;

        break;


    case CMD_SET_TIME:

        if (setRtcUnixTime(commandResult.unixTime)) {
            rtcAvailable = true;
        }

        break;


    case CMD_SET_AUTO:

        lastMode = autoMode;
        autoMode = true;

        break;


    case CMD_SET_MANUAL:

        lastMode = autoMode;
        autoMode = false;

        break;


    case CMD_GENSET_ON:

        nowManualState = GENSET_ON;

        break;


    case CMD_GENSET_OFF:

        nowManualState = GENSET_OFF;

        break;


    case CMD_NONE:
    default:

        break;
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
          if (rtcAvailable) {
            scheduleNextWarmup();
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
                scheduleNextWarmup();
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

  lcdTask(
    stateToString(nowState),
    teganganPln,
    teganganGenset,
    teganganAki,
    sisaJam,
    sisaMenit,
    sisaDetik,
    emergencyNotified,
    rtcAvailable,
    getRtcNow()
  );
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
