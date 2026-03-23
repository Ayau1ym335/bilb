"""
llm/prompt.py  —  Prompt Engineering & Output Parsing
═══════════════════════════════════════════════════════
Отвечает за:
  · Сборку промпта из шаблона + контекст здания + RAG-знания
  · Парсинг ответа Gemini → валидированный список сценариев
  · Fallback-сценарии (без API-ключа или при ошибке)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("bilb.prompt")

# ══════════════════════════════════════════════════════════════
#  Схема одного сценария (валидация ответа Gemini)
# ══════════════════════════════════════════════════════════════
SCENARIO_TYPES = ("cultural", "commercial", "educational", "residential", "industrial")


class Scenario(BaseModel):
    id:                    int
    title:                 str   = Field(min_length=3, max_length=100)
    type:                  str   = Field(pattern=r"^(cultural|commercial|educational|residential|industrial)$")
    tagline:               str   = Field(min_length=5, max_length=120)
    description:           str   = Field(min_length=30)
    benefits:              list[str]
    challenges:            list[str]
    priority_works:        list[str]
    estimated_cost_usd_m2: float = Field(ge=100, le=10000)
    roi_years:             float = Field(ge=1, le=30)
    co2_saving_pct:        float = Field(ge=0, le=100)
    feasibility_score:     int   = Field(ge=0, le=100)

    @field_validator("benefits", "challenges", "priority_works", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> list:
        if isinstance(v, str):
            return [v]
        return v or []


# ══════════════════════════════════════════════════════════════
#  Контекст здания для промпта
# ══════════════════════════════════════════════════════════════
def build_building_context(building_data: dict) -> str:
    """
    building_data: dict с полями из BuildingProfile + ML-результаты.
    Ожидаемые ключи (все опциональны):
      name, city, year_built, area_m2, floors, address,
      overall_status, degradation_score,
      avg_humidity, avg_temperature, avg_light_lux,
      max_tilt_roll, max_tilt_pitch, vibration_events, total_readings,
      issues (list[str] или str)
    """
    name        = building_data.get("name")        or "Unknown Building"
    city        = building_data.get("city")        or "Unknown City"
    year_built  = building_data.get("year_built")  or "Unknown"
    area        = building_data.get("area_m2")
    floors      = building_data.get("floors")
    status      = building_data.get("overall_status") or building_data.get("status") or "UNKNOWN"
    score       = building_data.get("degradation_score") or building_data.get("score") or 0
    humidity    = building_data.get("avg_humidity")    or building_data.get("humidity")    or 0
    temp        = building_data.get("avg_temperature") or building_data.get("temperature") or 0
    light       = building_data.get("avg_light_lux")   or building_data.get("light_lux")   or 0
    tilt_r      = building_data.get("max_tilt_roll")   or building_data.get("tilt_roll")   or 0
    tilt_p      = building_data.get("max_tilt_pitch")  or building_data.get("tilt_pitch")  or 0
    vib_events  = building_data.get("vibration_events") or 0

    # Normalize issues to list
    raw_issues  = building_data.get("issues") or []
    if isinstance(raw_issues, str):
        try:
            raw_issues = json.loads(raw_issues)
        except Exception:
            raw_issues = [i.strip() for i in raw_issues.split(",") if i.strip()]
    issues_str  = ", ".join(raw_issues) if raw_issues else "None detected"

    area_str   = f"{area:.0f} m²" if area else "unknown"
    floors_str = f"{floors} floors" if floors else "unknown"

    return f"""Building: {name}
Location: {city}
Year built: {year_built}
Size: {area_str}, {floors_str}

AI Diagnostic Status: {status} (Degradation Score: {score:.1f}/100)

Sensor Data (averaged across all scans):
  Temperature:      {temp:.1f}°C
  Humidity:         {humidity:.1f}%
  Light level:      {light:.0f} lux
  Max tilt (roll):  {tilt_r:.1f}°
  Max tilt (pitch): {tilt_p:.1f}°
  Vibration events: {vib_events}

