#include <WiFi.h> 
#include <HTTPClient.h>
#include <SPIFFS.h>
#include "Config.h"

static bool     s_spiffsOk      = false;
static bool     s_backendOnline = false;
static uint32_t s_failCount     = 0;
static uint32_t s_successCount  = 0;

// ════════════════════════════════════════════════════════════════
//  initHTTPClient()  —  Вызывать в setup() (before WiFi OK for SPIFFS init)
// ════════════════════════════════════════════════════════════════
void initHTTPClient() {
  s_spiffsOk = SPIFFS.begin(true);   // true = форматировать если пуст
  if (s_spiffsOk) {
    size_t used  = SPIFFS.usedBytes();
    size_t total = SPIFFS.totalBytes();
    Serial.printf("[HTTP] SPIFFS OK  %u/%u bytes used\n", used, total);
  } else {
    Serial.println(F("[HTTP] SPIFFS FAIL — offline buffer disabled"));
  }
}

// ════════════════════════════════════════════════════════════════
//  httpPost()  —  Один HTTP POST запрос
//  Возвращает: HTTP status code, -1 = ошибка соединения
// ════════════════════════════════════════════════════════════════
static int httpPost(const char* url, const char* body, size_t len) {
  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-ID",   BUILDING_ID);
  http.addHeader("X-FW-Version",  FW_VERSION);
  http.setTimeout(HTTP_TIMEOUT_MS);

  int code = http.POST((uint8_t*)body, len);
  http.end();
  return code;
}

// ════════════════════════════════════════════════════════════════
//  writeToBuffer()  —  Запись в SPIFFS при отсутствии связи
// ════════════════════════════════════════════════════════════════
static void writeToBuffer(const char* json, size_t len) {
  if (!s_spiffsOk) return;

  // Проверка размера буфера
  size_t used = SPIFFS.usedBytes();
  if (used + len + 2 > SPIFFS_MAX_BYTES) {
    // Удаляем старый файл и начинаем заново (simple rotation)
    SPIFFS.remove(SPIFFS_BUFFER_FILE);
    Serial.println(F("[HTTP] Buffer full — rotated"));
  }

  File f = SPIFFS.open(SPIFFS_BUFFER_FILE, FILE_APPEND);
  if (!f) return;
  f.print(json);
  f.print('\n');
  f.close();
}

// ════════════════════════════════════════════════════════════════
//  flushBuffer()  —  Отправить накопленные пакеты при восстановлении
// ════════════════════════════════════════════════════════════════
static void flushBuffer() {
  if (!s_spiffsOk) return;
  if (!SPIFFS.exists(SPIFFS_BUFFER_FILE)) return;

  File f = SPIFFS.open(SPIFFS_BUFFER_FILE, FILE_READ);
  if (!f) return;

  uint32_t sent = 0, failed = 0;
  static char lineBuf[768];       // match max JSON output size

  while (f.available()) {
    size_t ln = f.readBytesUntil('\n', lineBuf, sizeof(lineBuf)-1);
    if (ln == 0) continue;
    lineBuf[ln] = '\0';

    // Skip malformed lines (truncated reads)
    if (lineBuf[0] != '{') continue;

    int code = httpPost(HTTP_BACKEND_URL, lineBuf, ln);
    if (code == 200 || code == 201) {
      sent++;
    } else {
      failed++;
      break;   // не пытаемся дальше если снова упало
    }
  }
  f.close();

  if (failed == 0) {
    // Все отправлены — чистим буфер
    SPIFFS.remove(SPIFFS_BUFFER_FILE);
    Serial.printf("[HTTP] Flushed %u buffered packets\n", sent);
  } else {
    Serial.printf("[HTTP] Flush partial: sent=%u failed=%u\n", sent, failed);
  }
}

// ════════════════════════════════════════════════════════════════
//  httpPostTelemetry()  —  Главная публичная функция
//  Вызывается из Profile.ino::generateProfile()
// ════════════════════════════════════════════════════════════════
void httpPostTelemetry(const char* json, size_t len) {
  // In AP mode the robot is the hotspot; WL_CONNECTED is for STA.
  // We can still reach HTTP_BACKEND_URL if a client connected and
  // the backend runs on that client. Skip the send if no station
  // is associated (no one to route the packet through).
  if (WiFi.softAPgetStationNum() == 0) {
    writeToBuffer(json, len);
    return;
  }

  // Попытка отправить
  int code = httpPost(HTTP_BACKEND_URL, json, len);

  if (code == 200 || code == 201) {
    s_backendOnline = true;
    s_successCount++;
    s_failCount = 0;

    // Flush буфера при восстановлении
    if (SPIFFS.exists(SPIFFS_BUFFER_FILE)) {
      flushBuffer();
    }
  } else {
    s_backendOnline = false;
    s_failCount++;
    if (s_failCount <= 3) {
      Serial.printf("[HTTP] POST failed code=%d  fail#%u\n", code, s_failCount);
    }
    writeToBuffer(json, len);
  }
}

// ════════════════════════════════════════════════════════════════
//  getHTTPStats()  —  Для OLED / Serial диагностики
// ════════════════════════════════════════════════════════════════
void getHTTPStats(bool& online, uint32_t& ok, uint32_t& fail) {
  online = s_backendOnline;
  ok     = s_successCount;
  fail   = s_failCount;
}

size_t getBufferBytes() {
  if (!s_spiffsOk || !SPIFFS.exists(SPIFFS_BUFFER_FILE)) return 0;
  File f = SPIFFS.open(SPIFFS_BUFFER_FILE, FILE_READ);
  size_t sz = f.size(); f.close(); return sz;
}
