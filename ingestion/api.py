"""
ingestion/api.py  —  FastAPI Application
═════════════════════════════════════════
Эндпоинты:
  POST /api/telemetry              — приём JSON от ESP32
  GET  /api/telemetry/{building}   — последние N записей
  GET  /api/telemetry/{building}/latest — одна свежая запись
  POST /api/buildings              — регистрация здания
  GET  /api/buildings              — список зданий
  GET  /api/buildings/{id}         — профиль здания
  POST /api/sessions/{id}/close    — закрыть сессию
  GET  /api/heatmap/{building}     — тепловая карта
  GET  /health                     — health check

▶ НАСТРОЙТЕ:
  AGGREGATE_EVERY_N = 10  — как часто пересчитывать агрегаты
  API_KEY             — секрет для заголовка X-API-Key (опционально)
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import (
    Depends, FastAPI, Header, HTTPException,
    Query, Request, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .database import create_tables, get_db, ping_db
from .models import BuildingProfile, SensorReading
from .repository import (
    build_heatmap,
    close_session,
    count_all_readings,
    count_readings,
    get_building_profile,
    get_latest_reading,
    get_latest_readings,
    get_or_create_session,
    insert_reading,
    list_buildings,
    list_sessions,
    refresh_building_aggregates,
    upsert_building_profile,
)
from .schemas import (
    BuildingProfileOut,
    BuildingRegisterRequest,
    HealthResponse,
    ScanSessionOut,
    SensorReadingOut,
    TelemetryIngestResponse,
    TelemetryPayload,
)

log = logging.getLogger("bilb.api")

# ── Конфигурация ──────────────────────────────────────────────
AGGREGATE_EVERY_N: int = int(os.getenv("AGGREGATE_EVERY_N", "10"))
API_KEY: Optional[str] = os.getenv("BILB_API_KEY")    # ▶ НАСТРОЙТЕ если нужна auth

# Счётчик записей для триггера агрегации
_ingest_counter: dict[str, int] = {}


# ══════════════════════════════════════════════════════════════
#  Lifespan — инициализация и shutdown
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("BILB API starting up...")
    await create_tables()
    log.info("DB tables ready")
    yield
    log.info("BILB API shutting down")


# ══════════════════════════════════════════════════════════════
#  App
# ══════════════════════════════════════════════════════════════
# Uvicorn reload import path — must match the `app` object below.
APP_IMPORT_NAME: str = "ingestion.api:app"

app = FastAPI(
    title="BILB Data Ingestion API",
    version="2.1.0",
    description="Receives telemetry from BILB robot, stores to DB, exposes analytics.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — разрешаем Streamlit (localhost:8501) и control.html
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",    # Streamlit
        "http://127.0.0.1:8501",
        "http://192.168.4.2:8501",  # ▶ НАСТРОЙТЕ: IP вашего ноутбука в сети робота
        "*",                         # Убери в продакшне
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
#  Middleware — логирование времени запросов
# ══════════════════════════════════════════════════════════════
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    if request.url.path != "/health":   # health спам не логируем
        log.debug("%s %s → %d  (%.1fms)",
                  request.method, request.url.path, response.status_code, ms)
    return response


# ══════════════════════════════════════════════════════════════
#  Auth dependency (опциональный API key)
# ══════════════════════════════════════════════════════════════
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )


# ══════════════════════════════════════════════════════════════
#  POST /api/telemetry  —  ГЛАВНЫЙ ЭНДПОИНТ
# ══════════════════════════════════════════════════════════════
@app.post(
    "/api/telemetry",
    response_model=TelemetryIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest robot telemetry packet",
    dependencies=[Depends(verify_api_key)],
)
async def ingest_telemetry(
    payload: TelemetryPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TelemetryIngestResponse:
    """
    Принимает JSON-пакет от ESP32 (формат из Profile.ino::serializeToJson).
    Сохраняет в sensor_readings с привязкой к координатам (x, y).
    Периодически обновляет агрегаты в building_profiles.
    """
    # Сохраняем raw JSON для отладки (опционально)
    raw = None
    try:
        body = await request.body()
        raw = body.decode("utf-8", errors="replace")[:2000]   # ▶ НАСТРОЙТЕ: лимит raw
    except Exception:
        pass

    # Получить или создать сессию сканирования
    scan_session = await get_or_create_session(
        db, payload.building_id, fw_version=payload.v
    )

    # Сохранить запись
    reading = await insert_reading(
        db, payload, session_id=scan_session.id, raw_json=raw
    )

    # Триггер агрегации каждые AGGREGATE_EVERY_N записей
    bid = payload.building_id
    _ingest_counter[bid] = _ingest_counter.get(bid, 0) + 1

    if _ingest_counter[bid] % AGGREGATE_EVERY_N == 0:
        await refresh_building_aggregates(db, bid)
        log.info("[%s] Aggregates refreshed after %d readings", bid, _ingest_counter[bid])

    return TelemetryIngestResponse(
        ok         = True,
        reading_id = reading.id,
        session_id = scan_session.id,
        status     = reading.status or "UNKNOWN",
        score      = reading.score,
    )


# ══════════════════════════════════════════════════════════════
#  GET /api/telemetry/{building_id}
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/telemetry/{building_id}",
    response_model=list[SensorReadingOut],
    summary="Get latest readings for a building",
)
async def get_readings(
    building_id: str,
    limit:  int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0,   ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[SensorReading]:
    return await get_latest_readings(db, building_id, limit=limit, offset=offset)


# ══════════════════════════════════════════════════════════════
#  GET /api/telemetry/{building_id}/latest
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/telemetry/{building_id}/latest",
    response_model=SensorReadingOut,
    summary="Get single latest reading",
)
async def get_latest(
    building_id: str,
    db: AsyncSession = Depends(get_db),
) -> SensorReading:
    r = await get_latest_reading(db, building_id)
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No readings found for building '{building_id}'",
        )
    return r


# ══════════════════════════════════════════════════════════════
#  POST /api/buildings  —  Регистрация объекта
# ══════════════════════════════════════════════════════════════
@app.post(
    "/api/buildings",
    response_model=BuildingProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update building metadata",
)
async def register_building(
    req: BuildingRegisterRequest,
    db:  AsyncSession = Depends(get_db),
) -> BuildingProfile:
    profile = await upsert_building_profile(
        db,
        building_id = req.building_id,
        name        = req.name,
        city        = req.city,
        address     = req.address,
        year_built  = req.year_built,
        area_m2     = req.area_m2,
        floors      = req.floors,
    )
    log.info("Building registered/updated: %s (%s)", req.building_id, req.name)
    return profile


# ══════════════════════════════════════════════════════════════
#  GET /api/buildings
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/buildings",
    response_model=list[BuildingProfileOut],
    summary="List all buildings",
)
async def get_buildings(
    db: AsyncSession = Depends(get_db),
) -> list[BuildingProfile]:
    return await list_buildings(db)


# ══════════════════════════════════════════════════════════════
#  GET /api/buildings/{building_id}
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/buildings/{building_id}",
    response_model=BuildingProfileOut,
    summary="Get building profile",
)
async def get_building(
    building_id: str,
    db: AsyncSession = Depends(get_db),
) -> BuildingProfile:
    p = await get_building_profile(db, building_id)
    if p is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building '{building_id}' not found",
        )
    return p


# ══════════════════════════════════════════════════════════════
#  POST /api/buildings/{building_id}/scenarios
#  Triggers LLM strategist → saves result to BuildingProfile
# ══════════════════════════════════════════════════════════════
@app.post(
    "/api/buildings/{building_id}/scenarios",
    summary="Generate adaptive reuse scenarios via LLM strategist",
)
async def generate_building_scenarios(
    building_id:    str,
    force_fallback: bool = Query(default=False,
                                 description="Skip Gemini, use rule-based fallback"),
    db: AsyncSession = Depends(get_db),
):
    """
    Генерирует 3 сценария адаптивного повторного использования для здания.
    Результат сохраняется в BuildingProfile.scenarios_json.
    """
    from llm import generate_scenarios_async

    profile = await get_building_profile(db, building_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building '{building_id}' not found",
        )

    # Собираем building_data из профиля
    building_data = {
        "building_id":      profile.building_id,
        "name":             profile.name,
        "city":             profile.city,
        "address":          profile.address,
        "year_built":       profile.year_built,
        "area_m2":          profile.area_m2,
        "floors":           profile.floors,
        "overall_status":   profile.overall_status,
        "degradation_score": profile.degradation_score,
        "avg_humidity":     profile.avg_humidity,
        "avg_temperature":  profile.avg_temperature,
        "avg_light_lux":    profile.avg_light_lux,
        "max_tilt_roll":    profile.max_tilt_roll,
        "max_tilt_pitch":   profile.max_tilt_pitch,
        "vibration_events": profile.vibration_events,
        "issues":           profile.issues,
    }

    scenarios = await generate_scenarios_async(
        building_data,
        use_cache      = not force_fallback,
        force_fallback = force_fallback,
    )

    # Сохраняем результат в БД
    await upsert_building_profile(
        db,
        building_id,
        scenarios_json = json.dumps(scenarios),
    )

    return {"building_id": building_id, "scenarios": scenarios}


# ══════════════════════════════════════════════════════════════
#  POST /api/buildings/{building_id}/sustainability
#  Runs Движок 3 (Economist) and persists result to DB
# ══════════════════════════════════════════════════════════════
@app.post(
    "/api/buildings/{building_id}/sustainability",
    summary="Calculate sustainability & financial model (Engine 3)",
)
async def calculate_sustainability(
    building_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Запускает математическую модель Economist для здания.
    Результат сохраняется в BuildingProfile.sustainability_json.
    """
    from economist import calculate_from_profile

    profile = await get_building_profile(db, building_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building '{building_id}' not found",
        )

    report = calculate_from_profile({
        "building_id": profile.building_id,
        "area_m2":     profile.area_m2,
        "floors":      profile.floors,
    })

    await upsert_building_profile(
        db,
        building_id,
        sustainability_json=json.dumps(report.to_dict()),
    )

    return {"building_id": building_id, "summary": report.summary}


