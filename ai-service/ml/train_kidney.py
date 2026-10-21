from __future__ import annotations

import hashlib
import itertools
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
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
DATASET = SERVICE_ROOT / "datasets" / "raw" / "chronic_kidney_disease_full.csv"
ARTIFACT_DIR = HERE / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "kidney_rf_v1.joblib"
METRICS_PATH = ARTIFACT_DIR / "kidney_rf_v1.metrics.json"

ARTIFACT_VERSION = "1.0.0"
MODEL_ID = "kidney_rf"
RANDOM_STATE = 42
TEST_SIZE = 0.25
CV_FOLDS = 5

COLUMN_RENAME: Dict[str, str] = {
    "sc": "creatinine",
    "hemo": "hemoglobin",
    "bgr": "blood_glucose",
    "age": "age",
    "htn": "hypertension",
}

REQUIRED_FEATURES: Tuple[str, ...] = ("creatinine", "hemoglobin")
OPTIONAL_NUMERIC: Tuple[str, ...] = ("blood_glucose", "age")

TRI_STATE_CATEGORICAL: str = "hypertension"

VARIANTS: Dict[str, Tuple[str, ...]] = {
    "with_hypertension": (TRI_STATE_CATEGORICAL,),
    "without_hypertension": (),
}

HYPERPARAMETERS: Dict[str, Any] = {
    "n_estimators": 300,
    "min_samples_leaf": 2,
    "class_weight": "balanced_subsample",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

INDICATED_MINIMUM_RECALL = 0.98
BORDERLINE_MINIMUM_RECALL = 0.99

MODULE_10_TARGET_PRECISION = 0.90

VALID_CLASSES = ("ckd", "notckd")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not DATASET.exists():
        raise SystemExit(
            f"dataset not found: {DATASET}\n"
            "This project uses REAL published data only. Do not generate a "
            "substitute -- see datasets/PROVENANCE.md."
        )
    raw = pd.read_csv(DATASET, skipinitialspace=True)
    rows_raw = len(raw)

    for column in raw.columns:
        if raw[column].dtype == object:
            raw[column] = raw[column].astype(str).str.strip().replace(
                {"": np.nan, "nan": np.nan}
            )

    label_counts = raw["class"].value_counts(dropna=False).to_dict()

    malformed = ~raw["class"].isin(VALID_CLASSES)
    malformed_rows = int(malformed.sum())
    frame = raw[~malformed].reset_index(drop=True)

    frame = frame.rename(columns=COLUMN_RENAME)
    for name in ("creatinine", "hemoglobin", "blood_glucose", "age"):
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    frame["hypertension"] = frame["hypertension"].where(
        frame["hypertension"].isin(("yes", "no"))
    )
    frame["ckd"] = (frame["class"] == "ckd").astype(int)

    used = list(REQUIRED_FEATURES) + list(OPTIONAL_NUMERIC) + [TRI_STATE_CATEGORICAL]
    provenance = {
        "path": str(DATASET.relative_to(SERVICE_ROOT)).replace("\\", "/"),
        "sha256": sha256_of(DATASET),
        "rows_raw": rows_raw,
        "rows_used": len(frame),
        "raw_class_counts": {str(k): int(v) for k, v in label_counts.items()},
        "malformed_label_rows_dropped": malformed_rows,
        "malformed_label_policy": (
            "The single row whose class reads 'no' is dropped, not repaired. "
            "Its `dm` is empty, its `appet` holds 'no' (domain: good/poor) and "
            "its `pe` holds 'good' (domain: no/yes), so the record is "
            "structurally shifted, not merely mislabelled. Repairing the label "
            "would mean guessing whether the patient had CKD, which is "
            "fabricating training data."
        ),
        "positives": int(frame["ckd"].sum()),
        "negatives": int((frame["ckd"] == 0).sum()),
        "prevalence": float(frame["ckd"].mean()),
        "missing_cells_total_raw": int(raw.isna().sum().sum()),
        "missing_cells_in_used_features": {
            name: int(frame[name].isna().sum()) for name in used
        },
        "missing_value_policy": (
            "Imputed inside the pipeline (median for numerics, most-frequent "
            "for categoricals), fitted per fold. No row is dropped for "
            "missingness: with 399 rows that would discard most of the file "
            "and would bias it towards patients with a complete workup."
        ),
        "units": {
            "creatinine": "mg/dl",
            "hemoglobin": "g/dl",
            "blood_glucose": "mg/dl (RANDOM glucose, per UCI's documentation)",
            "age": "years",
        },
        "unit_conversion": "none -- UCI's units already match feature_catalog.py",
        "columns_available_but_unused": [
            c for c in raw.columns if c not in list(COLUMN_RENAME) + ["class"]
        ],
        "columns_unused_reason": (
            "Real and useful, but absent from app/data/feature_catalog.py, so "
            "VaidyaAI cannot supply them at prediction time. Training on them "
            "would publish metrics for a model that never runs."
        ),
        "hypertension_levels": ["no", "yes"],
        "synthetic_rows": 0,
        "resampling": "none -- class weights only, no SMOTE, no oversampling",
    }
    return frame, provenance


def build_pipeline(numeric: List[str], categorical: List[str]) -> Pipeline:
    transformers: List[Any] = [("numeric", SimpleImputer(strategy="median"), numeric)]
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            )
        )
    return Pipeline(
        [
            ("preprocess", ColumnTransformer(transformers, remainder="drop")),
            ("model", RandomForestClassifier(**HYPERPARAMETERS)),
        ]
    )


