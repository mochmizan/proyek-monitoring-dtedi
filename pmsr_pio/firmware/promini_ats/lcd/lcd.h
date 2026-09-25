#ifndef LCD_H
#define LCD_H

#include <Arduino.h>
#include <RTClib.h>

void lcdInit();

void lcdTask(
    const __FlashStringHelper* state,
    double teganganPln,
    double teganganGenset,
    double teganganAki,
    long sisaJam,
    long sisaMenit,
    long sisaDetik,
    bool emergencyNotified,
    bool rtcAvailable,
    const DateTime& nowTime
);

#endif