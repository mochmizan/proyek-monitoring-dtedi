#ifndef RTC_MODULE_H
#define RTC_MODULE_H

#include <Arduino.h>
#include <RTClib.h>

// ============================================================
// DATA STRUCTURE
// ============================================================

struct WarmupCountdown {
    long remSecTotal;
    long remSec;
    long remMin;
    long remHour;
};

// ============================================================
// RTC
// ============================================================

bool rtcInit();
void rtcTask();

bool isRtcAvailable();
DateTime getRtcNow();

bool setRtcUnixTime(unsigned long unixTime);

// ============================================================
// WARMUP
// ============================================================

WarmupCountdown getWarmupCountdown();

DateTime getNextWarmup();

void scheduleNextWarmup();

#endif