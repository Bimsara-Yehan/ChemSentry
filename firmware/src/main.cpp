#include <Arduino.h>
#include <Wire.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>

// Pin Definitions
#define DHTPIN 4           // GPIO 4 for DHT22 Data
#define DHTTYPE DHT22      // DHT 22 (AM2302)
#define MQ135_PIN 34       // GPIO 34 (ADC1 Pin, input-only safe)

// Initialize Peripherals
DHT dht(DHTPIN, DHTTYPE);
// 16x2 I2C display at I2C address 0x27 (use 0x3F if display stays blank)
LiquidCrystal_I2C lcd(0x27, 16, 2);

void setup() {
  Serial.begin(115200);
  Serial.println(F("ChemSentry IoT Node Initializing..."));

  // Initialize Wire / I2C (SDA=21, SCL=22 default on ESP32)
  Wire.begin(21, 22);

  // Initialize LCD
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ChemSentry IoT");
  lcd.setCursor(0, 1);
  lcd.print("Warming up...");

  // Initialize DHT Sensor
  dht.begin();

  // Configure Analog Read resolution (12-bit, 0-4095)
  analogReadResolution(12);

  delay(2000); // Sensor warmup pause
}

void loop() {
  // Read Temperature & Humidity from DHT22
  float humidity = dht.readHumidity();
  float tempC = dht.readTemperature();

  // Read Raw Analog Value from MQ-135 Gas Sensor
  int rawGas = analogRead(MQ135_PIN);
  float gasVoltage = (rawGas / 4095.0) * 3.3; // Convert ADC value to voltage

  // Simple PPM estimation based on baseline calibration ratio
  float gasPPM = map(rawGas, 0, 4095, 10, 1000); 

  // Print readings to Serial Monitor
  Serial.print("Temp: "); Serial.print(tempC, 1); Serial.print(" C | ");
  Serial.print("Hum: "); Serial.print(humidity, 1); Serial.print(" % | ");
  Serial.print("Gas Raw: "); Serial.print(rawGas); Serial.print(" ("); Serial.print(gasVoltage, 2); Serial.println("V)");

  // Render to 16x2 LCD Display
  lcd.clear();
  if (isnan(humidity) || isnan(tempC)) {
    lcd.setCursor(0, 0);
    lcd.print("DHT22 Error!");
  } else {
    lcd.setCursor(0, 0);
    lcd.print("T:"); lcd.print(tempC, 1); lcd.print("C ");
    lcd.print("H:"); lcd.print(humidity, 1); lcd.print("%");
  }

  lcd.setCursor(0, 1);
  lcd.print("Gas:"); lcd.print(rawGas);
  if (rawGas > 1500) {
    lcd.print(" [ALERT]");
  } else {
    lcd.print(" [SAFE]");
  }

  delay(2000); // Refresh interval
}

