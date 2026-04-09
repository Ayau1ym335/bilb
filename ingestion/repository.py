"""
ingestion/repository.py  —  Data Access Layer
══════════════════════════════════════════════
Весь SQL — здесь. Роутеры и bridge не трогают session напрямую.
Паттерн: async функции, принимают AsyncSession как первый аргумент.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BuildingProfile, ScanSession, SensorReading
from .schemas import TelemetryPayload

log = logging.getLogger("bilb.repo")


# ══════════════════════════════════════════════════════════════
#  SensorReading
# ══════════════════════════════════════════════════════════════

async def insert_reading(
    db: AsyncSession,
    payload: TelemetryPayload,
    session_id: Optional[int],
    raw_json: Optional[str] = None,
) -> SensorReading:
    """
    Преобразует TelemetryPayload → SensorReading ORM-объект и сохраняет.
    Возвращает объект с заполненным id (после flush).
    """
    p   = payload.pos
    env = payload.env
    st  = payload.str_
    d   = payload.dist

    reading = SensorReading(
        building_id  = payload.building_id,
        session_id   = session_id,
        scan_id      = payload.scan_id,
        fw_version   = payload.v,
        device_ts_ms = payload.ts_ms,

        # Координаты — ключевое требование ТЗ
        pos_x        = p.x   if p else None,
        pos_y        = p.y   if p else None,
        pos_heading  = p.hdg if p else None,

        # Экологические
        temperature  = env.t  if env else None,
        humidity     = env.h  if env else None,
        pressure     = env.p  if env else None,
        light_lux    = env.lx if env else None,

        # Структурные
        tilt_roll    = st.roll  if st else None,
        tilt_pitch   = st.pitch if st else None,
        accel_x      = st.ax    if st else None,
        accel_y      = st.ay    if st else None,
        accel_z      = st.az    if st else None,
        vibration    = st.vib   if st else False,

        # Дистанции
        dist_front   = d.f if d else None,
        dist_back    = d.b if d else None,
        dist_left    = d.l if d else None,
        dist_right   = d.r if d else None,

        # Оценка
        status       = payload.status,
        score        = payload.score,
        issues       = json.dumps(payload.issues) if payload.issues else None,

        raw_json     = raw_json,
    )

    db.add(reading)
    await db.flush()   # получаем id без commit
    log.debug("Inserted reading id=%d building=%s status=%s score=%s",
              reading.id, reading.building_id, reading.status, reading.score)
    return reading


async def get_latest_readings(
    db: AsyncSession,
    building_id: str,
    limit: int = 200,
    offset: int = 0,
) -> list[SensorReading]:
    """Последние N записей по зданию, от новых к старым."""
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.building_id == building_id)
        .order_by(SensorReading.received_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_latest_reading(
    db: AsyncSession,
    building_id: str,
) -> Optional[SensorReading]:
    """Самая свежая запись для быстрого live-статуса."""
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.building_id == building_id)
        .order_by(SensorReading.received_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_readings_in_cell(
    db: AsyncSession,
    building_id: str,
    x: float,
    y: float,
    radius: float = 0.6,   # клеток
) -> list[SensorReading]:
    """
    Все измерения в радиусе radius от клетки (x, y).
    Используется для построения тепловой карты.
    """
    result = await db.execute(
        select(SensorReading)
        .where(
            SensorReading.building_id == building_id,
            SensorReading.pos_x.isnot(None),
            SensorReading.pos_y.isnot(None),
            # Простое Chebyshev расстояние (без sqrt для производительности)
            func.abs(SensorReading.pos_x - x) <= radius,
            func.abs(SensorReading.pos_y - y) <= radius,
        )
        .order_by(SensorReading.received_at.desc())
    )
    return list(result.scalars().all())


async def count_readings(db: AsyncSession, building_id: str) -> int:
    result = await db.execute(
        select(func.count()).where(SensorReading.building_id == building_id)
    )
    return result.scalar_one()


async def count_all_readings(db: AsyncSession) -> int:
    """Total sensor readings across all buildings."""
    result = await db.execute(
        select(func.count()).select_from(SensorReading)
    )
    return result.scalar_one()


# ══════════════════════════════════════════════════════════════
#  ScanSession
# ══════════════════════════════════════════════════════════════

async def get_or_create_session(
    db: AsyncSession,
    building_id: str,
    fw_version: Optional[str] = None,
) -> ScanSession:
    """
    Возвращает активную (незакрытую) сессию или создаёт новую.
    «Активная» = ended_at IS NULL.
    """
    result = await db.execute(
        select(ScanSession)
        .where(
            ScanSession.building_id == building_id,
            ScanSession.ended_at.is_(None),
        )
        .order_by(ScanSession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if session is None:
        session = ScanSession(
            building_id = building_id,
            fw_version  = fw_version,
        )
        db.add(session)
        await db.flush()
        log.info("New scan session id=%d building=%s", session.id, building_id)

    return session


async def close_session(db: AsyncSession, session_id: int) -> Optional[ScanSession]:
    """
    Закрывает сессию: проставляет ended_at и пересчитывает агрегаты.
    """
    result = await db.execute(
        select(ScanSession).where(ScanSession.id == session_id)
    )
    sess = result.scalar_one_or_none()
    if not sess:
        return None

    # Агрегируем показатели из readings этой сессии
    agg = await db.execute(
        select(
            func.count(SensorReading.id).label("total"),
            func.sum(SensorReading.vibration.cast(Integer)).label("vib_events"),
            func.avg(SensorReading.humidity).label("avg_hum"),
            func.avg(SensorReading.temperature).label("avg_temp"),
            func.max(func.abs(SensorReading.tilt_roll)).label("max_roll"),
            func.max(func.abs(SensorReading.tilt_pitch)).label("max_pitch"),
        ).where(SensorReading.session_id == session_id)
    )
    row = agg.one()

    sess.ended_at         = datetime.now(timezone.utc)
    sess.total_readings   = row.total   or 0
    sess.vibration_events = int(row.vib_events or 0)
    sess.avg_humidity     = float(row.avg_hum)   if row.avg_hum   else None
    sess.avg_temperature  = float(row.avg_temp)  if row.avg_temp  else None
    sess.max_tilt_roll    = float(row.max_roll)  if row.max_roll  else None
    sess.max_tilt_pitch   = float(row.max_pitch) if row.max_pitch else None

    await db.flush()
    log.info("Session %d closed: %d readings, %d vib events",
             session_id, sess.total_readings, sess.vibration_events)
    return sess


async def list_sessions(
    db: AsyncSession,
    building_id: str,
    limit: int = 20,
) -> list[ScanSession]:
    result = await db.execute(
        select(ScanSession)
        .where(ScanSession.building_id == building_id)
        .order_by(ScanSession.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════
#  BuildingProfile  —  upsert и обновление агрегатов
# ══════════════════════════════════════════════════════════════

async def upsert_building_profile(
    db: AsyncSession,
    building_id: str,
    **kwargs,
) -> BuildingProfile:
    """
    INSERT OR UPDATE профиля здания.
    kwargs: любые поля BuildingProfile кроме id и building_id.
    """
    result = await db.execute(
        select(BuildingProfile).where(BuildingProfile.building_id == building_id)
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = BuildingProfile(building_id=building_id, **kwargs)
        db.add(profile)
    else:
        for k, v in kwargs.items():
            setattr(profile, k, v)
        profile.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return profile


async def refresh_building_aggregates(
    db: AsyncSession,
    building_id: str,
) -> BuildingProfile:
    """
    Пересчитывает агрегированные показатели профиля из всех readings.
    Вызывать после каждых N новых записей (например, каждые 10).
    """
    agg = await db.execute(
        select(
            func.count(SensorReading.id).label("total"),
            func.sum(SensorReading.vibration.cast(Integer)).label("vib_total"),
            func.avg(SensorReading.temperature).label("avg_t"),
            func.avg(SensorReading.humidity).label("avg_h"),
            func.avg(SensorReading.light_lux).label("avg_lx"),
            func.max(func.abs(SensorReading.tilt_roll)).label("max_roll"),
            func.max(func.abs(SensorReading.tilt_pitch)).label("max_pitch"),
        ).where(SensorReading.building_id == building_id)
    )
    row = agg.one()

    # Последний статус
    latest = await get_latest_reading(db, building_id)
    n_sessions = await db.execute(
        select(func.count(ScanSession.id))
        .where(ScanSession.building_id == building_id)
    )

    return await upsert_building_profile(
        db,
        building_id,
        total_readings    = row.total   or 0,
        total_scans       = n_sessions.scalar_one() or 0,
        vibration_events  = int(row.vib_total or 0),
        avg_temperature   = float(row.avg_t)   if row.avg_t   else None,
        avg_humidity      = float(row.avg_h)   if row.avg_h   else None,
        avg_light_lux     = float(row.avg_lx)  if row.avg_lx  else None,
        max_tilt_roll     = float(row.max_roll) if row.max_roll else None,
        max_tilt_pitch    = float(row.max_pitch)if row.max_pitch else None,
        overall_status    = latest.status if latest else None,
        degradation_score = latest.score  if latest else None,
        issues            = latest.issues if latest else None,
    )


async def get_building_profile(
    db: AsyncSession,
    building_id: str,
) -> Optional[BuildingProfile]:
    result = await db.execute(
        select(BuildingProfile).where(BuildingProfile.building_id == building_id)
    )
    return result.scalar_one_or_none()


async def list_buildings(db: AsyncSession) -> list[BuildingProfile]:
    result = await db.execute(
        select(BuildingProfile).order_by(BuildingProfile.updated_at.desc())
    )
    return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════
#  Тепловая карта аномалий
#  Структура: dict["{x}_{y}", {"avg_score": float, "count": int, "max_status": str}]
# ══════════════════════════════════════════════════════════════

async def build_heatmap(
    db: AsyncSession,
    building_id: str,
    cell_size: float = 1.0,   # ▶ НАСТРОЙТЕ: размер ячейки карты в клетках сетки
) -> dict:
    """
    Агрегирует score по пространственным ячейкам.
    Возвращает dict для сохранения в BuildingProfile.heatmap_json.
    """
    result = await db.execute(
        select(
            SensorReading.pos_x,
            SensorReading.pos_y,
            SensorReading.score,
            SensorReading.status,
        ).where(
            SensorReading.building_id == building_id,
            SensorReading.pos_x.isnot(None),
            SensorReading.pos_y.isnot(None),
            SensorReading.score.isnot(None),
        )
    )
    rows = result.all()

    heatmap: dict[str, dict] = {}
    for row in rows:
        # Квантуем координаты в ячейку размером cell_size
        cx = round(float(row.pos_x) / cell_size) * cell_size
        cy = round(float(row.pos_y) / cell_size) * cell_size
        key = f"{cx:.1f}_{cy:.1f}"

        if key not in heatmap:
            heatmap[key] = {
                "x": cx, "y": cy,
                "sum_score": 0.0, "count": 0,
                "max_status": "OK",
            }

        cell = heatmap[key]
        cell["sum_score"] += float(row.score)
        cell["count"]     += 1

        # Эскалируем статус до максимального
        priority = {"OK": 0, "WARNING": 1, "CRITICAL": 2}
        cur = priority.get(row.status or "OK", 0)
        mx  = priority.get(cell["max_status"], 0)
        if cur > mx:
            cell["max_status"] = row.status

    # Постобработка: вычисляем avg_score
    result_map = {}
    for key, cell in heatmap.items():
        result_map[key] = {
            "x":          cell["x"],
            "y":          cell["y"],
            "avg_score":  round(cell["sum_score"] / cell["count"], 1),
            "count":      cell["count"],
            "max_status": cell["max_status"],
        }

    return result_map
