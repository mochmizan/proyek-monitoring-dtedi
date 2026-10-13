#include "lcd.h"

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <avr/wdt.h>

const int BTN_LEFT = 7;
const int BTN_RIGHT = 8;

LiquidCrystal_I2C lcd(0x27, 16, 2);

bool lcdAvailable = false;

static int menu = 0;

static unsigned long debounce_left = 0;
static unsigned long debounce_right = 0;


// ============================================================
// LCD INIT
// ============================================================

void lcdInit() {

    pinMode(BTN_LEFT, INPUT_PULLUP);
    pinMode(BTN_RIGHT, INPUT_PULLUP);

    Wire.beginTransmission(0x27);
    lcdAvailable = (Wire.endTransmission() == 0);

    if (lcdAvailable) {

        lcd.init();
        lcd.backlight();

        lcd.setCursor(0, 0);
        lcd.print(F("Hello World!"));
    }
}


// ============================================================
// LCD TASK
// ============================================================

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
) {

    if (!lcdAvailable) {
        return;
    }

    wdt_reset();

    // ========================================================
    // BUTTON
    // ========================================================

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


    // ========================================================
    // EMERGENCY BLINK
    // ========================================================

    bool blink = (millis() / 1000) % 2;


    // ========================================================
    // DISPLAY
    // ========================================================

    lcd.clear();


    // ========================================================
    // NORMAL MODE
    // ========================================================

    if (!emergencyNotified) {

        // ----------------------------------------------------
        // MENU 0
        // ----------------------------------------------------

        if (menu <= 0) {

            menu = 0;

            lcd.setCursor(0, 0);
            lcd.print(F("STATE:"));

            lcd.setCursor(0, 1);
            lcd.print(state);
        }


        // ----------------------------------------------------
        // MENU 1
        // ----------------------------------------------------

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


        // ----------------------------------------------------
        // MENU 2
        // ----------------------------------------------------

        else if (menu == 2) {

            lcd.setCursor(0, 0);
            lcd.print(F("Warmup Rem. Time"));

            char line2[17];

            long jamCap = sisaJam > 99 ? 99 : sisaJam;

            sprintf(
                line2,
                "%02ld:%02ld:%02ld",
                jamCap,
                sisaMenit,
                sisaDetik
            );

            lcd.setCursor(0, 1);
            lcd.print(line2);
        }


        // ----------------------------------------------------
        // MENU 3
        // ----------------------------------------------------

        else if (menu >= 3) {

            menu = 3;

            if (!rtcAvailable) {

                lcd.setCursor(0, 0);
                lcd.print(F("RTC offline"));
            }

            else {

                char line1[17];
                char line2[17];

                sprintf(
                    line1,
                    "D:%02d/%02d/%02d",
                    nowTime.day(),
                    nowTime.month(),
                    nowTime.year() % 100
                );

                sprintf(
                    line2,
                    "T:%02d:%02d:%02d",
                    nowTime.hour(),
                    nowTime.minute(),
                    nowTime.second()
                );

                lcd.setCursor(0, 0);
                lcd.print(line1);

                lcd.setCursor(0, 1);
                lcd.print(line2);
            }
        }
    }


    // ========================================================
    // EMERGENCY MODE
    // ========================================================

    else {

        if (blink) {

            lcd.setCursor(2, 0);
            lcd.print(F("EMERGENCY!"));

            lcd.setCursor(0, 1);
            lcd.print(F("GENSET FAILURE!"));
        }

        else {

            lcd.setCursor(0, 0);
            lcd.print(F("STATE:"));

            lcd.setCursor(0, 1);
            lcd.print(state);
        }
    }
}