#include <Adafruit_BME280.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <BH1750.h>
#include "Config.h"

static Adafruit_BME280  s_bme;
static Adafruit_MPU6050 s_mpu;
static BH1750           s_bh;

static bool s_bmeOk = false;
static bool s_mpuOk = false;
static bool s_bhOk  = false;

template<typename T, uint8_t N>
class MovAvg {
  T buf[N] = {};
  uint8_t idx = 0;
  uint8_t cnt = 0;
public:
  void push(T v) {
    buf[idx] = v;
    idx = (idx + 1) % N;
    if (cnt < N) cnt++;
  }
  T get() const {
    if (cnt == 0) return T(0);
    float s = 0;
    for (uint8_t i = 0; i < cnt; i++) s += buf[i];
    return T(s / cnt);
  }
  bool ready() const { return cnt == N; }
};

static MovAvg<float, 4> mf_temp;
static MovAvg<float, 4> mf_hum;
static MovAvg<float, 4> mf_press;
static MovAvg<float, 4> mf_lux;
static MovAvg<float, 4> mf_tiltR;
static MovAvg<float, 4> mf_tiltP;
static MovAvg<float, 3> mf_dF;
static MovAvg<float, 3> mf_dB;
static MovAvg<float, 3> mf_dL;
static MovAvg<float, 3> mf_dR;

volatile bool g_vibrationFlag = false;
static void IRAM_ATTR vibISR() {
  g_vibrationFlag = true;
}

static unsigned long s_lastReadMs = 0;
void initSensors() {
  s_bmeOk = s_bme.begin(ADDR_BME280);
  if (s_bmeOk) {
    s_bme.setSampling(
      Adafruit_BME280::MODE_NORMAL,
      Adafruit_BME280::SAMPLING_X2,   // temp
      Adafruit_BME280::SAMPLING_X16,  // pressure
      Adafruit_BME280::SAMPLING_X1,   // humidity
      Adafruit_BME280::FILTER_X4,
      Adafruit_BME280::STANDBY_MS_500
    );
    Serial.printf("[SENS] BME280  OK  addr=0x%02X\n", ADDR_BME280);
  } else {
    Serial.printf("[SENS] BME280  FAIL addr=0x%02X — check SDO pin\n", ADDR_BME280);
  }

  s_mpuOk = s_mpu.begin(ADDR_MPU6050);
  if (s_mpuOk) {
    s_mpu.setAccelerometerRange(MPU6050_RANGE_4_G);  
    s_mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    s_mpu.setFilterBandwidth(MPU6050_BAND_10_HZ);    
    Serial.printf("[SENS] MPU6050 OK  addr=0x%02X\n", ADDR_MPU6050);
  } else {
    Serial.printf("[SENS] MPU6050 FAIL addr=0x%02X — check AD0 pin\n", ADDR_MPU6050);
  }

  s_bhOk = s_bh.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, ADDR_BH1750);
  if (s_bhOk) {
    Serial.printf("[SENS] BH1750  OK  addr=0x%02X\n", ADDR_BH1750);
  } else {
    Serial.printf("[SENS] BH1750  FAIL addr=0x%02X — check ADDR pin\n", ADDR_BH1750);
  }

  pinMode(PIN_US_F_TRIG, OUTPUT); digitalWrite(PIN_US_F_TRIG, LOW);
  pinMode(PIN_US_B_TRIG, OUTPUT); digitalWrite(PIN_US_B_TRIG, LOW);
  pinMode(PIN_US_L_TRIG, OUTPUT); digitalWrite(PIN_US_L_TRIG, LOW);
  pinMode(PIN_US_R_TRIG, OUTPUT); digitalWrite(PIN_US_R_TRIG, LOW);
  
  pinMode(PIN_VIBRATION, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_VIBRATION), vibISR, RISING);
  Serial.println(F("[SENS] SW-420  OK  (interrupt mode)"));

  Serial.println(F("[SENS] Init complete."));
}

// ════════════════════════════════════════════════════════════════
//  pingUS()  —  Один измерительный импульс HC-SR04
//  Возвращает: расстояние cm | DIST_MAX_CM если нет эха
//
//  ▶ НАСТРОЙТЕ DIST_ECHO_TIMEOUT_US если нужно иное макс. расстояние
// ════════════════════════════════════════════════════════════════
static float pingUS(uint8_t trigPin, uint8_t echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(4);

  // 10 мкс HIGH → запуск измерения
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // Ждём фронт эха (timeout защищает от зависания)
  long us = pulseIn(echoPin, HIGH, DIST_ECHO_TIMEOUT_US);

  if (us == 0) return DIST_MAX_CM;          // нет эха = нет препятствия

  // v_sound ≈ 0.03432 cm/µs при ~20°C
  // Коррекция на температуру если BME280 OK:
  float v = 0.03432f;
  if (s_bmeOk) {
    // v_sound = 331.3 * sqrt(1 + T/273.15) ≈ 331.3 + 0.606*T  (cm/µs = /1e4)
    v = (331.3f + 0.606f * g_sensor.temperature) / 10000.0f;
  }

  float cm = (us * v) / 2.0f;

  // Отбраковка: < 2 cm = артефакт, > max = нет отражателя
  if (cm < 2.0f || cm > DIST_MAX_CM) return DIST_MAX_CM;
  return cm;
}