def variant_columns(tri: Tuple[str, ...]) -> Tuple[List[str], List[str]]:
    numeric = list(REQUIRED_FEATURES) + list(OPTIONAL_NUMERIC)
    return numeric, list(tri)


def out_of_fold_scores(
    numeric: List[str], categorical: List[str], X: pd.DataFrame, y: pd.Series
) -> np.ndarray:
    return cross_val_predict(
        build_pipeline(numeric, categorical),
        X,
        y,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
        method="predict_proba",
        n_jobs=1,
    )[:, 1]


def choose_thresholds(y_true: np.ndarray, scores: np.ndarray) -> Dict[str, Any]:
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    prec, rec = precision[:-1], recall[:-1]
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    best = int(np.nanargmax(f1))
    prevalence = float(np.mean(y_true))

    eligible = np.where(rec >= INDICATED_MINIMUM_RECALL)[0]
    if len(eligible):
        best_precision = float(np.max(prec[eligible]))
        chosen = eligible[np.argmax(prec[eligible] >= best_precision)]
        indicated = float(thresholds[chosen])
    else:
        indicated = float(thresholds[0])
        best_precision = float(prec[0])

    module_10_hits = np.where(prec >= MODULE_10_TARGET_PRECISION)[0]
    module_10_threshold = (
        float(thresholds[module_10_hits[0]]) if len(module_10_hits) else None
    )

    keeps_recall = np.where(rec >= BORDERLINE_MINIMUM_RECALL)[0]
    borderline = (
        float(thresholds[keeps_recall[-1]])
        if len(keeps_recall)
        else float(thresholds[0])
    )
    borderline = min(borderline, indicated)

    borderline_index = min(
        int(np.searchsorted(thresholds, borderline, side="left")), len(prec) - 1
    )
    indicated_index = min(
        int(np.searchsorted(thresholds, indicated, side="left")), len(prec) - 1
    )
    return {
        "indicated": indicated,
        "borderline": borderline,
        "f1_optimal": float(thresholds[best]),
        "f1_optimal_precision": float(prec[best]),
        "f1_optimal_recall": float(rec[best]),
        "f1_optimal_f1": float(f1[best]),
        "indicated_minimum_recall": INDICATED_MINIMUM_RECALL,
        "indicated_best_precision_at_that_recall": best_precision,
        "module_10_rule_target_precision": MODULE_10_TARGET_PRECISION,
        "module_10_rule_would_give": module_10_threshold,
        "module_10_rule_note": (
            "Recorded to show WHY it was not used: it is satisfied so early on "
            "this model's curve that it does not discriminate, and the "
            "precision achieved at the cut-off actually chosen is well above "
            "it anyway."
        ),
        "indicated_precision_achieved": float(prec[indicated_index]),
        "indicated_recall_achieved": float(rec[indicated_index]),
        "borderline_minimum_recall": BORDERLINE_MINIMUM_RECALL,
        "borderline_recall_achieved": float(rec[borderline_index]),
        "borderline_precision_achieved": float(prec[borderline_index]),
        "selection_prevalence": prevalence,
        "selection_rows": int(len(y_true)),
        "selected_on": "out-of-fold predictions over the training portion",
        "criterion_note": (
            "indicated = the most precise threshold whose CUMULATIVE recall is "
            "still >= indicated_minimum_recall; borderline = the largest "
            "threshold whose CUMULATIVE recall is still >= "
            "borderline_minimum_recall. Both are cumulative (score >= t) "
            "quantities, both read off the measured curve, neither a round "
            "number. Chosen out-of-fold because a holdout slice of ~60 "
            "patients would make the cut-off noise. Both cut-offs are stated "
            "as sensitivity guarantees because a missed case is this "
            "condition's dangerous failure; Module 10's precision-floor rule "
            "is non-binding on a model this well separated and is recorded "
            "rather than applied."
        ),
    }


