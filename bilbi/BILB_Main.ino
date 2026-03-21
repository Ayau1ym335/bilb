
//    CPU Freq:       240 MHz
//    Flash Size:     4MB (32Mb)
//    Partition:      Default 4MB with spiffs   
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <esp_task_wdt.h>  
#include "Config.h"

SensorData      g_sensor     = {};
BuildingProfile g_profile    = {};
RobotPose       g_pose       = {};
RobotState      g_state      = RobotState::IDLE;
volatile bool   g_vibrationFlag = false;   
uint32_t        g_scanCounter   = 0;

static Adafruit_SSD1306 s_oled(OLED_W, OLED_H, &Wire, OLED_RESET);
static bool             s_oledOk = false;

static unsigned long s_displayLastMs = 0;
static unsigned long s_buzzerLastMs  = 0;
static unsigned long s_scanStartMs   = 0;
static bool          s_buzzerOn      = false;

void initSensors(); void readAllSensors(); void printSensorDiag();
void initMotors();
void motorStop(); void motorForward(uint8_t); void motorBackward(uint8_t);
void motorTurnLeft(uint8_t); void motorTurnRight(uint8_t);
void reactiveAvoid(); bool isEmergency();
void updatePose();
void wpTick(); bool wpIsRunning(); uint8_t wpCurrentIdx(); uint8_t wpCount();
void wsNotifyWpReached(uint8_t); void wsNotifyMissionComplete();
void assessDegradation(); void generateProfile();
extern unsigned long g_profileLastMs;
void initWiFiAP(); void initWebSocket(); void tickWebSocket();
void wsSendState(uint8_t, RobotState); int wsActiveClient();
void initHTTPClient(); void httpPostTelemetry(const char*, size_t);
void getHTTPStats(bool&, uint32_t&, uint32_t&); size_t getBufferBytes();

// ════════════════════════════════════════════════════════════════
//  setRobotState()  —  Публичная функция смены состояния
//  Вызывается из WebSocket_Server.ino и внутренних переходов
// ════════════════════════════════════════════════════════════════
void setRobotState(RobotState ns) {
  static const char* names[] = {
    "IDLE","SCANNING","MANUAL","WAYPOINT","EMERGENCY"
  };
  uint8_t oi = (uint8_t)g_state, ni = (uint8_t)ns;
  if (oi == ni) return;

  Serial.printf("[SM] %s → %s\n",
    oi < 5 ? names[oi] : "?",
    ni < 5 ? names[ni] : "?"
  );

  // Entry actions
  if (ns == RobotState::SCANNING || ns == RobotState::WAYPOINT) {
    s_scanStartMs = millis();
  }
  if (ns == RobotState::EMERGENCY_STOP) {
    motorStop();
  }
  if (ns == RobotState::IDLE) {
    motorStop();
    s_buzzerOn = false;
    digitalWrite(PIN_BUZZER, LOW);
  }

  g_state = ns;

  // Уведомить WebSocket-клиента о смене состояния
  int c = wsActiveClient();
  if (c >= 0) wsSendState((uint8_t)c, ns);

  rgbForState(ns);
}

// ════════════════════════════════════════════════════════════════
//  RGB LED helper
// ════════════════════════════════════════════════════════════════
void rgbForState(RobotState st) {
  bool r = false, g = false, b = false;
  switch (st) {
    case RobotState::IDLE:            b = true;         break;  // Синий   = ожидание
    case RobotState::SCANNING:        g = true;         break;  // Зелёный = сканирование
    case RobotState::MANUAL:          g = true; b=true; break;  // Голубой = ручное
    case RobotState::WAYPOINT:        g = true; r=true; break;  // Жёлтый  = миссия
    case RobotState::EMERGENCY_STOP:  r = true;         break;  // Красный = авария
  }
  digitalWrite(PIN_RGB_R, r ? HIGH : LOW);
  digitalWrite(PIN_RGB_G, g ? HIGH : LOW);
  digitalWrite(PIN_RGB_B, b ? HIGH : LOW);
}

