#include <Arduino.h>
#include <Wire.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <time.h>

// WiFi creds, broker address, and TLS material live in secrets.h, which is
// gitignored (see .gitignore) precisely so a `git add` of this file can
// never push a real private key -- see firmware/src/secrets.example.h for
// the template and how to regenerate it. This #include intentionally fails
// the build if secrets.h hasn't been created yet, by design.
#include "secrets.h"

// Pin Definitions
#define DHTPIN 4           // GPIO 4 for DHT22 Data
#define DHTTYPE DHT22      // DHT 22 (AM2302)
#define MQ135_PIN 34       // GPIO 34 (ADC1 Pin, input-only safe)

const char *WIFI_SSID = SECRET_WIFI_SSID;
const char *WIFI_PASSWORD = SECRET_WIFI_PASSWORD;
const char *MQTT_HOST = SECRET_MQTT_HOST;
const uint16_t MQTT_PORT = SECRET_MQTT_PORT;

// This device belongs to Zone_C (Oxidizer Storage) -- see
// agents/agent_c_environment/zone_inventory.py. Zone_C is deliberately the
// only zone with a chemical (Hydrogen peroxide solution) that has a real
// extracted numeric storage-temperature range in this project's corpus, so
// it is the only zone where a live reading can produce a genuine SAFE/WARNING
// rather than an honest UNKNOWN.
// Set per device in secrets.h. The fallback keeps a secrets.h written before
// SECRET_ZONE_ID existed compiling, with the zone this firmware always used.
#ifndef SECRET_ZONE_ID
#define SECRET_ZONE_ID "Zone_C"
#endif
const char *ZONE_ID = SECRET_ZONE_ID;

// Topic scheme fixed by agents/agent_c_environment/mqtt_subscriber.py:
// chemsentry/sensors/<zone_id>/reading -- must match exactly, Agent C parses
// the zone_id out of both the topic and the payload. Joined at compile time
// (adjacent string literals), so no heap String is built at startup.
const char *MQTT_TOPIC = "chemsentry/sensors/" SECRET_ZONE_ID "/reading";

// TLS material (see secrets.h) mirrors exactly what
// agents/agent_c_environment/mqtt_subscriber.py and
// simulator/telemetry_simulator.py pass to paho-mqtt's tls_set(): the CA cert
// to verify the broker, plus this device's own cert+key, because
// firmware/mosquitto.conf sets `require_certificate true` (mutual TLS) --
// there is no plaintext or server-only-TLS fallback path.
static const char *CA_CERT = SECRET_CA_CERT;
static const char *CLIENT_CERT = SECRET_CLIENT_CERT;
static const char *CLIENT_KEY = SECRET_CLIENT_KEY;

// Initialize Peripherals
DHT dht(DHTPIN, DHTTYPE);
// 16x2 I2C display at I2C address 0x27 (use 0x3F if display stays blank)
LiquidCrystal_I2C lcd(0x27, 16, 2);

WiFiClientSecure tlsClient;
PubSubClient mqttClient(tlsClient);
String deviceId;  // set from WiFi MAC once connected -- stable per device

const unsigned long PUBLISH_INTERVAL_MS = 5000;
unsigned long lastPublishMs = 0;

void connectWiFi() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi");
  Serial.print("Connecting to WiFi ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi connected, IP: ");
  Serial.println(WiFi.localIP());

  deviceId = WiFi.macAddress();  // e.g. "AA:BB:CC:DD:EE:FF" -- matches
                                  // api.models.SensorReading's device_id
                                  // comment ("ESP32 MAC or name")

  lcd.setCursor(0, 1);
  lcd.print(WiFi.localIP());
}

void syncTime() {
  // SensorReading.timestamp must be a real datetime -- the ESP32 has no
  // battery-backed RTC, so without NTP every reading would carry a bogus
  // 1970 timestamp. gmtime()/strftime() below format it as UTC ("Z"),
  // matching what api.models.SensorReading (a Pydantic datetime field)
  // and the rest of the pipeline expect from telemetry_simulator.py.
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.print("Syncing time via NTP");
  time_t now = time(nullptr);
  int attempts = 0;
  while (now < 8 * 3600 * 2 && attempts < 20) {  // wait for a plausible epoch
    delay(500);
    Serial.print(".");
    now = time(nullptr);
    attempts++;
  }
  Serial.println();
  if (now < 8 * 3600 * 2) {
    Serial.println("WARNING: NTP sync failed; timestamps will be wrong.");
  } else {
    Serial.print("Time synced: ");
    Serial.println(now);
  }
}