// ════════════════════════════════════════════════════════════════
//  calcTilt()  —  Угол крена и тангажа из акселерометра (°)
//  Метод: complementary filter (простой, без гироскопной интеграции)
//  Если нужен Kalman — замени эту функцию.
// ════════════════════════════════════════════════════════════════
static void calcTilt(float ax, float ay, float az,
                     float& rollDeg, float& pitchDeg) {
  // Roll  (крен  вокруг оси X)
  rollDeg  = atan2f(ay, sqrtf(ax*ax + az*az)) * (180.0f / PI);
  // Pitch (тангаж вокруг оси Y)
  pitchDeg = atan2f(-ax, sqrtf(ay*ay + az*az)) * (180.0f / PI);
  //
  // ▶ НАСТРОЙТЕ: если MPU6050 смонтирован под углом — добавь смещение:
  //   rollDeg  -= MOUNT_ROLL_OFFSET_DEG;
  //   pitchDeg -= MOUNT_PITCH_OFFSET_DEG;
}

void readAllSensors() {
  unsigned long now = millis();
  if (now - s_lastReadMs < IVMS_SENSORS) return;
  s_lastReadMs = now;

  if (s_bmeOk) {
    mf_temp.push(s_bme.readTemperature());
    mf_hum.push(s_bme.readHumidity());
    mf_press.push(s_bme.readPressure() / 100.0f);

    g_sensor.temperature = mf_temp.get();
    g_sensor.humidity    = mf_hum.get();
    g_sensor.pressure    = mf_press.get();
  }

  if (s_bhOk) {
    float lux = s_bh.readLightLevel();
    if (lux >= 0) {                            // -1 = ошибка
      mf_lux.push(lux);
      g_sensor.lightLux = mf_lux.get();
    }
  }

  if (s_mpuOk) {
    sensors_event_t eA, eG, eT;
    s_mpu.getEvent(&eA, &eG, &eT);

    g_sensor.accelX = eA.acceleration.x;
    g_sensor.accelY = eA.acceleration.y;
    g_sensor.accelZ = eA.acceleration.z;
    g_sensor.gyroX  = eG.gyro.x;
    g_sensor.gyroY  = eG.gyro.y;
    g_sensor.gyroZ  = eG.gyro.z;

    float r, p;
    calcTilt(g_sensor.accelX, g_sensor.accelY, g_sensor.accelZ, r, p);
    mf_tiltR.push(r);
    mf_tiltP.push(p);
    g_sensor.tiltRoll  = mf_tiltR.get();
    g_sensor.tiltPitch = mf_tiltP.get();
  }

  mf_dF.push(pingUS(PIN_US_F_TRIG, PIN_US_F_ECHO));
  delayMicroseconds(10000);
  mf_dB.push(pingUS(PIN_US_B_TRIG, PIN_US_B_ECHO));
  delayMicroseconds(10000);
  mf_dL.push(pingUS(PIN_US_L_TRIG, PIN_US_L_ECHO));
  delayMicroseconds(10000);
  mf_dR.push(pingUS(PIN_US_R_TRIG, PIN_US_R_ECHO));

  g_sensor.distFront = mf_dF.get();
  g_sensor.distBack  = mf_dB.get();
  g_sensor.distLeft  = mf_dL.get();
  g_sensor.distRight = mf_dR.get();

  noInterrupts();
  bool vib = g_vibrationFlag;
  g_vibrationFlag = false;
  interrupts();
  g_sensor.vibration = vib;

  g_sensor.timestampMs = now;
  g_sensor.scanId      = g_scanCounter;
}

void printSensorDiag() {
  Serial.printf("[DIAG] BME=%d MPU=%d BH=%d\n",
                s_bmeOk, s_mpuOk, s_bhOk);
  Serial.printf("[DIAG] T=%.1f°C H=%.1f%% P=%.1fhPa Lux=%.0f\n",
                g_sensor.temperature, g_sensor.humidity,
                g_sensor.pressure,    g_sensor.lightLux);
  Serial.printf("[DIAG] Roll=%.2f° Pitch=%.2f°\n",
                g_sensor.tiltRoll, g_sensor.tiltPitch);
  Serial.printf("[DIAG] F=%.0f B=%.0f L=%.0f R=%.0f cm\n",
                g_sensor.distFront, g_sensor.distBack,
                g_sensor.distLeft,  g_sensor.distRight);
  Serial.printf("[DIAG] VIB=%d\n", g_sensor.vibration);
}
