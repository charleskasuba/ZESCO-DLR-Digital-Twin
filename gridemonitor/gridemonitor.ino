#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <PZEM004Tv30.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ---------------------------------------------------------------------------
// Wi-Fi & Backend Configuration
// ---------------------------------------------------------------------------
const char* WIFI_SSID = "THE METHOD ZONE";
const char* WIFI_PASS = "Chabu321+";

// Render-hosted backend (HTTPS) or local Flask server (HTTP), e.g.
//   const char* SERVER_URL = "http://192.168.1.50:5000";
const char* SERVER_URL      = "https://zesco-dlr-digital-twin.onrender.com";
const char* TELEMETRY_PATH  = "/api/telemetry";
const bool  SERVER_USE_TLS  = true;   // true for https://, false for http://

// Identifies this node on the dashboard (/api/device/status).
const char* DEVICE_ID = "esp32-node-01";

// ---------------------------------------------------------------------------
// Pin Definitions
// ---------------------------------------------------------------------------
const int PZEM_RX_PIN      = 25;
const int PZEM_TX_PIN      = 26;

const int SDA_PIN          = 21;
const int SCL_PIN          = 22;

const int DHT_PIN          = 4;
#define DHT_TYPE DHT22

const int DS18B20_PIN      = 18;  // Yellow DATA wire (with 4.7k pull-up to 3V3)

const int TRIG1_PIN        = 13;  // Ultrasonic 1 (Sag)
const int ECHO1_PIN        = 34;  // Input-only pin (use voltage divider if 5V echo)

const int TRIG2_PIN        = 14;  // Ultrasonic 2 (Ground Clearance)
const int ECHO2_PIN        = 35;  // Input-only pin (use voltage divider if 5V echo)

const int RELAY_PIN        = 27;
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

// ---------------------------------------------------------------------------
// Protection & Geometry Calibration Constants
// ---------------------------------------------------------------------------
const float OVERCURRENT_TRIP_A   = 15.0;  // Trip relay above this current (A)
const float OVERCURRENT_RESET_A  = 12.0;  // Allow re-close below this current (A)
const float DEFAULT_WIND_SPEED   = 2.0;   // Fallback wind speed (m/s)

// Adjust these two reference heights (in meters) to match your physical rig:
const float SAG_REF_HEIGHT_M     = 4.50;
const float CLEARANCE_BASE_M     = 6.00;

// ---------------------------------------------------------------------------
// Hardware & State Objects
// ---------------------------------------------------------------------------
LiquidCrystal_I2C lcd(0x27, 20, 4);
DHT dht(DHT_PIN, DHT_TYPE);
OneWire oneWire(DS18B20_PIN);
DallasTemperature ds18b20(&oneWire);
PZEM004Tv30 pzem(Serial2, PZEM_RX_PIN, PZEM_TX_PIN);

// Electrical (PZEM)
float line_voltage_V  = 0.0;
float line_current_A  = 0.0;
float line_power_W    = 0.0;
float line_energy_kWh = 0.0;
float line_pf         = 0.0;

// Environment & Conductor
float ambient_temp_C   = 25.0;
float humidity_pct     = 50.0;
float conductor_temp_C = 25.0;
float wind_speed_ms    = DEFAULT_WIND_SPEED;

// Ultrasonic & Sag / Clearance
float dist1_m       = 0.0;
float dist2_m       = 0.0;
float sag_m         = 0.0;
float clearance_m   = 0.0;

// Relay & Telemetry Tracking
bool relayTripped = false;
unsigned long lastSampleTime    = 0;
unsigned long lastWiFiCheck     = 0;
unsigned long lastDisplaySwitch = 0;

const unsigned long SAMPLE_INTERVAL  = 5000;  // Read sensors & POST every 5s
const unsigned long WIFI_INTERVAL    = 15000; // Check Wi-Fi every 15s
const unsigned long LCD_INTERVAL     = 4000;  // Cycle LCD pages every 4s