Identified structural/environmental issues:
  {issues_str}"""


# ══════════════════════════════════════════════════════════════
#  Системный промпт (статический)
# ══════════════════════════════════════════════════════════════
_SYSTEM_PROMPT = """You are an expert in adaptive reuse of historic buildings, \
sustainable architecture, and real estate development economics. \
You analyze building inspection data and generate commercially viable \
renovation scenarios for architects, investors, and city planners.

Your scenarios must:
1. Be grounded in the actual sensor data and structural condition
2. Reference specific issues (humidity, tilt, vibration) and propose solutions
3. Be commercially realistic for the local market context
4. Include honest feasibility scores based on the building condition
5. Prioritize the most urgent structural works given the sensor findings

Respond ONLY with a valid JSON object. No markdown, no code fences, no preamble."""


# ══════════════════════════════════════════════════════════════
#  Пользовательский промпт (динамический)
# ══════════════════════════════════════════════════════════════
_USER_TEMPLATE = """
## Architectural & Financial Knowledge Base (retrieved context):
{kb_context}

---

## Building Inspection Report:
{building_context}

---

## Task:
Generate exactly 3 adaptive reuse scenarios for this building.
Each scenario must account for the actual building condition above.
Scenarios should represent meaningfully different use-cases with different
risk/reward profiles.

Respond ONLY with this exact JSON structure (no markdown, no code fences):
{{
  "scenarios": [
    {{
      "id": 1,
      "title": "Scenario title (max 8 words)",
      "type": "cultural|commercial|educational|residential|industrial",
      "tagline": "One compelling sentence, max 15 words",
      "description": "3-4 sentences. Reference specific building condition. Be concrete about what makes this viable or challenging given the sensor data.",
      "benefits": ["Benefit 1", "Benefit 2", "Benefit 3"],
      "challenges": ["Challenge 1", "Challenge 2"],
      "priority_works": ["First work needed", "Second work needed"],
      "estimated_cost_usd_m2": 1200,
      "roi_years": 7.5,
      "co2_saving_pct": 55,
      "feasibility_score": 82
    }}
  ]
}}

Generate all 3 scenarios now:"""


def build_prompt(building_data: dict, kb_context: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) ready for Gemini.
    """
    building_ctx = build_building_context(building_data)
    user = _USER_TEMPLATE.format(
        kb_context       = kb_context or "(no knowledge base context available)",
        building_context = building_ctx,
    )
    return _SYSTEM_PROMPT, user


