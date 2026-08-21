#include <Arduino.h>

const int LED = LED_BUILTIN;

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
  Serial.println("PlatformIO ESP32 blink test");
}

void loop() {
  digitalWrite(LED, HIGH);
  delay(500);
  digitalWrite(LED, LOW);
  delay(500);
}
