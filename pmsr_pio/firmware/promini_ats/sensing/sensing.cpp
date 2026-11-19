#include "sensing.h"

#include <Arduino.h>
#include <ZMPT101B.h>

#define SENSITIVITAS_SENSOR_AC 500.0f

#define VAC_ON 210.0f
#define VAC_OFF 190.0f

#define AKI_ON 12.5f
#define AKI_OFF 11.5f

namespace
{
    const int PLN_PIN = A1;
    const int GENSET_PIN = A0;
    const int AKI_PIN = A2;

    ZMPT101B sensorPLN(PLN_PIN, 50.0);
    ZMPT101B sensorGenset(GENSET_PIN, 50.0);

    SensingData data = {
        0.0,
        0.0,
        0.0,
        false,
        false,
        false
    };

    double readVAC(ZMPT101B &VAC)
    {
        double a = VAC.getRmsVoltage();
        delay(10);

        double b = VAC.getRmsVoltage();
        delay(10);

        double c = VAC.getRmsVoltage();

        // Median 3
        if ((a <= b && b <= c) || (c <= b && b <= a))
            return b;

        if ((b <= a && a <= c) || (c <= a && a <= b))
            return a;

        return c;
    }

    double readVDC(int pin)
    {
        int v1 = analogRead(pin);
        delay(10);

        int v2 = analogRead(pin);
        delay(10);

        int v3 = analogRead(pin);

        // Median 3
        int m;

        if ((v1 <= v2 && v2 <= v3) || (v3 <= v2 && v2 <= v1))
            m = v2;
        else if ((v2 <= v1 && v1 <= v3) || (v3 <= v1 && v1 <= v2))
            m = v1;
        else
            m = v3;

        double vdc = map(m, 0, 1023, 0, 2500);
        vdc /= 100.0;

        return vdc;
    }
}

void sensingInit()
{
    sensorPLN.setSensitivity(SENSITIVITAS_SENSOR_AC);
    sensorGenset.setSensitivity(SENSITIVITAS_SENSOR_AC);
}

void sensingTask()
{
    data.pln = readVAC(sensorPLN);
    data.genset = readVAC(sensorGenset);
    data.aki = readVDC(AKI_PIN);

    // Hysteresis PLN
    data.plnOn =
        data.plnOn
            ? (data.pln >= VAC_OFF)
            : (data.pln >= VAC_ON);

    // Hysteresis genset
    data.gensetOn =
        data.gensetOn
            ? (data.genset >= VAC_OFF)
            : (data.genset >= VAC_ON);

    // Hysteresis aki
    data.akiOn =
        data.akiOn
            ? (data.aki >= AKI_OFF)
            : (data.aki >= AKI_ON);
}

const SensingData& getSensingData()
{
    return data;
}