


"""
llm/  —  BILB LLM Strategist (Движок 2)
═════════════════════════════════════════
Публичный API:

    from llm import generate_scenarios, generate_scenarios_async

    # Синхронно (для bridge, CLI, Streamlit)
    scenarios = generate_scenarios(building_data)

    # Асинхронно (для FastAPI)
    scenarios = await generate_scenarios_async(building_data)

    # Каждый сценарий — dict:
    # {
    #   "id": 1,
    #   "title": "Cultural Hub & Coworking",
    #   "type": "cultural",
    #   "tagline": "Historic character becomes the brand.",
    #   "description": "...",
    #   "benefits": ["...", "..."],
    #   "challenges": ["...", "..."],
    #   "priority_works": ["...", "..."],
    #   "estimated_cost_usd_m2": 950,
    #   "roi_years": 6.5,
    #   "co2_saving_pct": 58.0,
    #   "feasibility_score": 82
    # }
"""

from .rag import retrieve, reload_index, list_kb_files
from .prompt import Scenario, build_building_context, fallback_scenarios, parse_scenarios
from .strategist import (
    LLMStrategist,
    generate_scenarios,
    generate_scenarios_async,
    get_strategist,
)

__all__ = [
    # RAG
    "retrieve", "reload_index", "list_kb_files",
    # Prompt / Schema
    "Scenario", "build_building_context", "fallback_scenarios", "parse_scenarios",
    # Strategist
    "LLMStrategist", "get_strategist",
    "generate_scenarios", "generate_scenarios_async",
]
