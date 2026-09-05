"""Train the Module 11 Heart Disease model. RUN THIS BY HAND -- never at import.

    python ml/train_heart.py

Nothing in `app/` imports this file. The service loads the persisted artifact
and never fits a model; the test suite loads the same artifact. Training at
request time (or in a test run) would make predictions non-reproducible and
would make the metrics below unfalsifiable. This mirrors `ml/train_diabetes.py`
deliberately -- one training pattern, not two.

==========================================================================
THE DATA
==========================================================================

`datasets/raw/cardio_train.csv` -- Kaggle's "Cardiovascular Disease dataset",
70,000 rows, SEMICOLON-delimited, verified byte-identical across three
independent GitHub sources. See `datasets/PROVENANCE.md`.

REAL DATA ONLY. Nothing here generates, augments, resamples-with-synthesis (no
SMOTE) or fabricates a row. The only row-level operation applied is DROPPING
physiologically impossible records, counted and reported below.

==========================================================================
THE SIX MODELLING DECISIONS, AND WHY
==========================================================================

1. BLOOD PRESSURE IS EXCLUDED FROM THE SHIPPED MODEL. This is the big one.

   `ap_hi` / `ap_lo` are by far the strongest predictors in this dataset. Adding
   them lifts held-out ROC-AUC from ~0.70 to ~0.80. They are ALSO the single
   thing VaidyaAI cannot supply at prediction time: Module 2 does not collect
   blood pressure, `app/data/feature_catalog.py` has no such feature, and
   Module 4 does not extract it from a laboratory report.

   A model trained on `ap_hi` would therefore be median-imputing its most
   important input for EVERY patient, forever. Its published 0.80 ROC-AUC would
   describe a model that never runs; the model that actually runs would be a
   different, worse, unmeasured one. That is precisely the failure spec Module
   12 legislates against, applied to Module 11.

   So the shipped model excludes blood pressure, and the cost is measured
   rather than hidden: the BP-inclusive model is fitted anyway, purely as a
   REFERENCE, and its numbers are recorded in the metrics artifact under
   `blood_pressure_reference_model` with an explicit `shipped: false`. The
   honest summary is that this predictor is a WEAK one, that the weakness is a
   data-availability problem and not a modelling failure, and that collecting
   systolic BP in Module 2 is the single highest-value change anyone could make
   to Module 11.

2. `age` IS IN DAYS. Divided by 365.25 and FLOORED TO WHOLE YEARS.

   Raw range 10,798-23,713 days = 29.6-64.9 years. Flooring rather than keeping
   the float is deliberate: `feature_catalog.py` types `age` as an INTEGER in
   whole years, so that is exactly what arrives at prediction time. Training on
   fractional years would place tree split points at values the deployed model
   can never see.

3. `cholesterol` IS AN ORDINAL BAND (1/2/3), NOT mg/dL.

   The dataset's `cholesterol` is 1 = normal, 2 = above normal, 3 = well above
   normal. VaidyaAI's `cholesterol` feature is TOTAL cholesterol in mg/dL.
   Feeding one as the other would hand the forest a 200-ish number where it was
   trained on 1, 2 or 3 -- every real patient would land beyond the largest
   split point and the feature would collapse to a constant.

   The model column is therefore named `cholesterol_band`, never `cholesterol`,
   and `app/ml/heart.py` maps mg/dL -> band with the NCEP ATP III total
   cholesterol cut-offs:

       < 200 mg/dL          -> 1  (desirable)
       200 - 239 mg/dL      -> 2  (borderline high)
       >= 240 mg/dL         -> 3  (high)

   Those three names are the dataset's own three labels in the same order, and
   ATP III is the reference `app/data/validation_rules.py` and Module 8's
   cholesterol rule already use, so the mapping does not introduce a second
   cholesterol vocabulary into the project. The cut-offs live in ONE place
   (`app/ml/heart.py`), are recorded in this artifact, and are asserted at their
   boundaries by `tests/test_heart_predictor.py`.

   `gluc` is the same kind of ordinal and is DELIBERATELY NOT USED. Measured:
   adding it moves held-out ROC-AUC by +0.003. Unlike cholesterol, the source
   documentation does not say whether its bands are fasting or random glucose,
   so a mg/dL -> band mapping would be an unverifiable assumption. +0.003 does
   not buy an unverifiable assumption, and `blood_glucose` remains available to
   Module 8 and Module 10 regardless.

4. `gender` IS 1/2 AND THE SOURCE DOES NOT SAY WHICH IS WHICH. INFERRED.

       gender=1: n=45,530, mean height 161.4 cm, mean weight 72.6 kg, 1.8% smoke
       gender=2: n=24,470, mean height 169.9 cm, mean weight 77.3 kg, 21.9% smoke

   An 8.6 cm mean height difference in that direction, with a 12-fold smoking
   difference on top of it, admits one reading: 1 = FEMALE, 2 = MALE. Both
   signals point the same way and each is large relative to its spread, which
   is why this is recorded as an inference with a stated basis rather than a
   coin toss. The mapping is stored in the artifact as `gender_mapping` so a
   reviewer can challenge it without reading this file.

   Gender is then modelled as a STRING categorical ("female"/"male"), so Module
   2's `other` and `prefer_not_to_say` -- which have no dataset equivalent --
   reach a `handle_unknown="ignore"` encoder and become an all-zero block:
   "no category asserted", never "the majority gender".

5. THE DATASET IS DIRTY. IMPOSSIBLE BODY MEASUREMENTS ARE DROPPED.

   Raw height spans 55-250 cm and weight 10-200 kg, giving derived BMI
   3.5-298.7. A 55 cm, 10 kg adult aged 29-65 is a data-entry error, not a
   patient. The rule, applied only to columns this model actually uses:

       height   120 - 220 cm
       weight    30 - 250 kg
       bmi        8 - 200 kg/m2   <- Module 6's own `possible` band

   Cleaning is restricted to modelled columns on purpose. Dropping a row for an
   implausible value in a column the shipped model never reads (`ap_hi` of
   16020, say) would discard a real (features, label) pair for no modelling
   benefit. The count of rows kept despite implausible blood pressure is
   reported, and a sensitivity fit on the BP-plausible subset is recorded, so
   the choice can be checked rather than trusted.

6. `smoke` IS BINARY BUT MODULE 2'S `smoking_history` IS SIX-VALUED, AND ONE OF
   THOSE VALUES MEANS "NOBODY ASKED".

   Mapping (see `app/ml/heart.py`):

       never, former, not_current  -> 0   (does not currently smoke)
       current                     -> 1
       ever, no_info, absent       -> UNKNOWN

   `ever` is genuinely ambiguous -- it covers current and former smokers alike
   -- so it is treated as unknown rather than guessed at.

   An UNKNOWN is not encoded as 0. Following Module 10, TWO pipelines are fitted
   from the same real rows:

       with_smoking  |  without_smoking

   and the `without_smoking` variant's ColumnTransformer simply has no smoking
   column. At prediction time the variant matching what the patient actually
   answered is used, so the matrix handed to the forest never contains a value
   nobody supplied.

   The honest footnote: `smoking_current` carries ~0.4% of this model's global
   importance and the two variants score within 0.001 ROC-AUC of each other.
   The variant machinery is therefore correctness at no measurable cost -- and
   nobody should claim smoking is doing real work in THIS model. It is a spec
   feature and it is present; it is not a driver.

==========================================================================
OUTPUTS
==========================================================================

    ml/artifacts/heart_rf_v1.joblib        the WHOLE pipeline(s), one file
    ml/artifacts/heart_rf_v1.metrics.json  every number below, auditable

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
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
DATASET = SERVICE_ROOT / "datasets" / "raw" / "cardio_train.csv"
ARTIFACT_DIR = HERE / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "heart_rf_v1.joblib"
METRICS_PATH = ARTIFACT_DIR / "heart_rf_v1.metrics.json"

ARTIFACT_VERSION = "1.0.0"
MODEL_ID = "heart_rf"
RANDOM_STATE = 42
TEST_SIZE = 0.20
CV_FOLDS = 5
ABLATION_FOLDS = 3

#: DECISION 4. Inferred from height/weight/smoking distributions; see the
#: module docstring for the numbers the inference rests on.
GENDER_MAPPING: Dict[int, str] = {1: "female", 2: "male"}

#: DECISION 5. Applied only to columns the shipped model reads.
HEIGHT_CM_RANGE: Tuple[float, float] = (120.0, 220.0)
WEIGHT_KG_RANGE: Tuple[float, float] = (30.0, 250.0)
BMI_RANGE: Tuple[float, float] = (8.0, 200.0)  # Module 6's `possible` band

#: Plausibility band used ONLY for the reported sensitivity check -- rows
#: failing it are KEPT in the shipped training data (see DECISION 5).
AP_HI_RANGE: Tuple[float, float] = (60.0, 300.0)
AP_LO_RANGE: Tuple[float, float] = (30.0, 200.0)

#: The three inputs the forest is effectively built on (~98% of global
#: importance between them). See `app/ml/heart.py`'s sufficiency note.
REQUIRED_FEATURES: Tuple[str, ...] = ("age", "bmi", "cholesterol_band")
CATEGORICAL: Tuple[str, ...] = ("gender",)

#: The tri-state input, handled by variant selection rather than imputation.
TRI_STATE_NUMERIC: str = "smoking_current"

VARIANTS: Dict[str, Tuple[str, ...]] = {
    "with_smoking": (TRI_STATE_NUMERIC,),
    "without_smoking": (),
}

HYPERPARAMETERS: Dict[str, Any] = {
    "n_estimators": 300,
    "min_samples_leaf": 50,
    "class_weight": "balanced_subsample",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

#: THRESHOLD CRITERIA -- and why they are NOT Module 10's.
#:
#: Module 10 asks for an absolute 0.90 cumulative precision at the INDICATED
#: cut-off. That target is right for an 8.5%-prevalence problem with a strong
#: model. It is WRONG here for a measurable reason: this cohort is 50% positive
#: and this model's ROC-AUC is ~0.70, so no threshold on the measured curve
#: reaches 0.90 precision at any usable recall. Applying Module 10's rule
#: unchanged would fall through to its "no threshold reaches the target"
#: fallback and pick the most selective point on the curve -- a cut-off chosen
#: by an error branch rather than by evidence.
#:
#: So the INDICATED target is expressed as a LIFT over the cohort's own base
#: rate: the smallest threshold whose cumulative precision is at least
#: PRECISION_LIFT_INDICATED times prevalence. At 50% prevalence that is a 0.75
#: PPV target -- "half again as likely as the cohort average" -- which IS
#: attainable, and which means the same thing at any prevalence.
PRECISION_LIFT_INDICATED = 1.5

#: The rule-out floor. Module 10 uses 0.99 because a false reassurance on a
#: rare condition is its worst failure. At 50% prevalence a 0.99-recall cut-off
#: leaves a Low band holding ~3% of the cohort, which is not a usable rule-out
#: -- it just relabels almost everyone as "not ruled out". 0.95 keeps the miss
#: rate at 1 positive in 20 while leaving a Low band that means something. The
#: resulting band sizes are reported in `risk_bands_on_test`; read them before
#: trusting the cut-off.
BORDERLINE_MINIMUM_RECALL = 0.95


# --------------------------------------------------------------------------
# Loading, cleaning and normalisation
# --------------------------------------------------------------------------


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
    raw = pd.read_csv(DATASET, sep=";")
    rows_raw = len(raw)

    frame = raw.copy()
    # DECISION 2: days -> whole years, matching feature_catalog's integer age.
    frame["age"] = np.floor(frame["age"] / 365.25).astype(int)
    frame["bmi"] = frame["weight"] / (frame["height"] / 100.0) ** 2
    # DECISION 3: the dataset's 1/2/3 IS the band. Renamed so it can never be
    # confused with VaidyaAI's mg/dL `cholesterol` feature.
    frame["cholesterol_band"] = frame["cholesterol"].astype(int)
    # DECISION 4.
    frame["gender"] = frame["gender"].map(GENDER_MAPPING)
    # DECISION 6.
    frame["smoking_current"] = frame["smoke"].astype(int)

    # DECISION 5: drop physiologically impossible body measurements.
    height_ok = frame["height"].between(*HEIGHT_CM_RANGE)
    weight_ok = frame["weight"].between(*WEIGHT_KG_RANGE)
    bmi_ok = frame["bmi"].between(*BMI_RANGE)
    keep = height_ok & weight_ok & bmi_ok
    removed = {
        "height_outside_120_220_cm": int((~height_ok).sum()),
        "weight_outside_30_250_kg": int((~weight_ok).sum()),
        "bmi_outside_8_200": int((~bmi_ok).sum()),
        "rows_removed_total": int((~keep).sum()),
    }
    cleaned = frame[keep].reset_index(drop=True)

    bp_implausible = int(
        (
            ~cleaned["ap_hi"].between(*AP_HI_RANGE)
            | ~cleaned["ap_lo"].between(*AP_LO_RANGE)
            | (cleaned["ap_hi"] < cleaned["ap_lo"])
        ).sum()
    )

    provenance = {
        "path": str(DATASET.relative_to(SERVICE_ROOT)).replace("\\", "/"),
        "delimiter": ";",
        "sha256": sha256_of(DATASET),
        "rows_raw": rows_raw,
        "rows_used": len(cleaned),
        "cleaning_rule": {
            "height_cm": list(HEIGHT_CM_RANGE),
            "weight_kg": list(WEIGHT_KG_RANGE),
            "bmi": list(BMI_RANGE),
            "basis": (
                "Applied ONLY to columns the shipped model reads. The bmi band "
                "is Module 6's own `possible` band from validation_rules.py; "
                "the height and weight bands exclude values incompatible with "
                "an adult aged 29-65, which is the whole cohort."
            ),
            "removed": removed,
        },
        "exact_duplicate_rows_present": int(cleaned.duplicated().sum()),
        "duplicate_policy": (
            "NOT de-duplicated. Unlike the diabetes set, this file carries an "
            "`id` column and rows are distinct records; two patients sharing "
            "coarse features is not evidence of a duplicated record."
        ),
        "rows_kept_despite_implausible_blood_pressure": bp_implausible,
        "positives": int(cleaned["cardio"].sum()),
        "negatives": int((cleaned["cardio"] == 0).sum()),
        "prevalence": float(cleaned["cardio"].mean()),
        "age_units_raw": "days",
        "age_conversion": "floor(days / 365.25) -> whole years",
        "age_years_min": int(cleaned["age"].min()),
        "age_years_max": int(cleaned["age"].max()),
        "gender_mapping": {str(k): v for k, v in GENDER_MAPPING.items()},
        "gender_mapping_basis": (
            "INFERRED, not documented by the source. gender=1: n=45530, mean "
            "height 161.4 cm, 1.8% smokers. gender=2: n=24470, mean height "
            "169.9 cm, 21.9% smokers. Both signals agree: 1=female, 2=male."
        ),
        "gender_levels": sorted(cleaned["gender"].dropna().unique().tolist()),
        "cholesterol_semantics": (
            "ORDINAL BAND 1=normal, 2=above normal, 3=well above normal. NOT "
            "mg/dL. app/ml/heart.py maps mg/dL -> band using NCEP ATP III "
            "total-cholesterol cut-offs (<200, 200-239, >=240)."
        ),
        "cholesterol_band_cutoffs_mg_dl": [200.0, 240.0],
        "smoking_semantics": (
            "smoke=1 means CURRENTLY smokes. Module 2's never/former/"
            "not_current map to 0; current maps to 1; ever/no_info/absent are "
            "UNKNOWN and select the without_smoking variant."
        ),
        "excluded_columns": {
            "ap_hi": "blood pressure -- not collected anywhere in VaidyaAI (DECISION 1)",
            "ap_lo": "blood pressure -- not collected anywhere in VaidyaAI (DECISION 1)",
            "gluc": (
                "ordinal glucose band whose fasting/random basis is "
                "undocumented; worth +0.003 ROC-AUC (DECISION 3)"
            ),
            "alco": "alcohol use -- no VaidyaAI feature",
            "active": "physical activity -- no VaidyaAI feature",
            "id": "record identifier",
        },
        "synthetic_rows": 0,
        "resampling": "none -- class weights only, no SMOTE, no oversampling",
    }
    return cleaned, provenance


# --------------------------------------------------------------------------
# Pipeline construction
# --------------------------------------------------------------------------


def build_pipeline(numeric: List[str], categorical: List[str]) -> Pipeline:
    """Spec section 10's pipeline, as one object.

    numeric:      median imputation
    categorical:  most-frequent imputation -> one-hot (unknown -> all zeros)
    model:        Random Forest

    A single `Pipeline`, so `joblib.dump` persists preprocessing and model
    together and a prediction can never be made with a mismatched encoder.
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
                                    ("encode", OneHotEncoder(handle_unknown="ignore")),
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
    numeric = list(REQUIRED_FEATURES) + list(tri)
    return numeric, list(CATEGORICAL)


