#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include "config.h"

static WebSocketsServer s_ws(WS_PORT);
static int              s_activeClient = -1;
static unsigned long    s_telemLastMs  = 0;

// Forward declarations
void onWsEvent(uint8_t cId, WStype_t type, uint8_t* payload, size_t len);

extern void motorForward(uint8_t);
extern void motorBackward(uint8_t);
extern void motorTurnLeft(uint8_t);
extern void motorTurnRight(uint8_t);
extern void motorStop();
extern bool wpAddPoint(float, float);
extern void wpClear();
extern bool wpStart();
extern bool wpIsRunning();
extern uint8_t wpCurrentIdx();
extern uint8_t wpCount();
extern void assessAndCache();
extern const char* getLastJsonBuffer();

extern void setRobotState(RobotState s);
void initWiFiAP() {
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_AP);

  IPAddress ip, gw, sn;
  ip.fromString(AP_IP_ADDR);
  gw.fromString(AP_GATEWAY);
  sn.fromString(AP_SUBNET);
  WiFi.softAPConfig(ip, gw, sn);

  bool ok = WiFi.softAP(
    WIFI_AP_SSID, WIFI_AP_PASS,
    WIFI_AP_CHANNEL,
    0,
    WIFI_AP_MAX_CONN
  );

  if (!ok) {
    Serial.println(F("[WiFi] AP FAILED — перезагрузка через 3 с"));
    delay(3000); ESP.restart();
  }

  Serial.printf("[WiFi] AP  SSID=%-15s  IP=%s\n",
                WIFI_AP_SSID, WiFi.softAPIP().toString().c_str());
  Serial.printf("[WiFi] AP  PASS=%-15s  CH=%d\n",
                WIFI_AP_PASS, WIFI_AP_CHANNEL);
}

void initWebSocket() {
  s_ws.begin();
  s_ws.onEvent(onWsEvent);
  s_ws.setReconnectInterval(3000);
  s_ws.enableHeartbeat(5000, 2000, 3);   
  Serial.printf("[WS] Server on port %d\n", WS_PORT);
}

void tickWebSocket() {
  s_ws.loop();
  unsigned long now = millis();
  if (s_activeClient >= 0 && now - s_telemLastMs >= IVMS_TELEMETRY) {
    s_telemLastMs = now;
    pushTelemetry();
  }
}

void onWsEvent(uint8_t cId, WStype_t type, uint8_t* payload, size_t len) {
  switch (type) {

    case WStype_CONNECTED: {
      IPAddress clientIp = s_ws.remoteIP(cId);
      Serial.printf("[WS] Client #%d connected from %s\n",
                    cId, clientIp.toString().c_str());
      s_activeClient = cId;
      wsSendAck(cId, "CONNECTED");
      wsSendState(cId, g_state);
      break;
    }

    case WStype_DISCONNECTED:
      Serial.printf("[WS] Client #%d disconnected\n", cId);
      if (s_activeClient == (int)cId) {
        s_activeClient = -1;
        if (g_state == RobotState::MANUAL) {
          motorStop();
          setRobotState(RobotState::IDLE);
        }
      }
      break;

    case WStype_TEXT:
      dispatchCommand(cId, (const char*)payload, len);
      break;

    case WStype_PING:
      break;

    case WStype_ERROR:
      Serial.printf("[WS] Error client #%d\n", cId);
      break;

    default: break;
  }
}

