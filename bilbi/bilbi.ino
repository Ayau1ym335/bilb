#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <BH1750.h>
#include <ArduinoJson.h>
#include "Config.h"

Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, -1);
Adafruit_BME280  bme;
Adafruit_MPU6050 mpu;
BH1750           lightMeter;

SensorData      sensorData;   
BuildingProfile buildingProfile;  

RobotState     currentState    = STATE_IDLE;
unsigned long  scanStartTime   = 0;

unsigned long lastDisplayUpdate = 0;
unsigned long lastBuzzerToggle  = 0;
bool          buzzerOn          = false;

void initSensors();
void readAllSensors();
void initMotors();
void stopMotors();
void avoidObstacles();
bool checkEmergencyConditions();
void generateJSONProfile();
void assessDegradation();
extern unsigned long lastProfileUpdate; 

void setup() {
  Serial.begin(115200);
  delay(300);  
  Serial.println(F("\n============================="));
  Serial.println(F("  BILB v1.0  —  BOOTING...  "));

  // Индикаторы
  pinMode(RGB_R_PIN,  OUTPUT);
  pinMode(RGB_G_PIN,  OUTPUT);
  pinMode(RGB_B_PIN,  OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  setRGB(false, false, true);  // Синий = загрузка

  Wire.begin(SDA_PIN, SCL_PIN);

  // OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("[MAIN] ERROR: OLED not found!"));
  } else {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(4, 4);
    display.println(F("BILB v1.0"));
    display.setCursor(4, 16);
    display.println(F("Initializing..."));
    display.display();
  }

  // Подсистемы датчиков и моторов
  initSensors();
  initMotors();

  // Дефолтный профиль
  buildingProfile.status = STATUS_OK;
  strcpy(buildingProfile.statusLabel, "OK");
  buildingProfile.degradationScore = 0.0f;
  strcpy(buildingProfile.issues, "NONE");

  Serial.println(F("[MAIN] Ready."));
  Serial.println(F("[CMD]  S=Scan  I=Idle  R=Reset  P=Print JSON"));
  setRGB(false, false, true);  // Синий = IDLE
}

void loop() {
  handleSerial();
  readAllSensors();
  updateDisplay();
  switch (currentState) {

    // ── IDLE 
    case STATE_IDLE:
      stopMotors();
      setRGB(false, false, true);   // Синий = ожидание
      generateJSONProfile();        // Периодически выводим профиль
      break;

    // ── SCANNING 
    case STATE_SCANNING:
      // Проверка аварийных условий 
      if (checkEmergencyConditions()) {
        Serial.println(F("[SM] EMERGENCY: critical condition!"));
        transitionTo(STATE_EMERGENCY_STOP);
        break;
      }
      // Проверка завершения скана по таймеру
      if (millis() - scanStartTime >= SCAN_DURATION_MS) {
        Serial.println(F("[SM] Scan complete -> IDLE"));
        transitionTo(STATE_IDLE);
        break;
      }
      // Навигация с объездом препятствий
      avoidObstacles();
      setRGB(false, true, false);   // Зелёный = активный скан
      generateJSONProfile();
      break;

    // ── EMERGENCY_STOP 
    case STATE_EMERGENCY_STOP:
      stopMotors();
      setRGB(true, false, false);   // Красный = авария
      {
        unsigned long now = millis();
        if (now - lastBuzzerToggle >= INTERVAL_BUZZER_MS) {
          lastBuzzerToggle = now;
          buzzerOn = !buzzerOn;
          digitalWrite(BUZZER_PIN, buzzerOn ? HIGH : LOW);
        }
      }

      if (!checkEmergencyConditions() &&
          sensorData.distFront > CAUTION_DIST_CM) {
        Serial.println(F("[SM] Emergency cleared -> IDLE"));
        digitalWrite(BUZZER_PIN, LOW);
        buzzerOn = false;
        transitionTo(STATE_IDLE);
      }
      break;
  }
}

void transitionTo(RobotState newState) {
  const char* names[] = {"IDLE", "SCANNING", "EMERGENCY_STOP"};
  Serial.print(F("[SM] "));
  Serial.print(names[currentState]);
  Serial.print(F(" -> "));
  Serial.println(names[newState]);

  if (newState == STATE_SCANNING) {
    scanStartTime = millis();
  }
  currentState = newState;
}

void handleSerial() {
  if (!Serial.available()) return;

  char cmd = toupper(Serial.read());
  while (Serial.available()) Serial.read();

  switch (cmd) {
    case 'S':
      if (currentState == STATE_EMERGENCY_STOP) {
        Serial.println(F("[CMD] Cannot start: emergency active. Send 'R' first."));
      } else {
        transitionTo(STATE_SCANNING);
        Serial.println(F("[CMD] Scan started."));
      }
      break;

    case 'I':
      stopMotors();
      transitionTo(STATE_IDLE);
      break;

    case 'R':
      stopMotors();
      digitalWrite(BUZZER_PIN, LOW);
      buzzerOn = false;
      transitionTo(STATE_IDLE);
      Serial.println(F("[CMD] Emergency reset."));
      break;

    case 'P':
      assessDegradation();
      lastProfileUpdate = 0;
      generateJSONProfile();
      break;

    default:
      Serial.println(F("[CMD] Unknown. Use: S I R P"));
      break;
  }
}

void updateDisplay() {
  unsigned long now = millis();
  if (now - lastDisplayUpdate < INTERVAL_DISPLAY_MS) return;
  lastDisplayUpdate = now;

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // Строка 0 (y=0): Состояние
  display.setCursor(0, 0);
  display.print(F("BILB|"));
  switch (currentState) {
    case STATE_IDLE:           display.print(F("IDLE"));  break;
    case STATE_SCANNING:       display.print(F("SCAN"));  break;
    case STATE_EMERGENCY_STOP: display.print(F("EMRG"));  break;
  }
  display.print(F(" "));
  display.print(buildingProfile.statusLabel);

  // Строка 1 (y=10): Температура и влажность
  display.setCursor(0, 10);
  display.print(F("T:"));
  display.print(sensorData.temperature, 1);
  display.print(F("C H:"));
  display.print(sensorData.humidity, 0);
  display.print(F("%"));

  // Строка 2 (y=20): Дистанции спереди и сзади
  display.setCursor(0, 20);
  display.print(F("F:"));
  display.print((int)sensorData.distFront);
  display.print(F(" B:"));
  display.print((int)sensorData.distBack);
  display.print(F(" cm"));

  // Строка 3 (y=30): Дистанции слева и справа
  display.setCursor(0, 30);
  display.print(F("L:"));
  display.print((int)sensorData.distLeft);
  display.print(F(" R:"));
  display.print((int)sensorData.distRight);
  display.print(F(" cm"));

  // Строка 4 (y=40): Вибрация и наклон
  display.setCursor(0, 40);
  display.print(F("VIB:"));
  display.print(sensorData.vibrationDetected ? F("YES") : F("NO"));
  display.print(F(" TILT:"));
  display.print(sensorData.tiltAngle, 1);

  // Строка 5 (y=50): Итоговая оценка деградации
  display.setCursor(0, 50);
  display.print(F("SCORE:"));
  display.print(buildingProfile.degradationScore, 1);
  display.print(F("/100 LUX:"));
  display.print((int)sensorData.lightLux);

  display.display();
}

void setRGB(bool r, bool g, bool b) {
  digitalWrite(RGB_R_PIN, r ? HIGH : LOW);
  digitalWrite(RGB_G_PIN, g ? HIGH : LOW);
  digitalWrite(RGB_B_PIN, b ? HIGH : LOW);
}