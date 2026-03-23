"""
ml/features.py  —  Feature Engineering
═══════════════════════════════════════
Единственный источник правды для:
  · Имён и порядка 13 признаков (FEATURE_COLS)
  · Пороговых значений (зеркало Config.h прошивки)
  · Rule-based авторазметки (зеркало profile.ino::assessDegradation)
  · Преобразования любого входного формата → numpy вектор

Входные форматы:
  · dict (из БД / API / bridge)
  · SensorReading ORM-объект
  · TelemetryPayload Pydantic-объект

▶ Если пороги в прошивке изменились — меняй только здесь.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union
import numpy as np

# ══════════════════════════════════════════════════════════════
#  Пороги — зеркало Config.h
#  ▶ НАСТРОЙТЕ: синхронизируй с Config.h если меняешь прошивку
# ══════════════════════════════════════════════════════════════
THR_HUMIDITY_CRIT  = 70.0   # %
THR_HUMIDITY_WARN  = 55.0   # %
THR_TEMP_CRIT      = 40.0   # °C
THR_TEMP_WARN      = 30.0   # °C
THR_LIGHT_LOW      = 100.0  # lux
THR_TILT_CRIT      = 15.0   # °
THR_TILT_WARN      = 5.0    # °
DIST_MAX_CM        = 400.0  # cm — значение «нет препятствия»
DIST_OBSTACLE_CM   = 25.0   # cm — аварийное расстояние

# Метки классов
LABEL_NAMES  = {0: "OK", 1: "WARNING", 2: "CRITICAL"}
LABEL_VALUES = {"OK": 0, "WARNING": 1, "CRITICAL": 2}

# ══════════════════════════════════════════════════════════════
#  13 признаков — фиксированный порядок
#  Менять порядок НЕЛЬЗЯ после обучения модели.
#  Добавлять новые — только в конец + переобучать.
# ══════════════════════════════════════════════════════════════
FEATURE_COLS: list[str] = [
    # Экологические (BME280 + BH1750) — 4 признака
    "humidity",       # 0  %
    "temperature",    # 1  °C
    "light_lux",      # 2  lux
    "pressure",       # 3  hPa  (косвенный: низкое давление → влажность)

    # Структурные (MPU6050) — 5 признаков
    "tilt_roll",      # 4  ° крен
    "tilt_pitch",     # 5  ° тангаж
    "max_tilt",       # 6  max(|roll|, |pitch|) — агрегат для RF
    "accel_z",        # 7  m/s² — отклонение от 9.81 = наклон/удар
    "vibration",      # 8  0/1  (SW-420)

    # Пространственные (HC-SR04) — 4 признака
    "dist_front",     # 9  cm  (999 → 400 нормализуем)
    "dist_back",      # 10 cm
    "dist_left",      # 11 cm
    "dist_right",     # 12 cm
]

N_FEATURES = len(FEATURE_COLS)  # 13


# ══════════════════════════════════════════════════════════════
#  Заполнение пропусков (импутация)
#  Значения по умолчанию при отсутствии поля (graceful degradation).
#  Выбраны как «нейтральные» — не должны искусственно влиять на класс.
# ══════════════════════════════════════════════════════════════
_FILL_DEFAULTS: dict[str, float] = {
    "humidity":    50.0,    # средняя влажность
    "temperature": 20.0,    # комнатная температура
    "light_lux":   200.0,   # умеренный свет
    "pressure":    1013.0,  # стандартное давление
    "tilt_roll":   0.0,
    "tilt_pitch":  0.0,
    "max_tilt":    0.0,
    "accel_z":     9.81,    # норма при горизонтальном положении
    "vibration":   0.0,
    "dist_front":  DIST_MAX_CM,
    "dist_back":   DIST_MAX_CM,
    "dist_left":   DIST_MAX_CM,
    "dist_right":  DIST_MAX_CM,
}


# ══════════════════════════════════════════════════════════════
#  Извлечение сырых значений из любого источника
# ══════════════════════════════════════════════════════════════
def _extract_raw(reading: Any) -> dict[str, Any]:
    """
    Универсальный экстрактор: dict / ORM SensorReading / TelemetryPayload.
    Возвращает плоский dict с именами полей = FEATURE_COLS.
    """
    # ── dict (из API, bridge, демо-генератора) ────────────────
    if isinstance(reading, dict):
        return reading

    # ── TelemetryPayload (Pydantic) ───────────────────────────
    # Определяем по наличию атрибута 'env' (субструктура)
    if hasattr(reading, "env"):
        env  = reading.env
        st   = reading.str_
        dist = reading.dist
        return {
            "humidity":    env.h  if env else None,
            "temperature": env.t  if env else None,
            "light_lux":   env.lx if env else None,
            "pressure":    env.p  if env else None,
            "tilt_roll":   st.roll  if st else None,
            "tilt_pitch":  st.pitch if st else None,
            "accel_z":     st.az    if st else None,
            "vibration":   float(st.vib) if st else 0.0,
            "dist_front":  dist.f if dist else None,
            "dist_back":   dist.b if dist else None,
            "dist_left":   dist.l if dist else None,
            "dist_right":  dist.r if dist else None,
        }

    # ── SensorReading ORM (поля напрямую) ────────────────────
    return {
        "humidity":    getattr(reading, "humidity",    None),
        "temperature": getattr(reading, "temperature", None),
        "light_lux":   getattr(reading, "light_lux",   None),
        "pressure":    getattr(reading, "pressure",    None),
        "tilt_roll":   getattr(reading, "tilt_roll",   None),
        "tilt_pitch":  getattr(reading, "tilt_pitch",  None),
        "accel_z":     getattr(reading, "accel_z",     None),
        "vibration":   float(getattr(reading, "vibration", False)),
        "dist_front":  getattr(reading, "dist_front",  None),
        "dist_back":   getattr(reading, "dist_back",   None),
        "dist_left":   getattr(reading, "dist_left",   None),
        "dist_right":  getattr(reading, "dist_right",  None),
    }


def _cap_dist(v: float | None) -> float:
    """999 (нет препятствия) → DIST_MAX_CM; None → default."""
    if v is None:
        return DIST_MAX_CM
    return min(float(v), DIST_MAX_CM)


def extract_features(reading: Any) -> np.ndarray:
    """
    reading → numpy вектор формы (13,).
    Безопасен к любым None / отсутствующим полям.
    """
    raw = _extract_raw(reading)

    roll  = float(raw.get("tilt_roll")  or 0.0)
    pitch = float(raw.get("tilt_pitch") or 0.0)

    values: list[float] = [
        float(raw.get("humidity")    or _FILL_DEFAULTS["humidity"]),
        float(raw.get("temperature") or _FILL_DEFAULTS["temperature"]),
        float(raw.get("light_lux")   or _FILL_DEFAULTS["light_lux"]),
        float(raw.get("pressure")    or _FILL_DEFAULTS["pressure"]),
        roll,
        pitch,
        max(abs(roll), abs(pitch)),       # max_tilt — агрегат
        float(raw.get("accel_z") or _FILL_DEFAULTS["accel_z"]),
        float(raw.get("vibration") or 0.0),
        _cap_dist(raw.get("dist_front")),
        _cap_dist(raw.get("dist_back")),
        _cap_dist(raw.get("dist_left")),
        _cap_dist(raw.get("dist_right")),
    ]

    return np.array(values, dtype=np.float32)


def extract_features_batch(readings: list[Any]) -> np.ndarray:
    """Батч-версия: список → матрица (N, 13)."""
    return np.stack([extract_features(r) for r in readings], axis=0)


# ══════════════════════════════════════════════════════════════
#  Rule-based авторазметка
#  ТОЧНОЕ зеркало profile.ino::assessDegradation()
#  Порядок операций: score → clamp(0,100) → escalate status
# ══════════════════════════════════════════════════════════════
@dataclass
class RuleResult:
    label:  int    # 0=OK, 1=WARNING, 2=CRITICAL
    status: str
    score:  float
    issues: list[str]


def rule_label(reading: Any) -> RuleResult:
    """
    Детерминированная разметка по правилам прошивки.
    Используется для:
      1. Авторазметки обучающих данных (нет ground truth)
      2. MockClassifier пока модель не обучена
      3. Валидации предсказаний RF
    """
    raw    = _extract_raw(reading)
    score  = 0.0
    status = "OK"
    issues: list[str] = []

    h    = float(raw.get("humidity")    or 0.0)
    t    = float(raw.get("temperature") or 0.0)
    roll = abs(float(raw.get("tilt_roll")  or 0.0))
    ptch = abs(float(raw.get("tilt_pitch") or 0.0))
    lux  = float(raw.get("light_lux") or 0.0)
    vib  = bool(raw.get("vibration") or False)
    max_tilt = max(roll, ptch)

    # ── Зеркало profile.ino::assessDegradation() ─────────────
    # Некоторые блоки ставят status напрямую (=),
    # другие только повышают: if (status < X) status = X.
    # Порядок строго совпадает с прошивкой.

    # ── Local helper: raise status only, never downgrade ─────────
    # String comparison ("CRITICAL" < "OK" < "WARNING" alphabetically)
    # is the INVERSE of semantic severity — always use numeric LABEL_VALUES.
    def _raise(new: str) -> str:
        return new if LABEL_VALUES[new] > LABEL_VALUES[status] else status

    # Влажность
    if h >= THR_HUMIDITY_CRIT:
        score += 40.0
        status = "CRITICAL"                    # прямое присвоение
        issues.append("HIGH_HUMIDITY")
    elif h >= THR_HUMIDITY_WARN:
        score += 20.0
        status = _raise("WARNING")             # только повышаем
        issues.append("ELEVATED_HUMIDITY")

    # Вибрация + комбо
    if vib:
        score += 25.0
        issues.append("VIBRATION_DETECTED")
        if h >= THR_HUMIDITY_CRIT:
            score += 15.0
            status = "CRITICAL"                # прямое присвоение
            issues.append("STRUCTURAL_RISK_COMBO")
        else:
            status = _raise("WARNING")

    # Температура
    if t >= THR_TEMP_CRIT:
        score += 20.0
        status = _raise("WARNING")
        issues.append("HIGH_TEMPERATURE")
    elif t >= THR_TEMP_WARN:
        score += 8.0
        issues.append("ELEVATED_TEMPERATURE")

    # Наклон
    if max_tilt >= THR_TILT_CRIT:
        score += 35.0
        status = "CRITICAL"                    # прямое присвоение
        issues.append("CRITICAL_STRUCTURAL_TILT")
    elif max_tilt >= THR_TILT_WARN:
        score += 12.0
        status = _raise("WARNING")
        issues.append("TILT_DETECTED")

    # Освещённость
    if 0.0 < lux < THR_LIGHT_LOW:
        score += 5.0
        issues.append("POOR_DAYLIGHTING")

    # ── score = constrain(score, 0, 100)  FIRST ───────────────
    # ── затем эскалация ТОЛЬКО из нижних состояний ───────────
    # (строки 69-71 прошивки)
    score = min(score, 100.0)

    if status == "OK"      and score >= 30.0:
        status = "WARNING"
    if status == "WARNING" and score >= 65.0:
        status = "CRITICAL"

    return RuleResult(
        label  = LABEL_VALUES[status],
        status = status,
        score  = round(score, 1),
        issues = issues,
    )
