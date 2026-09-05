"""Train the Module 10 Diabetes model. RUN THIS BY HAND -- never at import time.

    python ml/train_diabetes.py

Nothing in `app/` imports this file. The service loads the persisted artifact
and never fits a model; the test suite loads the same artifact. Training at
request time (or in a test run) would make predictions non-reproducible and
would make the metrics below unfalsifiable.

==========================================================================
THE DATA
==========================================================================

`datasets/raw/diabetes_prediction_dataset.csv` -- Kaggle's "Diabetes prediction
dataset", verified byte-identical across two independent HuggingFace mirrors.
See `datasets/PROVENANCE.md`. REAL DATA ONLY: nothing here generates,
augments, resamples-with-synthesis (no SMOTE) or fabricates a row. The only
row-level operation applied is DROPPING exact duplicates.

==========================================================================
THE FIVE MODELLING DECISIONS, AND WHY
==========================================================================

1. TRI-STATE `hypertension` / `heart_disease` -> AVAILABILITY-PATTERN VARIANTS.

   Module 2 stores these as true / false / ABSENT-MEANS-UNKNOWN. The dataset
   has only 0/1. Encoding an absent answer as 0 would fabricate a negative
   clinical finding -- the model would be told "this patient does not have
   hypertension" when nobody ever asked. Median-imputing them is the same
   thing wearing a hat: the median of a 92%-zero column IS 0.

   So instead of imputing, FOUR pipelines are fitted from the same real rows,
   one per availability pattern:

       both  |  hypertension_only  |  heart_disease_only  |  neither

   Each variant's ColumnTransformer simply does not contain the column(s) it
   cannot know. At prediction time the predictor picks the variant matching
   what the patient actually answered, so the feature matrix handed to the
   forest NEVER contains a value that was not observed. `tests/` asserts this
   on the real matrix, not on the intent.

   The distinction being drawn is deliberate: imputing a CONTINUOUS
   MEASUREMENT (bmi, age) substitutes a population value for an unmeasured
   quantity, which is a documented statistical choice and what spec section 10
   asks for. Imputing a BOOLEAN CLINICAL FINDING invents a diagnosis the
   patient never gave. Those are not the same act and are not treated the same
   way here.

2. DUPLICATES -> DROPPED BEFORE SPLITTING.

   3,854 exact duplicate rows exist. De-duplicating AFTER the split would let
   the same row sit in train and test, and the test score would then partly
   measure memorisation. Dropping first guarantees no exact row appears on
   both sides. The cost is real and is stated: some of those rows are probably
   distinct patients who coincidentally match on eight coarse features, so a
   little genuine information is discarded to protect the evaluation.

3. `bmi == 27.32` x 25,495 (25.5%) -> KEPT, NOT DROPPED.

   The dataset's author median-filled missing BMI, so a quarter of the column
   is imputed rather than measured, and it is not recoverable which rows those
   are (a few subjects genuinely have that BMI). Dropping 25% of the rows would
   discard 25% of the positives and would bias the sample if the fill was not
   missing-at-random. They are kept, and the consequence is reported rather
   than hidden: the model's learned BMI effect near 27.32 is ATTENUATED,
   because a quarter of subjects share that value regardless of their true BMI.
   BMI should be read as a weak feature in this model for that reason.

4. CLASS IMBALANCE (8.5% positive) -> class weights + a tuned threshold.

   `class_weight="balanced_subsample"` reweights the real rows; no synthetic
   minority rows are created. The decision threshold is then TUNED on a
   held-out validation split rather than left at 0.5. Accuracy is computed
   because spec section 11 asks for it, but it is reported last and with the
   majority-class baseline (91.2%) printed beside it, because on this dataset
   accuracy mostly measures the prevalence.

5. UNSEEN CATEGORIES -> encoded as ALL ZEROS, never as the majority category.

   `OneHotEncoder(handle_unknown="ignore")`. Module 2 allows
   `gender="prefer_not_to_say"`, which has no dataset equivalent; an unknown
   smoking token is possible too. Both arrive at the encoder as a value it
   never saw and become an all-zero block, which reads as "no category
   asserted". The spec-required most-frequent imputer is still fitted and
   present in the pipeline, but the predictor deliberately never hands it a
   missing categorical -- it sends an explicit sentinel token instead -- so
   "unknown gender" can never become "the majority gender".

==========================================================================
OUTPUTS
==========================================================================

    ml/artifacts/diabetes_rf_v1.joblib        the WHOLE pipeline(s), one file
    ml/artifacts/diabetes_rf_v1.metrics.json  every number below, auditable

The metrics file records the sha256 of the joblib it was produced from, so a
test can prove the committed metrics describe the committed model.
"""

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
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
DATASET = SERVICE_ROOT / "datasets" / "raw" / "diabetes_prediction_dataset.csv"
ARTIFACT_DIR = HERE / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "diabetes_rf_v1.joblib"
METRICS_PATH = ARTIFACT_DIR / "diabetes_rf_v1.metrics.json"

