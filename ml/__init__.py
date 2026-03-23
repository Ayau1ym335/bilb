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