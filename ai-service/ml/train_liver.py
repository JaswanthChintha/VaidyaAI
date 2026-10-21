from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.data import conditions as C
from app.data.feature_catalog import FEATURES
from app.schemas.decisions import DecisionStatus, RiskLevel
from app.services.decision_engine import merge_decision_set
from app.services.rule_engine import evaluate_rules

DATASET = SERVICE_ROOT / "datasets" / "raw" / "ilpd_uci.csv"
ARTIFACT_DIR = HERE / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "liver_rf_v1.joblib"
METRICS_PATH = ARTIFACT_DIR / "liver_rf_v1.metrics.json"
COMPARISON_PATH = ARTIFACT_DIR / "liver_rules_vs_model.json"

ARTIFACT_VERSION = "1.0.0"
MODEL_ID = "liver_rf"
RANDOM_STATE = 42
TEST_SIZE = 0.25
CV_FOLDS = 5
BOOTSTRAP_RESAMPLES = 2000
SPECIFICITY_TOLERANCE = 0.05
ROBUSTNESS_SPLITS = 100

UCI_COLUMNS = [
    "age", "gender", "tb", "db", "alkphos", "sgpt", "sgot", "tp", "alb",
    "ag_ratio", "selector",
]
COLUMN_RENAME = {
    "tb": "bilirubin_total",
    "sgpt": "alt",
    "sgot": "ast",
    "alkphos": "alp",
    "alb": "albumin",
}

APP_NUMERIC = ["alt", "ast", "bilirubin_total", "age"]
PAPER_EXTRA = ["alp", "albumin"]
SEX = "gender"

HYPERPARAMETERS: Dict[str, Any] = {
    "n_estimators": 300,
    "min_samples_leaf": 2,
    "class_weight": "balanced_subsample",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not DATASET.exists():
        raise SystemExit(
            f"dataset not found: {DATASET}\nThis project uses REAL published "
            "data only. Do not generate a substitute."
        )
    raw = pd.read_csv(DATASET, header=None, names=UCI_COLUMNS)
    rows_raw = len(raw)

    duplicates = raw.duplicated(keep="first")
    frame = raw[~duplicates]
    impossible = frame["db"] > frame["tb"]
    frame = frame[~impossible]
    children = frame["age"] < 18
    frame = frame[~children].reset_index(drop=True)

    frame = frame.rename(columns=COLUMN_RENAME)
    frame[SEX] = frame[SEX].str.strip().str.lower()
    frame["liver"] = (frame["selector"] == 1).astype(int)

    provenance = {
        "path": str(DATASET.relative_to(SERVICE_ROOT)).replace("\\", "/"),
        "source": "UCI Machine Learning Repository, id 225 (ILPD), downloaded 2026-10-06",
        "sha256": sha256_of(DATASET),
        "rows_raw": rows_raw,
        "raw_class_counts": {
            "liver_patient": int((raw["selector"] == 1).sum()),
            "non_liver_patient": int((raw["selector"] == 2).sum()),
        },
        "exact_duplicate_copies_dropped": int(duplicates.sum()),
        "direct_above_total_bilirubin_dropped": int(impossible.sum()),
        "under_18_dropped": int(children.sum()),
        "rows_used": len(frame),
        "positives": int(frame["liver"].sum()),
        "negatives": int((frame["liver"] == 0).sum()),
        "prevalence": float(frame["liver"].mean()),
        "age_top_coded_at_90": int((frame["age"] == 90).sum()),
        "missing_cells_in_used_features": {
            name: int(frame[name].isna().sum())
            for name in APP_NUMERIC + PAPER_EXTRA + [SEX]
        },
        "label_note": (
            "'Non liver patient' means the hospital did not record liver "
            "disease, not that the person is healthy. Kept exactly as published."
        ),
        "units": {
            "alt": "IU/L", "ast": "IU/L", "alp": "IU/L",
            "bilirubin_total": "mg/dL", "albumin": "g/dL", "age": "years",
        },
        "synthetic_rows": 0,
        "resampling": "none -- class weights only, no SMOTE, no oversampling",
    }
    return frame, provenance


_RISK_SCORE = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def _feature(name: str, value: Any, unit: str | None) -> Dict[str, Any]:
    source = FEATURES[name].source
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "canonical_unit": True,
        "source": source,
        "provenance": {"source": source},
    }


