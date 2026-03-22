"""
ingestion/schemas.py  —  Pydantic v2 Schemas
═════════════════════════════════════════════
ВАЖНО: ArduinoJson serialized(String(val, N)) сериализует float-поля
как JSON-строки ("47.5", "3.50"). Все числовые поля имеют
coerce-валидатор, принимающий и str и float.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Внутренний хелпер: str|float → float ─────────────────────
def _to_float(v: Any) -> Optional[float]:
    """ArduinoJson serialized() шлёт числа как строки — принимаем оба."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


# ══════════════════════════════════════════════════════════════
#  I. INBOUND — JSON от ESP32
#  Соответствует Profile.ino::serializeToJson()
#  Числовые поля: serialized(String(...)) → приходят как строки
# ══════════════════════════════════════════════════════════════

class ESP32Pos(BaseModel):
    """Позиция dead-reckoning. x/y приходят как строки: "3.50"."""
    x:   float = Field(ge=0.0, le=100.0)
    y:   float = Field(ge=0.0, le=100.0)
    hdg: int   = Field(ge=0, le=359)

    @field_validator("x", "y", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> float:
        r = _to_float(v)
        if r is None:
            raise ValueError(f"Cannot coerce '{v}' to float")
        return r


class ESP32Env(BaseModel):
    """
    Экологические данные. t/h/p — строки от serialized(String(...)).
    lx — int (прямое присваивание в прошивке).
    """
    t:  Optional[float] = Field(None, ge=-40.0, le=85.0)
    h:  Optional[float] = Field(None, ge=0.0,   le=100.0)
    p:  Optional[float] = Field(None, ge=800.0,  le=1200.0)
    lx: Optional[float] = Field(None, ge=0.0)

    @field_validator("t", "h", "p", "lx", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Optional[float]:
        return _to_float(v)


class ESP32Str(BaseModel):
    """
    Структурные данные (MPU6050 + SW-420).
    roll/pitch — строки от serialized().
    ax/ay/az — присутствуют только в HTTP POST (Profile.ino),
               отсутствуют в WS pushTelemetry() — полностью опциональны.
    vib — bool (прямое присваивание, не строка).
    """
    roll:  Optional[float] = Field(None, ge=-180.0, le=180.0)
    pitch: Optional[float] = Field(None, ge=-90.0,  le=90.0)
    ax:    Optional[float] = None   # только в HTTP POST пакете
    ay:    Optional[float] = None
    az:    Optional[float] = None
    vib:   bool            = False

    @field_validator("roll", "pitch", "ax", "ay", "az", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Optional[float]:
        return _to_float(v)


class ESP32Dist(BaseModel):
    """
    Дистанции HC-SR04. Прошивка пишет (int) → приходят как целые.
    999 = нет препятствия (DIST_MAX_CM).
    """
    f: Optional[float] = Field(None, ge=0.0, le=999.0)
    b: Optional[float] = Field(None, ge=0.0, le=999.0)
    l: Optional[float] = Field(None, ge=0.0, le=999.0)
    r: Optional[float] = Field(None, ge=0.0, le=999.0)

    @field_validator("f", "b", "l", "r", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Optional[float]:
        return _to_float(v)


class TelemetryPayload(BaseModel):
    """
    Полный JSON-пакет от ESP32.

    Два источника:
      · HTTP POST  — Profile.ino::serializeToJson()  [JSON] prefix
      · WebSocket  — WebSocket_Server.ino::pushTelemetry()

    Различия:
      · WS-пакет содержит доп. поля: type, state, wp_idx, wp_total, wp_run
      · WS-пакет НЕ содержит ax/ay/az (учтено в ESP32Str)
      · score приходит как строка "47.5" из serialized(String(...))
    """
    # Идентификация
    building_id: str           = Field(..., min_length=1, max_length=64)
    scan_id:     Optional[int] = None
    ts_ms:       Optional[int] = Field(None, ge=0)
    v:           Optional[str] = Field(None, max_length=20)

    # Оценка деградации
    status: Optional[str]   = Field(None, pattern=r"^(OK|WARNING|CRITICAL)$")
    score:  Optional[float] = Field(None, ge=0.0, le=100.0)

    # Субструктуры
    pos:   Optional[ESP32Pos]  = None
    env:   Optional[ESP32Env]  = None
    str_:  Optional[ESP32Str]  = Field(None, alias="str")
    dist:  Optional[ESP32Dist] = None

    # Issues — массив строк или CSV строка ("HIGH_HUMIDITY,VIB")
    issues: list[str] = Field(default_factory=list)

    # WS-only поля (игнорируем при сохранении в БД, но не отвергаем)
    type:     Optional[str]  = None   # "telem"
    state:    Optional[str]  = None   # "SCANNING" etc.
    wp_idx:   Optional[int]  = None
    wp_total: Optional[int]  = None
    wp_run:   Optional[bool] = None

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v: Any) -> Optional[float]:
        """score тоже приходит как строка "47.5"."""
        return _to_float(v)

    @field_validator("issues", mode="before")
    @classmethod
    def _coerce_issues(cls, v: Any) -> list[str]:
        """Принимаем ['A','B'], 'A,B', 'NONE'."""
        if isinstance(v, str):
            if v.strip().upper() == "NONE" or not v.strip():
                return []
            return [i.strip() for i in v.split(",") if i.strip()]
        if isinstance(v, list):
            return [str(i) for i in v if str(i).upper() != "NONE"]
        return []


# ══════════════════════════════════════════════════════════════
#  II. BUILDING REGISTRATION
# ══════════════════════════════════════════════════════════════

class BuildingRegisterRequest(BaseModel):
    building_id: str             = Field(..., min_length=1, max_length=64)
    name:        str             = Field(..., min_length=1, max_length=200)
    city:        Optional[str]   = Field(None, max_length=100)
    address:     Optional[str]   = None
    year_built:  Optional[int]   = Field(None, ge=1000, le=2100)
    area_m2:     Optional[float] = Field(None, gt=0.0)
    floors:      Optional[int]   = Field(None, ge=1, le=200)


# ══════════════════════════════════════════════════════════════
#  III. API RESPONSES
# ══════════════════════════════════════════════════════════════

class TelemetryIngestResponse(BaseModel):
    ok:         bool
    reading_id: int
    session_id: Optional[int]
    status:     str
    score:      Optional[float]
    message:    str = "Telemetry ingested"


class SensorReadingOut(BaseModel):
    id:           int
    building_id:  str
    session_id:   Optional[int]
    scan_id:      Optional[int]
    received_at:  datetime
    pos_x:        Optional[float]
    pos_y:        Optional[float]
    pos_heading:  Optional[int]
    temperature:  Optional[float]
    humidity:     Optional[float]
    pressure:     Optional[float]
    light_lux:    Optional[float]
    tilt_roll:    Optional[float]
    tilt_pitch:   Optional[float]
    vibration:    bool
    dist_front:   Optional[float]
    dist_back:    Optional[float]
    dist_left:    Optional[float]
    dist_right:   Optional[float]
    status:       Optional[str]
    score:        Optional[float]
    issues:       Optional[str]
    model_config = {"from_attributes": True}


class BuildingProfileOut(BaseModel):
    id:                   int
    building_id:          str
    name:                 Optional[str]
    city:                 Optional[str]
    address:              Optional[str]
    year_built:           Optional[int]
    area_m2:              Optional[float]
    floors:               Optional[int]
    total_scans:          int
    total_readings:       int
    vibration_events:     int
    avg_temperature:      Optional[float]
    avg_humidity:         Optional[float]
    avg_light_lux:        Optional[float]
    max_tilt_roll:        Optional[float]
    max_tilt_pitch:       Optional[float]
    overall_status:       Optional[str]
    degradation_score:    Optional[float]
    issues:               Optional[str]   # JSON array string — latest reading issues
    scenarios_json:       Optional[str]
    sustainability_json:  Optional[str]
    heatmap_json:         Optional[str]
    updated_at:           datetime
    model_config = {"from_attributes": True}


class ScanSessionOut(BaseModel):
    id:               int
    building_id:      str
    started_at:       datetime
    ended_at:         Optional[datetime]
    total_readings:   int
    vibration_events: int
    avg_humidity:     Optional[float]
    avg_temperature:  Optional[float]
    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status:    str
    db:        bool
    readings:  int
    buildings: int
