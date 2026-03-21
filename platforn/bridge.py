import argparse
import json
import math
import random
import threading
import time
import os
from datetime import datetime, timezone

import serial
from dotenv import load_dotenv
from sqlalchemy import (Column, DateTime, Float, Integer, String,
                        Text, create_engine, desc)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/bilb.db")

# Гарантируем, что папка data существует
os.makedirs("data", exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    """
    Одна запись с робота. Соответствует JSON-схеме из ESP32.
    Схема согласована (День 1, Точка синхронизации).
    """
    __tablename__ = "sensor_readings"

    id           = Column(Integer, primary_key=True, index=True)
    building_id  = Column(String(50), index=True, default="BILB_001")
    scan_id      = Column(Integer)
    received_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Environmental (BME280)
    temperature  = Column(Float, nullable=True)
    humidity     = Column(Float, nullable=True)
    pressure     = Column(Float, nullable=True)
    light_lux    = Column(Float, nullable=True)

    # Structural (MPU6050 + SW-420)
    tilt_deg     = Column(Float, nullable=True)
    accel_x      = Column(Float, nullable=True)
    accel_y      = Column(Float, nullable=True)
    accel_z      = Column(Float, nullable=True)
    vibration    = Column(Integer, default=0)   # 0 / 1

    # Spatial (HC-SR04)
    dist_front   = Column(Float, nullable=True)
    dist_back    = Column(Float, nullable=True)
    dist_left    = Column(Float, nullable=True)
    dist_right   = Column(Float, nullable=True)
    edge         = Column(Integer, default=0)

    # Assessment (заполняется после ML-обработки)
    status       = Column(String(20), default="UNKNOWN")
    score        = Column(Float, nullable=True)
    issues       = Column(Text, nullable=True)    # JSON-массив строк


class BuildingProfile(Base):
    """
    Агрегированный «Цифровой профиль» объекта.
    Обновляется после каждой сессии сканирования.
    """
    __tablename__ = "building_profiles"

    id               = Column(Integer, primary_key=True, index=True)
    building_id      = Column(String(50), unique=True, index=True)
    name             = Column(String(200))
    city             = Column(String(100))
    year_built       = Column(Integer)
    updated_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    avg_temperature  = Column(Float, nullable=True)
    avg_humidity     = Column(Float, nullable=True)
    avg_light        = Column(Float, nullable=True)
    max_tilt         = Column(Float, nullable=True)
    vibration_events = Column(Integer, default=0)
    total_scans      = Column(Integer, default=0)

    overall_status   = Column(String(20), default="UNKNOWN")
    degradation_score = Column(Float, default=0.0)
    scenarios_json   = Column(Text, nullable=True)    # JSON от Gemini
    sustainability_json = Column(Text, nullable=True) # CO2 расчёты


# Создаём таблицы при первом запуске
Base.metadata.create_all(bind=engine)


# ──────────────────────────────────────────────────────────────────
#  JSON Schema (согласовано с ESP32 прошивкой)
# ──────────────────────────────────────────────────────────────────
AGREED_SCHEMA = {
    "building_id": str,
    "scan_id": int,
    "timestamp_ms": int,
    "status": str,
    "score": float,
    "environmental": {
        "temperature_c": float,
        "humidity_pct": float,
        "pressure_hpa": float,
        "light_lux": float,
    },
    "structural": {
        "tilt_deg": float,
        "accel_x": float,
        "accel_y": float,
        "accel_z": float,
        "vibration": bool,
    },
    "spatial": {
        "front_cm": float,
        "back_cm": float,
        "left_cm": float,
        "right_cm": float,
        "edge": bool,
    },
    "issues": list,
}


def parse_esp32_json(raw_line: str) -> dict | None:
    """
    Парсит строку вида '[JSON] {...}'.
    Возвращает dict или None при ошибке.
    """
    line = raw_line.strip()
    if not line.startswith("[JSON]"):
        return None
    try:
        json_str = line[len("[JSON]"):].strip()
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[BRIDGE] JSON parse error: {e} | raw: {line[:80]}")
        return None


def json_to_reading(data: dict) -> SensorReading:
    """
    Маппинг из согласованной JSON-схемы ESP32 → ORM-модель.
    Безопасен к отсутствию любого поля (graceful degradation).
    """
    env  = data.get("environmental", {})
    struc = data.get("structural", {})
    spat = data.get("spatial", {})
    issues = data.get("issues", [])

    return SensorReading(
        building_id  = data.get("building_id", "BILB_001"),
        scan_id      = data.get("scan_id", 0),
        received_at  = datetime.now(timezone.utc),

        temperature  = env.get("temperature_c"),
        humidity     = env.get("humidity_pct"),
        pressure     = env.get("pressure_hpa"),
        light_lux    = env.get("light_lux"),

        tilt_deg     = struc.get("tilt_deg"),
        accel_x      = struc.get("accel_x"),
        accel_y      = struc.get("accel_y"),
        accel_z      = struc.get("accel_z"),
        vibration    = int(struc.get("vibration", False)),

        dist_front   = spat.get("front_cm"),
        dist_back    = spat.get("back_cm"),
        dist_left    = spat.get("left_cm"),
        dist_right   = spat.get("right_cm"),
        edge         = int(spat.get("edge", False)),

        status       = data.get("status", "UNKNOWN"),
        score        = data.get("score"),
        issues       = json.dumps(issues),
    )


# ──────────────────────────────────────────────────────────────────
#  Demo Data Generator (День 1: фронтенд не ждёт ESP32)
# ──────────────────────────────────────────────────────────────────
_demo_scan_counter = 0


def generate_demo_reading() -> dict:
    """
    Генерирует реалистичные фиктивные данные для демо-режима.
    Имитирует постепенное ухудшение состояния здания.
    """
    global _demo_scan_counter
    _demo_scan_counter += 1
    t = _demo_scan_counter

    # Симулируем дрейф параметров со случайным шумом
    humidity    = 45.0 + 30.0 * math.sin(t / 20.0) + random.gauss(0, 3)
    temperature = 22.0 + 8.0  * math.sin(t / 15.0) + random.gauss(0, 1)
    tilt        = 2.0  + 1.5  * math.sin(t / 30.0) + random.gauss(0, 0.3)
    vibration   = humidity > 65 and random.random() > 0.4

    # Авто-статус (имитирует алгоритм ESP32)
    if humidity > 70 and vibration:
        status, score = "CRITICAL", random.uniform(70, 95)
    elif humidity > 55 or abs(tilt) > 5:
        status, score = "WARNING", random.uniform(30, 60)
    else:
        status, score = "OK", random.uniform(0, 25)

    issues = []
    if humidity > 70:  issues.append("HIGH_HUMIDITY")
    if vibration:      issues.append("VIBRATION_DETECTED")
    if abs(tilt) > 5:  issues.append("TILT_DETECTED")

    return {
        "building_id": os.getenv("BUILDING_ID", "BILB_001"),
        "scan_id": t,
        "timestamp_ms": int(time.time() * 1000),
        "status": status,
        "score": round(score, 1),
        "environmental": {
            "temperature_c": round(temperature, 2),
            "humidity_pct":  round(max(10, min(100, humidity)), 2),
            "pressure_hpa":  round(1013.2 + random.gauss(0, 2), 1),
            "light_lux":     round(max(0, 150 + 100 * math.sin(t / 10) + random.gauss(0, 15)), 1),
        },
        "structural": {
            "tilt_deg":  round(tilt, 2),
            "accel_x":   round(random.gauss(0.1, 0.05), 3),
            "accel_y":   round(random.gauss(-0.05, 0.03), 3),
            "accel_z":   round(random.gauss(9.78, 0.02), 3),
            "vibration": vibration,
        },
        "spatial": {
            "front_cm": round(random.uniform(20, 200), 1),
            "back_cm":  round(random.uniform(30, 999), 1),
            "left_cm":  round(random.uniform(15, 150), 1),
            "right_cm": round(random.uniform(25, 180), 1),
            "edge":     random.random() < 0.02,
        },
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────
#  Bridge Loop — Serial или Demo
# ──────────────────────────────────────────────────────────────────
_running = False


def serial_loop(port: str, baud: int):
    """Основной цикл чтения из Serial-порта ESP32."""
    print(f"[BRIDGE] Connecting to {port} @ {baud}bps...")
    try:
        ser = serial.Serial(port, baud, timeout=2)
        print(f"[BRIDGE] Connected. Listening...")
        while _running:
            try:
                line = ser.readline().decode("utf-8", errors="replace")
                data = parse_esp32_json(line)
                if data:
                    _save_reading(data)
            except serial.SerialException as e:
                print(f"[BRIDGE] Serial error: {e}. Retrying in 5s...")
                time.sleep(5)
    except serial.SerialException as e:
        print(f"[BRIDGE] Cannot open port {port}: {e}")
        print("[BRIDGE] Falling back to demo mode.")
        demo_loop()


def demo_loop():
    """Демо-цикл: генерирует данные каждые 2 секунды."""
    print("[BRIDGE] Demo mode active. Generating fake data every 2s...")
    while _running:
        data = generate_demo_reading()
        _save_reading(data)
        # Выводим в stdout как если бы это был ESP32
        print(f"[JSON] {json.dumps(data)}")
        time.sleep(2)


def _save_reading(data: dict):
    """Сохраняет распарсенные данные в БД."""
    with SessionLocal() as session:
        reading = json_to_reading(data)
        session.add(reading)
        session.commit()
        status_icon = {"OK": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}.get(reading.status, "⚪")
        print(f"[BRIDGE] Saved scan#{reading.scan_id} | "
              f"{status_icon} {reading.status} | "
              f"H:{reading.humidity:.1f}% T:{reading.temperature:.1f}°C")


# ──────────────────────────────────────────────────────────────────
#  Public API — используется из Streamlit
# ──────────────────────────────────────────────────────────────────
def get_latest_readings(building_id: str = "BILB_001",
                        limit: int = 100) -> list[dict]:
    """
    Возвращает последние N записей для данного здания.
    Используется в Streamlit для обновления графиков.
    """
    with SessionLocal() as session:
        rows = (
            session.query(SensorReading)
            .filter(SensorReading.building_id == building_id)
            .order_by(desc(SensorReading.received_at))
            .limit(limit)
            .all()
        )
        return [_reading_to_dict(r) for r in reversed(rows)]


def get_latest_status(building_id: str = "BILB_001") -> dict:
    """
    Возвращает самую свежую запись (для Live-монитора).
    СРАЗУ доступен фронтенду даже без обученного ML (День 1).
    Возвращает status=UNKNOWN если данных ещё нет.
    """
    with SessionLocal() as session:
        row = (
            session.query(SensorReading)
            .filter(SensorReading.building_id == building_id)
            .order_by(desc(SensorReading.received_at))
            .first()
        )
        if row is None:
            return {
                "status": "UNKNOWN", "score": 0,
                "temperature": None, "humidity": None,
                "vibration": False, "tilt_deg": None,
                "issues": [],
            }
        return _reading_to_dict(row)


def _reading_to_dict(r: SensorReading) -> dict:
    return {
        "id":          r.id,
        "building_id": r.building_id,
        "scan_id":     r.scan_id,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "temperature": r.temperature,
        "humidity":    r.humidity,
        "pressure":    r.pressure,
        "light_lux":   r.light_lux,
        "tilt_deg":    r.tilt_deg,
        "accel_x":     r.accel_x,
        "accel_y":     r.accel_y,
        "accel_z":     r.accel_z,
        "vibration":   bool(r.vibration),
        "dist_front":  r.dist_front,
        "dist_back":   r.dist_back,
        "dist_left":   r.dist_left,
        "dist_right":  r.dist_right,
        "edge":        bool(r.edge),
        "status":      r.status,
        "score":       r.score,
        "issues":      json.loads(r.issues) if r.issues else [],
    }


# ──────────────────────────────────────────────────────────────────
#  CLI Entry Point
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BILB Data Bridge")
    parser.add_argument("--port",  default=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"))
    parser.add_argument("--baud",  default=int(os.getenv("SERIAL_BAUD", 115200)), type=int)
    parser.add_argument("--demo",  action="store_true",
                        help="Run in demo mode (no ESP32 required)")
    args = parser.parse_args()

    _running = True
    print("=" * 55)
    print("  BILB Data Bridge — Starting...")
    print("=" * 55)

    if args.demo or os.getenv("USE_DEMO_DATA", "True").lower() == "true":
        demo_loop()
    else:
        serial_loop(args.port, args.baud)