def rules_on_row(row: pd.Series) -> Tuple[int, int, Dict[str, bool]]:
    features = {
        "alt": _feature("alt", float(row["alt"]), "u/l"),
        "ast": _feature("ast", float(row["ast"]), "u/l"),
        "bilirubin_total": _feature("bilirubin_total", float(row["bilirubin_total"]), "mg/dl"),
        "age": _feature("age", int(row["age"]), "years"),
        "gender": _feature("gender", row[SEX], None),
    }
    data = evaluate_rules(engineered={"features": features, "upstream": {"provided": True}})
    liver = [d for d in data.decisions if d.condition == C.LIVER_DISEASE]
    merged = merge_decision_set(liver)
    flagged = int(merged.status is DecisionStatus.INDICATED)
    score = _RISK_SCORE.get(merged.risk, 0) if merged.risk is not None else 0
    if merged.status is DecisionStatus.BORDERLINE:
        score = max(score, 1)
    used = {
        d.metadata.get("rule_id"): d.status is not DecisionStatus.INSUFFICIENT_DATA
        for d in liver
    }
    return flagged, score, used


def rules_on_frame(frame: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, Dict[str, int]]:
    flags, scores, not_applied = [], [], {}
    for _, row in frame.iterrows():
        flagged, score, used = rules_on_row(row)
        flags.append(flagged)
        scores.append(score)
        for rule_id, applied in used.items():
            if not applied:
                not_applied[rule_id] = not_applied.get(rule_id, 0) + 1
    return np.array(flags), np.array(scores), not_applied


def build_pipeline(numeric: List[str], categorical: List[str]) -> Pipeline:
    transformers: List[Any] = [("numeric", SimpleImputer(strategy="median"), numeric)]
    if categorical:
        transformers.append(
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical)
        )
    return Pipeline(
        [
            ("preprocess", ColumnTransformer(transformers, remainder="drop")),
            ("model", RandomForestClassifier(**HYPERPARAMETERS)),
        ]
    )


def out_of_fold(numeric, categorical, X, y) -> np.ndarray:
    return cross_val_predict(
        build_pipeline(numeric, categorical),
        X[numeric + categorical],
        y,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
        method="predict_proba",
        n_jobs=1,
    )[:, 1]


def sens_spec(y: np.ndarray, flagged: np.ndarray) -> Tuple[float, float]:
    pos, neg = y == 1, y == 0
    sens = float(flagged[pos].mean()) if pos.any() else float("nan")
    spec = float(1 - flagged[neg].mean()) if neg.any() else float("nan")
    return sens, spec


def threshold_matching_specificity(y: np.ndarray, scores: np.ndarray, target: float) -> float:
    negatives = np.sort(scores[y == 0])
    candidates = np.unique(np.concatenate([scores, [1.0 + 1e-9]]))
    best = None
    for t in candidates:
        spec = float((negatives < t).mean())
        if spec >= target:
            best = float(t)
            break
    return best if best is not None else 1.0 + 1e-9


def bootstrap(y, model_flag, rules_flag, model_score, rules_score) -> Dict[str, Any]:
    rng = np.random.default_rng(RANDOM_STATE)
    n = len(y)
    d_sens, d_spec, d_auc = [], [], []
    for _ in range(BOOTSTRAP_RESAMPLES):
        idx = rng.integers(0, n, n)
        yy = y[idx]
        if yy.min() == yy.max():
            continue
        ms, mp = sens_spec(yy, model_flag[idx])
        rs, rp = sens_spec(yy, rules_flag[idx])
        d_sens.append(ms - rs)
        d_spec.append(mp - rp)
        d_auc.append(
            roc_auc_score(yy, model_score[idx]) - roc_auc_score(yy, rules_score[idx])
        )

    def ci(values):
        return {
            "mean": float(np.mean(values)),
            "ci95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))],
        }

    return {
        "resamples_used": len(d_sens),
        "sensitivity_difference_model_minus_rules": ci(d_sens),
        "specificity_difference_model_minus_rules": ci(d_spec),
        "roc_auc_difference_model_minus_rules": ci(d_auc),
    }


