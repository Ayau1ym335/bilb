from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .features import (
    FEATURE_COLS, LABEL_NAMES, LABEL_VALUES, N_FEATURES,
    RuleResult, extract_features, extract_features_batch, rule_label,
)

log = logging.getLogger("bilb.ml")

MODEL_DIR   = Path(os.getenv("MODEL_DIR", "data/models"))
MODEL_PATH  = MODEL_DIR / "rf_model.joblib"
SCALER_PATH = MODEL_DIR / "rf_scaler.joblib"
META_PATH   = MODEL_DIR / "rf_meta.json"

MIN_SAMPLES_PER_CLASS = 20


@dataclass
class PredictionResult:
    status:        str                   # "OK" / "WARNING" / "CRITICAL"
    label:         int                   # 0 / 1 / 2
    score:         float                 # 0–100
    confidence:    float                 # вероятность предсказанного класса
    probabilities: dict[str, float]      # {"OK": 0.05, "WARNING": 0.12, "CRITICAL": 0.83}
    issues:        list[str]             # из rule_label (всегда заполняется)
    model:         str                   # "mock" / "random_forest"
    rule_status:   str                   # статус по правилам (для сравнения)
    features_used: int = N_FEATURES

class MockClassifier:
    def predict(self, reading: Any) -> PredictionResult:
        rule = rule_label(reading)

        rng         = np.random.default_rng(seed=int(rule.score * 100))
        confidence  = float(rng.uniform(0.68, 0.86))
        other_total = 1.0 - confidence
        other_a     = float(rng.uniform(0.0, other_total))
        other_b     = other_total - other_a

        proba = [0.0, 0.0, 0.0]
        proba[rule.label] = confidence
      
        others = [i for i in range(3) if i != rule.label]
        proba[others[0]] = other_a
        proba[others[1]] = other_b
        proba_arr = np.array(proba, dtype=np.float64)
        proba_arr = proba_arr / proba_arr.sum()

        return PredictionResult(
            status        = rule.status,
            label         = rule.label,
            score         = rule.score,
            confidence    = round(float(proba_arr[rule.label]), 3),
            probabilities = {
                LABEL_NAMES[i]: round(float(proba_arr[i]), 3)
                for i in range(3)
            },
            issues        = rule.issues,
            model         = "mock",
            rule_status   = rule.status,
        )

    def is_trained(self) -> bool:
        return False

