static unsigned long lastNavUpdate = 0;

void initMotors() {
  pinMode(MOTOR_L_IN1, OUTPUT);
  pinMode(MOTOR_L_IN2, OUTPUT);
  pinMode(MOTOR_R_IN3, OUTPUT);
  pinMode(MOTOR_R_IN4, OUTPUT);
  stopMotors();
  Serial.println(F("[NAV] Motors OK"));
}

static inline void setLeftMotors(bool fwd, bool bwd) {
  digitalWrite(MOTOR_L_IN1, fwd  ? HIGH : LOW);
  digitalWrite(MOTOR_L_IN2, bwd  ? HIGH : LOW);
}

static inline void setRightMotors(bool fwd, bool bwd) {
  digitalWrite(MOTOR_R_IN3, fwd  ? HIGH : LOW);
  digitalWrite(MOTOR_R_IN4, bwd  ? HIGH : LOW);
}

void moveForward() {
  setLeftMotors(true, false);
  setRightMotors(true, false);
}

void moveBackward() {
  setLeftMotors(false, true);
  setRightMotors(false, true);
}

void turnLeft() {
  setLeftMotors(false, true);
  setRightMotors(true, false);
}

void turnRight() {
  setLeftMotors(true, false);
  setRightMotors(false, true);
}

void stopMotors() {
  setLeftMotors(false, false);
  setRightMotors(false, false);
}

void avoidObstacles() {
  unsigned long now = millis();
  if (now - lastNavUpdate < INTERVAL_NAV_MS) return;
  lastNavUpdate = now;

  float front = sensorData.distFront;
  float back  = sensorData.distBack;
  float left  = sensorData.distLeft;
  float right = sensorData.distRight;

  if (sensorData.edgeDetected) {
    moveBackward();
    Serial.println(F("[NAV] EDGE detected -> backward"));
    return;
  }

  if (front < OBSTACLE_DIST_CM) {
    stopMotors();
    if (left >= right) {
      turnLeft();
      Serial.println(F("[NAV] Obstacle front -> turn LEFT"));
    } else {
      turnRight();
      Serial.println(F("[NAV] Obstacle front -> turn RIGHT"));
    }
    return;
  }

  if (back < OBSTACLE_DIST_CM) {
    moveForward(); // Rear obstacle — move away from it
    Serial.println(F("[NAV] Obstacle BACK -> move forward"));
    return;
  }

  if (left < CAUTION_DIST_CM && left < right) {
    turnRight();
    return;
  }

  if (right < CAUTION_DIST_CM && right < left) {
    turnLeft();
    return;
  }

  moveForward();
}

bool checkEmergencyConditions() {
  if (fabsf(sensorData.tiltAngle) > TILT_CRITICAL_DEG) {
    Serial.println(F("[NAV] EMRG: critical tilt!"));
    return true;
  }

  if (sensorData.distFront < 10.0f &&
      sensorData.distBack  < 10.0f) {
    Serial.println(F("[NAV] EMRG: trapped!"));
    return true;
  }
  
  if (sensorData.edgeDetected) {
    Serial.println(F("[NAV] EMRG: edge detected!"));
    return true;
  }

  return false;
}