def evaluate(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> Dict[str, Any]:
    predicted = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    prevalence = float(np.mean(y_true))
    return {
        "decision_threshold": float(threshold),
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "pr_auc_average_precision": float(average_precision_score(y_true, scores)),
        "positive_class": {
            "precision": float(precision_score(y_true, predicted, zero_division=0)),
            "recall": float(recall_score(y_true, predicted, zero_division=0)),
            "f1": float(f1_score(y_true, predicted, zero_division=0)),
            "support": int(tp + fn),
        },
        "negative_class": {
            "precision": float(
                precision_score(y_true, predicted, pos_label=0, zero_division=0)
            ),
            "recall": float(
                recall_score(y_true, predicted, pos_label=0, zero_division=0)
            ),
            "f1": float(f1_score(y_true, predicted, pos_label=0, zero_division=0)),
            "support": int(tn + fp),
        },
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
            "layout": "rows = actual [negative, positive], columns = predicted",
            "matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        },
        "accuracy": float(accuracy_score(y_true, predicted)),
        "majority_class_baseline_accuracy": float(max(prevalence, 1 - prevalence)),
        "test_prevalence": prevalence,
        "test_rows": int(len(y_true)),
        "small_sample_caveat": (
            "n=%d. A single misclassification moves recall by about %.1f "
            "points; treat these figures as indicative and prefer the "
            "cross-validated numbers." % (len(y_true), 100.0 / max(int(tp + fn), 1))
        ),
    }


def risk_band_report(
    y_true: np.ndarray, scores: np.ndarray, thresholds: Dict[str, Any]
) -> Dict[str, Any]:
    low = scores < thresholds["borderline"]
    high = scores >= thresholds["indicated"]
    medium = ~low & ~high
    out: Dict[str, Any] = {}
    for label, mask in (("low", low), ("medium", medium), ("high", high)):
        count = int(mask.sum())
        positives = int(y_true[mask].sum()) if count else 0
        out[label] = {
            "patients": count,
            "share_of_cohort": float(count / len(y_true)),
            "actual_positives": positives,
            "observed_positive_rate": float(positives / count) if count else None,
        }
    return out


def cross_validate_variant(
    numeric: List[str], categorical: List[str], X: pd.DataFrame, y: pd.Series
) -> Dict[str, Any]:
    scoring = ("f1", "precision", "recall", "roc_auc", "average_precision")
    results = cross_validate(
        build_pipeline(numeric, categorical),
        X,
        y,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
        scoring=scoring,
        n_jobs=1,
    )
    summary: Dict[str, Any] = {
        "folds": CV_FOLDS,
        "scheme": "StratifiedKFold(shuffle=True) on the training portion",
        "note": (
            "scored at sklearn's default 0.5 threshold; the tuned threshold is "
            "reported separately. With 399 rows these cross-validated figures "
            "are more trustworthy than the 100-patient test split."
        ),
    }
    for name in scoring:
        values = results[f"test_{name}"]
        summary[name] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "per_fold": [float(v) for v in values],
        }
    return summary


def feature_importances(
    pipeline: Pipeline, numeric: List[str], categorical: List[str]
) -> Dict[str, float]:
    names = list(numeric)
    if categorical:
        encoder = pipeline.named_steps["preprocess"].named_transformers_["categorical"]
        names += list(encoder.named_steps["encode"].get_feature_names_out(categorical))
    values = pipeline.named_steps["model"].feature_importances_
    grouped: Dict[str, float] = {}
    for name, value in zip(names, values):
        base = name
        for source in categorical:
            if name.startswith(source + "_"):
                base = source
                break
        grouped[base] = grouped.get(base, 0.0) + float(value)
    return dict(sorted(grouped.items(), key=lambda kv: -kv[1]))