class BILBClassifier:
    def __init__(self) -> None:
        self._model:     Any = None
        self._scaler:    Any = None
        self._meta:      dict = {}
        self._trained:   bool = False
        self._mock:      MockClassifier = MockClassifier()
        self._load()

    def _load(self) -> None:
        if not (MODEL_PATH.exists() and SCALER_PATH.exists()):
            log.info("[ML] No saved model found — using MockClassifier")
            return
        try:
            import joblib, json
            self._model  = joblib.load(MODEL_PATH)
            self._scaler = joblib.load(SCALER_PATH)
            if META_PATH.exists():
                self._meta = json.loads(META_PATH.read_text())
            self._trained = True
            log.info(
                "[ML] Model loaded: acc=%.2f%% features=%d trained_on=%d samples",
                self._meta.get("accuracy", 0) * 100,
                self._meta.get("n_features", N_FEATURES),
                self._meta.get("n_samples", 0),
            )
        except Exception as e:
            log.error("[ML] Model load failed: %s — using MockClassifier", e)
            self._trained = False

    def _save(self, metrics: dict) -> None:
        import joblib, json
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model,  MODEL_PATH)
        joblib.dump(self._scaler, SCALER_PATH)
        META_PATH.write_text(json.dumps(metrics, indent=2))
        log.info("[ML] Model saved to %s", MODEL_DIR)

    def is_trained(self) -> bool:
        return self._trained

    def train(
        self,
        readings: list[Any],
        *,
        save:              bool = True,
        n_estimators:      int  = 200,
        max_depth:         int  = 12,
        min_samples_leaf:  int  = 3,
        test_size:         float = 0.20,
        random_state:      int  = 42,
    ) -> dict:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split, StratifiedKFold
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import (
            classification_report, accuracy_score, confusion_matrix
        )

        if len(readings) == 0:
            raise ValueError("No readings provided for training")

        log.info("[ML] Extracting features from %d readings...", len(readings))

        X = extract_features_batch(readings)   # (N, 13)

        labels: list[int] = []
        for r in readings:
            lbl = None
            if isinstance(r, dict):
                if "label" in r:
                    lbl = int(r["label"])
                elif "status" in r and r["status"] in LABEL_VALUES:
                    lbl = LABEL_VALUES[r["status"]]
            elif hasattr(r, "label"):
                lbl = int(r.label)
            elif hasattr(r, "status") and getattr(r, "status") in LABEL_VALUES:
                lbl = LABEL_VALUES[r.status]

            if lbl is None:
                lbl = rule_label(r).label    # авторазметка
            labels.append(lbl)

        y = np.array(labels, dtype=np.int32)

        unique, counts = np.unique(y, return_counts=True)
        class_dist = {LABEL_NAMES[int(u)]: int(c) for u, c in zip(unique, counts)}
        log.info("[ML] Class distribution: %s", class_dist)

        rare = [k for k, v in class_dist.items() if v < MIN_SAMPLES_PER_CLASS]
        if rare:
            log.warning(
                "[ML] Rare classes %s (<% d samples) — model may be weak. "
                "Collect more data or use demo mode to augment.",
                rare, MIN_SAMPLES_PER_CLASS
            )

        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y,
            test_size    = test_size,
            stratify     = y,
            random_state = random_state,
        )

        self._scaler = StandardScaler()
        X_tr_s = self._scaler.fit_transform(X_tr)
        X_te_s = self._scaler.transform(X_te)

        self._model = RandomForestClassifier(
            n_estimators     = n_estimators,
            max_depth        = max_depth,
            min_samples_leaf = min_samples_leaf,
            class_weight     = "balanced",   # критично: CRITICAL редок
            random_state     = random_state,
            n_jobs           = -1,           # все CPU
            oob_score        = True,         # out-of-bag оценка
        )
        self._model.fit(X_tr_s, y_tr)
        self._trained = True

        y_pred     = self._model.predict(X_te_s)
        acc        = accuracy_score(y_te, y_pred)
        oob        = float(self._model.oob_score_)
        report     = classification_report(
            y_te, y_pred,
            target_names = ["OK", "WARNING", "CRITICAL"],
            output_dict  = True,
            zero_division = 0,
        )
        cm = confusion_matrix(y_te, y_pred, labels=[0, 1, 2]).tolist()

        importances = self._model.feature_importances_
        feat_imp = {
            col: round(float(imp), 4)
            for col, imp in zip(FEATURE_COLS, importances)
        }
        feat_imp_sorted = dict(
            sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)
        )

        metrics = {
            "accuracy":            round(acc, 4),
            "oob_score":           round(oob, 4),
            "n_samples":           len(readings),
            "n_train":             len(y_tr),
            "n_test":              len(y_te),
            "n_features":          N_FEATURES,
            "n_estimators":        n_estimators,
            "class_distribution":  class_dist,
            "per_class":           {
                cls: {
                    "precision": round(report[cls]["precision"], 3),
                    "recall":    round(report[cls]["recall"],    3),
                    "f1":        round(report[cls]["f1-score"],  3),
                    "support":   int(report[cls]["support"]),
                }
                for cls in ["OK", "WARNING", "CRITICAL"]
                if cls in report
            },
            "feature_importance":  feat_imp_sorted,
            "confusion_matrix":    cm,
        }

        log.info(
            "[ML] Training complete: acc=%.2f%% oob=%.2f%% n=%d",
            acc * 100, oob * 100, len(readings)
        )
        _log_feature_importance(feat_imp_sorted)

        if save:
            self._save(metrics)

        return metrics

    def predict(self, reading: Any) -> PredictionResult:
        if not self._trained:
            return self._mock.predict(reading)

        X   = extract_features(reading).reshape(1, -1)   # (1, 13)
        X_s = self._scaler.transform(X)

        label      = int(self._model.predict(X_s)[0])
        proba_arr  = self._model.predict_proba(X_s)[0]   # shape (3,)

        score = float(0.0 * proba_arr[0] +
                      50.0 * proba_arr[1] +
                      100.0 * proba_arr[2])

        rule = rule_label(reading)

        return PredictionResult(
            status        = LABEL_NAMES[label],
            label         = label,
            score         = round(score, 1),
            confidence    = round(float(proba_arr[label]), 3),
            probabilities = {
                LABEL_NAMES[i]: round(float(proba_arr[i]), 3)
                for i in range(3)
            },
            issues        = rule.issues,
            model         = "random_forest",
            rule_status   = rule.status,
        )

    def predict_batch(self, readings: list[Any]) -> list[PredictionResult]:
        if not self._trained:
            return [self._mock.predict(r) for r in readings]

        X   = extract_features_batch(readings)
        X_s = self._scaler.transform(X)

        labels     = self._model.predict(X_s)
        probas     = self._model.predict_proba(X_s)

        results = []
        for i, (reading, lbl, proba) in enumerate(zip(readings, labels, probas)):
            score = float(0.0 * proba[0] + 50.0 * proba[1] + 100.0 * proba[2])
            rule  = rule_label(reading)
            results.append(PredictionResult(
                status        = LABEL_NAMES[int(lbl)],
                label         = int(lbl),
                score         = round(score, 1),
                confidence    = round(float(proba[int(lbl)]), 3),
                probabilities = {LABEL_NAMES[j]: round(float(proba[j]), 3) for j in range(3)},
                issues        = rule.issues,
                model         = "random_forest",
                rule_status   = rule.status,
            ))
        return results

    @property
    def meta(self) -> dict:
        return self._meta.copy()

    @property
    def feature_importance(self) -> dict[str, float]:
        if not self._trained:
            return {}
        return dict(zip(FEATURE_COLS, self._model.feature_importances_))