int displayPage = 0;
int sendCount   = 0;
int failCount   = 0;

// ---------------------------------------------------------------------------
// Ultrasonic Distance Helper (returns distance in meters, -1.0 on timeout)
// ---------------------------------------------------------------------------
float readUltrasonicMeters(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(3);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration_us = pulseIn(echoPin, HIGH, 30000); // 30ms timeout (~5m max)
  if (duration_us <= 0) {
    return -1.0;
  }
  return (duration_us * 0.000343f) / 2.0f;
}

// ---------------------------------------------------------------------------
// Read All Sensors
// ---------------------------------------------------------------------------
void readAllSensors() {
  // 1. PZEM Electrical Parameters: Voltage, Current, Power, Energy, PF
  float v  = pzem.voltage();
  float i  = pzem.current();
  float p  = pzem.power();
  float e  = pzem.energy(); // kWh
  float pf = pzem.pf();

  if (!isnan(v) && v >= 0.0) {
    line_voltage_V  = v;
    line_current_A  = (!isnan(i) && i >= 0.0) ? i : 0.0;
    line_power_W    = (!isnan(p) && p >= 0.0) ? p : 0.0;
    line_energy_kWh = (!isnan(e) && e >= 0.0) ? e : line_energy_kWh;
    line_pf         = (!isnan(pf) && pf >= 0.0) ? pf : 0.0;
  } else {
    line_voltage_V = 0.0;
    line_current_A = 0.0;
    line_power_W   = 0.0;
    line_pf        = 0.0;
  }

  // 2. DHT22 Ambient Temperature & Humidity
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (!isnan(h) && !isnan(t)) {
    humidity_pct   = h;
    ambient_temp_C = t;
  }

  // 3. DS18B20 Probe Temperature on Conductor
  ds18b20.requestTemperatures();
  float probeTemp = ds18b20.getTempCByIndex(0);
  if (probeTemp != DEVICE_DISCONNECTED_C && probeTemp > -55.0 && probeTemp < 125.0) {
    conductor_temp_C = probeTemp;
  } else {
    Serial.println("[WARN] DS18B20 disconnected or invalid reading");
  }

  // 4. Two Ultrasonic Sensors for Sag & Ground Clearance
  float d1 = readUltrasonicMeters(TRIG1_PIN, ECHO1_PIN);
  if (d1 > 0.0) {
    dist1_m = d1;
    sag_m = max(0.0f, SAG_REF_HEIGHT_M - dist1_m);
  }

  delay(30); // Prevent acoustic crosstalk between sensor 1 and sensor 2

  float d2 = readUltrasonicMeters(TRIG2_PIN, ECHO2_PIN);
  if (d2 > 0.0) {
    dist2_m = d2;
    clearance_m = max(0.0f, CLEARANCE_BASE_M - sag_m - dist2_m);
  }

  // 5. Overcurrent Relay Protection with Hysteresis
  if (!relayTripped && line_current_A >= OVERCURRENT_TRIP_A) {
    relayTripped = true;
    digitalWrite(RELAY_PIN, RELAY_OFF);
    Serial.printf("[TRIP] Overcurrent %.2fA >= %.2fA -> Relay OFF\n", line_current_A, OVERCURRENT_TRIP_A);
  } else if (relayTripped && line_current_A <= OVERCURRENT_RESET_A) {
    relayTripped = false;
    digitalWrite(RELAY_PIN, RELAY_ON);
    Serial.printf("[SAFE] Current %.2fA <= %.2fA -> Relay ON\n", line_current_A, OVERCURRENT_RESET_A);
  }
}

