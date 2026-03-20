//  Алгоритм работает по системе «начисления очков» (0–100):
//    - Каждая проблема добавляет очки в degradationScore
//    - Явные правила задают статус (OK / WARNING / CRITICAL)
//    - Правило MVP: влажность > 70% И вибрация → немедленно CRITICAL

#include <ArduinoJson.h>
unsigned long lastProfileUpdate = 0;
static int scanCount = 0;

// Forward declarations for round helpers (defined at bottom of file)
static float round1(float v);
static float round2(float v);
static float round3(float v);

static const char* issuesBuf[10];
static int issueCount = 0;

static void addIssue(const char* issue) {
  if (issueCount < 10) {
    issuesBuf[issueCount++] = issue;
  }
}

void assessDegradation() {
  float score = 0.0f;
  DegradationStatus status = STATUS_OK;
  issueCount = 0; 

  // ── ВЛАЖНОСТЬ 
  if (sensorData.humidity >= HUMIDITY_CRITICAL) {
    score  += 40.0f;
    status  = STATUS_CRITICAL;
    addIssue("HIGH_HUMIDITY");
  } else if (sensorData.humidity >= HUMIDITY_WARNING) {
    score += 20.0f;
    if (status < STATUS_WARNING) status = STATUS_WARNING;
    addIssue("ELEVATED_HUMIDITY");
  }

  // ── ВИБРАЦИЯ 
  if (sensorData.vibrationDetected) {
    score += 25.0f;
    addIssue("VIBRATION_DETECTED");

    if (sensorData.humidity >= HUMIDITY_CRITICAL) {
      score  += 15.0f; 
      status  = STATUS_CRITICAL;
      addIssue("HUMIDITY_VIBRATION_COMBO");
    } else {
      if (status < STATUS_WARNING) status = STATUS_WARNING;
    }
  }

  // ── ТЕМПЕРАТУРА 
  if (sensorData.temperature >= TEMP_CRITICAL_C) {
    score += 20.0f;
    if (status < STATUS_WARNING) status = STATUS_WARNING;
    addIssue("HIGH_TEMPERATURE");
  } else if (sensorData.temperature >= TEMP_WARNING_C) {
    score += 8.0f;
    addIssue("ELEVATED_TEMPERATURE");
  }

  // ── НАКЛОН 
  if (fabsf(sensorData.tiltAngle) >= TILT_CRITICAL_DEG) {
    score  += 35.0f;
    status  = STATUS_CRITICAL;
    addIssue("CRITICAL_TILT");
  } else if (fabsf(sensorData.tiltAngle) >= TILT_WARNING_DEG) {
    score += 10.0f;
    if (status < STATUS_WARNING) status = STATUS_WARNING;
    addIssue("TILT_DETECTED");
  }

  // ── ОСВЕЩЁННОСТЬ 
  if (sensorData.lightLux < LIGHT_LOW_LUX && sensorData.lightLux > 0.0f) {
    score += 5.0f;
    addIssue("LOW_LIGHT");
  }

  // ── SCORE-BASED STATUS (если явные правила не сработали) ──
  if (status == STATUS_OK && score >= 30.0f) {
    status = STATUS_WARNING;
  }
  if (status < STATUS_CRITICAL && score >= 60.0f) {
    status = STATUS_CRITICAL;
  }

  score = constrain(score, 0.0f, 100.0f);
  buildingProfile.status = status;
  buildingProfile.degradationScore = score;

  switch (status) {
    case STATUS_OK:       strcpy(buildingProfile.statusLabel, "OK");       break;
    case STATUS_WARNING:  strcpy(buildingProfile.statusLabel, "WARNING");  break;
    case STATUS_CRITICAL: strcpy(buildingProfile.statusLabel, "CRITICAL"); break;
  }

  buildingProfile.issues[0] = '\0';
  if (issueCount == 0) {
    strcpy(buildingProfile.issues, "NONE");
  } else {
    for (int i = 0; i < issueCount; i++) {
      if (i > 0) strncat(buildingProfile.issues, ",",
                         sizeof(buildingProfile.issues) - strlen(buildingProfile.issues) - 1);
      strncat(buildingProfile.issues, issuesBuf[i],
              sizeof(buildingProfile.issues) - strlen(buildingProfile.issues) - 1);
    }
  }
}

void generateJSONProfile() {
  unsigned long now = millis();
  if (now - lastProfileUpdate < INTERVAL_PROFILE_MS) return;
  lastProfileUpdate = now;

  assessDegradation();
  scanCount++;
  DynamicJsonDocument doc(1024);

  doc["building_id"]  = "BILB_001";
  doc["scan_id"]      = scanCount;
  doc["timestamp_ms"] = sensorData.timestamp;
  doc["status"]       = buildingProfile.statusLabel;
  doc["score"]        = (int)(buildingProfile.degradationScore * 10 + 0.5f) / 10.0f;

  JsonObject env = doc.createNestedObject("environmental");
  env["temperature_c"] = round2(sensorData.temperature);
  env["humidity_pct"]  = round2(sensorData.humidity);
  env["pressure_hpa"]  = round1(sensorData.pressure);
  env["light_lux"]     = round1(sensorData.lightLux);

  JsonObject struc = doc.createNestedObject("structural");
  struc["tilt_deg"]  = round2(sensorData.tiltAngle);
  struc["accel_x"]   = round3(sensorData.accelX);
  struc["accel_y"]   = round3(sensorData.accelY);
  struc["accel_z"]   = round3(sensorData.accelZ);
  struc["vibration"] = sensorData.vibrationDetected;

  JsonObject spatial = doc.createNestedObject("spatial");
  spatial["front_cm"] = round1(sensorData.distFront);
  spatial["back_cm"]  = round1(sensorData.distBack);
  spatial["left_cm"]  = round1(sensorData.distLeft);
  spatial["right_cm"] = round1(sensorData.distRight);
  spatial["edge"]     = sensorData.edgeDetected;

  JsonArray issArr = doc.createNestedArray("issues");
  if (issueCount == 0) {
    issArr.add("NONE");
  } else {
    for (int i = 0; i < issueCount; i++) {
      issArr.add(issuesBuf[i]);
    }
  }

  // ── Serial output ─────────────────────────────────────
  Serial.print(F("[JSON] "));
  serializeJson(doc, Serial);
  Serial.println();

  Serial.println(F("[JSON_PRETTY]"));
  serializeJsonPretty(doc, Serial);
  Serial.println();

  // ── UDP telemetry ──────────────────────────────────────
  String jsonOut;
  jsonOut.reserve(512);
  serializeJson(doc, jsonOut);
  sendUDP(jsonOut);
}

static float round1(float v) { return roundf(v * 10.0f)  / 10.0f; }
static float round2(float v) { return roundf(v * 100.0f) / 100.0f; }
static float round3(float v) { return roundf(v * 1000.0f)/ 1000.0f; }