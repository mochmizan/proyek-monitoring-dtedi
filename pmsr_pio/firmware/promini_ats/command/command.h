#ifndef COMMAND_H
#define COMMAND_H

#include <Arduino.h>

// ============================================================
// JENIS AKSI COMMAND
// ============================================================

enum CommandAction {
    CMD_NONE,
    CMD_RESET_EMERGENCY,
    CMD_SET_TIME,
    CMD_SET_AUTO,
    CMD_SET_MANUAL,
    CMD_GENSET_ON,
    CMD_GENSET_OFF
};

// ============================================================
// DATA YANG DIKIRIM KE COMMAND MODULE
// ============================================================

struct CommandStatus {

    const __FlashStringHelper* state;

    double teganganPln;
    double teganganGenset;
    double teganganAki;

    long sisaDetik;
    long sisaMenit;
    long sisaJam;

    bool autoMode;
    bool emergencyNotified;
    bool rtcAvailable;

    bool gensetOnReady;
    bool gensetOffReady;
};

// ============================================================
// HASIL PARSING COMMAND
// ============================================================

struct CommandResult {

    CommandAction action;

    unsigned long unixTime;

    bool valid;
};

// ============================================================
// INIT
// ============================================================

void commandInit();

// ============================================================
// PROCESS SERIAL
// ============================================================

CommandResult commandTask(const CommandStatus& status);

#endif