def compare(
    name: str,
    numeric: List[str],
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    rules_train: np.ndarray,
    rules_test_flag: np.ndarray,
    rules_test_score: np.ndarray,
) -> Tuple[Dict[str, Any], Pipeline, Dict[str, Any]]:
    categorical = [SEX]
    _, rules_train_spec = sens_spec(y_train, rules_train)
    oof = out_of_fold(numeric, categorical, X_train, y_train)
    threshold = threshold_matching_specificity(y_train, oof, rules_train_spec)
    oof_sens, oof_spec = sens_spec(y_train, (oof >= threshold).astype(int))

    pipeline = build_pipeline(numeric, categorical)
    pipeline.fit(X_train[numeric + categorical], y_train)
    test_scores = pipeline.predict_proba(X_test[numeric + categorical])[:, 1]
    model_flag = (test_scores >= threshold).astype(int)

    m_sens, m_spec = sens_spec(y_test, model_flag)
    r_sens, r_spec = sens_spec(y_test, rules_test_flag)
    boot = bootstrap(y_test, model_flag, rules_test_flag, test_scores, rules_test_score)

    sens_ci = boot["sensitivity_difference_model_minus_rules"]["ci95"]
    ships = bool(sens_ci[0] > 0 and m_spec >= r_spec - SPECIFICITY_TOLERANCE)

    result = {
        "model_inputs": numeric + categorical,
        "operating_threshold": threshold,
        "threshold_basis": (
            "lowest out-of-fold threshold whose specificity on the TRAINING "
            "portion is at least the rules' specificity on that same portion"
        ),
        "rules_specificity_on_training_portion": rules_train_spec,
        "model_out_of_fold_at_threshold": {"sensitivity": oof_sens, "specificity": oof_spec},
        "model_out_of_fold_roc_auc": float(roc_auc_score(y_train, oof)),
        "test": {
            "model": {
                "sensitivity": m_sens,
                "specificity": m_spec,
                "roc_auc": float(roc_auc_score(y_test, test_scores)),
            },
            "rules": {
                "sensitivity": r_sens,
                "specificity": r_spec,
                "roc_auc": float(roc_auc_score(y_test, rules_test_score)),
            },
        },
        "paired_bootstrap_on_test": boot,
        "ship_criterion": (
            "95% interval of (model - rules) sensitivity entirely above zero, "
            f"AND model specificity >= rules specificity - {SPECIFICITY_TOLERANCE}"
        ),
        "beats_the_rules": ships,
    }
    importance = dict(
        zip(
            list(numeric)
            + list(
                pipeline.named_steps["preprocess"]
                .named_transformers_["categorical"]
                .get_feature_names_out(categorical)
            ),
            [float(v) for v in pipeline.named_steps["model"].feature_importances_],
        )
    )
    return result, pipeline, {"oof": oof, "test_scores": test_scores, "importance": importance}


def repeated_splits(frame: pd.DataFrame, numeric: List[str], seeds: int) -> Dict[str, Any]:
    y_all = frame["liver"].to_numpy()
    rules_flag_all, rules_score_all, _ = rules_on_frame(frame)
    rows: List[Dict[str, float]] = []
    for seed in range(seeds):
        idx_train, idx_test = train_test_split(
            np.arange(len(frame)), test_size=TEST_SIZE, stratify=y_all, random_state=seed
        )
        X_train, X_test = frame.iloc[idx_train], frame.iloc[idx_test]
        y_train, y_test = y_all[idx_train], y_all[idx_test]
        _, rules_train_spec = sens_spec(y_train, rules_flag_all[idx_train])
        oof = out_of_fold(numeric, [SEX], X_train, y_train)
        threshold = threshold_matching_specificity(y_train, oof, rules_train_spec)
        pipeline = build_pipeline(numeric, [SEX])
        pipeline.fit(X_train[numeric + [SEX]], y_train)
        scores = pipeline.predict_proba(X_test[numeric + [SEX]])[:, 1]
        m_sens, m_spec = sens_spec(y_test, (scores >= threshold).astype(int))
        r_sens, r_spec = sens_spec(y_test, rules_flag_all[idx_test])
        m_auc = float(roc_auc_score(y_test, scores))
        r_auc = float(roc_auc_score(y_test, rules_score_all[idx_test]))
        rows.append({
            "seed": seed,
            "model_sensitivity": m_sens, "rules_sensitivity": r_sens,
            "model_specificity": m_spec, "rules_specificity": r_spec,
            "model_roc_auc": m_auc, "rules_roc_auc": r_auc,
        })

    table = pd.DataFrame(rows)
    d_sens = table.model_sensitivity - table.rules_sensitivity
    d_spec = table.model_specificity - table.rules_specificity
    d_auc = table.model_roc_auc - table.rules_roc_auc

    def summary(values: pd.Series) -> Dict[str, float]:
        return {
            "mean": float(values.mean()),
            "middle_95_percent_of_splits": [
                float(values.quantile(0.025)), float(values.quantile(0.975))
            ],
        }

    return {
        "splits": seeds,
        "seeds": f"0..{seeds - 1} (stratified, test_size={TEST_SIZE})",
        "model_inputs": numeric + [SEX],
        "mean": {k: float(table[k].mean()) for k in table.columns if k != "seed"},
        "sensitivity_difference_model_minus_rules": summary(d_sens),
        "specificity_difference_model_minus_rules": summary(d_spec),
        "roc_auc_difference_model_minus_rules": summary(d_auc),
        "share_of_splits_model_auc_higher": float((d_auc > 0).mean()),
        "share_of_splits_meeting_criterion_point_estimates": float(
            ((d_sens > 0) & (d_spec >= -SPECIFICITY_TOLERANCE)).mean()
        ),
        "note": (
            "Point estimates per split; the per-split bootstrap is not repeated. "
            "'Meeting criterion point estimates' is LOOSER than the real ship "
            "criterion (which needs the sensitivity interval above zero), so it "
            "is an upper bound on how often the model would have shipped."
        ),
        "per_split": rows,
    }