# ══════════════════════════════════════════════════════════════
#  GET /api/buildings/{building_id}/report
#  Assembles all engines → generates PDF → returns as download
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/buildings/{building_id}/report",
    summary="Generate full PDF assessment report",
    response_class=Response,  # returns raw bytes
)
async def get_pdf_report(
    building_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Собирает данные всех трёх движков и генерирует PDF-отчёт.
    Требует предварительного вызова /scenarios и /sustainability.
    Возвращает application/pdf для прямого скачивания.
    """
    from report import generate_pdf
    from ml import get_status
    from economist import calculate_from_profile

    profile = await get_building_profile(db, building_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building '{building_id}' not found",
        )

    # building dict for generator
    building_data = {
        "building_id": profile.building_id,
        "name":        profile.name,
        "city":        profile.city,
        "year_built":  profile.year_built,
        "area_m2":     profile.area_m2,
        "floors":      profile.floors,
        "address":     profile.address,
    }

    # sensor_data assembled from profile aggregates
    sensor_data = {
        "avg_temperature":  profile.avg_temperature,
        "avg_humidity":     profile.avg_humidity,
        "avg_light_lux":    profile.avg_light_lux,
        "max_tilt_roll":    profile.max_tilt_roll,
        "max_tilt_pitch":   profile.max_tilt_pitch,
        "vibration_events": profile.vibration_events,
        "total_readings":   profile.total_readings,
        "total_scans":      profile.total_scans,
        "issues":           profile.issues,
    }

    # ML result from profile fields
    ml_result = {
        "status":     profile.overall_status or "UNKNOWN",
        "score":      profile.degradation_score or 0.0,
        "confidence": 0.0,
        "model":      "random_forest",
        "rule_status": profile.overall_status or "UNKNOWN",
    }

    # Scenarios — from cached sustainability_json or fallback
    scenarios: list[dict] = []
    if profile.scenarios_json:
        try:
            scenarios = json.loads(profile.scenarios_json)
        except Exception:
            pass

    # Sustainability report — recompute if not cached
    if profile.sustainability_json:
        try:
            sus_report = json.loads(profile.sustainability_json)
        except Exception:
            sus_report = calculate_from_profile(building_data).to_dict()
    else:
        sus_report = calculate_from_profile(building_data).to_dict()

    pdf_bytes = generate_pdf(
        building    = building_data,
        sensor_data = sensor_data,
        ml_result   = ml_result,
        scenarios   = scenarios,
        sus_report  = sus_report,
    )

    filename = f"BILB_{building_id}_{json.dumps({}).encode()[:8].hex()}.pdf"
    return Response(
        content     = pdf_bytes,
        media_type  = "application/pdf",
        headers     = {"Content-Disposition": f'attachment; filename="BILB_{building_id}.pdf"'},
    )


# ══════════════════════════════════════════════════════════════
#  GET /api/buildings/{building_id}/sessions
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/buildings/{building_id}/sessions",
    response_model=list[ScanSessionOut],
    summary="List scan sessions for a building",
)
async def get_sessions(
    building_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await list_sessions(db, building_id, limit=limit)


# ══════════════════════════════════════════════════════════════
#  POST /api/sessions/{session_id}/close
# ══════════════════════════════════════════════════════════════
@app.post(
    "/api/sessions/{session_id}/close",
    response_model=ScanSessionOut,
    summary="Close a scan session and compute aggregates",
)
async def close_scan_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    sess = await close_session(db, session_id)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return sess


# ══════════════════════════════════════════════════════════════
#  GET /api/heatmap/{building_id}
# ══════════════════════════════════════════════════════════════
@app.get(
    "/api/heatmap/{building_id}",
    summary="Get spatial anomaly heatmap",
)
async def get_heatmap(
    building_id: str,
    cell_size: float = Query(default=1.0, gt=0.0, le=10.0,
                              description="Cell size in grid units"),
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает dict {x_y: {avg_score, count, max_status}}.
    Используется Streamlit для рендеринга тепловой карты.
    """
    heatmap = await build_heatmap(db, building_id, cell_size=cell_size)
    return {"building_id": building_id, "cell_size": cell_size, "cells": heatmap}


# ══════════════════════════════════════════════════════════════
#  GET /health
# ══════════════════════════════════════════════════════════════
@app.get(
    "/health",
    summary="Health check",
)
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = await ping_db()
    n_readings = await count_all_readings(db) if db_ok else 0
    buildings  = await list_buildings(db)     if db_ok else []

    code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=code,
        content={
            "status":    "ok" if db_ok else "degraded",
            "db":        db_ok,
            "readings":  n_readings,
            "buildings": len(buildings),
        },
    )


# ══════════════════════════════════════════════════════════════
#  Global exception handler
# ══════════════════════════════════════════════════════════════
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
