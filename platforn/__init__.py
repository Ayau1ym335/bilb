"""
ml/  —  BILB Machine Learning Layer
════════════════════════════════════
Публичный API:

    from ml import get_status, get_classifier, rule_label

    # Быстрый predict для одной записи
    result = get_status(reading)
    # → {"status": "CRITICAL", "score": 72.5, "confidence": 0.91, ...}

    # Обучение
    clf = get_classifier()
    metrics = clf.train(readings_list)

    # Rule-based разметка (без ML)
    rule = rule_label(reading)
    # → RuleResult(label=2, status="CRITICAL", score=80.0, issues=[...])
"""

from .features import (
    FEATURE_COLS,
    LABEL_NAMES,
    LABEL_VALUES,
    N_FEATURES,
    RuleResult,
    extract_features,
    extract_features_batch,
    rule_label,
)
from .classifier import (
    BILBClassifier,
    MockClassifier,
    PredictionResult,
    get_classifier,
    get_status,
    reload_classifier,
)

__all__ = [
    # Features
    "FEATURE_COLS", "LABEL_NAMES", "LABEL_VALUES", "N_FEATURES",
    "RuleResult", "extract_features", "extract_features_batch", "rule_label",
    # Classifier
    "BILBClassifier", "MockClassifier", "PredictionResult",
    "get_classifier", "get_status", "reload_classifier",
]


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