# ══════════════════════════════════════════════════════════════
#  Парсинг и валидация ответа Gemini
# ══════════════════════════════════════════════════════════════
def _strip_fences(text: str) -> str:
    """Убирает markdown ```json ... ``` если Gemini всё-таки добавил."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # убираем первую и последнюю строку (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text  = "\n".join(inner).strip()
    return text


def parse_scenarios(raw_text: str) -> list[Scenario]:
    """
    Парсит сырой ответ Gemini → список Scenario.
    Raises ValueError если ответ нераспарсируем.
    """
    clean = _strip_fences(raw_text)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        # Попытка извлечь JSON из середины ответа (Gemini иногда добавляет текст)
        match = re.search(r'\{.*"scenarios".*\}', clean, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                raise ValueError(f"Cannot parse Gemini response as JSON: {e}") from e
        else:
            raise ValueError(f"No JSON found in Gemini response: {e}") from e

    raw_list = data.get("scenarios", [])
    if not raw_list:
        raise ValueError("Gemini response has no 'scenarios' key or empty list")

    scenarios: list[Scenario] = []
    for i, raw in enumerate(raw_list):
        try:
            # Присвоить id если не задан
            if "id" not in raw:
                raw["id"] = i + 1
            s = Scenario.model_validate(raw)
            scenarios.append(s)
        except Exception as e:
            log.warning("Scenario %d validation failed: %s — skipping", i, e)

    if not scenarios:
        raise ValueError("All scenarios failed validation")

    return scenarios[:3]   # максимум 3


# ══════════════════════════════════════════════════════════════
#  Fallback сценарии (без API или при ошибке)
# ══════════════════════════════════════════════════════════════
def fallback_scenarios(building_data: dict) -> list[Scenario]:
    """
    Генерирует детерминированные fallback-сценарии на основе
    статуса здания. Не требует API.
    """
    status  = (building_data.get("overall_status") or
                building_data.get("status") or "UNKNOWN").upper()
    issues  = building_data.get("issues") or []
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except Exception:
            issues = [i.strip() for i in issues.split(",") if i.strip()]

    # Формируем список приоритетных работ на основе issues
    priority: list[str] = []
    if any("HUMIDITY" in i for i in issues):
        priority.append("Waterproofing and dehumidification system")
    if any("VIBRATION" in i for i in issues) or any("STRUCTURAL" in i for i in issues):
        priority.append("Structural engineering assessment")
    if any("TILT" in i for i in issues):
        priority.append("Geotechnical survey and foundation review")
    if any("LIGHT" in i or "DAYLIGHTING" in i for i in issues):
        priority.append("Facade glazing or skylight installation")
    if not priority:
        priority = ["General building survey", "MEP audit"]

    # Корректируем feasibility в зависимости от состояния
    penalty = {"OK": 0, "WARNING": 10, "CRITICAL": 20}.get(status, 15)

    return [
        Scenario(
            id    = 1,
            title = "Cultural Hub & Coworking Space",
            type  = "cultural",
            tagline = "Historic character becomes the brand — rent premium guaranteed.",
            description = (
                f"The building's architectural fabric — with status {status} — "
                "requires targeted remediation before opening, but its spatial quality "
                "makes it ideal for creative coworking. High ceilings and exposed "
                "structure attract premium tenants willing to pay 20–25% above market rate."
            ),
            benefits        = [
                "Minimal structural reconfiguration preserves historic character",
                "Strong grant eligibility from cultural heritage programs",
                "25% rental premium vs standard office space",
            ],
            challenges      = ["Sound insulation requirements", "Fire code compliance"],
            priority_works  = priority[:2],
            estimated_cost_usd_m2 = 950,
            roi_years             = 6.5,
            co2_saving_pct        = 58.0,
            feasibility_score     = max(20, 88 - penalty),
        ),
        Scenario(
            id    = 2,
            title = "Boutique Heritage Hotel",
            type  = "commercial",
            tagline = "Sleep inside history — the fastest-growing luxury travel segment.",
            description = (
                "The 1950s–1970s architectural style is increasingly sought by "
                "experiential travelers. Current building condition requires full MEP "
                f"replacement ({status} status), but the heritage premium justifies "
                "higher capex. Target $150–300/night with 65% occupancy."
            ),
            benefits        = [
                "Unique positioning: no direct competition from chain hotels",
                "ESG credentials attract institutional investors and green bonds",
                "Heritage tourism growing 12% YoY globally",
            ],
            challenges      = ["Highest upfront capex", "Complex fire suppression retrofit"],
            priority_works  = priority + ["Full MEP replacement"],
            estimated_cost_usd_m2 = 1800,
            roi_years             = 9.0,
            co2_saving_pct        = 52.0,
            feasibility_score     = max(20, 74 - penalty),
        ),
        Scenario(
            id    = 3,
            title = "STEAM Education & Innovation Center",
            type  = "educational",
            tagline = "State grants cover 30% — lowest financial risk on the table.",
            description = (
                "Partnership with universities and tech companies provides stable "
                "long-term revenue regardless of building condition. Institutional "
                "tenants accept phased renovation. Government STEAM programs "
                f"provide grants covering 25–35% of total costs even at {status} status."
            ),
            benefits        = [
                "Government grants reduce net investment by 25–35%",
                "10-year institutional lease eliminates vacancy risk",
                "STEM talent pipeline attracts tech company co-location",
            ],
            challenges      = ["Requires accessibility upgrades", "Lab ventilation specifications"],
            priority_works  = priority[:2],
            estimated_cost_usd_m2 = 1100,
            roi_years             = 7.0,
            co2_saving_pct        = 61.0,
            feasibility_score     = max(20, 82 - penalty),
        ),
    ]
