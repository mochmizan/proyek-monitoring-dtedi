#include <Arduino.h>

#define INPUT_PIN D1

void setup()
{
    Serial.begin(115200);
    delay(500);

    pinMode(INPUT_PIN, INPUT);

    Serial.println();
    Serial.println("=== Digital Input Test ===");
}

void loop()
{
    int inputState = digitalRead(INPUT_PIN);

    Serial.print("Input D1 = ");

    if (inputState == HIGH)
    {
        Serial.println("HIGH");
    }
    else
    {
        Serial.println("LOW");
    }

    delay(500);
}