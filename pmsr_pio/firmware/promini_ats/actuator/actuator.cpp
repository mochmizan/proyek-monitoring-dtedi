#include "actuator.h"

static const int relay1 = 4;
static const int relay2 = 5;
static const int emergencyGensetPin = 2;

void actuatorInit() {
    // Relay glitch-safe: drive HIGH before OUTPUT
    digitalWrite(emergencyGensetPin, HIGH);
    digitalWrite(relay1, HIGH);
    digitalWrite(relay2, HIGH);

    pinMode(emergencyGensetPin, OUTPUT);
    pinMode(relay1, OUTPUT);
    pinMode(relay2, OUTPUT);

    matikan_genset();
    lepas_starter_genset();
    matikan_lampu_emergency();
}

void nyalakan_genset() {
    digitalWrite(relay1, LOW);
}

void matikan_genset() {
    digitalWrite(relay1, HIGH);
}

void mulai_starter_genset() {
    digitalWrite(relay2, LOW);
}

void lepas_starter_genset() {
    digitalWrite(relay2, HIGH);
}

void nyalakan_lampu_emergency() {
    digitalWrite(emergencyGensetPin, LOW);
}

void matikan_lampu_emergency() {
    digitalWrite(emergencyGensetPin, HIGH);
}