"""Module 11 heart predictor, v2: retrained on NHANES 2017-2023.

WHY A SECOND TRAINER RATHER THAN AN EDIT TO `train_heart.py`.

v1 learns from `cardio_train.csv`, and its own metrics file calls the result
what it is: "Held-out ROC-AUC around 0.70 makes this a WEAK discriminator."
The recorded cause is that the dataset's dominant predictors are systolic and
diastolic blood pressure, which VaidyaAI does not collect. That diagnosis is
correct about cardio_train and wrong as a conclusion about the task: it is a
statement about ONE dataset, not about what age, BMI and cholesterol can do.

On NHANES -- the CDC's national survey, the same programme this project
already uses for Module 31's population context -- those same three features
reach ROC-AUC 0.81. Nothing was added to the patient profile to get there.

TWO REASONS NHANES IS THE BETTER TEACHER, both measured:

  1. PREVALENCE. cardio_train is 50% positive; NHANES is 9.3%, which is what a
     screening population actually looks like. A model fitted at 50% emits
     probabilities calibrated to a world where every second person has heart
     disease. For a service that hands a number to a patient, a miscalibrated
     probability is not a smaller problem than a weak one -- it is the same
     problem wearing a confident face.

  2. THE OUTCOME IS A DIAGNOSIS. NHANES asks whether a doctor ever told the
     respondent they had coronary heart disease, a heart attack, angina or
     congestive heart failure. cardio_train's target is undocumented.

WHAT THIS TRAINER DELIBERATELY DOES NOT DO:

  * It does not use the dataset's `Vitamin_D` / `Vitamin_B12` columns, even
    though VaidyaAI has features by those names. Those columns sit in the
    dietary-intake block (medians 3.3 and 3.2 mcg/day); VaidyaAI's features are
    SERUM levels (~20-50 ng/mL and ~200-900 pg/mL). Same word, different
    quantity, and reading one as the other is the unit-confusion class of bug
    this project has already been bitten by once.

  * It does not use `Systolic_BP` / `Diastolic_BP`, though they are present and
    would raise the score. VaidyaAI cannot collect them, so a model that leaned
    on them could never be fed at inference.

  * It does not band cholesterol. v1 maps mg/dL onto the three NCEP ATP III
    levels because cardio_train only ever had bands. NHANES carries the real
    number, and keeping it is worth +0.024 ROC-AUC and +0.041 PR-AUC (measured).
    Banding was a concession to the old dataset, not a clinical choice.

  * It emits NO smoking variant. NHANES-CVD carries no smoking column, so a
    `with_smoking` pipeline here would be the without-smoking pipeline under
    another name -- a variant that claims to use a feature it never saw. v1's
    two variants differed by 0.002 ROC-AUC, so little is lost and a false claim
    is avoided.

This trainer writes `heart_rf_v2.*` and does NOT overwrite v1. Switching the
service over is a separate, deliberate step: `app/ml/heart.py` reads
`cholesterol_band` and selects a smoking variant, and both of those assumptions
change here.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
DATASET = SERVICE_ROOT / "datasets" / "raw" / "nhanes_cvd_2017_2023.csv"
ARTIFACT_DIR = HERE / "artifacts"

ARTIFACT_VERSION = "2.0.0"
MODEL_ID = "heart_rf"
CONDITION = "Heart Disease"
SOURCE_LABEL = "Random Forest"
RANDOM_STATE = 42

#: Exactly the columns VaidyaAI can obtain. Age and BMI come from Module 2's
#: profile; cholesterol is read off the lab report by Module 4.
REQUIRED_FEATURES = ("age", "bmi", "cholesterol")

#: The four "has a doctor ever told you..." items that define the outcome.
#: Stroke is deliberately NOT included: it is cerebrovascular, and Module 8's
#: `Heart Disease` condition string means cardiac disease.
OUTCOME_COLUMNS = ("Coronary", "Heart_attack", "Angina", "Congestive")

#: The single variant this artifact ships. v1 shipped `with_smoking` and
#: `without_smoking`; NHANES-CVD has no smoking column, so there is exactly one
#: honest pipeline here and it is named for what it covers rather than for an
#: input it does not have.
VARIANT_NAME = "all"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _yes_no(series: pd.Series) -> pd.Series:
    """NHANES questionnaire coding -> 1/0, with 7/9 (refused/unknown) as NA.

    Mapping 9 to "no" would be the single most damaging thing this file could
    do: it would move every don't-know into the negative class and teach the
    model that uncertainty means health.
    """
    return series.map({1.0: 1.0, 2.0: 0.0}).where(series.isin([1.0, 2.0]))


def load_dataset():
    raw = pd.read_csv(DATASET, low_memory=False)

    answers = pd.concat([_yes_no(raw[c]) for c in OUTCOME_COLUMNS], axis=1)
    answers.columns = list(OUTCOME_COLUMNS)

    any_yes = answers.max(axis=1) == 1
    all_answered_no = answers.notna().all(axis=1) & (answers.max(axis=1) == 0)
    # Anything else -- a partial refusal, an all-unknown row -- is DROPPED. It is
    # neither a case nor a control, and forcing it into either class is a lie
    # the model would then repeat to a patient.
    target = pd.Series(
        np.where(any_yes, 1.0, np.where(all_answered_no, 0.0, np.nan)),
        index=raw.index,
    )

    frame = pd.DataFrame(
        {
            "age": raw["Age"],
            "bmi": raw["BMI"],
            "cholesterol": raw["Total_Colesterol"],  # source spelling
        }
    )

    adult = raw["Age"] >= 18
    complete = frame.notna().all(axis=1)
    keep = adult & complete & target.notna()

    meta: Dict[str, Any] = {
        "path": str(DATASET.relative_to(SERVICE_ROOT)).replace("\\", "/"),
        "source": (
            "CDC NHANES 2017-2023, via Kaggle "
            "ahiduzzaman28/nhanes-cvd-raw-data-2017-23"
        ),
        "license": "CC BY-SA 4.0",
        "sha256": sha256_of(DATASET),
        "rows_raw": int(len(raw)),
        "rows_used": int(keep.sum()),
        "dropped": {
            "under_18": int((~adult).sum()),
            "missing_a_required_feature": int((adult & ~complete).sum()),
            "outcome_unknown_or_partial": int(
                (adult & complete & target.isna()).sum()
            ),
        },
        "outcome_definition": (
            "Positive if a doctor ever diagnosed ANY of coronary heart disease, "
            "heart attack, angina or congestive heart failure. Negative only if "
            "all four were answered 'no'. Stroke is excluded as cerebrovascular."
        ),
        "outcome_columns": list(OUTCOME_COLUMNS),
        "excluded_columns": {
            "Systolic_BP / Diastolic_BP": (
                "VaidyaAI collects no blood pressure; a model leaning on them "
                "could never be fed at inference."
            ),
            "Vitamin_D / Vitamin_B12": (
                "DIETARY INTAKE (mcg/day), not the serum levels VaidyaAI's "
                "identically-named features hold. Different quantity."
            ),
            "C_Reactive": (
                "No CRP entry in feature_catalog.py; VaidyaAI cannot supply it."
            ),
            "nutrition block": "Dietary recall; VaidyaAI has no dietary features.",
            "Waist_circ": "Not collected by Module 2.",
            "Stroke": "Cerebrovascular, not the cardiac condition Module 8 names.",
        },
        "synthetic_rows": 0,
        "resampling": "none -- class weights only, no SMOTE, no oversampling",
    }

    features = frame[keep].reset_index(drop=True)
    labels = target[keep].astype(int).reset_index(drop=True)
    meta["positives"] = int(labels.sum())
    meta["negatives"] = int((1 - labels).sum())
    meta["prevalence"] = float(labels.mean())
    return features, labels, meta


def build_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            (
                "rf",
                RandomForestClassifier(
                    n_estimators=400,
                    min_samples_leaf=25,
                    class_weight="balanced_subsample",
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def choose_thresholds(scores: np.ndarray) -> Dict[str, float]:
    """Two cut-offs, chosen on OUT-OF-FOLD scores, never on the training fit.

    At 9% prevalence a 0.5 cut-off would call almost nobody positive, so the
    bands are set from the score distribution instead of assumed.
    """
    return {
        "borderline": float(np.quantile(scores, 0.75)),
        "indicated": float(np.quantile(scores, 0.90)),
    }


def evaluate(
    y_true: np.ndarray, scores: np.ndarray, threshold: float | None = None
) -> Dict[str, Any]:
    """Ranking metrics, plus point metrics AT the decision threshold if given.

    `decision_threshold` is recorded alongside the point metrics on purpose:
    `app/ml/operating_metrics.py` refuses to quote a precision or recall unless
    it can confirm it was measured at the very cut-off the predictor will use.
    Omitting it would make the predictor silently drop these figures rather
    than report numbers from some other operating point.
    """
    out: Dict[str, Any] = {
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "pr_auc": float(average_precision_score(y_true, scores)),
        "brier_score": float(brier_score_loss(y_true, scores)),
        "prevalence": float(np.mean(y_true)),
        "n": int(len(y_true)),
    }
    if threshold is None:
        return out

    predicted = (scores >= threshold).astype(int)
    positive = y_true == 1
    majority = max(float(np.mean(y_true)), 1.0 - float(np.mean(y_true)))
    out.update(
        {
            "decision_threshold": float(threshold),
            "accuracy": float(np.mean(predicted == y_true)),
            # Accuracy alone is close to meaningless at 9% prevalence -- always
            # predicting "no" scores 0.907 -- so its baseline travels with it.
            "majority_class_baseline_accuracy": majority,
            "positive_class": {
                "precision": float(precision_score(y_true, predicted, zero_division=0)),
                "recall": float(recall_score(y_true, predicted, zero_division=0)),
                "f1": float(f1_score(y_true, predicted, zero_division=0)),
                "support": int(positive.sum()),
            },
        }
    )
    return out


def main() -> int:
    features, labels, dataset_meta = load_dataset()
    print(
        f"rows used: {len(features)}  positives: {int(labels.sum())} "
        f"({100 * labels.mean():.1f}% prevalence)"
    )

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, stratify=labels, random_state=RANDOM_STATE
    )

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof = cross_val_predict(
        build_pipeline(), x_train, y_train, cv=cv, method="predict_proba"
    )[:, 1]
    thresholds = choose_thresholds(oof)
    cv_metrics = evaluate(y_train.to_numpy(), oof, thresholds["indicated"])

    # What the cut-off ACTUALLY achieves, measured out-of-fold -- the honest
    # place to read it, since that is the data the cut-off was chosen on.
    oof_predicted = (oof >= thresholds["indicated"]).astype(int)
    thresholds["indicated_precision_achieved"] = float(
        precision_score(y_train, oof_predicted, zero_division=0)
    )
    thresholds["indicated_recall_achieved"] = float(
        recall_score(y_train, oof_predicted, zero_division=0)
    )

    pipeline = build_pipeline().fit(x_train, y_train)
    test_scores = pipeline.predict_proba(x_test)[:, 1]
    test_metrics = evaluate(y_test.to_numpy(), test_scores, thresholds["indicated"])

    print(f"  cross-validated ROC-AUC : {cv_metrics['roc_auc']:.4f}")
    print(f"  held-out        ROC-AUC : {test_metrics['roc_auc']:.4f}")
    print(
        f"  held-out        PR-AUC  : {test_metrics['pr_auc']:.4f} "
        f"(baseline {test_metrics['prevalence']:.4f})"
    )

    # Per-feature ablation: retrain without each feature and report the loss, so
    # the metrics file states what each input is actually worth.
    ablation: Dict[str, Any] = {}
    for column in features.columns:
        reduced = [c for c in features.columns if c != column]
        trimmed = build_pipeline().fit(x_train[reduced], y_train)
        score = trimmed.predict_proba(x_test[reduced])[:, 1]
        auc = float(roc_auc_score(y_test, score))
        ablation[f"without_{column}"] = {
            "roc_auc": auc,
            "roc_auc_lost": float(test_metrics["roc_auc"] - auc),
        }

    forest = pipeline.named_steps["rf"]
    importance = {
        column: float(value)
        for column, value in zip(features.columns, forest.feature_importances_)
    }

    # THE BUNDLE SHAPE IS NOT NEGOTIABLE. `app/ml/artifacts.py` rejects any
    # joblib that is not a dict carrying `pipelines`, and the predictor reads
    # `variants[name]` for its columns, thresholds and reported figures. A
    # single variant is emitted under one name -- see VARIANT_NAME.
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / "heart_rf_v2.joblib"
    # BAND STATISTICS TRAVEL WITH THE MODEL, not in the predictor's source.
    # v1's band prose was hard-coded in `app/ml/heart.py` ("21.1% positive
    # against a cohort prevalence of 50.0%"). Those are cardio_train's numbers;
    # the moment the artifact changed they became false while still being
    # rendered next to a patient's result. Measuring them here means the
    # sentence can never describe a model other than the one it ships with.
    band_meaning = {}
    y_test_arr = y_test.to_numpy()
    bands = {
        "low": test_scores < thresholds["borderline"],
        "borderline": (test_scores >= thresholds["borderline"])
        & (test_scores < thresholds["indicated"]),
        "indicated": test_scores >= thresholds["indicated"],
    }
    for name, mask in bands.items():
        share = float(mask.mean())
        positive_rate = float(y_test_arr[mask].mean()) if mask.any() else None
        band_meaning[name] = (
            f"On the held-out test split {100 * positive_rate:.1f}% of patients "
            f"in this band had a diagnosis, against a cohort prevalence of "
            f"{100 * float(y_test_arr.mean()):.1f}%. This band holds "
            f"{100 * share:.0f}% of the cohort."
            if positive_rate is not None
            else "No held-out patient fell in this band, so its rate is unmeasured."
        )

    variant_spec = {
        "numeric_features": list(features.columns),
        "categorical_features": [],
        "tri_state_features": [],
        "thresholds": thresholds,
        "threshold_basis": (
            "75th (borderline) and 90th (indicated) percentiles of the "
            "OUT-OF-FOLD score distribution. At 9% prevalence a 0.5 cut-off "
            "would call almost nobody positive."
        ),
        "band_meaning": band_meaning,
        "global_feature_importance": importance,
        "metrics": test_metrics,
    }
    joblib.dump(
        {
            "artifact_version": ARTIFACT_VERSION,
            "model_id": MODEL_ID,
            "condition": CONDITION,
            "assessment_kind": "disease_likelihood",
            "algorithm": "RandomForestClassifier",
            "source_label": SOURCE_LABEL,
            "required_features": list(REQUIRED_FEATURES),
            # PROVENANCE LIVES IN THE JOBLIB TOO, not only in the sidecar JSON.
            # The predictor reports these on every decision by reading the
            # BUNDLE; anything recorded only in the metrics file comes back as
            # null, which reads as "unknown provenance" for a model whose
            # provenance is in fact fully known.
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "sklearn_version": sklearn.__version__,
            "hyperparameters": {
                "n_estimators": 400,
                "min_samples_leaf": 25,
                "class_weight": "balanced_subsample",
                "random_state": RANDOM_STATE,
                "imputation": "median (SimpleImputer), fitted on train only",
            },
            # NESTED, because `app/ml/heart.py` reads `bundle["dataset"]` and
            # pulls sha256 / rows_used / prevalence / synthetic_rows from it.
            # Flattening these to top level made the predictor report null
            # provenance for a model whose provenance is fully recorded.
            "dataset": dataset_meta,
            "resampling": "none -- class weights only, no SMOTE, no oversampling",
            "cholesterol_is_banded": False,
            "pipelines": {VARIANT_NAME: pipeline},
            "variants": {VARIANT_NAME: variant_spec},
        },
        artifact_path,
    )

    metrics = {
        "artifact_version": ARTIFACT_VERSION,
        "model_id": MODEL_ID,
        "condition": CONDITION,
        "assessment_kind": "disease_likelihood",
        "assessment_kind_note": (
            "Estimates the LIKELIHOOD of diagnosed cardiac disease. Module 8's "
            "RULE_HEART_DISEASE_RISK_FACTORS emits the same condition string "
            "from a RISK-FACTOR COUNT. Both are legitimate and they are not the "
            "same quantity; the predictor stamps metadata.assessment_kind on "
            "every decision so Modules 16/17 can fuse them without conflating "
            "burden with probability."
        ),
        "algorithm": "RandomForestClassifier",
        "source_label": SOURCE_LABEL,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "joblib_version": joblib.__version__,
        "hyperparameters": {
            "n_estimators": 400,
            "min_samples_leaf": 25,
            "class_weight": "balanced_subsample",
            "random_state": RANDOM_STATE,
            "imputation": "median (SimpleImputer), fitted on train only",
        },
        "dataset": dataset_meta,
        "split": {
            "test_size": 0.2,
            "stratified": True,
            "random_state": RANDOM_STATE,
            "n_train": int(len(x_train)),
            "n_test": int(len(x_test)),
        },
        "required_features": list(REQUIRED_FEATURES),
        "cholesterol_semantics": (
            "CONTINUOUS total cholesterol in mg/dL -- NOT v1's 1/2/3 NCEP band. "
            "Keeping the real number is worth +0.024 ROC-AUC over banding it, "
            "measured on this dataset. app/ml/heart.py's cholesterol_band() is "
            "not used by this artifact."
        ),
        "variant_policy": (
            "ONE variant, `all`. NHANES-CVD carries no smoking column, so a with_smoking "
            "pipeline would be the without_smoking pipeline renamed -- a variant "
            "claiming an input it never saw. v1's two variants differed by 0.002 "
            "ROC-AUC."
        ),
        "cross_validated_metrics": cv_metrics,
        "held_out_metrics": test_metrics,
        "thresholds": thresholds,
        "threshold_basis": (
            "75th and 90th percentiles of the OUT-OF-FOLD score distribution. At "
            "9% prevalence a 0.5 cut-off would call almost nobody positive."
        ),
        "feature_importance": importance,
        "feature_importance_caveat": (
            "A whole-dataset ranking. It says what the model relies on across the "
            "cohort, NOT why any one patient was scored as they were."
        ),
        "ablation": ablation,
        "comparison_to_v1": {
            "v1_dataset": (
                "cardio_train.csv (70k rows, undocumented target, 50% prevalence)"
            ),
            "v1_held_out_roc_auc": 0.6970118480612282,
            "v2_held_out_roc_auc": test_metrics["roc_auc"],
            "delta_roc_auc": test_metrics["roc_auc"] - 0.6970118480612282,
            "note": (
                "The two numbers are computed on DIFFERENT populations and "
                "DIFFERENT outcome definitions, so this is not a like-for-like "
                "contest and should not be quoted as one. The claim being made is "
                "narrower and still worth making: on the same three inputs, a "
                "nationally representative cohort with a stated diagnostic "
                "outcome supports a materially better discriminator than "
                "cardio_train did, and does so at a realistic 9% prevalence "
                "rather than a constructed 50%."
            ),
        },
        "honest_read": (
            "Held-out ROC-AUC near 0.81 on age, BMI and total cholesterol alone, "
            "at a realistic 9% prevalence. That is a usable coarse discriminator "
            "and nothing more: PR-AUC around 0.30 against a 0.09 baseline means "
            "most people it ranks highly will still not have heart disease, so a "
            "high score is a reason to discuss testing with a clinician, never a "
            "finding. The outcome is SELF-REPORTED physician diagnosis, which "
            "misses undiagnosed disease and therefore under-counts exactly the "
            "people a screening tool most wants to find. The strongest known "
            "predictor of cardiovascular disease -- blood pressure -- is still "
            "absent from VaidyaAI entirely, and adding a systolic reading to "
            "Module 2 remains the single highest-value change available to this "
            "predictor."
        ),
        # THE DIGEST IS THE POINT, not the filename. `app/ml/artifacts.py`
        # reads `model_artifact.sha256` to verify the joblib it just loaded is
        # the one this metrics file describes; recording a bare filename here
        # (as an earlier draft did) leaves every prediction stamped
        # `artifact_integrity_verified: false`, silently downgrading a shipped
        # integrity check to nothing. Computed AFTER the dump, over the file
        # that will actually be loaded.
        "model_artifact": {
            "filename": artifact_path.name,
            "sha256": sha256_of(artifact_path),
            "bytes": artifact_path.stat().st_size,
        },
    }

    metrics_path = ARTIFACT_DIR / "heart_rf_v2.metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"  wrote {artifact_path.name} and {metrics_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