ARTIFACT_VERSION = "1.0.0"
MODEL_ID = "diabetes_rf"
RANDOM_STATE = 42
TEST_SIZE = 0.20
VALIDATION_SIZE = 0.20  # of the training portion
CV_FOLDS = 5

#: The two features the forest is effectively built on. See the sufficiency
#: note in `app/ml/diabetes.py`: absent either one, the predictor refuses.
REQUIRED_FEATURES: Tuple[str, ...] = ("hba1c", "blood_glucose")

#: Median-imputable continuous inputs.
OPTIONAL_NUMERIC: Tuple[str, ...] = ("age", "bmi")
CATEGORICAL: Tuple[str, ...] = ("gender", "smoking_history")

#: The tri-state pair, handled by variant selection rather than imputation.
TRI_STATE: Tuple[str, ...] = ("hypertension", "heart_disease")

#: name -> the tri-state columns that variant is allowed to see.
VARIANTS: Dict[str, Tuple[str, ...]] = {
    "both": ("hypertension", "heart_disease"),
    "hypertension_only": ("hypertension",),
    "heart_disease_only": ("heart_disease",),
    "neither": (),
}

HYPERPARAMETERS: Dict[str, Any] = {
    "n_estimators": 200,
    "min_samples_leaf": 50,
    "class_weight": "balanced_subsample",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

#: PPV (precision) an INDICATED decision must reach on held-out validation
#: data. 0.90 means roughly nine in ten people this model flags in a cohort
#: like the training one really are positive. Chosen BEFORE looking at the
#: resulting number, and cross-checked against the F1-maximising threshold.
TARGET_PRECISION_INDICATED = 0.90

#: The LOW / NOT_INDICATED band is a RULE-OUT band, and this is the sensitivity
#: it must preserve. `t_borderline` is the LARGEST validation threshold at which
#: recall is still at or above this value, so "Low" means "at this cut-off the
#: model would still have caught 99 of every 100 positive cases".
#:
#: The asymmetry is deliberate and is the whole reason this cut-off is not
#: chosen by the same criterion as the INDICATED one. A false "worth
#: discussing" costs a conversation. A false reassurance is the failure
#: `app/schemas/decisions.py` calls "the most dangerous failure mode this type
#: can have". So the lower boundary is set by sensitivity and the upper one by
#: precision, and neither is a round number: both are read off the measured
#: precision-recall curve of the held-out validation split.
BORDERLINE_MINIMUM_RECALL = 0.99


# --------------------------------------------------------------------------
# Loading and normalisation
# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise_smoking(series: "pd.Series[str]") -> "pd.Series[str]":
    """Dataset spelling -> Module 2 spelling.

    `No Info` -> `no_info`, `not current` -> `not_current`. Skipping this step
    silently drops the whole feature at prediction time: the profile would send
    `no_info`, the encoder would have been fitted on `No Info`, and
    handle_unknown="ignore" would quietly zero it. Nothing would raise.
    """
    return series.astype(str).str.strip().str.lower().str.replace(" ", "_", regex=False)


def load_dataset() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not DATASET.exists():
        raise SystemExit(
            f"dataset not found: {DATASET}\n"
            "This project uses REAL published data only. Do not generate a "
            "substitute -- see datasets/PROVENANCE.md."
        )
    raw = pd.read_csv(DATASET)
    rows_raw = len(raw)
    duplicates = int(raw.duplicated().sum())

    # DECISION 2: de-duplicate BEFORE any split.
    frame = raw.drop_duplicates().reset_index(drop=True)

    frame = frame.rename(
        columns={"HbA1c_level": "hba1c", "blood_glucose_level": "blood_glucose"}
    )
    frame["smoking_history"] = normalise_smoking(frame["smoking_history"])
    frame["gender"] = frame["gender"].astype(str).str.strip().str.lower()

    provenance = {
        "path": str(DATASET.relative_to(SERVICE_ROOT)).replace("\\", "/"),
        "sha256": sha256_of(DATASET),
        "rows_raw": rows_raw,
        "exact_duplicate_rows_dropped": duplicates,
        "rows_used": len(frame),
        "positives": int(frame["diabetes"].sum()),
        "negatives": int((frame["diabetes"] == 0).sum()),
        "prevalence": float(frame["diabetes"].mean()),
        "bmi_median_filled_rows": int((frame["bmi"] == 27.32).sum()),
        "duplicate_policy": "dropped before splitting (see module docstring)",
        "synthetic_rows": 0,
        "resampling": "none -- class weights only, no SMOTE, no oversampling",
        "gender_levels": sorted(frame["gender"].unique().tolist()),
        "smoking_history_levels": sorted(frame["smoking_history"].unique().tolist()),
    }
    return frame, provenance


# --------------------------------------------------------------------------
# Pipeline construction
# --------------------------------------------------------------------------


def build_pipeline(numeric: List[str], categorical: List[str]) -> Pipeline:
    """Spec section 10's pipeline, as one object.

    numeric:      median imputation
    categorical:  most-frequent imputation -> one-hot (unknown -> all zeros)
    model:        Random Forest

    The whole thing is a single `Pipeline`, so `joblib.dump` persists
    preprocessing and model together and a prediction can never be made with a
    mismatched encoder.
    """
    return Pipeline(
        [
            (
                "preprocess",
                ColumnTransformer(
                    [
                        ("numeric", SimpleImputer(strategy="median"), numeric),
                        (
                            "categorical",
                            Pipeline(
                                [
                                    ("impute", SimpleImputer(strategy="most_frequent")),
                                    (
                                        "encode",
                                        OneHotEncoder(handle_unknown="ignore"),
                                    ),
                                ]
                            ),
                            categorical,
                        ),
                    ],
                    remainder="drop",
                ),
            ),
            ("model", RandomForestClassifier(**HYPERPARAMETERS)),
        ]
    )


def variant_columns(tri: Tuple[str, ...]) -> Tuple[List[str], List[str]]:
    numeric = list(REQUIRED_FEATURES) + list(OPTIONAL_NUMERIC) + list(tri)
    return numeric, list(CATEGORICAL)


# --------------------------------------------------------------------------
# Threshold selection -- on VALIDATION data, never on test
# --------------------------------------------------------------------------


def choose_thresholds(y_true: np.ndarray, scores: np.ndarray) -> Dict[str, Any]:
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    # precision/recall have one more entry than thresholds.
    prec, rec = precision[:-1], recall[:-1]
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    best = int(np.nanargmax(f1))
    prevalence = float(np.mean(y_true))

    def first_threshold_reaching(target: float) -> float:
        hits = np.where(prec >= target)[0]
        if len(hits) == 0:
            # No threshold reaches the target: fall back to the most selective
            # point on the curve rather than silently accepting a lower PPV.
            return float(thresholds[-1])
        return float(thresholds[hits[0]])

    indicated = first_threshold_reaching(TARGET_PRECISION_INDICATED)

    # Largest threshold still preserving the required sensitivity. Recall is
    # non-increasing in the threshold, so this is the last qualifying index.
    keeps_recall = np.where(rec >= BORDERLINE_MINIMUM_RECALL)[0]
    borderline = (
        float(thresholds[keeps_recall[-1]]) if len(keeps_recall) else float(thresholds[0])
    )
    borderline = min(borderline, indicated)

    borderline_index = int(np.searchsorted(thresholds, borderline, side="left"))
    borderline_index = min(borderline_index, len(prec) - 1)
    return {
        "indicated": indicated,
        "borderline": borderline,
        "f1_optimal": float(thresholds[best]),
        "f1_optimal_precision": float(prec[best]),
        "f1_optimal_recall": float(rec[best]),
        "f1_optimal_f1": float(f1[best]),
        "target_precision_indicated": TARGET_PRECISION_INDICATED,
        "borderline_minimum_recall": BORDERLINE_MINIMUM_RECALL,
        "borderline_recall_achieved": float(rec[borderline_index]),
        "borderline_precision_achieved": float(prec[borderline_index]),
        "validation_prevalence": prevalence,
        "validation_rows": int(len(y_true)),
        "criterion_note": (
            "indicated = smallest threshold whose CUMULATIVE precision reaches "
            "the target; borderline = largest threshold whose CUMULATIVE recall "
            "still meets the sensitivity floor. Both are cumulative (score >= t) "
            "quantities. The observed positive rate WITHIN the middle band is "
            "reported separately under risk_bands_on_test and is lower -- that "
            "band means 'not ruled out', not 'elevated'."
        ),
    }


# --------------------------------------------------------------------------
# Evaluation -- spec section 11
# --------------------------------------------------------------------------


def evaluate(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> Dict[str, Any]:
    predicted = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    prevalence = float(np.mean(y_true))
    return {
        "decision_threshold": float(threshold),
        # Threshold-independent first: these are the honest numbers on an
        # 8.5%-positive problem.
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
        # Reported LAST and next to its baseline, deliberately.
        "accuracy": float(accuracy_score(y_true, predicted)),
        "majority_class_baseline_accuracy": float(max(prevalence, 1 - prevalence)),
        "test_prevalence": prevalence,
        "test_rows": int(len(y_true)),
    }


def risk_band_report(
    y_true: np.ndarray, scores: np.ndarray, thresholds: Dict[str, Any]
) -> Dict[str, Any]:
    """How many held-out patients land in each risk band, and how many of them
    are actually positive.

    This is the number that says whether the cut-offs are usable. A BORDERLINE
    band that swallows half the cohort would be noise, however defensible its
    derivation; a reviewer should be able to see that here rather than take it
    on trust.
    """
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
    """Spec section 11's k-fold cross-validation.

    Run on the TRAINING portion only, and a fresh pipeline is fitted inside
    every fold (the imputers and the encoder included), so no fold sees
    statistics derived from its own validation half.
    """
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
            "reported separately. These numbers measure STABILITY across "
            "splits, not the deployed operating point."
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


def feature_importances(pipeline: Pipeline, numeric: List[str]) -> Dict[str, float]:
    """GLOBAL, MODEL-LEVEL importances. NOT a per-patient explanation.

    Recorded so the ordering of evidence can be justified and reviewed. The
    predictor is explicitly forbidden from presenting these as the reason an
    INDIVIDUAL prediction came out the way it did -- spec section 24 forbids
    unsupported certainty, and a mean-impurity-decrease score says nothing
    about one patient.
    """
    encoder = pipeline.named_steps["preprocess"].named_transformers_["categorical"]
    encoded = list(encoder.named_steps["encode"].get_feature_names_out(CATEGORICAL))
    names = numeric + encoded
    values = pipeline.named_steps["model"].feature_importances_
    grouped: Dict[str, float] = {}
    for name, value in zip(names, values):
        # Fold one-hot columns back onto their source feature.
        base = name
        for source in CATEGORICAL:
            if name.startswith(source + "_"):
                base = source
                break
        grouped[base] = grouped.get(base, 0.0) + float(value)
    return dict(sorted(grouped.items(), key=lambda kv: -kv[1]))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> int:
    frame, provenance = load_dataset()
    y = frame["diabetes"].astype(int)
    X = frame.drop(columns=["diabetes"])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    X_fit, X_val, y_fit, y_val = train_test_split(
        X_train,
        y_train,
        test_size=VALIDATION_SIZE,
        stratify=y_train,
        random_state=RANDOM_STATE,
    )

    print(f"rows used {len(frame):,}  train {len(X_fit):,}  "
          f"validation {len(X_val):,}  test {len(X_test):,}")
    print(f"prevalence  train {y_fit.mean():.4f}  test {y_test.mean():.4f}")

    variants: Dict[str, Any] = {}
    for name, tri in VARIANTS.items():
        numeric, categorical = variant_columns(tri)
        print(f"\n--- variant {name}: numeric={numeric}")

        # Threshold selection: fit on the fit split only, choose on validation.
        selector = build_pipeline(numeric, categorical)
        selector.fit(X_fit[numeric + categorical], y_fit)
        val_scores = selector.predict_proba(X_val[numeric + categorical])[:, 1]
        thresholds = choose_thresholds(y_val.to_numpy(), val_scores)
        print(
            f"    thresholds indicated={thresholds['indicated']:.4f} "
            f"borderline={thresholds['borderline']:.4f} "
            f"f1_optimal={thresholds['f1_optimal']:.4f}"
        )

        # The SHIPPED model is refitted on fit+validation, so no data is wasted;
        # the test split has still never been touched.
        pipeline = build_pipeline(numeric, categorical)
        pipeline.fit(X_train[numeric + categorical], y_train)

        test_scores = pipeline.predict_proba(X_test[numeric + categorical])[:, 1]
        metrics = evaluate(y_test.to_numpy(), test_scores, thresholds["indicated"])
        metrics["at_default_threshold_0.5"] = evaluate(
            y_test.to_numpy(), test_scores, 0.5
        )
        metrics["risk_bands_on_test"] = risk_band_report(
            y_test.to_numpy(), test_scores, thresholds
        )
        metrics["cross_validation"] = cross_validate_variant(
            numeric, categorical, X_train[numeric + categorical], y_train
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
            "global_feature_importance": feature_importances(pipeline, numeric),
            "metrics": metrics,
        }

    common: Dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "model_id": MODEL_ID,
        "condition": "Diabetes",
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
            "validation_size_of_train": VALIDATION_SIZE,
            "stratified": True,
            "random_state": RANDOM_STATE,
            "deduplicated_before_split": True,
            "threshold_selected_on": "validation split",
            "metrics_measured_on": "held-out test split",
            "shipped_model_fitted_on": "train split (fit + validation)",
        },
        "required_features": list(REQUIRED_FEATURES),
        "optional_numeric_features": list(OPTIONAL_NUMERIC),
        "categorical_features": list(CATEGORICAL),
        "tri_state_features": list(TRI_STATE),
        "unknown_category_policy": (
            "OneHotEncoder(handle_unknown='ignore'): an unseen or unsupported "
            "category becomes an all-zero block -- 'no category asserted'. It "
            "is never replaced by the most frequent category."
        ),
        "tri_state_policy": (
            "One fitted pipeline per availability pattern. A tri-state value "
            "the patient never supplied is not imputed and not encoded as 0: "
            "the variant used simply has no such column."
        ),
        "imbalance_policy": (
            "class_weight='balanced_subsample' on the real rows, plus a "
            "validation-tuned decision threshold. No synthetic minority rows "
            "(no SMOTE), no oversampling, no augmentation."
        ),
        "feature_importance_scope": "global_model_level",
        "feature_importance_caveat": (
            "Mean impurity decrease over the whole training set. It ranks "
            "features FOR THE MODEL and must never be presented as the reason "
            "an individual prediction came out as it did."
        ),
        "variants": {
            name: {k: v for k, v in payload.items() if k != "pipeline"}
            for name, payload in variants.items()
        },
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = dict(common)
    bundle["pipelines"] = {name: payload["pipeline"] for name, payload in variants.items()}
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

    print(f"\nwrote {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"wrote {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