// ════════════════════════════════════════════════════════════════
//  setup()
// ════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 2000) {}   // ждём Serial Monitor

  Serial.println(F("\n╔══════════════════════════════════════╗"));
  Serial.printf ("║  BILB Firmware v%-6s               ║\n", FW_VERSION);
  Serial.printf ("║  Building: %-26s║\n", BUILDING_ID);
  Serial.println(F("╚══════════════════════════════════════╝"));

  // ── Watchdog: 30 секунд (перезагрузка если loop зависнет) ───
  esp_task_wdt_init(30, true);
  esp_task_wdt_add(NULL);

  // ── Индикаторы ───────────────────────────────────────────────
  pinMode(PIN_RGB_R, OUTPUT); pinMode(PIN_RGB_G, OUTPUT);
  pinMode(PIN_RGB_B, OUTPUT); pinMode(PIN_BUZZER, OUTPUT);
  // Белый = инициализация
  digitalWrite(PIN_RGB_R, HIGH); digitalWrite(PIN_RGB_G, HIGH);
  digitalWrite(PIN_RGB_B, HIGH);

  // ── ADC ──────────────────────────────────────────────────────
  // ▶ НАСТРОЙТЕ: атенюация для SW-420 (VIBRATION) пина
  analogSetAttenuation(ADC_11db);   // 0–3.3V диапазон

  // ── I2C ──────────────────────────────────────────────────────
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(I2C_FREQ);

  // ── OLED ─────────────────────────────────────────────────────
  s_oledOk = s_oled.begin(SSD1306_SWITCHCAPVCC, ADDR_OLED);
  if (s_oledOk) {
    oledSplash();
  } else {
    Serial.println(F("[OLED] Not found — продолжаем без дисплея"));
  }

  // ── Подсистемы (порядок важен) ───────────────────────────────
  initSensors();          // I2C датчики + ISR
  initMotors();           // L298N + опц. LEDC PWM

  // SPIFFS нужен до Wi-Fi
  initHTTPClient();

  // Wi-Fi AP → WebSocket
  initWiFiAP();
  initWebSocket();

  // ── Начальный профиль ─────────────────────────────────────────
  g_profile.status = DegStatus::OK;
  strcpy(g_profile.statusStr, "OK");
  g_profile.score = 0.0f;
  strcpy(g_profile.issues, "NONE");

  // ── Финальное состояние ───────────────────────────────────────
  setRobotState(RobotState::IDLE);

  Serial.printf("[MAIN] Free heap: %u bytes\n", ESP.getFreeHeap());
  Serial.printf("[MAIN] Boot reason: %d\n", esp_reset_reason());
  Serial.println(F("[MAIN] Ready. Подключись к BILB_Robot и открой control.html"));
  Serial.println(F("[CMD]  S=Scan  I=Idle  M=Manual  R=Reset  D=Diag"));
}

