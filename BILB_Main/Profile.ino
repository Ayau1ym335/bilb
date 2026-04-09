#include <ArduinoJson.h>
#include "Config.h"

static char s_lastJsonBuf[600] = {};

unsigned long g_profileLastMs = 0;
uint32_t      g_scanCounter   = 0;

static const char* s_issues[16];
static uint8_t     s_issueCnt = 0;

static void issueAdd(const char* s) {
  if (s_issueCnt < 16) s_issues[s_issueCnt++] = s;
}

void assessDegradation() {
  float     score  = 0.0f;
  DegStatus status = DegStatus::OK;
  s_issueCnt = 0;

  if (g_sensor.humidity >= THR_HUMIDITY_CRIT) {
    score += 40.0f;
    status = DegStatus::CRITICAL;
    issueAdd("HIGH_HUMIDITY");
  } else if (g_sensor.humidity >= THR_HUMIDITY_WARN) {
    score += 20.0f;
    if (status < DegStatus::WARNING) status = DegStatus::WARNING;
    issueAdd("ELEVATED_HUMIDITY");
  }

  if (g_sensor.vibration) {
    score += 25.0f;
    issueAdd("VIBRATION_DETECTED");

    if (g_sensor.humidity >= THR_HUMIDITY_CRIT) {
      score  += 15.0f;        
      status  = DegStatus::CRITICAL;
      issueAdd("STRUCTURAL_RISK_COMBO");
    } else {
      if (status < DegStatus::WARNING) status = DegStatus::WARNING;
    }
  }

  if (g_sensor.temperature >= THR_TEMP_CRIT) {
    score += 20.0f;
    if (status < DegStatus::WARNING) status = DegStatus::WARNING;
    issueAdd("HIGH_TEMPERATURE");
  } else if (g_sensor.temperature >= THR_TEMP_WARN) {
    score += 8.0f;
    issueAdd("ELEVATED_TEMPERATURE");
  }

  float maxTilt = max(fabsf(g_sensor.tiltRoll), fabsf(g_sensor.tiltPitch));
  if (maxTilt >= THR_TILT_CRIT) {
    score += 35.0f;
    status  = DegStatus::CRITICAL;
    issueAdd("CRITICAL_STRUCTURAL_TILT");
  } else if (maxTilt >= THR_TILT_WARN) {
    score += 12.0f;
    if (status < DegStatus::WARNING) status = DegStatus::WARNING;
    issueAdd("TILT_DETECTED");
  }

  if (g_sensor.lightLux > 0.0f && g_sensor.lightLux < THR_LIGHT_LOW) {
    score += 5.0f;
    issueAdd("POOR_DAYLIGHTING");
  }

  score = constrain(score, 0.0f, 100.0f);   // clamp FIRST
  if (status == DegStatus::OK      && score >= 30.0f) status = DegStatus::WARNING;
  if (status == DegStatus::WARNING && score >= 65.0f) status = DegStatus::CRITICAL;

  g_profile.status = status;
  g_profile.score  = score;

  switch (status) {
    case DegStatus::OK:       strcpy(g_profile.statusStr, "OK");       break;
    case DegStatus::WARNING:  strcpy(g_profile.statusStr, "WARNING");  break;
    case DegStatus::CRITICAL: strcpy(g_profile.statusStr, "CRITICAL"); break;
  }

  g_profile.issues[0] = '\0';
  if (s_issueCnt == 0) {
    strcpy(g_profile.issues, "NONE");
  } else {
    for (uint8_t i = 0; i < s_issueCnt; i++) {
      if (i > 0) strncat(g_profile.issues, ",",
                          sizeof(g_profile.issues) - strlen(g_profile.issues) - 1);
      strncat(g_profile.issues, s_issues[i],
              sizeof(g_profile.issues) - strlen(g_profile.issues) - 1);
    }
  }
}

size_t serializeToJson(char* buf, size_t bufLen) {
  StaticJsonDocument<512> doc;

  doc["v"]            = FW_VERSION;
  doc["building_id"]  = BUILDING_ID;
  doc["scan_id"]      = g_sensor.scanId;
  doc["ts_ms"]        = g_sensor.timestampMs;
  doc["status"]       = g_profile.statusStr;
  doc["score"]        = serialized(String(g_profile.score, 1));

  // Позиция
  JsonObject pos = doc.createNestedObject("pos");
  pos["x"]   = serialized(String(g_pose.x, 2));
  pos["y"]   = serialized(String(g_pose.y, 2));
  pos["hdg"] = (int)g_pose.headingDeg;

  // Экологические
  JsonObject env = doc.createNestedObject("env");
  env["t"]  = serialized(String(g_sensor.temperature, 2));
  env["h"]  = serialized(String(g_sensor.humidity,    2));
  env["p"]  = serialized(String(g_sensor.pressure,    1));
  env["lx"] = (int)g_sensor.lightLux;

  // Структурные
  JsonObject stru = doc.createNestedObject("str");
  stru["roll"]  = serialized(String(g_sensor.tiltRoll,  2));
  stru["pitch"] = serialized(String(g_sensor.tiltPitch, 2));
  stru["ax"]    = serialized(String(g_sensor.accelX,    3));
  stru["ay"]    = serialized(String(g_sensor.accelY,    3));
  stru["az"]    = serialized(String(g_sensor.accelZ,    3));
  stru["vib"]   = g_sensor.vibration;

  // Дистанции
  JsonObject dist = doc.createNestedObject("dist");
  dist["f"] = (int)g_sensor.distFront;
  dist["b"] = (int)g_sensor.distBack;
  dist["l"] = (int)g_sensor.distLeft;
  dist["r"] = (int)g_sensor.distRight;

  JsonArray iss = doc.createNestedArray("issues");
  if (s_issueCnt == 0) {
    iss.add("NONE");
  } else {
    for (uint8_t i = 0; i < s_issueCnt; i++) iss.add(s_issues[i]);
  }

  return serializeJson(doc, buf, bufLen);
}

void generateProfile() {
  unsigned long now = millis();
  if (now - g_profileLastMs < IVMS_PROFILE) return;
  g_profileLastMs = now;

  if (g_state == RobotState::SCANNING) g_scanCounter++;
  assessDegradation();
  // Write directly into the shared buffer so getLastJsonBuffer() is always fresh
  size_t len = serializeToJson(s_lastJsonBuf, sizeof(s_lastJsonBuf));
  if (len == 0) {
    Serial.println(F("[PROF] JSON overflow — увеличь bufLen"));
    return;
  }
  Serial.print(F("[JSON] "));
  Serial.println(s_lastJsonBuf);
  httpPostTelemetry(s_lastJsonBuf, len);
}

const char* getLastJsonBuffer() { return s_lastJsonBuf; }

void assessAndCache() {
  assessDegradation();   // ensure fresh data even if called before generateProfile()
  serializeToJson(s_lastJsonBuf, sizeof(s_lastJsonBuf));
}
