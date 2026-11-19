#ifndef ACTUATOR_H
#define ACTUATOR_H

#include <Arduino.h>

void actuatorInit();

void nyalakan_genset();
void matikan_genset();

void mulai_starter_genset();
void lepas_starter_genset();

void nyalakan_lampu_emergency();
void matikan_lampu_emergency();

#endif