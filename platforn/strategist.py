"""
llm/strategist.py  —  Движок 2: Стратег
══════════════════════════════════════════
Публичный API:
    generate_scenarios(building_data) → list[dict]
    get_strategist()                  → LLMStrategist (singleton)

Жизненный цикл:
  1. При вызове: строит контекст здания + RAG retrieval
  2. Формирует промпт через prompt.py
  3. Отправляет в Gemini 1.5 Flash (быстрее и дешевле Pro для MVP)
  4. Парсит и валидирует ответ через Pydantic
  5. Если Gemini недоступен/ошибка → возвращает fallback_scenarios()
  6. Кэширует результат в памяти (TTL = 10 минут)

▶ НАСТРОЙТЕ в .env:
    GEMINI_API_KEY=your_key_here
    GEMINI_MODEL=gemini-1.5-flash   # или gemini-1.5-pro
    SCENARIO_CACHE_TTL=600          # секунды
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional

from .prompt import (
    Scenario,
    build_prompt,
    fallback_scenarios,
    parse_scenarios,
)
from .rag import retrieve, list_kb_files

log = logging.getLogger("bilb.llm")

# ── Настройки ─────────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")   # ▶ НАСТРОЙТЕ
CACHE_TTL       = int(os.getenv("SCENARIO_CACHE_TTL", "600"))       # секунды
MAX_RETRIES     = 2
TEMPERATURE     = 0.4   # низкая → более предсказуемые/структурированные ответы
MAX_TOKENS      = 2048


# ══════════════════════════════════════════════════════════════
#  In-memory cache (TTL-based)
# ══════════════════════════════════════════════════════════════
class _Cache:
    def __init__(self, ttl: int = CACHE_TTL) -> None:
        self._store: dict[str, tuple[float, list]] = {}
        self._ttl   = ttl

    def _key(self, building_data: dict) -> str:
        # Кэш-ключ на основе building_id + статуса + округлённых агрегатов
        parts = [
            building_data.get("building_id", ""),
            building_data.get("overall_status") or building_data.get("status") or "",
            str(round(building_data.get("degradation_score") or 0, 0)),
            str(round(building_data.get("avg_humidity")      or 0, 0)),
        ]
        return hashlib.md5("|".join(parts).encode()).hexdigest()

    def get(self, building_data: dict) -> Optional[list]:
        k = self._key(building_data)
        if k not in self._store:
            return None
        ts, value = self._store[k]
        if time.time() - ts > self._ttl:
            del self._store[k]
            return None
        return value

    def set(self, building_data: dict, value: list) -> None:
        self._store[self._key(building_data)] = (time.time(), value)

    def invalidate(self, building_data: dict) -> None:
        k = self._key(building_data)
        self._store.pop(k, None)

    def clear(self) -> None:
        self._store.clear()


# ══════════════════════════════════════════════════════════════
#  Gemini Client (тонкая обёртка)
# ══════════════════════════════════════════════════════════════
class _GeminiClient:
    def __init__(self) -> None:
        self._model = None
        self._ok    = False
        self._init()

    def _init(self) -> None:
        if not GEMINI_API_KEY:
            log.info("[LLM] GEMINI_API_KEY not set — will use fallback scenarios")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            self._model = genai.GenerativeModel(
                model_name     = GEMINI_MODEL,
                generation_config = {
                    "temperature":       TEMPERATURE,
                    "max_output_tokens": MAX_TOKENS,
                    "response_mime_type": "application/json",  # JSON mode
                },
            )
            self._ok = True
            log.info("[LLM] Gemini client ready: model=%s", GEMINI_MODEL)
        except ImportError:
            log.warning("[LLM] google-generativeai not installed. "
                        "Run: pip install google-generativeai")
        except Exception as e:
            log.error("[LLM] Gemini init failed: %s", e)

    @property
    def available(self) -> bool:
        return self._ok and self._model is not None

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Синхронный вызов Gemini.
        Возвращает raw text ответа.
        """
        if not self.available:
            raise RuntimeError("Gemini client not available")

        # Gemini не имеет отдельного system role — объединяем
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        response = self._model.generate_content(full_prompt)
        return response.text

    async def generate_async(self, system_prompt: str, user_prompt: str) -> str:
        """Async wrapper через run_in_executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.generate, system_prompt, user_prompt
        )


# ══════════════════════════════════════════════════════════════
#  LLMStrategist  —  главный класс
# ══════════════════════════════════════════════════════════════
class LLMStrategist:

    def __init__(self) -> None:
        self._client = _GeminiClient()
        self._cache  = _Cache()
        log.info("[LLM] Strategist ready. KB files: %s", list_kb_files())

    # ──────────────────────────────────────────────────────────
    #  Core: generate scenarios
    # ──────────────────────────────────────────────────────────
    def generate(
        self,
        building_data: dict,
        *,
        use_cache:      bool = True,
        force_fallback: bool = False,
    ) -> list[Scenario]:
        """
        Синхронная генерация 3 сценариев.

        building_data: dict с полями BuildingProfile + ML-результаты.
        use_cache:     использовать кэш (TTL = CACHE_TTL секунд).
        force_fallback: принудительно вернуть fallback без Gemini.

        Возвращает: list[Scenario] (всегда 3 элемента)
        """
        # 1. Кэш
        if use_cache:
            cached = self._cache.get(building_data)
            if cached is not None:
                log.debug("[LLM] Cache hit for building %s",
                          building_data.get("building_id"))
                return [Scenario.model_validate(s) for s in cached]

        # 2. Fallback bypass
        if force_fallback or not self._client.available:
            log.info("[LLM] Using fallback scenarios (Gemini unavailable)")
            scenarios = fallback_scenarios(building_data)
            if use_cache:
                self._cache.set(building_data, [s.model_dump() for s in scenarios])
            return scenarios

        # 3. RAG retrieval
        issues_str = _issues_to_str(building_data)
        status_str = (building_data.get("overall_status") or
                      building_data.get("status") or "")
        rag_query  = f"{status_str} {issues_str} adaptive reuse renovation scenario"
        kb_context = retrieve(rag_query)

        # 4. Prompt
        system_prompt, user_prompt = build_prompt(building_data, kb_context)

        # 5. Gemini call with retries
        scenarios: list[Scenario] = []
        last_err: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log.info("[LLM] Gemini request attempt %d/%d", attempt, MAX_RETRIES)
                raw = self._client.generate(system_prompt, user_prompt)
                scenarios = parse_scenarios(raw)
                log.info("[LLM] Generated %d scenarios via Gemini", len(scenarios))
                break
            except Exception as e:
                last_err = e
                log.warning("[LLM] Attempt %d failed: %s", attempt, e)

        if not scenarios:
            log.warning("[LLM] All Gemini attempts failed (%s) — using fallback", last_err)
            scenarios = fallback_scenarios(building_data)

        # 6. Кэшируем и возвращаем
        if use_cache:
            self._cache.set(building_data, [s.model_dump() for s in scenarios])
        return scenarios

    async def generate_async(
        self,
        building_data: dict,
        *,
        use_cache:      bool = True,
        force_fallback: bool = False,
    ) -> list[Scenario]:
        """Async версия для FastAPI/Streamlit."""
        # Кэш и fallback — без async overhead
        if use_cache:
            cached = self._cache.get(building_data)
            if cached is not None:
                return [Scenario.model_validate(s) for s in cached]

        if force_fallback or not self._client.available:
            scenarios = fallback_scenarios(building_data)
            if use_cache:
                self._cache.set(building_data, [s.model_dump() for s in scenarios])
            return scenarios

        # RAG + prompt (CPU-bound, но быстро)
        issues_str = _issues_to_str(building_data)
        status_str = building_data.get("overall_status") or building_data.get("status") or ""
        kb_context = retrieve(f"{status_str} {issues_str} adaptive reuse")
        system_prompt, user_prompt = build_prompt(building_data, kb_context)

        scenarios = []
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw       = await self._client.generate_async(system_prompt, user_prompt)
                scenarios = parse_scenarios(raw)
                log.info("[LLM] Generated %d scenarios (async)", len(scenarios))
                break
            except Exception as e:
                last_err = e
                log.warning("[LLM] Async attempt %d failed: %s", attempt, e)

        if not scenarios:
            scenarios = fallback_scenarios(building_data)

        if use_cache:
            self._cache.set(building_data, [s.model_dump() for s in scenarios])
        return scenarios

    # ──────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────
    def invalidate_cache(self, building_data: dict) -> None:
        self._cache.invalidate(building_data)

    def clear_cache(self) -> None:
        self._cache.clear()

    @property
    def gemini_available(self) -> bool:
        return self._client.available

    @property
    def model_name(self) -> str:
        return GEMINI_MODEL if self._client.available else "fallback"


# ══════════════════════════════════════════════════════════════
#  Singleton + публичный API
# ══════════════════════════════════════════════════════════════
_instance: Optional[LLMStrategist] = None


def get_strategist() -> LLMStrategist:
    """Глобальный экземпляр LLMStrategist (lazy init)."""
    global _instance
    if _instance is None:
        _instance = LLMStrategist()
    return _instance


def generate_scenarios(
    building_data: dict,
    *,
    use_cache:      bool = True,
    force_fallback: bool = False,
) -> list[dict]:
    """
    Главный публичный API Движка 2.

    building_data: dict с полями BuildingProfile / TelemetryPayload.
    Возвращает список из 3 словарей сценариев.

    Пример:
        scenarios = generate_scenarios(building_data)
        # → [
        #     {"id": 1, "title": "Cultural Hub", "type": "cultural",
        #      "feasibility_score": 82, "roi_years": 6.5,
        #      "co2_saving_pct": 58, "estimated_cost_usd_m2": 950,
        #      "benefits": [...], "challenges": [...], ...},
        #     {...},
        #     {...}
        #   ]
    """
    scenarios = get_strategist().generate(
        building_data,
        use_cache      = use_cache,
        force_fallback = force_fallback,
    )
    return [s.model_dump() for s in scenarios]


async def generate_scenarios_async(
    building_data: dict,
    *,
    use_cache:      bool = True,
    force_fallback: bool = False,
) -> list[dict]:
    """Async версия для FastAPI эндпоинтов."""
    scenarios = await get_strategist().generate_async(
        building_data,
        use_cache      = use_cache,
        force_fallback = force_fallback,
    )
    return [s.model_dump() for s in scenarios]


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════
def _issues_to_str(building_data: dict) -> str:
    issues = building_data.get("issues") or []
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except Exception:
            issues = [i.strip() for i in issues.split(",") if i.strip()]
    return " ".join(issues)