def sufficiency_evidence(X: pd.DataFrame, y: pd.Series) -> Dict[str, Any]:
    numeric_all = list(REQUIRED_FEATURES) + list(OPTIONAL_NUMERIC)
    all_features = numeric_all + [TRI_STATE_CATEGORICAL]
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    subsets: Dict[str, float] = {}
    for size in range(1, len(all_features) + 1):
        for combo in itertools.combinations(all_features, size):
            numeric = [c for c in combo if c in numeric_all]
            categorical = [c for c in combo if c == TRI_STATE_CATEGORICAL]
            if not numeric:
                continue
            score = float(
                np.mean(
                    cross_val_score(
                        build_pipeline(numeric, categorical),
                        X[list(combo)],
                        y,
                        cv=cv,
                        scoring="roc_auc",
                        n_jobs=1,
                    )
                )
            )
            subsets["+".join(combo)] = score
    return {
        "folds": CV_FOLDS,
        "measured_on": "training portion, cross-validated, ROC-AUC",
        "subsets": dict(sorted(subsets.items(), key=lambda kv: -kv[1])),
        "interpretation": (
            "Read the single-feature rows first. creatinine and hemoglobin are "
            "the load-bearing pair; blood_glucose, age and hypertension are "
            "helpful but not load-bearing. app/ml/kidney.py therefore REQUIRES "
            "creatinine and hemoglobin and treats the other three as optional. "
            "NOTE that every row here describes a model REFITTED without the "
            "feature -- an honest model that knows it lacks it. The shipped "
            "model instead MEDIAN-IMPUTES an absent input, which is strictly "
            "worse; see `imputed_at_prediction_time`, which is the number the "
            "skip is actually justified by."
        ),
    }


