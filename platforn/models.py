"""
ingestion/models.py  —  SQLAlchemy ORM Models
══════════════════════════════════════════════
Таблицы:
  · sensor_readings    — одна строка = один JSON-пакет от робота
  · building_profiles  — агрегированный профиль объекта (1 на здание)
  · scan_sessions      — метаданные сессии (start/end, общий маршрут)

Принцип:
  · Все координаты (x, y) хранятся как REAL (float) — клетки сетки
  · Временны́е метки — UTC, тип DateTime(timezone=True)
  · Nullable везде где ESP32 может не прислать поле (graceful degradation)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════
#  scan_sessions  —  одна поездка робота по объекту
# ══════════════════════════════════════════════════════════════
class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    building_id: Mapped[str]      = mapped_column(String(64), nullable=False, index=True)
    started_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fw_version:  Mapped[Optional[str]]      = mapped_column(String(20),  nullable=True)
    notes:       Mapped[Optional[str]]      = mapped_column(Text,        nullable=True)

    # Статистика сессии (заполняется при закрытии)
    total_readings:    Mapped[int]   = mapped_column(Integer, default=0)
    vibration_events:  Mapped[int]   = mapped_column(Integer, default=0)
    max_tilt_roll:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tilt_pitch:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_humidity:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_temperature:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Связи
    readings: Mapped[list[SensorReading]] = relationship(
        "SensorReading", back_populates="session", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<ScanSession id={self.id} building={self.building_id}>"


# ══════════════════════════════════════════════════════════════
#  sensor_readings  —  один JSON-пакет от робота
# ══════════════════════════════════════════════════════════════
class SensorReading(Base):
    __tablename__ = "sensor_readings"

    # ── Primary key ─────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Метаданные пакета ────────────────────────────────────
    building_id:   Mapped[str]            = mapped_column(String(64), nullable=False, index=True)
    session_id:    Mapped[Optional[int]]  = mapped_column(
        Integer, ForeignKey("scan_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scan_id:       Mapped[Optional[int]]  = mapped_column(Integer,    nullable=True)   # scan_id от ESP32
    fw_version:    Mapped[Optional[str]]  = mapped_column(String(20), nullable=True)
    received_at:   Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    # Время на устройстве (millis от boot) — для расчёта задержки доставки
    device_ts_ms:  Mapped[Optional[int]]  = mapped_column(BigInteger, nullable=True)

    # ── Координаты (dead-reckoning от ESP32) ─────────────────
    pos_x:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # клетки
    pos_y:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # клетки
    pos_heading: Mapped[Optional[int]]   = mapped_column(Integer, nullable=True) # °

    # ── Экологические (BME280) ───────────────────────────────
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # °C
    humidity:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # %
    pressure:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # hPa

    # ── Освещённость (BH1750) ────────────────────────────────
    light_lux:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # lux

    # ── Структурные (MPU6050) ────────────────────────────────
    tilt_roll:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # °
    tilt_pitch:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # °
    accel_x:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # m/s²
    accel_y:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accel_z:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Вибрация (SW-420) ────────────────────────────────────
    vibration:   Mapped[bool]            = mapped_column(Boolean, default=False)

    # ── Дистанции (HC-SR04 x4) ───────────────────────────────
    dist_front:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # cm
    dist_back:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dist_left:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dist_right:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Оценка деградации (от ESP32 rule-engine) ─────────────
    status:  Mapped[Optional[str]]   = mapped_column(String(20), nullable=True)   # OK/WARNING/CRITICAL
    score:   Mapped[Optional[float]] = mapped_column(Float,      nullable=True)   # 0–100
    issues:  Mapped[Optional[str]]   = mapped_column(Text,       nullable=True)   # JSON array string

    # ── Сырой пакет (для отладки) ────────────────────────────
    raw_json: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    # ── Связи ────────────────────────────────────────────────
    session: Mapped[Optional[ScanSession]] = relationship(
        "ScanSession", back_populates="readings"
    )

    # ── Индексы ──────────────────────────────────────────────
    __table_args__ = (
        # Быстрый запрос «последние N записей для здания»
        Index("ix_sr_building_received", "building_id", "received_at"),
        # Пространственный запрос «что в клетке (x, y)?»
        Index("ix_sr_pos", "building_id", "pos_x", "pos_y"),
        # Быстрый поиск CRITICAL событий
        Index("ix_sr_status", "building_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<SensorReading id={self.id} building={self.building_id} "
            f"status={self.status} score={self.score}>"
        )


# ══════════════════════════════════════════════════════════════
#  building_profiles  —  агрегированный профиль объекта
#  1 строка на здание; обновляется после каждой сессии
# ══════════════════════════════════════════════════════════════
class BuildingProfile(Base):
    __tablename__ = "building_profiles"

    # ── Primary key ─────────────────────────────────────────
    id:          Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    building_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # ── Метаданные здания (вводятся оператором) ──────────────
    name:       Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city:       Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address:    Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    year_built: Mapped[Optional[int]] = mapped_column(Integer,     nullable=True)
    area_m2:    Mapped[Optional[float]] = mapped_column(Float,     nullable=True)
    floors:     Mapped[Optional[int]]   = mapped_column(Integer,   nullable=True)

    # ── Агрегированные показатели ────────────────────────────
    total_scans:       Mapped[int]   = mapped_column(Integer, default=0)
    total_readings:    Mapped[int]   = mapped_column(Integer, default=0)
    vibration_events:  Mapped[int]   = mapped_column(Integer, default=0)

    avg_temperature:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_humidity:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_light_lux:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tilt_roll:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tilt_pitch:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── AI / ML результаты ───────────────────────────────────
    overall_status:    Mapped[Optional[str]]   = mapped_column(String(20), nullable=True)
    degradation_score: Mapped[Optional[float]] = mapped_column(Float,      nullable=True)
    issues:            Mapped[Optional[str]]   = mapped_column(Text,        nullable=True)  # JSON array — from latest reading
    ml_model_version:  Mapped[Optional[str]]   = mapped_column(String(50), nullable=True)

    # ── Результаты LLM стратега (JSON строка) ────────────────
    scenarios_json:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Sustainability расчёты (JSON строка) ─────────────────
    sustainability_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Тепловая карта аномалий (JSON: {x_y: score}) ─────────
    heatmap_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Временны́е метки ─────────────────────────────────────
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
        onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<BuildingProfile id={self.id} building={self.building_id} "
            f"status={self.overall_status} score={self.degradation_score}>"
        )
