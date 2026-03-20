#include <WiFi.h>
#include <WiFiUdp.h>

static WiFiUDP udp;
static bool wifiOK = false;

// ── initWiFi 
void initWiFi() {
  Serial.print(F("[WIFI] Connecting to "));
  Serial.print(F(WIFI_SSID));

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start >= WIFI_TIMEOUT_MS) {
      Serial.println(F("\n[WIFI] ERROR: timeout — UDP disabled."));
      wifiOK = false;
      return;
    }
    delay(250);
    Serial.print('.');
  }

  wifiOK = true;
  Serial.print(F("\n[WIFI] Connected. IP: "));
  Serial.println(WiFi.localIP());

  udp.begin(UDP_PORT);  
  Serial.println(F("[WIFI] UDP ready."));
}

// ── sendUDP 
//  Sends a JSON string as a UDP packet to UDP_HOST:UDP_PORT.
//  Safe to call every cycle — silently returns if WiFi is not up.
void sendUDP(const String& payload) {
  if (!wifiOK || WiFi.status() != WL_CONNECTED) return;

  if (!udp.beginPacket(UDP_HOST, UDP_PORT)) {
    Serial.println(F("[WIFI] UDP beginPacket failed."));
    return;
  }

  udp.print(payload);

  if (!udp.endPacket()) {
    Serial.println(F("[WIFI] UDP endPacket failed."));
  }
}