def main() -> int:
    frame, provenance = load_dataset()
    y = frame["liver"].to_numpy()
    X_train, X_test, y_train, y_test = train_test_split(
        frame, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    print(
        f"rows used {len(frame)}  train {len(X_train)}  test {len(X_test)}  "
        f"prevalence {y.mean():.3f}"
    )
    for key in ("exact_duplicate_copies_dropped", "direct_above_total_bilirubin_dropped",
                "under_18_dropped"):
        print(f"  {key}: {provenance[key]}")

    rules_train_flag, _, na_train = rules_on_frame(X_train)
    rules_test_flag, rules_test_score, na_test = rules_on_frame(X_test)
    print(f"  rules not applied (validator rejected the value): train {na_train} test {na_test}")

    app_result, app_pipeline, app_extra = compare(
        "app_inputs", APP_NUMERIC, X_train, y_train, X_test, y_test,
        rules_train_flag, rules_test_flag, rules_test_score,
    )
    paper_result, _, _ = compare(
        "with_alp_albumin", APP_NUMERIC + PAPER_EXTRA, X_train, y_train, X_test, y_test,
        rules_train_flag, rules_test_flag, rules_test_score,
    )

    for label, res in (("APP INPUTS", app_result), ("+ ALP, ALBUMIN (paper only)", paper_result)):
        t = res["test"]
        b = res["paired_bootstrap_on_test"]
        print(f"\n--- {label}: threshold {res['operating_threshold']:.3f}")
        print(f"    model  sens {t['model']['sensitivity']:.3f}  spec {t['model']['specificity']:.3f}  auc {t['model']['roc_auc']:.3f}")
        print(f"    rules  sens {t['rules']['sensitivity']:.3f}  spec {t['rules']['specificity']:.3f}  auc {t['rules']['roc_auc']:.3f}")
        print(f"    sens diff {b['sensitivity_difference_model_minus_rules']}")
        print(f"    spec diff {b['specificity_difference_model_minus_rules']}")
        print(f"    auc  diff {b['roc_auc_difference_model_minus_rules']}")
        print(f"    BEATS THE RULES: {res['beats_the_rules']}")

    robustness = {}
    for label, numeric in (("app_inputs_model", APP_NUMERIC),
                           ("paper_only_model_with_alp_albumin", APP_NUMERIC + PAPER_EXTRA)):
        result = repeated_splits(frame, numeric, ROBUSTNESS_SPLITS)
        robustness[label] = result
        print(f"\n--- {ROBUSTNESS_SPLITS} splits, {label}")
        print(f"    mean {json.dumps({k: round(v, 3) for k, v in result['mean'].items()})}")
        for key in ("sensitivity_difference_model_minus_rules",
                    "specificity_difference_model_minus_rules",
                    "roc_auc_difference_model_minus_rules"):
            print(f"    {key}: {result[key]}")
        print(f"    model AUC higher in {result['share_of_splits_model_auc_higher']:.0%} of splits; "
              f"criterion point estimates met in "
              f"{result['share_of_splits_meeting_criterion_point_estimates']:.0%}")

    comparison = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": "Does a Random Forest beat VaidyaAI's liver rules on held-out patients?",
        "dataset": provenance,
        "split": {
            "test_size": TEST_SIZE,
            "stratified": True,
            "random_state": RANDOM_STATE,
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
        },
        "rules": {
            "how_run": (
                "the real VaidyaAI validator + rule engine, fused with "
                "merge_decision_set; no printed limit (the dataset has none), so "
                "the rules' fallback limits apply"
            ),
            "not_applied_because_validator_rejected_value": {
                "train": na_train, "test": na_test,
            },
        },
        "app_inputs_model": app_result,
        "paper_only_model_with_alp_albumin": paper_result,
        "robustness_over_many_splits": robustness,
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "hyperparameters": HYPERPARAMETERS,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    COMPARISON_PATH.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {COMPARISON_PATH}")

    if not app_result["beats_the_rules"]:
        print("The app-inputs model does NOT beat the rules: no model artifact written.")
        return 0

    print("The app-inputs model beats the rules -- model artifact not yet written; "
          "build the predictor step deliberately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
