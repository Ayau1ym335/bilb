"""
ingestion/bridge.py  —  Serial / WebSocket → DB Bridge
═══════════════════════════════════════════════════════
Задача: слушать ESP32 локально (Serial или WebSocket) и
писать данные в ту же БД что и FastAPI.

Два режима (переключается через BRIDGE_MODE в .env):
  · serial     — читать [JSON] строки из USB-Serial
  · websocket  — подключиться к ESP32 WS (ws://192.168.4.1:81)
  · demo       — генерировать синтетические данные (без железа)

Запуск:
  python -m ingestion.bridge                  # из корня проекта
  python -m ingestion.bridge --mode serial --port /dev/ttyUSB0
  python -m ingestion.bridge --mode websocket
  python -m ingestion.bridge --mode demo

▶ НАСТРОЙТЕ в .env:
  BRIDGE_MODE=serial             # serial | websocket | demo
  SERIAL_PORT=/dev/ttyUSB0       # Windows: COM3
  SERIAL_BAUD=115200
  WS_URL=ws://192.168.4.1:81
  DEMO_INTERVAL_S=2.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import random
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import ValidationError

# Относительный импорт работает при запуске через python -m
from .database import create_tables, db_session
from .repository import (
    get_or_create_session,
    insert_reading,
    refresh_building_aggregates,
)
from .schemas import TelemetryPayload

load_dotenv()
log = logging.getLogger("bilb.bridge")

# ── Настройки ─────────────────────────────────────────────────
BRIDGE_MODE:      str   = os.getenv("BRIDGE_MODE",      "serial")
SERIAL_PORT:      str   = os.getenv("SERIAL_PORT",      "/dev/ttyUSB0")   # ▶ НАСТРОЙТЕ
SERIAL_BAUD:      int   = int(os.getenv("SERIAL_BAUD",  "115200"))
WS_URL:           str   = os.getenv("WS_URL",           "ws://192.168.4.1:81")
DEMO_INTERVAL_S:  float = float(os.getenv("DEMO_INTERVAL_S", "2.0"))
BUILDING_ID:      str   = os.getenv("BUILDING_ID",      "BILB_001")

# Каждые N пакетов пересчитываем агрегаты
AGGREGATE_EVERY_N: int  = int(os.getenv("AGGREGATE_EVERY_N", "10"))

# Переподключение при разрыве
RECONNECT_DELAY_S: float = 5.0
MAX_RECONNECT:     int   = 999


# ══════════════════════════════════════════════════════════════
#  Общая логика: разбор пакета → сохранение в БД
# ══════════════════════════════════════════════════════════════
_packet_counter: int = 0


async def process_packet(raw: str) -> bool:
    """
    Принимает сырую строку (от Serial или WS).
    Ищет JSON: строки с префиксом [JSON], или чистый JSON.
    Возвращает True если пакет успешно сохранён.
    """
    global _packet_counter

    raw = raw.strip()
    if not raw:
        return False

    # Извлекаем JSON из строки вида "[JSON] {...}"
    if raw.startswith("[JSON]"):
        raw = raw[len("[JSON]"):].strip()

    # Отбрасываем строки не являющиеся JSON
    if not raw.startswith("{"):
        return False

    # Parse JSON once and reuse the result.
    # WS-сервер шлёт ack/state/error/wp_reached — не сохраняем в БД.
    # Telemetry пакеты: либо нет поля "type", либо type=="telem".
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("JSON decode error: %s | raw=%.80s", e, raw)
        return False

    _pkt_type = data.get("type", "")
    if _pkt_type and _pkt_type != "telem":
        return False   # ack, state, error, wp_reached, mission_complete

    # Валидация через Pydantic
    try:
        payload = TelemetryPayload.model_validate(data)
    except ValidationError as e:
        log.warning("Payload validation error: %s", e.errors()[0])
        return False

    # Запись в БД
    try:
        async with db_session() as db:
            session = await get_or_create_session(
                db, payload.building_id, fw_version=payload.v
            )
            reading = await insert_reading(
                db, payload, session_id=session.id, raw_json=raw[:2000]
            )
            _packet_counter += 1

            if _packet_counter % AGGREGATE_EVERY_N == 0:
                await refresh_building_aggregates(db, payload.building_id)

            # Человекочитаемый лог
            pos_str = (
                f"X{payload.pos.x:.1f}Y{payload.pos.y:.1f}"
                if payload.pos else "pos=?"
            )
            status_icon = {"OK": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}.get(
                reading.status or "", "⚪"
            )
            log.info(
                "[%s] #%d %s %s  score=%.1f  T=%.1f° H=%.1f%%",
                payload.building_id,
                _packet_counter,
                status_icon,
                pos_str,
                reading.score or 0,
                payload.env.t if payload.env else 0,
                payload.env.h if payload.env else 0,
            )
            return True

    except Exception as e:
        log.error("DB write failed: %s", e, exc_info=True)
        return False


# ══════════════════════════════════════════════════════════════
#  РЕЖИМ 1: Serial
# ══════════════════════════════════════════════════════════════
async def run_serial(port: str, baud: int) -> None:
    """
    Читает строки из Serial порта ESP32.
    Обрабатывает только строки с префиксом [JSON].
    Автоматически переподключается при разрыве.
    """
    try:
        import serial_asyncio   # pip install pyserial-asyncio
    except ImportError:
        log.error("Install: pip install pyserial-asyncio")
        sys.exit(1)

    attempts = 0
    while attempts < MAX_RECONNECT:
        try:
            log.info("Connecting to %s @ %d baud...", port, baud)
            reader, _ = await serial_asyncio.open_serial_connection(
                url=port, baudrate=baud
            )
            attempts = 0
            log.info("Serial connected. Listening...")

            while True:
                line = await asyncio.wait_for(
                    reader.readline(), timeout=30.0
                )
                text = line.decode("utf-8", errors="replace")
                await process_packet(text)

        except asyncio.TimeoutError:
            log.warning("Serial timeout — no data for 30s. Is ESP32 running?")

        except Exception as e:
            attempts += 1
            log.error("Serial error (%d/%d): %s", attempts, MAX_RECONNECT, e)
            await asyncio.sleep(RECONNECT_DELAY_S)


# ══════════════════════════════════════════════════════════════
#  РЕЖИМ 2: WebSocket
#  Подключается к ESP32 как клиент (ESP32 = сервер)
# ══════════════════════════════════════════════════════════════
async def run_websocket(url: str) -> None:
    """
    Подключается к WebSocket серверу ESP32 (ws://192.168.4.1:81).
    Работает параллельно с control.html — оба могут быть подключены.
    """
    try:
        import websockets
    except ImportError:
        log.error("Install: pip install websockets")
        sys.exit(1)

    attempts = 0
    while attempts < MAX_RECONNECT:
        try:
            log.info("Connecting to WS %s ...", url)
            async with websockets.connect(
                url,
                ping_interval=10,
                ping_timeout=5,
                open_timeout=10,
            ) as ws:
                attempts = 0
                log.info("WebSocket connected to ESP32")

                async for message in ws:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8", errors="replace")
                    await process_packet(message)

        except Exception as e:
            attempts += 1
            log.error("WS error (%d/%d): %s", attempts, MAX_RECONNECT, e)
            log.info("Reconnecting in %.0fs...", RECONNECT_DELAY_S)
            await asyncio.sleep(RECONNECT_DELAY_S)


# ══════════════════════════════════════════════════════════════
#  РЕЖИМ 3: Demo  —  синтетические данные без ESP32
# ══════════════════════════════════════════════════════════════
class DemoGenerator:
    """
    Генерирует реалистичные данные:
    · Постепенный дрейф влажности (синусоида + шум)
    · Случайные события вибрации при высокой влажности
    · Круговой маршрут по сетке (dead-reckoning)
    """

    def __init__(self, building_id: str = BUILDING_ID):
        self.building_id = building_id
        self.t           = 0.0    # «время» симуляции
        self.scan_id     = 0
        # Начальная позиция
        self.x           = 5.0
        self.y           = 5.0
        self.heading     = 0.0

    def next(self) -> dict:
        self.t      += 0.1
        self.scan_id += 1

        # Влажность: дрейф + шум
        humidity = 50.0 + 25.0 * math.sin(self.t / 20.0) + random.gauss(0, 2)
        humidity = max(10.0, min(100.0, humidity))

        temperature = 22.0 + 6.0 * math.sin(self.t / 15.0) + random.gauss(0, 0.5)
        pressure    = 1013.2 + random.gauss(0, 1.5)
        light       = max(0.0, 180.0 + 100.0 * math.sin(self.t / 10.0) + random.gauss(0, 10))

        tilt_roll   = 1.5 * math.sin(self.t / 8.0) + random.gauss(0, 0.2)
        tilt_pitch  = 1.0 * math.cos(self.t / 12.0) + random.gauss(0, 0.15)

        vibration   = humidity > 65 and random.random() > 0.6

        # Движение по кругу
        self.heading  = (self.t * 12.0) % 360.0
        rad = math.radians(self.heading - 90)
        self.x = 10.0 + 4.0 * math.cos(self.t * 0.3)
        self.y = 10.0 + 4.0 * math.sin(self.t * 0.3)

        # Scoring — зеркало profile.ino::assessDegradation()
        # порядок: накопить score → clamp → эскалировать статус
        score  = 0.0
        status = "OK"
        issues = []

        if humidity >= 70:
            score += 40.0; issues.append("HIGH_HUMIDITY")
        elif humidity >= 55:
            score += 20.0; issues.append("ELEVATED_HUMIDITY")

        if vibration:
            score += 25.0; issues.append("VIBRATION_DETECTED")
            if humidity >= 70:
                score += 15.0; issues.append("STRUCTURAL_RISK_COMBO")

        if temperature >= 40:
            score += 20.0; issues.append("HIGH_TEMPERATURE")
        elif temperature >= 30:
            score += 8.0

        if abs(tilt_roll) >= 15:
            score += 35.0; issues.append("CRITICAL_STRUCTURAL_TILT")
        elif abs(tilt_roll) >= 5:
            score += 12.0; issues.append("TILT_DETECTED")

        if 0 < light < 100:
            score += 5.0; issues.append("POOR_DAYLIGHTING")

        # Clamp FIRST (как в прошивке: constrain перед эскалацией)
        score = min(score, 100.0)

        # Escalate status
        if score >= 65:   status = "CRITICAL"
        elif score >= 30: status = "WARNING"
        else:             status = "OK"

        return {
            "v":           "2.1.0-demo",
            "building_id": self.building_id,
            "scan_id":     self.scan_id,
            "ts_ms":       int(time.time() * 1000),
            "status":      status,
            # ArduinoJson serialized(String(val,N)) → строки, зеркалим это
            "score":       f"{score:.1f}",
            "pos": {
                "x":   f"{self.x:.2f}",
                "y":   f"{self.y:.2f}",
                "hdg": int(self.heading),
            },
            "env": {
                "t":  f"{temperature:.2f}",
                "h":  f"{humidity:.2f}",
                "p":  f"{pressure:.1f}",
                "lx": int(light),
            },
            "str": {
                "roll":  f"{tilt_roll:.2f}",
                "pitch": f"{tilt_pitch:.2f}",
                "ax": f"{random.gauss(0.1,  0.05):.3f}",
                "ay": f"{random.gauss(-0.05, 0.03):.3f}",
                "az": f"{random.gauss(9.78,  0.02):.3f}",
                "vib": vibration,
            },
            "dist": {
                "f": round(random.uniform(20, 200), 1),
                "b": round(random.uniform(30, 400), 1),
                "l": round(random.uniform(15, 150), 1),
                "r": round(random.uniform(20, 180), 1),
            },
            "issues": issues,
        }


async def run_demo(interval_s: float) -> None:
    gen = DemoGenerator()
    log.info(
        "Demo mode: generating telemetry every %.1fs for building '%s'",
        interval_s, BUILDING_ID,
    )
    while True:
        packet = gen.next()
        raw = "[JSON] " + json.dumps(packet)
        ok = await process_packet(raw)
        if ok:
            # score, env, and pos values are serialized as strings (mirrors
            # ArduinoJson serialized(String(val, N))) — cast to float before
            # using float format specs to avoid TypeError.
            print(
                f"\r[DEMO] Scan#{packet['scan_id']:4d} | "
                f"{packet['status']:<8} | "
                f"Score={float(packet['score']):5.1f} | "
                f"H={float(packet['env']['h']):5.1f}% | "
                f"T={float(packet['env']['t']):5.1f}°C | "
                f"X={float(packet['pos']['x']):.1f} Y={float(packet['pos']['y']):.1f}",
                end="", flush=True,
            )
        await asyncio.sleep(interval_s)


# ══════════════════════════════════════════════════════════════
#  Entrypoint
# ══════════════════════════════════════════════════════════════
async def main(args: argparse.Namespace) -> None:
    # Инициализация БД
    await create_tables()

    mode = args.mode or BRIDGE_MODE
    log.info("Bridge starting in mode: %s", mode.upper())

    if mode == "serial":
        await run_serial(args.port or SERIAL_PORT, args.baud or SERIAL_BAUD)
    elif mode == "websocket":
        await run_websocket(args.url or WS_URL)
    elif mode == "demo":
        await run_demo(args.interval or DEMO_INTERVAL_S)
    else:
        log.error("Unknown mode: %s  (use: serial | websocket | demo)", mode)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="BILB Data Bridge")
    parser.add_argument("--mode",     choices=["serial", "websocket", "demo"],
                        help="Bridge mode (overrides BRIDGE_MODE env)")
    parser.add_argument("--port",     help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--baud",     type=int, help="Serial baud rate (default 115200)")
    parser.add_argument("--url",      help="WebSocket URL (default ws://192.168.4.1:81)")
    parser.add_argument("--interval", type=float, help="Demo interval seconds (default 2.0)")
    args = parser.parse_args()

    print("=" * 56)
    print("  BILB Data Bridge  v2.1.0")
    print("=" * 56)

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n[BRIDGE] Stopped by user")