// ════════════════════════════════════════════════════════════════
//  dispatchCommand()  —  Разбор и исполнение команды JSON
// ════════════════════════════════════════════════════════════════
void dispatchCommand(uint8_t cId, const char* json, size_t len) {
  StaticJsonDocument<256> doc;
  DeserializationError e = deserializeJson(doc, json, len);
  if (e) {
    Serial.printf("[WS] JSON err: %s\n", e.c_str());
    wsSendError(cId, "JSON_PARSE_ERROR");
    return;
  }

  const char* cmd = doc["cmd"] | "";

  // ── Движение (только в MANUAL) ───────────────────────────────
  if (g_state == RobotState::MANUAL) {
    if      (!strcmp(cmd,"FORWARD"))  { motorForward(MOTOR_SPEED_FULL);  wsSendAck(cId,cmd); return; }
    else if (!strcmp(cmd,"BACKWARD")) { motorBackward(MOTOR_SPEED_FULL); wsSendAck(cId,cmd); return; }
    else if (!strcmp(cmd,"LEFT"))     { motorTurnLeft(MOTOR_SPEED_TURN); wsSendAck(cId,cmd); return; }
    else if (!strcmp(cmd,"RIGHT"))    { motorTurnRight(MOTOR_SPEED_TURN);wsSendAck(cId,cmd); return; }
  }
  if (!strcmp(cmd,"STOP")) {
    motorStop(); wpClear();
    setRobotState(RobotState::IDLE);
    wsSendAck(cId,"STOP"); return;
  }

  // ── Смена режима ─────────────────────────────────────────────
  if (!strcmp(cmd,"MODE")) {
    const char* val = doc["val"] | "MANUAL";
    if      (!strcmp(val,"MANUAL"))  { motorStop(); setRobotState(RobotState::MANUAL);   }
    else if (!strcmp(val,"AUTO"))    { setRobotState(RobotState::SCANNING); }
    else if (!strcmp(val,"SCAN"))    { setRobotState(RobotState::SCANNING); }
    else { wsSendError(cId,"UNKNOWN_MODE"); return; }
    wsSendAck(cId, cmd); return;
  }

  // ── Waypoints ────────────────────────────────────────────────
  if (!strcmp(cmd,"WAYPOINT")) {
    float x = doc["x"] | g_pose.x;
    float y = doc["y"] | g_pose.y;
    x = constrain(x, 0.0f, (float)(GRID_COLS-1));
    y = constrain(y, 0.0f, (float)(GRID_ROWS-1));
    if (wpAddPoint(x, y)) {
      char ack[64];
      snprintf(ack, sizeof(ack),
               "{\"type\":\"ack\",\"cmd\":\"WAYPOINT\",\"idx\":%d,\"x\":%.1f,\"y\":%.1f}",
               wpCount()-1, x, y);
      s_ws.sendTXT(cId, ack);
    } else {
      wsSendError(cId,"WP_QUEUE_FULL");
    }
    return;
  }

  if (!strcmp(cmd,"RUN_WAYPOINTS")) {
    if (wpStart()) {
      setRobotState(RobotState::WAYPOINT);
      wsSendAck(cId,"RUN_WAYPOINTS");
    } else {
      wsSendError(cId,"NO_WAYPOINTS");
    }
    return;
  }

  if (!strcmp(cmd,"CLEAR_WAYPOINTS")) {
    wpClear();
    setRobotState(RobotState::IDLE);
    wsSendAck(cId,"CLEAR_WAYPOINTS");
    return;
  }

  // ── Сброс позиции ────────────────────────────────────────────
  if (!strcmp(cmd,"RESET_POSE")) {
    g_pose.x          = doc["x"]   | (float)(GRID_COLS/2);
    g_pose.y          = doc["y"]   | (float)(GRID_ROWS/2);
    g_pose.headingDeg = doc["hdg"] | 0.0f;
    wsSendAck(cId,"RESET_POSE"); return;
  }

  // ── Принудительный запрос статуса ────────────────────────────
  if (!strcmp(cmd,"GET_STATUS")) {
    assessAndCache();
    wsSendTelemetry(cId, getLastJsonBuffer());
    return;
  }

  wsSendError(cId,"UNKNOWN_CMD");
}

