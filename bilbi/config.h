#pragma once
#include <Arduino.h>

#define FW_VERSION      "2.1.0"
#define BUILDING_ID     "BILB_001"    // ▶ НАСТРОЙТЕ: уникальный ID объекта

#define PIN_SDA   21
#define PIN_SCL   22
#define I2C_FREQ  400000UL       

#define PIN_L_IN1   13           
#define PIN_L_IN2   12            
#define PIN_R_IN3   14
#define PIN_R_IN4   27         
#define PIN_L_ENA   32      
#define PIN_R_ENB   33       
#define MOTORS_USE_PWM     true   

#define PIN_US_F_TRIG   26          
#define PIN_US_F_ECHO   35     
#define PIN_US_B_TRIG   25     
#define PIN_US_B_ECHO   34        
#define PIN_US_L_TRIG    5        
#define PIN_US_L_ECHO   18        
#define PIN_US_R_TRIG   19    
#define PIN_US_R_ECHO   36         

#define PIN_VIBRATION   23          

#define PIN_RGB_R        2
#define PIN_RGB_G        4
#define PIN_RGB_B       15
#define PIN_BUZZER      17        

// ── PWM Channels (ESP32 LEDC) ─────────────────────────────────
#define LEDC_L_CH        0           // Left motor  PWM channel
#define LEDC_R_CH        1           // Right motor PWM channel
#define LEDC_BUZ_CH      2           // Buzzer PWM channel
#define LEDC_FREQ     1000           // Hz
#define LEDC_RES         8           // bits  (0–255)

// ════════════════════════════════════════════════════════════════
//  II. I2C АДРЕСА УСТРОЙСТВ
// ════════════════════════════════════════════════════════════════
#define ADDR_OLED     0x3C           // SSD1306 128×64
#define ADDR_BME280   0x76           // ▶ НАСТРОЙТЕ: 0x76 или 0x77 (зависит от SDO)
#define ADDR_MPU6050  0x68           // ▶ НАСТРОЙТЕ: 0x68 или 0x69 (зависит от AD0)
#define ADDR_BH1750   0x23           // ADDR pin → GND=0x23, VCC=0x5C

#define OLED_W  128
#define OLED_H   64
#define OLED_RESET -1

#define WIFI_AP_SSID      "BILB_Robot" 
#define WIFI_AP_PASS      "bilb2026"   
#define WIFI_AP_CHANNEL   6           
#define WIFI_AP_MAX_CONN  2        

#define AP_IP_ADDR    "192.168.4.1"
#define AP_GATEWAY    "192.168.4.1"
#define AP_SUBNET     "255.255.255.0"

#define WS_PORT       81

// HTTP POST эндпоинт бэкенда (fallback если WS недоступен)
// ▶ НАСТРОЙТЕ: IP/порт вашего FastAPI сервера
#define HTTP_BACKEND_URL  "http://192.168.4.2:8000/api/telemetry"
#define HTTP_TIMEOUT_MS   2000

// SPIFFS буфер при потере связи
#define SPIFFS_BUFFER_FILE  "/telemetry_buffer.jsonl"
#define SPIFFS_MAX_BYTES    (100 * 1024)   // 100 KB  ▶ НАСТРОЙТЕ под размер SPIFFS

#define ROBOT_TRACK_MM      150.0f   // расстояние между левым и правым бортом, мм
#define ROBOT_WHEEL_DIAM_MM  65.0f
#define ROBOT_SPEED_MM_S    220.0f   // линейная скорость при полном PWM, мм/с
//                                    (измерьте: проедьте 1 м, засеките время)
#define ROBOT_TURN_RATE_DEG_S 180.0f // угловая скорость при pivot-повороте, °/с
//                                    (измерьте: 360° поворот, засеките время)

#define GRID_COLS         20        
#define GRID_ROWS         20
#define GRID_CELL_MM     300.0f     