// ════════════════════════════════════════════════════════════════
//  loop()  —  Главный цикл (всё non-blocking)
// ════════════════════════════════════════════════════════════════
void loop() {
  // ── Сброс watchdog (сигнал «я жив») ─────────────────────────
  esp_task_wdt_reset();

  // ── Читаем датчики (каждые IVMS_SENSORS) ─────────────────────
  readAllSensors();

  // ── Dead-reckoning (каждый вызов loop) ───────────────────────
  updatePose();

  // ── WebSocket: приём команд + push телеметрии ────────────────
  tickWebSocket();

  // ── Serial CLI ───────────────────────────────────────────────
  handleSerial();

  // ── State Machine ────────────────────────────────────────────
  switch (g_state) {

    // ── IDLE: стоим, периодически отправляем профиль ───────────
    case RobotState::IDLE:
      generateProfile();
      break;

    // ── SCANNING: автономный объезд + полный сбор данных ───────
    case RobotState::SCANNING:
      if (isEmergency()) {
        setRobotState(RobotState::EMERGENCY_STOP); break;
      }
      reactiveAvoid();
      generateProfile();
      // Автовыход после SCAN_TIMEOUT_MS
      if (millis() - s_scanStartMs >= SCAN_TIMEOUT_MS) {
        Serial.println(F("[SM] Scan timeout → IDLE"));
        setRobotState(RobotState::IDLE);
      }
      break;

    // ── MANUAL: моторы управляются через WebSocket ─────────────
    case RobotState::MANUAL:
      // Если WS-клиент отвалился — безопасно уходим в IDLE
      if (wsActiveClient() < 0) {
        motorStop();
        setRobotState(RobotState::IDLE);
      }
      generateProfile();
      break;

    // ── WAYPOINT: навигация по маршрутным точкам ───────────────
    case RobotState::WAYPOINT:
      if (isEmergency()) {
        setRobotState(RobotState::EMERGENCY_STOP); break;
      }
      {
        uint8_t prevIdx = wpCurrentIdx();
        wpTick();   // Navigation.ino
        uint8_t curIdx  = wpCurrentIdx();

        // Уведомляем клиента о достижении точки
        if (curIdx != prevIdx) wsNotifyWpReached(prevIdx);

        if (!wpIsRunning()) {
          wsNotifyMissionComplete();
          setRobotState(RobotState::IDLE);
        }
      }
      generateProfile();
      break;

    // ── EMERGENCY STOP ─────────────────────────────────────────
    case RobotState::EMERGENCY_STOP:
      motorStop();

      // Пульсирующий зуммер
      {
        unsigned long now = millis();
        if (now - s_buzzerLastMs >= IVMS_BUZZER) {
          s_buzzerLastMs = now;
          s_buzzerOn = !s_buzzerOn;
          digitalWrite(PIN_BUZZER, s_buzzerOn ? HIGH : LOW);
        }
      }

      // Авто-восстановление если условия нормализовались
      if (!isEmergency() && g_sensor.distFront > DIST_CAUTION_CM) {
        digitalWrite(PIN_BUZZER, LOW); s_buzzerOn = false;
        Serial.println(F("[SM] Emergency cleared → IDLE"));
        setRobotState(RobotState::IDLE);
      }
      break;
  }

  // ── OLED обновление ──────────────────────────────────────────
  updateOLED();
}

// ════════════════════════════════════════════════════════════════
//  handleSerial()  —  USB CLI для отладки и демо
// ════════════════════════════════════════════════════════════════
void handleSerial() {
  if (!Serial.available()) return;
  char c = toupper((char)Serial.read());
  while (Serial.available()) Serial.read();  // flush

  switch (c) {
    case 'S':
      if (g_state == RobotState::EMERGENCY_STOP) {
        Serial.println(F("[CMD] Сначала сбрось emergency (R)"));
      } else {
        setRobotState(RobotState::SCANNING);
      }
      break;
    case 'I':
      setRobotState(RobotState::IDLE);
      break;
    case 'M':
      setRobotState(RobotState::MANUAL);
      break;
    case 'R':
      setRobotState(RobotState::IDLE);
      Serial.println(F("[CMD] Reset OK"));
      break;
    case 'D':
      printSensorDiag();
      Serial.printf("[CMD] Heap=%u  State=%d  Score=%.1f\n",
                    ESP.getFreeHeap(), (int)g_state, g_profile.score);
      {
        bool online; uint32_t ok, fail;
        getHTTPStats(online, ok, fail);
        Serial.printf("[CMD] HTTP online=%d ok=%u fail=%u buf=%u bytes\n",
                      online, ok, fail, getBufferBytes());
      }
      break;
    case 'P':
      g_profileLastMs = 0;   // форсируем немедленный вывод
      generateProfile();
      break;
    default:
      Serial.println(F("[CMD] S=Scan I=Idle M=Manual R=Reset D=Diag P=Profile"));
      break;
  }
}

// ════════════════════════════════════════════════════════════════
//  updateOLED()  —  Non-blocking OLED refresh
//  Три «экрана» листаются автоматически каждые 3 с
// ════════════════════════════════════════════════════════════════
static uint8_t s_oledPage = 0;

