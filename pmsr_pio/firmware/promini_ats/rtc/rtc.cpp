#include "rtc.h"

#include <Wire.h>
#include <EEPROM.h>

// ============================================================
// KONFIGURASI WARMUP
// ============================================================

const int WARMUP_DAY = 0;       // 0 = Sunday
const int WARMUP_HOUR = 18;

// ============================================================
// INTERNAL RTC STATE
// ============================================================

static RTC_DS3231 rtc;

static DateTime nowTime;
static DateTime nextWarmup;

static bool rtcAvailable = false;

// ============================================================
// INTERNAL FUNCTION PROTOTYPES
// ============================================================

static DateTime calculateNextWarmup(DateTime now);
static void saveNextWarmup(DateTime dt);
static bool loadNextWarmup();

// ============================================================
// RTC INIT
// ============================================================

bool rtcInit() {

    if (!rtc.begin()) {

        rtcAvailable = false;

        Serial.println(
            F("<RTC tidak ditemukan! Mode degradasi: "
              "warmup countdown nonaktif, FSM tetap jalan>")
        );

        return false;
    }

    rtcAvailable = true;

    // --------------------------------------------------------
    // RTC kehilangan power
    // --------------------------------------------------------

    if (rtc.lostPower()) {

        Serial.println(
            F("<RTC kehilangan power, set waktu!>")
        );

        rtc.adjust(
            DateTime(F(__DATE__), F(__TIME__))
        );
    }

    // --------------------------------------------------------
    // Load jadwal warmup dari EEPROM
    // --------------------------------------------------------

    if (!loadNextWarmup()) {

        nextWarmup = calculateNextWarmup(rtc.now());

        saveNextWarmup(nextWarmup);

        Serial.println(
            F("<Data EEPROM kosong / invalid, "
              "jadwal warmup awal disimpan>")
        );
    }
    else {

        Serial.println(
            F("<Jadwal warmup berhasil dimuat>")
        );
    }

    nowTime = rtc.now();

    return true;
}

// ============================================================
// RTC TASK
// ============================================================

void rtcTask() {

    if (!rtcAvailable) {
        return;
    }

    nowTime = rtc.now();
}

// ============================================================
// RTC STATUS
// ============================================================

bool isRtcAvailable() {
    return rtcAvailable;
}

// ============================================================
// GET CURRENT TIME
// ============================================================

DateTime getRtcNow() {
    return nowTime;
}

// ============================================================
// SET RTC USING UNIX TIME
// ============================================================

bool setRtcUnixTime(unsigned long unixTime) {

    if (!rtcAvailable) {
        return false;
    }

    rtc.adjust(DateTime(unixTime));

    nowTime = rtc.now();

    return true;
}

// ============================================================
// WARMUP COUNTDOWN
// ============================================================

WarmupCountdown getWarmupCountdown() {

    if (!rtcAvailable) {

        // Mode degradasi:
        // warmup dianggap sudah selesai
        return {0, 0, 0, 0};
    }

    long remSecTotal =
        (long)nextWarmup.unixtime()
        - (long)nowTime.unixtime();

    if (remSecTotal < 0) {
        remSecTotal = 0;
    }

    long remHour =
        (remSecTotal - (remSecTotal % 3600))
        / 3600;

    long hourInSec =
        remHour * 3600;

    long remSec =
        (remSecTotal - hourInSec) % 60;

    long remMin =
        ((remSecTotal - hourInSec) - remSec)
        / 60;

    return {
        remSecTotal,
        remSec,
        remMin,
        remHour
    };
}

// ============================================================
// GET NEXT WARMUP
// ============================================================

DateTime getNextWarmup() {
    return nextWarmup;
}

// ============================================================
// SCHEDULE NEXT WARMUP
// ============================================================

void scheduleNextWarmup() {

    if (!rtcAvailable) {
        return;
    }

    nextWarmup = calculateNextWarmup(nowTime);

    saveNextWarmup(nextWarmup);
}

// ============================================================
// CALCULATE NEXT WARMUP
// ============================================================

static DateTime calculateNextWarmup(DateTime now) {

    DateTime candidate(
        now.year(),
        now.month(),
        now.day(),
        WARMUP_HOUR,
        0,
        0
    );

    int daysAhead =
        (WARMUP_DAY
         - candidate.dayOfTheWeek()
         + 7) % 7;

    candidate =
        candidate
        + TimeSpan(daysAhead, 0, 0, 0);

    if (candidate.unixtime() <= now.unixtime()) {

        candidate =
            candidate
            + TimeSpan(7, 0, 0, 0);
    }

    return candidate;
}

// ============================================================
// SAVE NEXT WARMUP
// ============================================================

static void saveNextWarmup(DateTime dt) {

    EEPROM.put(
        0,
        dt.unixtime()
    );
}

// ============================================================
// LOAD NEXT WARMUP
// ============================================================

static bool loadNextWarmup() {

    unsigned long savedTime;

    EEPROM.get(
        0,
        savedTime
    );

    if (savedTime > 1700000000UL) {

        if (rtcAvailable) {

            unsigned long now =
                rtc.now().unixtime();

            if (
                savedTime < now + 8UL * 86400UL
                &&
                savedTime > now - 86400UL
            ) {

                nextWarmup =
                    DateTime(savedTime);

                return true;
            }
        }
    }

    return false;
}