// ---------------------------------------------------------------------------
// Send Telemetry to Flask Backend (POST /api/telemetry)
// ---------------------------------------------------------------------------
String buildTelemetryPayload() {
  String payload = "{";
  payload += "\"device_id\":\""    + String(DEVICE_ID) + "\",";
  payload += "\"conductor_temp\":" + String(conductor_temp_C, 2) + ",";
  payload += "\"ambient_temp\":"   + String(ambient_temp_C, 2)   + ",";
  payload += "\"humidity\":"       + String(humidity_pct, 1)     + ",";
  payload += "\"wind_speed\":"     + String(wind_speed_ms, 2)    + ",";
  payload += "\"current_load\":"   + String(line_current_A, 3)   + ",";
  payload += "\"voltage_v\":"      + String(line_voltage_V, 2)   + ",";
  payload += "\"power_w\":"        + String(line_power_W, 2)     + ",";
  payload += "\"energy_kwh\":"     + String(line_energy_kWh, 4)  + ",";
  payload += "\"pf\":"             + String(line_pf, 2)          + ",";
  payload += "\"sag_m\":"          + String(sag_m, 3)            + ",";
  payload += "\"clearance_m\":"    + String(clearance_m, 3)      + ",";
  payload += "\"relay_tripped\":"  + String(relayTripped ? "true" : "false");
  payload += "}";
  return payload;
}

void postToBackend(WiFiClient& client, const String& endpoint, const String& payload) {
  HTTPClient http;
  http.begin(client, endpoint);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(8000);

  int httpCode = http.POST(payload);
  sendCount++;

  if (httpCode == 201 || httpCode == 200) {
    failCount = 0;
    Serial.printf("[OK #%d] POST %d | V:%.1fV I:%.2fA P:%.1fW E:%.3fkWh Tc:%.1fC Sag:%.2fm Clr:%.2fm\n",
                  sendCount, httpCode, line_voltage_V, line_current_A, line_power_W,
                  line_energy_kWh, conductor_temp_C, sag_m, clearance_m);
  } else {
    failCount++;
    Serial.printf("[FAIL #%d] HTTP %d: %s\n",
                  sendCount, httpCode, http.errorToString(httpCode).c_str());
  }

  http.end();
}

void sendTelemetryToServer() {
  if (WiFi.status() != WL_CONNECTED) {
    failCount++;
    Serial.println("[WARN] Wi-Fi not connected; skipping POST");
    return;
  }

  String endpoint = String(SERVER_URL) + TELEMETRY_PATH;
  String payload = buildTelemetryPayload();

  if (SERVER_USE_TLS) {
    WiFiClientSecure client;
    client.setInsecure();
    postToBackend(client, endpoint, payload);
  } else {
    WiFiClient client;
    postToBackend(client, endpoint, payload);
  }
}