// ════════════════════════════════════════════════════════════════
//  pushTelemetry()  —  Broadcast текущего состояния всем клиентам
// ════════════════════════════════════════════════════════════════
void pushTelemetry() {
  // Build complete telemetry JSON in one pass — no double parse/serialize.
  assessDegradation();

  StaticJsonDocument<768> doc;

  doc["type"]        = "telem";
  doc["v"]           = FW_VERSION;
  doc["building_id"] = BUILDING_ID;
  doc["scan_id"]     = g_sensor.scanId;
  doc["ts_ms"]       = g_sensor.timestampMs;
  doc["status"]      = g_profile.statusStr;
  doc["score"]       = serialized(String(g_profile.score, 1));

  static const char* stateNames[] = {"IDLE","SCANNING","MANUAL","WAYPOINT","EMERGENCY"};
  uint8_t si = (uint8_t)g_state;
  doc["state"] = (si < 5) ? stateNames[si] : "UNKNOWN";

  JsonObject pos = doc.createNestedObject("pos");
  pos["x"]   = serialized(String(g_pose.x, 2));
  pos["y"]   = serialized(String(g_pose.y, 2));
  pos["hdg"] = (int)g_pose.headingDeg;

  JsonObject env = doc.createNestedObject("env");
  env["t"]  = serialized(String(g_sensor.temperature, 2));
  env["h"]  = serialized(String(g_sensor.humidity,    2));
  env["p"]  = serialized(String(g_sensor.pressure,    1));
  env["lx"] = (int)g_sensor.lightLux;

  JsonObject stru = doc.createNestedObject("str");
  stru["roll"]  = serialized(String(g_sensor.tiltRoll,  2));
  stru["pitch"] = serialized(String(g_sensor.tiltPitch, 2));
  stru["vib"]   = g_sensor.vibration;

  JsonObject dist = doc.createNestedObject("dist");
  dist["f"] = (int)g_sensor.distFront;
  dist["b"] = (int)g_sensor.distBack;
  dist["l"] = (int)g_sensor.distLeft;
  dist["r"] = (int)g_sensor.distRight;

  doc["wp_idx"]   = wpCurrentIdx();
  doc["wp_total"] = wpCount();
  doc["wp_run"]   = wpIsRunning();

  static char outBuf[768];
  size_t outLen = serializeJson(doc, outBuf, sizeof(outBuf));
  if (outLen > 0) s_ws.broadcastTXT(outBuf, outLen);
}

// ── Уведомление о достижении точки ───────────────────────────
void wsNotifyWpReached(uint8_t idx) {
  if (s_activeClient < 0) return;
  char buf[64];
  snprintf(buf, sizeof(buf), "{\"type\":\"wp_reached\",\"idx\":%d}", idx);
  s_ws.sendTXT(s_activeClient, buf);
}

void wsNotifyMissionComplete() {
  if (s_activeClient < 0) return;
  s_ws.sendTXT(s_activeClient,
               "{\"type\":\"mission_complete\"}");
}

static void wsSendTelemetry(uint8_t cId, const char* json) {
  s_ws.sendTXT(cId, json);
}

void wsSendAck(uint8_t cId, const char* cmd) {
  char buf[80];
  snprintf(buf, sizeof(buf), "{\"type\":\"ack\",\"cmd\":\"%s\"}", cmd);
  s_ws.sendTXT(cId, buf);
}

void wsSendError(uint8_t cId, const char* msg) {
  char buf[120];
  snprintf(buf, sizeof(buf), "{\"type\":\"error\",\"msg\":\"%s\"}", msg);
  s_ws.sendTXT(cId, buf);
}

void wsSendState(uint8_t cId, RobotState st) {
  static const char* names[] = {"IDLE","SCANNING","MANUAL","WAYPOINT","EMERGENCY"};
  uint8_t si = (uint8_t)st;
  char buf[80];
  snprintf(buf, sizeof(buf), "{\"type\":\"state\",\"val\":\"%s\"}",
           (si < 5) ? names[si] : "UNKNOWN");
  s_ws.sendTXT(cId, buf);
}

int wsActiveClient() { return s_activeClient; }
