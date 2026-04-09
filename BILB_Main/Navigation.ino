#include "Config.h"

static unsigned long s_navLastMs  = 0;
static unsigned long s_poseLastMs = 0;
static unsigned long s_wpLastMs   = 0;

#define MAX_WAYPOINTS 32
static Waypoint s_wpQueue[MAX_WAYPOINTS];
static uint8_t  s_wpCount   = 0;
static uint8_t  s_wpIdx     = 0;
static bool     s_wpRunning = false;

enum class MotionState : uint8_t {
  STOPPED, FORWARD, BACKWARD, TURN_LEFT, TURN_RIGHT
};
static MotionState s_motionState = MotionState::STOPPED;

static void setMotorRaw(bool lFwd, bool lBwd, bool rFwd, bool rBwd,
                         uint8_t speedL = MOTOR_SPEED_FULL,
                         uint8_t speedR = MOTOR_SPEED_FULL) {
  digitalWrite(PIN_L_IN1, lFwd ? HIGH : LOW);
  digitalWrite(PIN_L_IN2, lBwd ? HIGH : LOW);
  digitalWrite(PIN_R_IN3, rFwd ? HIGH : LOW);
  digitalWrite(PIN_R_IN4, rBwd ? HIGH : LOW);

#if MOTORS_USE_PWM
  uint8_t sL = (lFwd || lBwd) ? speedL : 0;
  uint8_t sR = (rFwd || rBwd) ? speedR : 0;
  ledcWrite(LEDC_L_CH, sL);
  ledcWrite(LEDC_R_CH, sR);
#endif
}

void motorForward(uint8_t spd) {
  setMotorRaw(true, false, true, false, spd, spd);
  s_motionState = MotionState::FORWARD;
}

void motorBackward(uint8_t spd) {
  setMotorRaw(false, true, false, true, spd, spd);
  s_motionState = MotionState::BACKWARD;
}

void motorTurnLeft(uint8_t spd) {
  setMotorRaw(false, true, true, false, spd, spd);
  s_motionState = MotionState::TURN_LEFT;
}

void motorTurnRight(uint8_t spd) {
  setMotorRaw(true, false, false, true, spd, spd);
  s_motionState = MotionState::TURN_RIGHT;
}

void motorCurve(float bias, uint8_t baseSpd) {
  bias = constrain(bias, -1.0f, 1.0f);
  uint8_t sL = (uint8_t)constrain(baseSpd * (1.0f - max(0.0f,  bias)), 0, 255);
  uint8_t sR = (uint8_t)constrain(baseSpd * (1.0f - max(0.0f, -bias)), 0, 255);
  setMotorRaw(true, false, true, false, sL, sR);
  s_motionState = MotionState::FORWARD;
}

void motorStop() {
  setMotorRaw(false, false, false, false, 0, 0);
  s_motionState = MotionState::STOPPED;
}

void updatePose() {
  unsigned long now = millis();
  if (s_poseLastMs == 0) { s_poseLastMs = now; return; }

  float dt = (now - s_poseLastMs) / 1000.0f;  
  s_poseLastMs = now;

  switch (s_motionState) {

    case MotionState::FORWARD: {
      float dMM   = ROBOT_SPEED_MM_S * dt;
      float dCells = dMM / GRID_CELL_MM;
      float rad    = (g_pose.headingDeg - 90.0f) * DEG_TO_RAD;
      g_pose.x += cosf(rad) * dCells;
      g_pose.y -= sinf(rad) * dCells;  
      break;
    }

    case MotionState::BACKWARD: {
      float dMM   = ROBOT_SPEED_MM_S * 0.85f * dt; 
      float dCells = dMM / GRID_CELL_MM;
      float rad    = (g_pose.headingDeg - 90.0f) * DEG_TO_RAD;
      g_pose.x -= cosf(rad) * dCells;
      g_pose.y += sinf(rad) * dCells;
      break;
    }

    case MotionState::TURN_LEFT:
      g_pose.headingDeg -= ROBOT_TURN_RATE_DEG_S * dt;
      break;

    case MotionState::TURN_RIGHT:
      g_pose.headingDeg += ROBOT_TURN_RATE_DEG_S * dt;
      break;

    default: break;
  }

  // Normalise heading to [0, 360)
  g_pose.headingDeg = fmodf(g_pose.headingDeg + 3600.0f, 360.0f);

  // Границы сетки
  g_pose.x = constrain(g_pose.x, 0.0f, (float)(GRID_COLS - 1));
  g_pose.y = constrain(g_pose.y, 0.0f, (float)(GRID_ROWS - 1));
}