def imputation_damage(
    pipeline: Pipeline,
    numeric: List[str],
    categorical: List[str],
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> Dict[str, Any]:
    cols = numeric + categorical
    baseline = float(roc_auc_score(y_test, pipeline.predict_proba(X_test[cols])[:, 1]))
    out: Dict[str, Any] = {
        "measured_on": "held-out test split, shipped pipeline, one input blanked",
        "all_inputs_present_roc_auc": baseline,
        "blanked": {},
    }
    for name in cols:
        damaged = X_test[cols].copy()
        damaged[name] = np.nan
        score = float(
            roc_auc_score(y_test, pipeline.predict_proba(damaged)[:, 1])
        )
        out["blanked"][name] = {"roc_auc": score, "delta": score - baseline}
    return out


def main() -> int:
    frame, provenance = load_dataset()
    y = frame["ckd"].astype(int)
    X = frame

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    print(
        f"rows used {len(frame)}  train {len(X_train)}  test {len(X_test)}  "
        f"prevalence {y.mean():.4f}  (dropped {provenance['malformed_label_rows_dropped']} "
        "malformed-label row)"
    )

    variants: Dict[str, Any] = {}
    for name, tri in VARIANTS.items():
        numeric, categorical = variant_columns(tri)
        cols = numeric + categorical
        print(f"\n--- variant {name}: numeric={numeric} categorical={categorical}")

        oof = out_of_fold_scores(numeric, categorical, X_train[cols], y_train)
        thresholds = choose_thresholds(y_train.to_numpy(), oof)
        print(
            f"    thresholds indicated={thresholds['indicated']:.4f} "
            f"borderline={thresholds['borderline']:.4f} "
            f"f1_optimal={thresholds['f1_optimal']:.4f}"
        )

        pipeline = build_pipeline(numeric, categorical)
        pipeline.fit(X_train[cols], y_train)

        test_scores = pipeline.predict_proba(X_test[cols])[:, 1]
        metrics = evaluate(y_test.to_numpy(), test_scores, thresholds["indicated"])
        metrics["at_default_threshold_0.5"] = evaluate(
            y_test.to_numpy(), test_scores, 0.5
        )
        metrics["risk_bands_on_test"] = risk_band_report(
            y_test.to_numpy(), test_scores, thresholds
        )
        metrics["cross_validation"] = cross_validate_variant(
            numeric, categorical, X_train[cols], y_train
        )
        print(
            f"    test roc_auc={metrics['roc_auc']:.4f} "
            f"pr_auc={metrics['pr_auc_average_precision']:.4f} "
            f"P={metrics['positive_class']['precision']:.4f} "
            f"R={metrics['positive_class']['recall']:.4f} "
            f"F1={metrics['positive_class']['f1']:.4f} "
            f"acc={metrics['accuracy']:.4f} (baseline "
            f"{metrics['majority_class_baseline_accuracy']:.4f})"
        )

        variants[name] = {
            "pipeline": pipeline,
            "numeric_features": numeric,
            "categorical_features": categorical,
            "tri_state_features": list(tri),
            "thresholds": thresholds,
            "global_feature_importance": feature_importances(
                pipeline, numeric, categorical
            ),
            "metrics": metrics,
        }

    print("\n--- sufficiency evidence (every feature subset)")
    numeric, categorical = variant_columns(VARIANTS["with_hypertension"])
    evidence = sufficiency_evidence(X_train[numeric + categorical], y_train)
    evidence["imputed_at_prediction_time"] = imputation_damage(
        variants["with_hypertension"]["pipeline"],
        numeric,
        categorical,
        X_test,
        y_test,
    )
    for name, payload in evidence["imputed_at_prediction_time"]["blanked"].items():
        print(f"    blanked {name:18s} roc_auc={payload['roc_auc']:.4f} "
              f"({payload['delta']:+.4f})")
    for key in list(evidence["subsets"])[:3]:
        print(f"    best  {key:45s} {evidence['subsets'][key]:.4f}")
    for single in list(REQUIRED_FEATURES) + list(OPTIONAL_NUMERIC) + [
        TRI_STATE_CATEGORICAL
    ]:
        if single in evidence["subsets"]:
            print(f"    alone {single:45s} {evidence['subsets'][single]:.4f}")

    common: Dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "model_id": MODEL_ID,
        "condition": "Kidney Disease",
        "assessment_kind": "disease_likelihood",
        "assessment_kind_note": (
            "This model estimates the LIKELIHOOD of chronic kidney disease. "
            "Module 8's creatinine rule assesses the same condition string from "
            "a threshold on one analyte. The predictor stamps "
            "metadata.assessment_kind on every decision so Module 16/17 can "
            "fuse them without conflating the two quantities."
        ),
        "algorithm": "RandomForestClassifier",
        "source_label": "Random Forest",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "joblib_version": joblib.__version__,
        "hyperparameters": HYPERPARAMETERS,
        "dataset": provenance,
        "split": {
            "test_size": TEST_SIZE,
            "stratified": True,
            "random_state": RANDOM_STATE,
            "threshold_selected_on": "out-of-fold predictions on the training portion",
            "metrics_measured_on": "held-out test split",
            "shipped_model_fitted_on": "the whole training portion",
        },
        "required_features": list(REQUIRED_FEATURES),
        "optional_numeric_features": list(OPTIONAL_NUMERIC),
        "tri_state_features": [TRI_STATE_CATEGORICAL],
        "unknown_category_policy": (
            "OneHotEncoder(handle_unknown='ignore'): an unseen category becomes "
            "an all-zero block -- 'no category asserted'. It is never replaced "
            "by the most frequent category. In practice the predictor never "
            "hands the encoder an unknown: an unanswered hypertension question "
            "selects the without_hypertension variant instead."
        ),
        "tri_state_policy": (
            "One fitted pipeline per hypertension-availability pattern. A "
            "hypertension answer the patient never gave is not imputed and "
            "NEVER encoded as 'no': the variant used simply has no such column."
        ),
        "imbalance_policy": (
            "62.7% positive -- mildly imbalanced, so the majority-class "
            "baseline accuracy (0.627) is reported next to accuracy. "
            "class_weight='balanced_subsample' on the real rows; no synthetic "
            "rows, no SMOTE, no oversampling."
        ),
        "sufficiency_evidence": evidence,
        "feature_importance_scope": "global_model_level",
        "feature_importance_caveat": (
            "Mean impurity decrease over the whole training set. It ranks "
            "features FOR THE MODEL and must never be presented as the reason "
            "an individual prediction came out as it did."
        ),
        "honest_read": (
            "The numbers are near-perfect and the dataset is the reason. This "
            "is a 399-row, single-centre UCI cohort in which serum creatinine "
            "and haemoglobin separate CKD from not-CKD almost cleanly, so a "
            "ROC-AUC near 0.99 says the model learned an easy separation, not "
            "that it would perform this way on a screening population. The "
            "100-patient test split cannot distinguish 0.97 from 1.00. Treat "
            "the cross-validated figures as the honest ones, and treat the "
            "sufficiency skip -- not the accuracy -- as this module's "
            "contribution."
        ),
        "variants": {
            name: {k: v for k, v in payload.items() if k != "pipeline"}
            for name, payload in variants.items()
        },
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = dict(common)
    bundle["pipelines"] = {
        name: payload["pipeline"] for name, payload in variants.items()
    }
    joblib.dump(bundle, MODEL_PATH, compress=3)

    metrics_document = dict(common)
    metrics_document["model_artifact"] = {
        "filename": MODEL_PATH.name,
        "sha256": sha256_of(MODEL_PATH),
        "bytes": MODEL_PATH.stat().st_size,
    }
    METRICS_PATH.write_text(
        json.dumps(metrics_document, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    print(f"\nwrote {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1e6:.2f} MB)")
    print(f"wrote {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
