static bool bmeOK = false;
static bool mpuOK = false;
static bool bhOK  = false;

static unsigned long lastSensorRead = 0;
void initSensors() {
  bmeOK = bme.begin(BME280_ADDR);
  if (bmeOK) {
    bme.setSampling(Adafruit_BME280::MODE_NORMAL,
                    Adafruit_BME280::SAMPLING_X1,  // температура
                    Adafruit_BME280::SAMPLING_X1,  // давление
                    Adafruit_BME280::SAMPLING_X1,  // влажность
                    Adafruit_BME280::FILTER_OFF,
                    Adafruit_BME280::STANDBY_MS_500);
    Serial.println(F("[SENS] BME280 OK"));
  } else {
    Serial.println(F("[SENS] ERROR: BME280 not found at 0x76"));
  }

  mpuOK = mpu.begin();
  if (mpuOK) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println(F("[SENS] MPU6050 OK"));
  } else {
    Serial.println(F("[SENS] ERROR: MPU6050 not found at 0x68"));
  }

  bhOK = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
  if (bhOK) {
    Serial.println(F("[SENS] BH1750 OK"));
  } else {
    Serial.println(F("[SENS] ERROR: BH1750 not found at 0x23"));
  }

  pinMode(US_FRONT_TRIG, OUTPUT); pinMode(US_FRONT_ECHO, INPUT);
  pinMode(US_BACK_TRIG,  OUTPUT); pinMode(US_BACK_ECHO,  INPUT);
  pinMode(US_LEFT_TRIG,  OUTPUT); pinMode(US_LEFT_ECHO,  INPUT);
  pinMode(US_RIGHT_TRIG, OUTPUT); pinMode(US_RIGHT_ECHO, INPUT);

  // EDGE_PIN (GPIO 36) is input-only on ESP32 — no pinMode needed
  pinMode(VIBRATION_PIN, INPUT);
  Serial.println(F("[SENS] Init complete."));
}

// ================================================================
//  readUltrasonic() — Измерение расстояния одним HC-SR04
//
//  Параметры: trigPin, echoPin
//  Возврат:   расстояние в сантиметрах
//             999.0f  если нет эха (нет препятствия в зоне досягаемости)
//
//  Блокирующий вызов (pulseIn), но с таймаутом 25 мс.
//  4 вызова подряд = ~100 мс макс. Приемлемо для MVP при интервале 500 мс.
// ================================================================
float readUltrasonic(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 25000);

  if (duration == 0) return 999.0f; 
  float dist = (duration * 0.0343f) / 2.0f;
  return (dist < 2.0f) ? 999.0f : dist;
}

void readAllSensors() {
  unsigned long now = millis();
  if (now - lastSensorRead < INTERVAL_SENSORS_MS) return;
  lastSensorRead = now;

  // ── BME280 
  if (bmeOK) {
    sensorData.temperature = bme.readTemperature();        // °C
    sensorData.humidity    = bme.readHumidity();           // %
    sensorData.pressure    = bme.readPressure() / 100.0f;  // hPa
  }

  // ── BH1750 
  if (bhOK && lightMeter.measurementReady()) {
    sensorData.lightLux = lightMeter.readLightLevel();     // Lux
  }

  // ── MPU6050 
  if (mpuOK) {
    sensors_event_t accelEvt, gyroEvt, tempEvt;
    mpu.getEvent(&accelEvt, &gyroEvt, &tempEvt);

    sensorData.accelX = accelEvt.acceleration.x;
    sensorData.accelY = accelEvt.acceleration.y;
    sensorData.accelZ = accelEvt.acceleration.z;

    // Угол наклона вдоль оси X (Roll), °
    sensorData.tiltAngle = atan2(sensorData.accelX,
                                 sensorData.accelZ) * (180.0f / PI);
  }

  // ── HC-SR04 (4 направления) 
  sensorData.distFront = readUltrasonic(US_FRONT_TRIG, US_FRONT_ECHO);
  delay(10);  // 10 ms inter-sensor gap (use delay() not delayMicroseconds() for >=1ms)
  sensorData.distBack  = readUltrasonic(US_BACK_TRIG,  US_BACK_ECHO);
  delay(10);
  sensorData.distLeft  = readUltrasonic(US_LEFT_TRIG,  US_LEFT_ECHO);
  delay(10);
  sensorData.distRight = readUltrasonic(US_RIGHT_TRIG, US_RIGHT_ECHO);

  // ── SW-420 (Вибрация) 
  sensorData.vibrationDetected = (digitalRead(VIBRATION_PIN) == HIGH);

  // ── TCRT5000 (Край/обрыв) — аналоговый, 12-bit ADC ───────
  int edgeRaw = analogRead(EDGE_PIN);
  sensorData.edgeDetected = (edgeRaw > EDGE_ADC_THRESHOLD);

  sensorData.timestamp = now;
}