void reactiveAvoid() {
  unsigned long now = millis();
  if (now - s_navLastMs < IVMS_NAV) return;
  s_navLastMs = now;

  // Non-blocking pause after front-stop: let other subsystems run during the wait
  static unsigned long s_avoidPauseUntil = 0;
  if (now < s_avoidPauseUntil) return;

  float f = g_sensor.distFront;
  float b = g_sensor.distBack;
  float l = g_sensor.distLeft;
  float r = g_sensor.distRight;

  if (f < DIST_OBSTACLE_CM && b < DIST_OBSTACLE_CM) {
    motorStop();
    return;
  }

  if (f < DIST_OBSTACLE_CM) {
    if (s_motionState == MotionState::TURN_LEFT || s_motionState == MotionState::TURN_RIGHT) {
      // Already turning to avoid, continue turning
      return;
    }

    if (s_avoidPauseUntil == 0) {
      // First detection: stop and set a short pause
      motorStop();
      s_avoidPauseUntil = now + 50;   // 50 ms non-blocking pause
      return;
    }
    // Pause expired, obstacle still present: choose turn direction
    s_avoidPauseUntil = 0;
    (l > r) ? motorTurnLeft(MOTOR_SPEED_TURN)
            : motorTurnRight(MOTOR_SPEED_TURN);
    return;
  }
  s_avoidPauseUntil = 0;

  if (b < DIST_OBSTACLE_CM && s_motionState == MotionState::BACKWARD) {
    motorStop(); return;
  }

  if (l < DIST_CAUTION_CM || r < DIST_CAUTION_CM) {
    float bias = 0.0f;
    if (l < DIST_CAUTION_CM && r >= DIST_CAUTION_CM)
      bias =  (DIST_CAUTION_CM - l) / DIST_CAUTION_CM;
    if (r < DIST_CAUTION_CM && l >= DIST_CAUTION_CM)
      bias = -(DIST_CAUTION_CM - r) / DIST_CAUTION_CM;
    motorCurve(bias * 0.6f, MOTOR_SPEED_FULL);
    return;
  }

  motorForward(MOTOR_SPEED_FULL);
}

bool isEmergency() {
  if (fabsf(g_sensor.tiltRoll)  > THR_TILT_CRIT) {
    Serial.println(F("[NAV] EMRG: critical roll"));
    return true;
  }
  if (fabsf(g_sensor.tiltPitch) > THR_TILT_CRIT) {
    Serial.println(F("[NAV] EMRG: critical pitch"));
    return true;
  }
  if (g_sensor.distFront < DIST_TRAPPED_CM && g_sensor.distBack < DIST_TRAPPED_CM) {
    Serial.println(F("[NAV] EMRG: trapped"));
    return true;
  }
  return false;
}

bool wpAddPoint(float x, float y) {
  if (s_wpCount >= MAX_WAYPOINTS) return false;
  s_wpQueue[s_wpCount++] = { x, y };
  return true;
}

void wpClear() {
  s_wpCount = 0; s_wpIdx = 0; s_wpRunning = false;
  motorStop();
}