# ══════════════════════════════════════════════════════════════
#  Singleton + публичный API
# ══════════════════════════════════════════════════════════════
_instance: Optional[BILBClassifier] = None


def get_classifier() -> BILBClassifier:
    """
    Возвращает глобальный экземпляр BILBClassifier.
    Lazy-init при первом вызове.
    """
    global _instance
    if _instance is None:
        _instance = BILBClassifier()
    return _instance


def get_status(reading: Any) -> dict:
    """
    Главный публичный API Движка 1.

    Принимает: dict / SensorReading ORM / TelemetryPayload
    Возвращает:
        {
            "status":        "WARNING",
            "label":         1,
            "score":         47.5,
            "confidence":    0.83,
            "probabilities": {"OK": 0.05, "WARNING": 0.83, "CRITICAL": 0.12},
            "issues":        ["HIGH_HUMIDITY", "VIBRATION_DETECTED"],
            "model":         "random_forest",   # или "mock"
            "rule_status":   "WARNING",
        }
    """
    result = get_classifier().predict(reading)
    return {
        "status":        result.status,
        "label":         result.label,
        "score":         result.score,
        "confidence":    result.confidence,
        "probabilities": result.probabilities,
        "issues":        result.issues,
        "model":         result.model,
        "rule_status":   result.rule_status,
    }


def reload_classifier() -> BILBClassifier:
    """Принудительно перезагружает модель с диска (после переобучения)."""
    global _instance
    _instance = BILBClassifier()
    return _instance


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════
def _log_feature_importance(feat_imp: dict[str, float]) -> None:
    log.info("[ML] Feature importance (top 5):")
    for i, (feat, imp) in enumerate(list(feat_imp.items())[:5]):
        bar = "█" * int(imp * 40)
        log.info("  %-18s %s %.4f", feat, bar, imp)


