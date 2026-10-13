#include "command.h"

#include <string.h>
#include <stdlib.h>

// ============================================================
// CONFIGURATION
// ============================================================

const int CMD_BUF_LEN = 64;

// ============================================================
// INTERNAL STATE
// ============================================================

static char cmdBuffer[CMD_BUF_LEN + 1];
static int cmdBufferLen = 0;
static unsigned long serialOverflowCount = 0;

// ============================================================
// INIT
// ============================================================

void commandInit() {

    cmdBufferLen = 0;
    cmdBuffer[0] = '\0';
}

// ============================================================
// GET COMMAND RESPONSE
// ============================================================

static void sendStatus(const CommandStatus& status) {

    Serial.print(F("<STATE,"));
    Serial.print(status.state);
    Serial.println(F(">"));

    Serial.print(F("<PLN,"));
    Serial.print(status.teganganPln);
    Serial.println(F(">"));

    Serial.print(F("<GENSET,"));
    Serial.print(status.teganganGenset);
    Serial.println(F(">"));

    Serial.print(F("<AKI,"));
    Serial.print(status.teganganAki);
    Serial.println(F(">"));

    Serial.print(F("<REM_SEC,"));
    Serial.print(status.sisaDetik);
    Serial.println(F(">"));

    Serial.print(F("<REM_MIN,"));
    Serial.print(status.sisaMenit);
    Serial.println(F(">"));

    Serial.print(F("<REM_HOUR,"));
    Serial.print(status.sisaJam);
    Serial.println(F(">"));

    Serial.print(F("<AUTO_MODE,"));
    Serial.print(status.autoMode);
    Serial.println(F(">"));

    Serial.print(F("<EMERGENCY,"));
    Serial.print(status.emergencyNotified);
    Serial.println(F(">"));

    Serial.print(F("<RTC_OK,"));
    Serial.print(status.rtcAvailable ? 1 : 0);
    Serial.println(F(">"));
}

// ============================================================
// PARSE ONE COMPLETE COMMAND
// ============================================================

static CommandResult processCommand(
    const char* msg,
    const CommandStatus& status
) {

    CommandResult result;

    result.action = CMD_NONE;
    result.unixTime = 0;
    result.valid = false;

    const char* comma = strchr(msg, ',');
    const char* end = strchr(msg, '>');

    if (comma == NULL || end == NULL) {
        return result;
    }

    int typeLen = comma - msg - 1;
    int dataLen = end - comma - 1;

    const char* type = msg + 1;
    const char* data = comma + 1;

    // ========================================================
    // <C,GET>
    // ========================================================

    if (
        typeLen == 1 &&
        type[0] == 'C' &&
        dataLen == 3 &&
        strncmp(data, "GET", 3) == 0
    ) {

        sendStatus(status);

        result.valid = true;
        return result;
    }

    // ========================================================
    // <RST,rst>
    // ========================================================

    else if (
        typeLen == 3 &&
        strncmp(type, "RST", 3) == 0 &&
        dataLen == 3 &&
        strncmp(data, "rst", 3) == 0
    ) {

        result.action = CMD_RESET_EMERGENCY;
        result.valid = true;

        return result;
    }

    // ========================================================
    // <T,UNIX_TIME>
    // ========================================================

    else if (
        typeLen == 1 &&
        type[0] == 'T'
    ) {

        unsigned long t = atol(data);

        if (
            t > 1700000000UL &&
            t < 4100000000UL
        ) {

            result.action = CMD_SET_TIME;
            result.unixTime = t;
            result.valid = true;
        }

        return result;
    }

    // ========================================================
    // <M,auto>
    // <M,manual>
    // ========================================================

    else if (
        typeLen == 1 &&
        type[0] == 'M'
    ) {

        if (
            dataLen == 4 &&
            strncmp(data, "auto", 4) == 0
        ) {

            result.action = CMD_SET_AUTO;
            result.valid = true;
        }

        else if (
            dataLen == 6 &&
            strncmp(data, "manual", 6) == 0
        ) {

            result.action = CMD_SET_MANUAL;
            result.valid = true;
        }

        return result;
    }

    // ========================================================
    // <SGM,on>
    // <SGM,off>
    // ========================================================

    else if (
        typeLen == 3 &&
        strncmp(type, "SGM", 3) == 0
    ) {

        if (
            status.autoMode
        ) {

            Serial.println(
                F("<SGM blocked autoMode=1>")
            );

            return result;
        }

        if (
            !status.gensetOnReady ||
            !status.gensetOffReady
        ) {

            return result;
        }

        if (
            dataLen == 2 &&
            strncmp(data, "on", 2) == 0
        ) {

            result.action = CMD_GENSET_ON;
            result.valid = true;
        }

        else if (
            dataLen == 3 &&
            strncmp(data, "off", 3) == 0
        ) {

            result.action = CMD_GENSET_OFF;
            result.valid = true;
        }

        return result;
    }

    return result;
}

// ============================================================
// COMMAND TASK
// ============================================================

CommandResult commandTask(
    const CommandStatus& status
) {

    CommandResult result;

    result.action = CMD_NONE;
    result.unixTime = 0;
    result.valid = false;

    while (Serial.available()) {

        char c = Serial.read();

        // ----------------------------------------------------
        // START COMMAND
        // ----------------------------------------------------

        if (c == '<') {

            cmdBufferLen = 0;

            cmdBuffer[cmdBufferLen++] = c;
        }

        // ----------------------------------------------------
        // END COMMAND
        // ----------------------------------------------------

        else if (c == '>') {

            if (cmdBufferLen < CMD_BUF_LEN) {

                cmdBuffer[cmdBufferLen++] = c;
            }

            cmdBuffer[cmdBufferLen] = '\0';

            result = processCommand(
                cmdBuffer,
                status
            );

            cmdBufferLen = 0;

            // Satu command diproses per pemanggilan
            return result;
        }

        // ----------------------------------------------------
        // NORMAL DATA
        // ----------------------------------------------------

        else {

            if (cmdBufferLen < CMD_BUF_LEN) {

                cmdBuffer[cmdBufferLen++] = c;
            }

            else {

                serialOverflowCount++;

                Serial.print(F("<ERR,overflow,"));
                Serial.print(serialOverflowCount);
                Serial.println(F(">"));

                cmdBufferLen = 0;
            }
        }
    }

    return result;
}