bool wpStart() {
  if (s_wpCount == 0) return false;
  s_wpIdx = 0; s_wpRunning = true;
  Serial.printf("[WP] Mission start: %d waypoints\n", s_wpCount);
  return true;
}

bool wpIsRunning() { return s_wpRunning; }
uint8_t wpCurrentIdx() { return s_wpIdx; }
uint8_t wpCount()    { return s_wpCount; }

static float wrapAngle(float deg) {
  while (deg >  180.0f) deg -= 360.0f;
  while (deg < -180.0f) deg += 360.0f;
  return deg;
}

void wpTick() {
  if (!s_wpRunning) return;
  unsigned long now = millis();
  if (now - s_wpLastMs < IVMS_WP_NAV) return;
  s_wpLastMs = now;

  if (s_wpIdx >= s_wpCount) {
    s_wpRunning = false;
    motorStop();
    Serial.println(F("[WP] Mission complete."));
    return;
  }

  if (isEmergency()) {
    s_wpRunning = false;
    motorStop();
    return;
  }

  Waypoint& tgt = s_wpQueue[s_wpIdx];
  float dx = tgt.x - g_pose.x;
  float dy = tgt.y - g_pose.y;
  float dist = sqrtf(dx*dx + dy*dy);

  if (dist < WP_REACH_CELLS) {
    Serial.printf("[WP] Reached #%d (%.1f,%.1f)\n",
                  s_wpIdx + 1, tgt.x, tgt.y);
    s_wpIdx++;
    motorStop();
    return;
  }

  if (g_sensor.distFront < DIST_OBSTACLE_CM) {
    (g_sensor.distLeft > g_sensor.distRight)
      ? motorTurnLeft(MOTOR_SPEED_TURN)
      : motorTurnRight(MOTOR_SPEED_TURN);
    return;
  }

  float targetHdg = atan2f(dx, -dy) * RAD_TO_DEG;
  if (targetHdg < 0.0f) targetHdg += 360.0f;

  float hdgErr = wrapAngle(targetHdg - g_pose.headingDeg);

  if (fabsf(hdgErr) > WP_HEADING_TOL_DEG) {
    float fErr = fabsf(hdgErr);
    float t = constrain((fErr - WP_HEADING_TOL_DEG) / (90.0f - WP_HEADING_TOL_DEG), 0.0f, 1.0f);
    uint8_t tSpd = (uint8_t)(MOTOR_SPEED_SLOW + t * (MOTOR_SPEED_TURN - MOTOR_SPEED_SLOW));
    tSpd = constrain(tSpd, MOTOR_SPEED_SLOW, MOTOR_SPEED_TURN);
    (hdgErr > 0) ? motorTurnRight(tSpd) : motorTurnLeft(tSpd);
  } else {
  
    uint8_t fSpd = (dist < 1.0f)
                   ? MOTOR_SPEED_SLOW
                   : MOTOR_SPEED_FULL;
    motorForward(fSpd);
  }
}

void initMotors() {
  pinMode(PIN_L_IN1, OUTPUT); pinMode(PIN_L_IN2, OUTPUT);
  pinMode(PIN_R_IN3, OUTPUT); pinMode(PIN_R_IN4, OUTPUT);

#if MOTORS_USE_PWM
  ledcAttachChannel(PIN_L_ENA, LEDC_FREQ, LEDC_RES, LEDC_L_CH);
  ledcAttachChannel(PIN_R_ENB, LEDC_FREQ, LEDC_RES, LEDC_R_CH);
  Serial.println(F("[NAV] Motors OK  (PWM mode)"));
#else
  pinMode(PIN_L_ENA, OUTPUT); pinMode(PIN_R_ENB, OUTPUT);
  digitalWrite(PIN_L_ENA, HIGH); digitalWrite(PIN_R_ENB, HIGH);
  Serial.println(F("[NAV] Motors OK  (digital mode)"));
#endif

  motorStop();
  g_pose = { 1.0f, 1.0f, 0.0f };
}