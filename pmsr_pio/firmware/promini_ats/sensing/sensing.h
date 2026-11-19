#ifndef SENSING_H
#define SENSING_H

struct SensingData
{
    double pln;
    double genset;
    double aki;

    bool plnOn;
    bool gensetOn;
    bool akiOn;
};

void sensingInit();
void sensingTask();

const SensingData& getSensingData();

#endif