void connectMqtt() {
  tlsClient.setCACert(CA_CERT);
  tlsClient.setCertificate(CLIENT_CERT);
  tlsClient.setPrivateKey(CLIENT_KEY);
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  // PubSubClient's default 256-byte buffer covers topic + JSON payload +
  // MQTT framing here with only ~60 bytes to spare; a longer device_id or
  // topic would silently fail to publish. 512 gives real headroom.
  mqttClient.setBufferSize(512);

  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT broker ");
    Serial.print(MQTT_HOST);
    Serial.print(":");
    Serial.print(MQTT_PORT);
    Serial.print(" ... ");

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Connecting MQTT");

    // client_id must be unique per device on the broker; MAC-derived so two
    // nodes never collide.
    String clientId = "chemsentry-" + deviceId;
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected.");
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 2s");
      delay(2000);
    }
  }
}

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

  connectWiFi();
  syncTime();
  connectMqtt();
}

void loop() {
  mqttClient.loop();
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqttClient.connected()) {
    connectMqtt();
  }

  // Read Temperature & Humidity from DHT22
  float humidity = dht.readHumidity();
  float tempC = dht.readTemperature();

  // Read Raw Analog Value from MQ-135 Gas Sensor
  int rawGas = analogRead(MQ135_PIN);
  float gasVoltage = (rawGas / 4095.0) * 3.3; // Convert ADC value to voltage

  // Print readings to Serial Monitor
  Serial.print("Temp: "); Serial.print(tempC, 1); Serial.print(" C | ");
  Serial.print("Hum: "); Serial.print(humidity, 1); Serial.print(" % | ");
  Serial.print("Gas Raw: "); Serial.print(rawGas); Serial.print(" ("); Serial.print(gasVoltage, 2); Serial.println("V)");

  // Render to 16x2 LCD Display. Deliberately no local SAFE/ALERT judgement
  // here (a prior version compared rawGas against a hardcoded 1500 and
  // printed its own verdict) -- CLAUDE.md's central principle is that no
  // safety threshold is ever hardcoded and no safety state is decided
  // outside the deterministic layer. This node's only job is to report raw
  // readings; Zone_C's real SAFE/WARNING/UNKNOWN state comes back from
  // Agent C's real retrieval + safety evaluation, visible in the UI/API,
  // not on this display.
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
  lcd.print(mqttClient.connected() ? " MQTT:OK" : " MQTT:--");

  unsigned long nowMs = millis();
  if (nowMs - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    lastPublishMs = nowMs;

    if (isnan(humidity) || isnan(tempC)) {
      Serial.println("Skipping publish: invalid DHT22 reading.");
    } else {
      time_t now = time(nullptr);
      struct tm timeinfo;
      gmtime_r(&now, &timeinfo);
      char timestamp[25];
      strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

      // Field names/shape must match api.models.SensorReading exactly --
      // agents/agent_c_environment/mqtt_subscriber.py's parse_reading()
      // constructs a SensorReading straight from this JSON and drops the
      // message if it doesn't validate.
      char payload[256];
      snprintf(
          payload, sizeof(payload),
          "{\"zone_id\":\"%s\",\"temperature_celsius\":%.1f,"
          "\"humidity_percent\":%.1f,\"timestamp\":\"%s\","
          "\"device_id\":\"%s\"}",
          ZONE_ID, tempC, humidity, timestamp, deviceId.c_str());

      if (mqttClient.publish(MQTT_TOPIC, payload)) {
        Serial.print("Published to ");
        Serial.print(MQTT_TOPIC);
        Serial.print(": ");
        Serial.println(payload);
      } else {
        Serial.println("Publish FAILED.");
      }
    }
  }

  delay(2000); // Refresh interval
}