#define CELLS_PER_S  (ROBOT_SPEED_MM_S / GRID_CELL_MM)
#define CELLS_PER_DEG (ROBOT_TURN_RATE_DEG_S / GRID_CELL_MM)

//  ▶ НАСТРОЙТЕ: подберите под моторы (слишком низкое = не трогается)
#define MOTOR_SPEED_FULL    230      // нормальное движение
#define MOTOR_SPEED_TURN    200      // поворот на месте
#define MOTOR_SPEED_SLOW    150      // подъезд к точке вплотную
#define MOTOR_DEAD_ZONE      80      // минимальный PWM, при котором мотор вращается

#define DIST_OBSTACLE_CM    25.0f   
#define DIST_CAUTION_CM     50.0f    
#define DIST_MAX_CM        400.0f    
#define DIST_ECHO_TIMEOUT_US 25000  

#define THR_HUMIDITY_CRIT   70.0f    // % — критическая влажность
#define THR_HUMIDITY_WARN   55.0f    // %
#define THR_TEMP_CRIT       40.0f    // °C
#define THR_TEMP_WARN       30.0f    // °C
#define THR_LIGHT_LOW      100.0f    // lux — плохая инсоляция
#define THR_TILT_CRIT       15.0f    // ° — критический наклон
#define THR_TILT_WARN        5.0f    // °

#define WP_REACH_CELLS      0.5f  
#define WP_HEADING_TOL_DEG  15.0f  

#define IVMS_SENSORS        500UL   
#define IVMS_NAV            80UL   
#define IVMS_TELEMETRY      200UL    // WebSocket push
#define IVMS_PROFILE       5000UL    // JSON в Serial / HTTP POST
#define IVMS_DISPLAY       1000UL    // обновление OLED
#define IVMS_BUZZER         300UL    // период пульсации зуммера
#define IVMS_WP_NAV         100UL    
#define SCAN_TIMEOUT_MS   420000UL    

struct SensorData {
  // BME280
  float  temperature;       // °C
  float  humidity;          // %
  float  pressure;          // hPa
  // BH1750
  float  lightLux;          // lux
  // MPU6050
  float  accelX, accelY, accelZ;   // m/s²
  float  gyroX,  gyroY,  gyroZ;    // °/s
  float  tiltRoll;          // °  — крен (roll)
  float  tiltPitch;         // °  — тангаж (pitch)
  // HC-SR04
  float  distFront;         // cm
  float  distBack;          // cm
  float  distLeft;          // cm
  float  distRight;         // cm
  // Binary
  bool   vibration;         // SW-420: TRUE = событие
  // Metadata
  unsigned long timestampMs;
  uint32_t      scanId;
};

enum class DegStatus : uint8_t { OK = 0, WARNING = 1, CRITICAL = 2 };

struct BuildingProfile {
  DegStatus status;
  char      statusStr[12]; 
  float     score;       
  char      issues[256];   
};

struct RobotPose {
  float x;       
  float y;         
  float headingDeg;
};


struct Waypoint {
  float x, y;
};

enum class RobotState : uint8_t {
  IDLE           = 0,
  SCANNING       = 1, 
  MANUAL         = 2,  
  WAYPOINT       = 3, 
  EMERGENCY_STOP = 4,
};

enum class CmdType : uint8_t {
  NONE = 0,
  FORWARD, BACKWARD, LEFT, RIGHT, STOP,
  SET_MODE_MANUAL, SET_MODE_AUTO, SET_MODE_SCAN,
  ADD_WAYPOINT, RUN_WAYPOINTS, CLEAR_WAYPOINTS,
  RESET_POSE, GET_STATUS,
};

struct Command {
  CmdType type  = CmdType::NONE;
  float   paramX = 0.0f;
  float   paramY = 0.0f;
};

extern SensorData     g_sensor;
extern BuildingProfile g_profile;
extern RobotPose      g_pose;
extern RobotState     g_state;
extern volatile bool  g_vibrationFlag;   
extern uint32_t       g_scanCounter;