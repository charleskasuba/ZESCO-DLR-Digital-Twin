/*
 * ZESCO DLR Digital Twin - ESP32 Sensor Node Firmware
 * ====================================================
 * Reads four sensors and streams telemetry to the Flask backend:
 *   - DS18B20  : conductor (wire) temperature  -> GPIO 4
 *   - DHT22    : ambient temperature/humidity -> GPIO 16
 *   - ACS712   : line current (5 A variant)   -> GPIO 34 (ADC)
 *   - Anemometer: wind speed                  -> GPIO 35 (ADC)
 *
 * Libraries (Arduino IDE -> Library Manager):
 *   - OneWire            by Paul Stoffregen
 *   - DallasTemperature  by Miles Burton
 *   - DHT sensor library by Adafruit
 *   - ArduinoJson        by Benoit Blanchon
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "DHT.h"
#include <ArduinoJson.h>

// =====================================================
// CONFIGURATION - UPDATE THESE VALUES FOR YOUR NETWORK
// =====================================================
const char* ssid       = "YOUR_WIFI_SSID";
const char* password   = "YOUR_WIFI_PASSWORD";
// Render free tier serves HTTPS. For a local backend use:
//   http://<your-PC-LAN-IP>:5000/api/telemetry
const char* serverUrl  = "https://zesco-dlr-twin.onrender.com/api/telemetry";

// ---- Pin definitions ----
#define ONE_WIRE_BUS 4     // DS18B20 wire temperature sensor
#define DHTPIN 16          // DHT22 ambient sensor
#define DHTTYPE DHT22
#define CURRENT_PIN 34     // ACS712 current sensor (analog ADC)
#define ANEMOMETER_PIN 35  // anemometer wind speed (analog ADC)

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature wireTempSensor(&oneWire);
DHT dht(DHTPIN, DHTTYPE);

// ---- ACS712 calibration (5A variant) ----
const float VREF        = 3.3;         // ESP32 ADC reference voltage
const float ADC_SCALE   = 4095.0;      // 12-bit resolution
const float SENSITIVITY = 0.185;       // 185 mV/A for the 5A module
const float ZERO_OFFSET = 1.65;        // 0 A midpoint on a 3.3 V system

// ---- Sample averaging ----
const int   SAMPLES     = 20;
const float SAMPLE_GAP  = 10;          // ms between ADC samples

unsigned long lastPost = 0;
const unsigned long POST_INTERVAL = 1000;  // telemetry refresh (ms)

void setup() {
  Serial.begin(115200);
  wireTempSensor.begin();
  dht.begin();

  analogReadResolution(12);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - t0 > 20000) {
      Serial.println("\nWi-Fi connection timed out. Check SSID/password.");
      return;
    }
  }
  Serial.println();
  Serial.println("Wi-Fi connected! IP: " + WiFi.localIP().toString());
}

float averageAnalog(int pin) {
  long sum = 0;
  for (int i = 0; i < SAMPLES; i++) {
    sum += analogRead(pin);
    delay(SAMPLE_GAP);
  }
  return (float)sum / SAMPLES;
}

float readCurrent() {
  float rawADC = averageAnalog(CURRENT_PIN);
  float voltage = (rawADC / ADC_SCALE) * VREF;
  float current = fabs((voltage - ZERO_OFFSET) / SENSITIVITY);
  return (current < 0.05) ? 0.0 : current;  // noise filter
}

float readWindSpeed() {
  float rawADC = averageAnalog(ANEMOMETER_PIN);
  float voltage = (rawADC / ADC_SCALE) * VREF;
  // Maps 0.4 V - 2.0 V analog output to 0 - 32 m/s
  if (voltage < 0.4) return 0.0;
  return ((voltage - 0.4) / (2.0 - 0.4)) * 32.0;
}

void loop() {
  if (WiFi.status() == WL_CONNECTED && millis() - lastPost >= POST_INTERVAL) {
    lastPost = millis();

    // 1. Read sensors
    wireTempSensor.requestTemperatures();
    float conductorTemp = wireTempSensor.getTempCByIndex(0);
    float ambientTemp   = dht.readTemperature();
    float humidity      = dht.readHumidity();
    float lineCurrent   = readCurrent();
    float windSpeed     = readWindSpeed();

    // 2. Sensor sanity check
    if (isnan(ambientTemp) || isnan(humidity) || conductorTemp == DEVICE_DISCONNECTED_C) {
      Serial.println("Sensor read error - retrying next cycle");
      return;
    }

    // 3. Build JSON payload
    StaticJsonDocument<256> doc;
    doc["conductor_temp"] = conductorTemp;
    doc["ambient_temp"]   = ambientTemp;
    doc["humidity"]       = humidity;
    doc["wind_speed"]     = windSpeed;
    doc["current_load"]   = lineCurrent;

    String payload;
    serializeJson(doc, payload);

    // 4. POST to the DLR backend
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);

    int code = http.POST(payload);
    Serial.printf("Telemetry [%d]: %s\n", code, payload.c_str());

    http.end();
  }
  delay(200);
}