// ---------------------------------------------------------------------------
// Update 20x4 I2C LCD Display
// ---------------------------------------------------------------------------
void updateLCDScreen() {
  char buf[21];
  lcd.clear();

  switch (displayPage) {
    case 0: // Electrical: Voltage, Current, Power, Energy
      lcd.setCursor(0, 0);
      lcd.print("== LINE ELECTRICAL ==");
      snprintf(buf, sizeof(buf), "V:%6.1fV I:%6.2fA", line_voltage_V, line_current_A);
      lcd.setCursor(0, 1); lcd.print(buf);
      snprintf(buf, sizeof(buf), "P:%6.1fW PF:%4.2f", line_power_W, line_pf);
      lcd.setCursor(0, 2); lcd.print(buf);
      snprintf(buf, sizeof(buf), "E:%7.3fkWh RLY:%s", line_energy_kWh, relayTripped ? "TRIP" : "OK  ");
      lcd.setCursor(0, 3); lcd.print(buf);
      break;

    case 1: // Conductor & Ambient Thermal + Humidity
      lcd.setCursor(0, 0);
      lcd.print("=== THERMAL & ENV ===");
      snprintf(buf, sizeof(buf), "Wire Temp: %6.1f C", conductor_temp_C);
      lcd.setCursor(0, 1); lcd.print(buf);
      snprintf(buf, sizeof(buf), "Amb Temp : %6.1f C", ambient_temp_C);
      lcd.setCursor(0, 2); lcd.print(buf);
      snprintf(buf, sizeof(buf), "Humidity : %6.1f %%", humidity_pct);
      lcd.setCursor(0, 3); lcd.print(buf);
      break;

    case 2: // Sag & Ground Clearance (Dual Ultrasonic)
      lcd.setCursor(0, 0);
      lcd.print("== SAG & CLEARANCE ==");
      snprintf(buf, sizeof(buf), "Sag      : %6.2f m", sag_m);
      lcd.setCursor(0, 1); lcd.print(buf);
      snprintf(buf, sizeof(buf), "Clearance: %6.2f m", clearance_m);
      lcd.setCursor(0, 2); lcd.print(buf);
      snprintf(buf, sizeof(buf), "U1:%4.2fm  U2:%4.2fm", dist1_m, dist2_m);
      lcd.setCursor(0, 3); lcd.print(buf);
      break;

    case 3: // Network & Sync Status
      lcd.setCursor(0, 0);
      lcd.print("==== LINK STATUS ====");
      lcd.setCursor(0, 1);
      lcd.print(WiFi.status() == WL_CONNECTED ? "WiFi: Connected     " : "WiFi: Disconnected  ");
      snprintf(buf, sizeof(buf), "Sent:%-4d Fail:%-4d", sendCount, failCount);
      lcd.setCursor(0, 2); lcd.print(buf);
      snprintf(buf, sizeof(buf), "Uptime: %6lu min", millis() / 60000);
      lcd.setCursor(0, 3); lcd.print(buf);
      break;
  }

  displayPage = (displayPage + 1) % 4;
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== ZESCO DLR DIGITAL TWIN - ESP32 NODE ===");

  // Relay default ON (safe closed state until overcurrent trip)
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_ON);
  relayTripped = false;

  // Ultrasonic pins
  pinMode(TRIG1_PIN, OUTPUT);
  pinMode(ECHO1_PIN, INPUT);
  pinMode(TRIG2_PIN, OUTPUT);
  pinMode(ECHO2_PIN, INPUT);
  digitalWrite(TRIG1_PIN, LOW);
  digitalWrite(TRIG2_PIN, LOW);

  // I2C & LCD
  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ZESCO DLR Node");
  lcd.setCursor(0, 1);
  lcd.print("Booting sensors...");

  // DHT22 & DS18B20
  dht.begin();
  ds18b20.begin();
  ds18b20.setResolution(12); // 0.0625 C resolution

  // Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  lcd.clear();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[OK] Wi-Fi connected. IP: %s\n", WiFi.localIP().toString().c_str());
    lcd.setCursor(0, 0); lcd.print("WiFi Connected!");
    lcd.setCursor(0, 1); lcd.print(WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WARN] Wi-Fi not connected yet.");
    lcd.setCursor(0, 0); lcd.print("WiFi Pending...");
    lcd.setCursor(0, 1); lcd.print("Logging locally");
  }
  delay(1500);

  readAllSensors();
  sendTelemetryToServer();
  updateLCDScreen();
  lastSampleTime = millis();
  lastDisplaySwitch = millis();
}

// ---------------------------------------------------------------------------
// Main Loop
// ---------------------------------------------------------------------------
void loop() {
  unsigned long now = millis();

  if (now - lastWiFiCheck >= WIFI_INTERVAL) {
    lastWiFiCheck = now;
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.reconnect();
    }
  }

  if (now - lastSampleTime >= SAMPLE_INTERVAL) {
    lastSampleTime = now;
    readAllSensors();
    sendTelemetryToServer();
  }

  if (now - lastDisplaySwitch >= LCD_INTERVAL) {
    lastDisplaySwitch = now;
    updateLCDScreen();
  }
}