# --------------------------------------------------------------------------
# Threshold selection -- on OUT-OF-FOLD training predictions, never on test
# --------------------------------------------------------------------------


def out_of_fold_scores(
    numeric: List[str], categorical: List[str], X: pd.DataFrame, y: pd.Series
) -> np.ndarray:
    """Out-of-fold P(positive) for every training row.

    Preferred over a single held-out validation slice because every training
    row contributes to the threshold estimate while none of them is scored by a
    model that saw it. The test split is not touched.
    """
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
    target_precision = PRECISION_LIFT_INDICATED * prevalence

    hits = np.where(prec >= target_precision)[0]
    indicated = float(thresholds[hits[0]]) if len(hits) else float(thresholds[-1])
    indicated_reachable = bool(len(hits))

    keeps_recall = np.where(rec >= BORDERLINE_MINIMUM_RECALL)[0]
    borderline = (
        float(thresholds[keeps_recall[-1]])
        if len(keeps_recall)
        else float(thresholds[0])
    )
    borderline = min(borderline, indicated)

    borderline_index = int(np.searchsorted(thresholds, borderline, side="left"))
    borderline_index = min(borderline_index, len(prec) - 1)
    indicated_index = int(np.searchsorted(thresholds, indicated, side="left"))
    indicated_index = min(indicated_index, len(prec) - 1)
    return {
        "indicated": indicated,
        "borderline": borderline,
        "f1_optimal": float(thresholds[best]),
        "f1_optimal_precision": float(prec[best]),
        "f1_optimal_recall": float(rec[best]),
        "f1_optimal_f1": float(f1[best]),
        "precision_lift_indicated": PRECISION_LIFT_INDICATED,
        "target_precision_indicated": float(target_precision),
        "target_precision_reachable": indicated_reachable,
        "indicated_precision_achieved": float(prec[indicated_index]),
        "indicated_recall_achieved": float(rec[indicated_index]),
        "borderline_minimum_recall": BORDERLINE_MINIMUM_RECALL,
        "borderline_recall_achieved": float(rec[borderline_index]),
        "borderline_precision_achieved": float(prec[borderline_index]),
        "selection_prevalence": prevalence,
        "selection_rows": int(len(y_true)),
        "selected_on": "out-of-fold predictions over the training portion",
        "criterion_note": (
            "indicated = smallest threshold whose CUMULATIVE precision reaches "
            "PRECISION_LIFT_INDICATED x prevalence; borderline = largest "
            "threshold whose CUMULATIVE recall still meets the sensitivity "
            "floor. Both are cumulative (score >= t) quantities. The observed "
            "positive rate WITHIN the middle band is reported separately under "
            "risk_bands_on_test and is lower -- that band means 'not ruled "
            "out', not 'elevated'. The lift-based target replaces Module 10's "
            "absolute 0.90 precision because at 50% prevalence and ROC-AUC "
            "~0.70 no threshold attains 0.90, so the absolute rule would "
            "degenerate to its own fallback branch."
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
    }


def risk_band_report(
    y_true: np.ndarray, scores: np.ndarray, thresholds: Dict[str, Any]
) -> Dict[str, Any]:
    """How many held-out patients land in each band, and how many are positive.

    This is the number that says whether the cut-offs are usable at all.
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
    """Spec section 11's k-fold cross-validation, on the training portion only.

    A fresh pipeline is fitted inside every fold (imputers and encoder
    included), so no fold sees statistics derived from its own held-out half.
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


def feature_importances(
    pipeline: Pipeline, numeric: List[str], categorical: List[str]
) -> Dict[str, float]:
    """GLOBAL, MODEL-LEVEL importances. NOT a per-patient explanation.

    Recorded so the ordering of evidence can be justified and reviewed. The
    predictor is explicitly forbidden from presenting these as the reason an
    INDIVIDUAL prediction came out the way it did.
    """
    encoder = pipeline.named_steps["preprocess"].named_transformers_["categorical"]
    encoded = list(encoder.named_steps["encode"].get_feature_names_out(categorical))
    names = numeric + encoded
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


def ablation(
    numeric: List[str], categorical: List[str], X: pd.DataFrame, y: pd.Series
) -> Dict[str, Any]:
    """ROC-AUC with each single feature removed. THE SUFFICIENCY EVIDENCE.

    `app/ml/heart.py` refuses to predict without `age`, `bmi` and
    `cholesterol_band`. This measures what dropping each one actually costs, so
    the sufficiency rule rests on numbers rather than intuition. Cross-
    validated on the training portion; the test split is untouched.
    """
    cv = StratifiedKFold(n_splits=ABLATION_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    baseline = float(
        np.mean(
            cross_val_score(
                build_pipeline(numeric, categorical),
                X,
                y,
                cv=cv,
                scoring="roc_auc",
                n_jobs=1,
            )
        )
    )
    out: Dict[str, Any] = {
        "folds": ABLATION_FOLDS,
        "measured_on": "training portion, cross-validated",
        "all_features_roc_auc": baseline,
        "without": {},
    }
    for dropped in list(numeric) + list(categorical):
        n = [c for c in numeric if c != dropped]
        c = [c for c in categorical if c != dropped]
        if not n:
            continue
        score = float(
            np.mean(
                cross_val_score(
                    build_pipeline(n, c),
                    X[n + c],
                    y,
                    cv=cv,
                    scoring="roc_auc",
                    n_jobs=1,
                )
            )
        )
        out["without"][dropped] = {
            "roc_auc": score,
            "delta": score - baseline,
        }
    out["interpretation"] = (
        "Every row here describes a model REFITTED without the feature -- an "
        "honest model that knows it lacks it. The shipped model instead "
        "MEDIAN-IMPUTES an absent input, which is strictly worse; see "
        "`imputed_at_prediction_time`."
    )
    return out


def imputation_damage(
    pipeline: Pipeline,
    numeric: List[str],
    categorical: List[str],
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> Dict[str, Any]:
    """What the SHIPPED model scores when one input is missing at run time.

    The honest measure of the harm the sufficiency gate prevents: in production
    the pipeline's median imputer substitutes a population value and the forest
    is never told, so the probability becomes partly a statement about the
    training cohort rather than about the patient.
    """
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
        score = float(roc_auc_score(y_test, pipeline.predict_proba(damaged)[:, 1]))
        out["blanked"][name] = {"roc_auc": score, "delta": score - baseline}
    return out


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> int:
    frame, provenance = load_dataset()
    y = frame["cardio"].astype(int)
    X = frame

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    print(
        f"rows used {len(frame):,}  train {len(X_train):,}  test {len(X_test):,}  "
        f"prevalence {y.mean():.4f}"
    )
    print(f"cleaning removed {provenance['cleaning_rule']['removed']}")

    variants: Dict[str, Any] = {}
    for name, tri in VARIANTS.items():
        numeric, categorical = variant_columns(tri)
        cols = numeric + categorical
        print(f"\n--- variant {name}: numeric={numeric}")

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

    # ---- sufficiency evidence, on the richer variant ----
    numeric, categorical = variant_columns(VARIANTS["with_smoking"])
    print("\n--- ablation (sufficiency evidence)")
    ablation_report = ablation(
        numeric, categorical, X_train[numeric + categorical], y_train
    )
    for dropped, payload in ablation_report["without"].items():
        print(f"    without {dropped:18s} roc_auc={payload['roc_auc']:.4f} "
              f"({payload['delta']:+.4f})")
    ablation_report["imputed_at_prediction_time"] = imputation_damage(
        variants["with_smoking"]["pipeline"], numeric, categorical, X_test, y_test
    )
    for name, payload in ablation_report["imputed_at_prediction_time"][
        "blanked"
    ].items():
        print(f"    blanked {name:18s} roc_auc={payload['roc_auc']:.4f} "
              f"({payload['delta']:+.4f})")

    # ---- DECISION 1: the reference model that is NOT shipped ----
    print("\n--- blood-pressure reference model (NOT shipped)")
    bp_numeric = numeric + ["ap_hi", "ap_lo"]
    bp_pipeline = build_pipeline(bp_numeric, categorical)
    bp_pipeline.fit(X_train[bp_numeric + categorical], y_train)
    bp_scores = bp_pipeline.predict_proba(X_test[bp_numeric + categorical])[:, 1]
    bp_reference = {
        "shipped": False,
        "why_not_shipped": (
            "Module 2 does not collect blood pressure and there is no "
            "`blood_pressure` feature in app/data/feature_catalog.py, so these "
            "columns would be median-imputed for every real patient. The "
            "numbers below describe a model that could never run; they are "
            "recorded to MEASURE what the exclusion costs, not to advertise a "
            "capability."
        ),
        "features": bp_numeric + list(categorical),
        "roc_auc": float(roc_auc_score(y_test, bp_scores)),
        "pr_auc_average_precision": float(average_precision_score(y_test, bp_scores)),
        "accuracy_at_0.5": float(accuracy_score(y_test, (bp_scores >= 0.5).astype(int))),
        "shipped_model_roc_auc": variants["with_smoking"]["metrics"]["roc_auc"],
        "roc_auc_cost_of_exclusion": float(roc_auc_score(y_test, bp_scores))
        - variants["with_smoking"]["metrics"]["roc_auc"],
    }
    print(
        f"    reference roc_auc={bp_reference['roc_auc']:.4f} vs shipped "
        f"{bp_reference['shipped_model_roc_auc']:.4f} "
        f"({bp_reference['roc_auc_cost_of_exclusion']:+.4f})"
    )

    # ---- DECISION 5 sensitivity: what if implausible-BP rows were dropped? ----
    def bp_plausible(f: pd.DataFrame) -> pd.Series:
        return (
            f["ap_hi"].between(*AP_HI_RANGE)
            & f["ap_lo"].between(*AP_LO_RANGE)
            & (f["ap_hi"] >= f["ap_lo"])
        )

    tr_mask, te_mask = bp_plausible(X_train), bp_plausible(X_test)
    sens_pipeline = build_pipeline(numeric, categorical)
    sens_pipeline.fit(X_train[tr_mask][numeric + categorical], y_train[tr_mask])
    sens_scores = sens_pipeline.predict_proba(
        X_test[te_mask][numeric + categorical]
    )[:, 1]
    cleaning_sensitivity = {
        "question": (
            "The shipped model KEEPS rows whose blood pressure is implausible, "
            "because it never reads those columns. Would dropping them have "
            "produced a better model?"
        ),
        "rows_dropped_from_train": int((~tr_mask).sum()),
        "rows_dropped_from_test": int((~te_mask).sum()),
        "roc_auc_on_bp_plausible_test_subset": float(
            roc_auc_score(y_test[te_mask], sens_scores)
        ),
        "shipped_model_roc_auc": variants["with_smoking"]["metrics"]["roc_auc"],
        "note": "Not comparable row-for-row; reported so the choice can be checked.",
    }
    print(
        f"    cleaning sensitivity roc_auc="
        f"{cleaning_sensitivity['roc_auc_on_bp_plausible_test_subset']:.4f}"
    )

    common: Dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "model_id": MODEL_ID,
        "condition": "Heart Disease",
        "assessment_kind": "disease_likelihood",
        "assessment_kind_note": (
            "This model estimates the LIKELIHOOD of cardiovascular disease. "
            "Module 8's RULE_HEART_DISEASE_RISK_FACTORS emits the same "
            "condition string from a RISK-FACTOR COUNT. Both are legitimate "
            "and they are not the same quantity; the predictor stamps "
            "metadata.assessment_kind on every decision so Module 16/17 can "
            "fuse them without conflating burden with probability."
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
        "categorical_features": list(CATEGORICAL),
        "tri_state_features": [TRI_STATE_NUMERIC],
        "model_column_semantics": {
            "age": "whole years (dataset days / 365.25, floored)",
            "bmi": "kg/m2, derived from height and weight",
            "cholesterol_band": (
                "ORDINAL 1/2/3, NOT mg/dL. Mapped from mg/dL at prediction "
                "time using NCEP ATP III cut-offs."
            ),
            "smoking_current": "1 = currently smokes, 0 = does not currently smoke",
            "gender": "'female' / 'male' (dataset 1/2, inferred)",
        },
        "unknown_category_policy": (
            "OneHotEncoder(handle_unknown='ignore'): an unseen or unsupported "
            "category becomes an all-zero block -- 'no category asserted'. It "
            "is never replaced by the most frequent category. Module 2 allows "
            "gender='other' and 'prefer_not_to_say', which this dataset has no "
            "equivalent for."
        ),
        "tri_state_policy": (
            "One fitted pipeline per smoking-availability pattern. A smoking "
            "history the patient never supplied -- or the ambiguous 'ever' -- "
            "is not imputed and not encoded as 0: the variant used simply has "
            "no such column."
        ),
        "imbalance_policy": (
            "The cohort is near-balanced (50.0% positive), so accuracy IS "
            "meaningful here and is reported next to the majority-class "
            "baseline anyway. class_weight='balanced_subsample' on the real "
            "rows; no synthetic rows, no SMOTE, no oversampling."
        ),
        "blood_pressure_reference_model": bp_reference,
        "cleaning_sensitivity": cleaning_sensitivity,
        "sufficiency_evidence": ablation_report,
        "feature_importance_scope": "global_model_level",
        "feature_importance_caveat": (
            "Mean impurity decrease over the whole training set. It ranks "
            "features FOR THE MODEL and must never be presented as the reason "
            "an individual prediction came out as it did."
        ),
        "honest_read": (
            "Held-out ROC-AUC around 0.70 makes this a WEAK discriminator. The "
            "cause is measured, not guessed: the dataset's dominant predictors "
            "are systolic and diastolic blood pressure, which VaidyaAI does not "
            "collect, and excluding them costs about 0.10 ROC-AUC. What remains "
            "is age, BMI and a three-level cholesterol band. Read this "
            "predictor as a coarse risk indicator that is honest about its "
            "inputs, and read the Low band's small share of the cohort as what "
            "it is: this model rarely rules heart disease out."
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

    print(f"\nwrote {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"wrote {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