void updateOLED() {
  if (!s_oledOk) return;
  unsigned long now = millis();
  if (now - s_displayLastMs < IVMS_DISPLAY) return;
  s_displayLastMs = now;

  // Смена страницы каждые 3 обновления
  static uint8_t tick = 0;
  if (++tick >= 3) { tick = 0; s_oledPage = (s_oledPage + 1) % 3; }

  s_oled.clearDisplay();
  s_oled.setTextSize(1);
  s_oled.setTextColor(SSD1306_WHITE);

  switch (s_oledPage) {

    // Страница 0: Статус + Wi-Fi
    case 0:
      s_oled.setCursor(0, 0);
      s_oled.print(F("BILB v")); s_oled.println(FW_VERSION);
      s_oled.print(F("State:")); oledPrintState(); s_oled.println();
      s_oled.print(F("Status:"));s_oled.println(g_profile.statusStr);
      s_oled.print(F("Score: ")); s_oled.println(g_profile.score, 1);
      s_oled.println(F("192.168.4.1:81"));
      s_oled.print(WIFI_AP_SSID);
      break;

    // Страница 1: Сенсоры
    case 1:
      s_oled.setCursor(0, 0);
      s_oled.print(F("T:")); s_oled.print(g_sensor.temperature, 1);
      s_oled.print(F("C H:")); s_oled.print(g_sensor.humidity,  0); s_oled.println('%');
      s_oled.print(F("P:")); s_oled.print(g_sensor.pressure, 0);
      s_oled.print(F(" L:")); s_oled.println((int)g_sensor.lightLux);
      s_oled.print(F("Roll:")); s_oled.print(g_sensor.tiltRoll,  1);
      s_oled.print(F(" P:")); s_oled.println(g_sensor.tiltPitch, 1);
      s_oled.print(F("VIB:")); s_oled.println(g_sensor.vibration ? F("YES") : F("NO"));
      break;

    // Страница 2: Дистанции + позиция
    case 2:
      s_oled.setCursor(0, 0);
      s_oled.print(F("F:")); s_oled.print((int)g_sensor.distFront);
      s_oled.print(F(" B:")); s_oled.println((int)g_sensor.distBack);
      s_oled.print(F("L:")); s_oled.print((int)g_sensor.distLeft);
      s_oled.print(F(" R:")); s_oled.println((int)g_sensor.distRight);
      s_oled.print(F("X:")); s_oled.print(g_pose.x, 1);
      s_oled.print(F(" Y:")); s_oled.println(g_pose.y, 1);
      s_oled.print(F("Hdg:")); s_oled.println((int)g_pose.headingDeg);
      {
        bool on; uint32_t ok, fail;
        getHTTPStats(on, ok, fail);
        s_oled.print(on ? F("HTTP:OK") : F("HTTP:--"));
        s_oled.print(F(" Buf:")); s_oled.println(getBufferBytes());
      }
      break;
  }

  s_oled.display();
}

// ════════════════════════════════════════════════════════════════
//  oledSplash()  —  Заставка при загрузке
// ════════════════════════════════════════════════════════════════
void oledSplash() {
  s_oled.clearDisplay();
  s_oled.setTextSize(2);
  s_oled.setTextColor(SSD1306_WHITE);
  s_oled.setCursor(20, 10); s_oled.println(F("BILB"));
  s_oled.setTextSize(1);
  s_oled.setCursor(8, 36);  s_oled.println(F("Initializing..."));
  s_oled.setCursor(8, 48);  s_oled.print(F("v")); s_oled.println(FW_VERSION);
  s_oled.display();
  delay(1500);   // единственный delay() во всём проекте
}

static void oledPrintState() {
  switch(g_state){
    case RobotState::IDLE:           s_oled.print(F("IDLE"));  break;
    case RobotState::SCANNING:       s_oled.print(F("SCAN"));  break;
    case RobotState::MANUAL:         s_oled.print(F("MAN"));   break;
    case RobotState::WAYPOINT:       s_oled.print(F("WP"));    break;
    case RobotState::EMERGENCY_STOP: s_oled.print(F("EMRG"));  break;
  }
}
