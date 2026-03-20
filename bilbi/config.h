#pragma once
#include <Arduino.h>

#define SDA_PIN  21
#define SCL_PIN  22

#define MOTOR_L_IN1  13
#define MOTOR_L_IN2  12
#define MOTOR_R_IN3  14
#define MOTOR_R_IN4  27

#define US_FRONT_TRIG  32
#define US_FRONT_ECHO  35
#define US_BACK_TRIG   33
#define US_BACK_ECHO   34
#define US_LEFT_TRIG   25
#define US_LEFT_ECHO   26
#define US_RIGHT_TRIG   5
#define US_RIGHT_ECHO  18

#define VIBRATION_PIN  19
#define EDGE_PIN       36

#define RGB_R_PIN   2
#define RGB_G_PIN   4
#define RGB_B_PIN  15
#define BUZZER_PIN 23

#define OLED_ADDR    0x3C
#define BME280_ADDR  0x76
#define MPU6050_ADDR 0x68
#define BH1750_ADDR  0x23

#define OLED_W  128
#define OLED_H   64

#define OBSTACLE_DIST_CM     25.0f   // Препятствие — аварийная остановка
#define CAUTION_DIST_CM      50.0f   // Зона предупреждения
#define EDGE_ADC_THRESHOLD  2000     // АЦП 12-bit: 0–4095, порог края

#define HUMIDITY_CRITICAL    70.0f   // Критическая влажность, %
#define HUMIDITY_WARNING     55.0f   // Предупреждение влажности, %
#define TEMP_CRITICAL_C      40.0f   // Критическая температура, °C
#define TEMP_WARNING_C       30.0f
#define LIGHT_LOW_LUX       100.0f   // Недостаточное освещение, Lux
#define TILT_CRITICAL_DEG    15.0f   // Критический наклон, градусы
#define TILT_WARNING_DEG      5.0f

#define INTERVAL_SENSORS_MS    500UL
#define INTERVAL_NAV_MS        100UL
#define INTERVAL_PROFILE_MS   5000UL
#define INTERVAL_DISPLAY_MS   1000UL
#define INTERVAL_BUZZER_MS     250UL
#define SCAN_DURATION_MS     20000UL  

struct SensorData {
  // --- Экологические (BME280) ---
  float temperature;    // °C
  float humidity;       // %
  float pressure;       // hPa

  // --- Освещённость (BH1750) ---
  float lightLux;       // Lux

  // --- Структурные (MPU6050) ---
  float accelX, accelY, accelZ;  // м/с²
  float tiltAngle;               // Угол наклона, °

  // --- Проксимальные (HC-SR04) ---
  float distFront, distBack, distLeft, distRight;  // см

  // --- Дискретные ---
  bool vibrationDetected;
  bool edgeDetected;

  unsigned long timestamp;
};

enum DegradationStatus : uint8_t {
  STATUS_OK       = 0,
  STATUS_WARNING  = 1,
  STATUS_CRITICAL = 2
};

struct BuildingProfile {
  DegradationStatus status;
  char  statusLabel[12];   
  float degradationScore; 
  char  issues[200];       
};

enum RobotState : uint8_t {
  STATE_IDLE           = 0, 
  STATE_SCANNING       = 1,  
  STATE_EMERGENCY_STOP = 2  
};

// ── WiFi / UDP Telemetry ──────────────────────────────
#define WIFI_SSID       "YOUR_SSID"
#define WIFI_PASSWORD   "YOUR_PASSWORD"
#define UDP_HOST        "192.168.1.100"   // PC / dashboard IP
#define UDP_PORT        4210
#define WIFI_TIMEOUT_MS 10000UL            // Max wait for connection