# ══════════════════════════════════════════════════════════════
#  CLI — обучение из командной строки
#  python -m ml.classifier --train
#  python -m ml.classifier --train --min-samples 100
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse, asyncio, sys, json
    sys.path.insert(0, str(Path(__file__).parent.parent))

    BUILDING_ID: str = os.getenv("BUILDING_ID", "BILB_001")   # mirrors bridge.py

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="BILB ML Classifier Training")
    parser.add_argument("--train",       action="store_true", help="Train model")
    parser.add_argument("--min-samples", type=int, default=50,
                        help="Min readings; use demo data if fewer")
    parser.add_argument("--estimators",  type=int, default=200)
    parser.add_argument("--depth",       type=int, default=12)
    parser.add_argument("--evaluate",    action="store_true",
                        help="Run evaluation on latest data")
    args = parser.parse_args()

    async def _run():
        from ingestion.database import create_tables
        from ingestion.repository import get_latest_readings
        from ingestion.database import db_session

        await create_tables()

        async with db_session() as db:
            readings = await get_latest_readings(db, BUILDING_ID, limit=10000)

        log.info("Loaded %d readings from DB", len(readings))

        if len(readings) < args.min_samples:
            log.warning(
                "Only %d readings, need %d — generating synthetic data...",
                len(readings), args.min_samples
            )
            # Импортируем демо-генератор из bridge
            from ingestion.bridge import DemoGenerator
            import json as _json
            gen = DemoGenerator("BILB_001")
            synthetic = []
            for _ in range(max(args.min_samples * 10, 2000)):
                pkt = gen.next()
                # Конвертируем string-floats обратно в float для feature extraction
                synthetic.append({
                    "humidity":    float(pkt["env"]["h"]),
                    "temperature": float(pkt["env"]["t"]),
                    "light_lux":   float(pkt["env"]["lx"]),
                    "pressure":    float(pkt["env"]["p"]),
                    "tilt_roll":   float(pkt["str"]["roll"]),
                    "tilt_pitch":  float(pkt["str"]["pitch"]),
                    "accel_z":     float(pkt["str"]["az"]),
                    "vibration":   float(pkt["str"]["vib"]),
                    "dist_front":  float(pkt["dist"]["f"]),
                    "dist_back":   float(pkt["dist"]["b"]),
                    "dist_left":   float(pkt["dist"]["l"]),
                    "dist_right":  float(pkt["dist"]["r"]),
                })
            readings = synthetic
            log.info("Using %d synthetic samples", len(readings))

        if args.train:
            clf = get_classifier()
            metrics = clf.train(
                readings,
                n_estimators = args.estimators,
                max_depth    = args.depth,
            )
            print("\n" + "=" * 50)
            print(f"  Accuracy:  {metrics['accuracy']:.2%}")
            print(f"  OOB Score: {metrics['oob_score']:.2%}")
            print(f"  Samples:   {metrics['n_samples']}")
            print(f"  Classes:   {metrics['class_distribution']}")
            print("=" * 50)
            print("\nPer-class metrics:")
            for cls, m in metrics["per_class"].items():
                print(f"  {cls:<10} P={m['precision']:.2f} R={m['recall']:.2f} "
                      f"F1={m['f1']:.2f} n={m['support']}")
            print("\nTop features:")
            for feat, imp in list(metrics["feature_importance"].items())[:6]:
                bar = "█" * int(imp * 50)
                print(f"  {feat:<18} {bar} {imp:.4f}")

        if args.evaluate:
            clf = get_classifier()
            if not clf.is_trained():
                print("Model not trained yet. Run with --train first.")
                return
            results = clf.predict_batch(readings[:100])
            acc = sum(
                1 for r, raw in zip(results, readings[:100])
                if r.status == r.rule_status
            ) / len(results)
            print(f"\nAgreement with rule baseline: {acc:.1%}")

    asyncio.run(_run())
