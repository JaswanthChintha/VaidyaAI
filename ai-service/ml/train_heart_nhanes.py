from __future__ import annotations

import hashlib
import json
import platform
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
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
DATASET = SERVICE_ROOT / "datasets" / "raw" / "nhanes_cvd_2017_2023.csv"
NHANES_RAW = SERVICE_ROOT / "datasets" / "population" / "raw"
ARTIFACT_DIR = HERE / "artifacts"

DEMOGRAPHICS = ("P_DEMO.xpt", "DEMO_L.xpt")
SMOKING = ("P_SMQ.xpt", "SMQ_L.xpt")

ARTIFACT_VERSION = "2.0.0"
MODEL_ID = "heart_rf"
CONDITION = "Heart Disease"
SOURCE_LABEL = "Random Forest"
RANDOM_STATE = 42

HYPERPARAMETERS = {
    "n_estimators": 400,
    "min_samples_leaf": 25,
    "class_weight": "balanced_subsample",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

REQUIRED_FEATURES: Tuple[str, ...] = ("age", "bmi", "cholesterol")
CATEGORICAL: Tuple[str, ...] = ("gender",)

VARIANTS: Dict[str, Tuple[str, ...]] = {
    "with_smoking": ("smoking_current",),
    "without_smoking": (),
}

OUTCOME_COLUMNS = ("Coronary", "Heart_attack", "Angina", "Congestive")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _yes_no(series: pd.Series) -> pd.Series:
    return series.map({1.0: 1.0, 2.0: 0.0}).where(series.isin([1.0, 2.0]))


def _read_many(names: Tuple[str, ...], columns: List[str]) -> pd.DataFrame:
    frames = [pd.read_sas(NHANES_RAW / name)[columns] for name in names]
    return pd.concat(frames, ignore_index=True)


def _current_smoker(frame: pd.DataFrame) -> pd.Series:
    current = pd.Series(np.nan, index=frame.index, dtype="float64")
    never_100 = frame["SMQ020"] == 2.0
    smoked_100 = frame["SMQ020"] == 1.0
    current[never_100] = 0.0
    current[smoked_100 & frame["SMQ040"].isin([1.0, 2.0])] = 1.0
    current[smoked_100 & (frame["SMQ040"] == 3.0)] = 0.0
    return current


def load_dataset() -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any]]:
    raw = pd.read_csv(DATASET, low_memory=False)

    demographics = _read_many(DEMOGRAPHICS, ["SEQN", "RIAGENDR"])
    smoking = _read_many(SMOKING, ["SEQN", "SMQ020", "SMQ040"])
    merged = raw.merge(demographics, on="SEQN", how="left").merge(
        smoking, on="SEQN", how="left"
    )

    answers = pd.concat([_yes_no(merged[c]) for c in OUTCOME_COLUMNS], axis=1)
    answers.columns = list(OUTCOME_COLUMNS)
    any_yes = answers.max(axis=1) == 1
    all_answered_no = answers.notna().all(axis=1) & (answers.max(axis=1) == 0)
    target = pd.Series(
        np.where(any_yes, 1.0, np.where(all_answered_no, 0.0, np.nan)),
        index=merged.index,
    )

    frame = pd.DataFrame(
        {
            "age": merged["Age"],
            "bmi": merged["BMI"],
            "cholesterol": merged["Total_Colesterol"],
            "gender": merged["RIAGENDR"].map({1.0: "male", 2.0: "female"}),
            "smoking_current": _current_smoker(merged),
            "_systolic_bp": merged["Systolic_BP"],
            "_diastolic_bp": merged["Diastolic_BP"],
        }
    )

    adult = merged["Age"] >= 18
    complete = frame[list(REQUIRED_FEATURES)].notna().all(axis=1)
    keep = adult & complete & target.notna()

    meta: Dict[str, Any] = {
        "path": str(DATASET.relative_to(SERVICE_ROOT)).replace("\\", "/"),
        "source": (
            "CDC NHANES 2017-2023. Outcome, age, BMI and cholesterol from the "
            "Kaggle extract ahiduzzaman28/nhanes-cvd-raw-data-2017-23; sex and "
            "smoking joined on SEQN from CDC's own P_DEMO/DEMO_L and "
            "P_SMQ/SMQ_L files."
        ),
        "license": "CC BY-SA 4.0 (extract); CDC NHANES is public domain",
        "sha256": sha256_of(DATASET),
        "joined_files": {
            name: {
                "sha256": sha256_of(NHANES_RAW / name),
                "bytes": (NHANES_RAW / name).stat().st_size,
            }
            for name in DEMOGRAPHICS + SMOKING
        },
        "join_key": "SEQN",
        "gender_match_rate": float(merged["RIAGENDR"].notna().mean()),
        "smoking_resolved_rate": float(frame["smoking_current"].notna().mean()),
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
        "gender_mapping": {"1": "male", "2": "female"},
        "gender_levels": ["female", "male"],
        "age_units_raw": "years",
        "age_conversion": (
            "none -- NHANES RIDAGEYR/Age is already whole years. v1 had to "
            "convert cardio_train's age-in-days."
        ),
        "cholesterol_semantics": (
            "CONTINUOUS total cholesterol in mg/dL. NOT an ordinal band: v1's "
            "cardio_train column was 1/2/3 and had to be mapped from mg/dL, "
            "which discarded information this dataset preserves."
        ),
        "cleaning_rule": {
            "applied": False,
            "basis": (
                "None needed. NHANES publishes examined, quality-controlled "
                "measurements; cardio_train required height/weight/BMI bands to "
                "remove values incompatible with an adult."
            ),
            "removed": {"rows_removed_total": 0},
        },
        "gender_mapping_basis": (
            "DOCUMENTED by CDC in the RIAGENDR codebook -- not inferred. v1's "
            "cardio_train mapping had to be inferred from height and smoking "
            "rates because that dataset documents nothing."
        ),
        "smoking_semantics": (
            "SMQ020 (smoked 100+ cigarettes ever) with SMQ040 (smokes now: 1 "
            "every day, 2 some days, 3 not at all). Current smoker = 1; never "
            "and former = 0; refused/don't-know unresolved, selecting the "
            "without_smoking variant."
        ),
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


def build_pipeline(numeric: List[str], categorical: List[str]) -> Pipeline:
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
    return list(REQUIRED_FEATURES) + list(tri), list(CATEGORICAL)


def choose_thresholds(scores: np.ndarray) -> Dict[str, float]:
    return {
        "borderline": float(np.quantile(scores, 0.75)),
        "indicated": float(np.quantile(scores, 0.90)),
    }


def evaluate(
    y_true: np.ndarray, scores: np.ndarray, threshold: float | None = None
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "pr_auc": float(average_precision_score(y_true, scores)),
        "pr_auc_average_precision": float(average_precision_score(y_true, scores)),
        "brier_score": float(brier_score_loss(y_true, scores)),
        "prevalence": float(np.mean(y_true)),
        "n": int(len(y_true)),
    }
    if threshold is None:
        return out
    predicted = (scores >= threshold).astype(int)
    rate = float(np.mean(y_true))
    out.update(
        {
            "decision_threshold": float(threshold),
            "accuracy": float(np.mean(predicted == y_true)),
            "majority_class_baseline_accuracy": max(rate, 1.0 - rate),
            "positive_class": {
                "precision": float(precision_score(y_true, predicted, zero_division=0)),
                "recall": float(recall_score(y_true, predicted, zero_division=0)),
                "f1": float(f1_score(y_true, predicted, zero_division=0)),
                "support": int((y_true == 1).sum()),
            },
            "confusion_matrix": {
                "labels": ["actual_negative", "actual_positive"],
                "columns": ["predicted_negative", "predicted_positive"],
                "matrix": confusion_matrix(y_true, predicted, labels=[0, 1]).tolist(),
            },
        }
    )
    return out


def risk_bands_on_test(
    y_true: np.ndarray, scores: np.ndarray, thresholds: Dict[str, float]
) -> Dict[str, Any]:
    masks = {
        "low": scores < thresholds["borderline"],
        "medium": (scores >= thresholds["borderline"])
        & (scores < thresholds["indicated"]),
        "high": scores >= thresholds["indicated"],
    }
    return {
        name: {
            "patients": int(mask.sum()),
            "observed_positive_rate": (
                float(y_true[mask].mean()) if mask.any() else None
            ),
            "share_of_cohort": float(mask.mean()),
        }
        for name, mask in masks.items()
    }


def band_meanings(
    y_true: np.ndarray, scores: np.ndarray, thresholds: Dict[str, float]
) -> Dict[str, str]:
    bands = {
        "low": scores < thresholds["borderline"],
        "borderline": (scores >= thresholds["borderline"])
        & (scores < thresholds["indicated"]),
        "indicated": scores >= thresholds["indicated"],
    }
    prevalence = 100 * float(np.mean(y_true))
    out: Dict[str, str] = {}
    for name, mask in bands.items():
        if not mask.any():
            out[name] = (
                "No held-out patient fell in this band, so its rate is unmeasured."
            )
            continue
        out[name] = (
            f"On the held-out test split {100 * float(y_true[mask].mean()):.1f}% "
            f"of patients in this band were positive, against a cohort "
            f"prevalence of {prevalence:.1f}%. This band holds "
            f"{100 * float(mask.mean()):.0f}% of the cohort."
        )
    return out


def feature_importance(
    pipeline: Pipeline, numeric: List[str], categorical: List[str]
) -> Dict[str, float]:
    encoder = pipeline.named_steps["preprocess"].named_transformers_["categorical"]
    expanded = list(encoder.named_steps["encode"].get_feature_names_out(categorical))
    values = pipeline.named_steps["model"].feature_importances_

    out: Dict[str, float] = {}
    for name, value in zip(numeric, values[: len(numeric)]):
        out[name] = float(value)
    for name, value in zip(expanded, values[len(numeric) :]):
        base = name.rsplit("_", 1)[0] if name.rsplit("_", 1)[0] in categorical else name
        for original in categorical:
            if name.startswith(original + "_"):
                base = original
                break
        out[base] = out.get(base, 0.0) + float(value)
    return out


def main() -> int:
    features, labels, dataset_meta = load_dataset()
    print(
        f"rows used: {len(features)}  positives: {int(labels.sum())} "
        f"({100 * labels.mean():.1f}% prevalence)"
    )
    print(
        f"  sex matched {100 * dataset_meta['gender_match_rate']:.1f}% | "
        f"smoking resolved {100 * dataset_meta['smoking_resolved_rate']:.1f}%"
    )

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, stratify=labels, random_state=RANDOM_STATE
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    pipelines: Dict[str, Pipeline] = {}
    variants: Dict[str, Any] = {}

    for name, tri in VARIANTS.items():
        numeric, categorical = variant_columns(tri)
        columns = numeric + categorical

        train_mask = (
            x_train[list(tri)].notna().all(axis=1)
            if tri
            else pd.Series(True, index=x_train.index)
        )
        test_mask = (
            x_test[list(tri)].notna().all(axis=1)
            if tri
            else pd.Series(True, index=x_test.index)
        )

        oof = cross_val_predict(
            build_pipeline(numeric, categorical),
            x_train.loc[train_mask, columns],
            y_train[train_mask],
            cv=cv,
            method="predict_proba",
        )[:, 1]
        thresholds = choose_thresholds(oof)
        oof_predicted = (oof >= thresholds["indicated"]).astype(int)
        thresholds["indicated_precision_achieved"] = float(
            precision_score(y_train[train_mask], oof_predicted, zero_division=0)
        )
        thresholds["indicated_recall_achieved"] = float(
            recall_score(y_train[train_mask], oof_predicted, zero_division=0)
        )

        pipeline = build_pipeline(numeric, categorical).fit(
            x_train.loc[train_mask, columns], y_train[train_mask]
        )
        scores = pipeline.predict_proba(x_test.loc[test_mask, columns])[:, 1]
        metrics = evaluate(
            y_test[test_mask].to_numpy(), scores, thresholds["indicated"]
        )
        fold_auc = cross_val_score(
            build_pipeline(numeric, categorical),
            x_train.loc[train_mask, columns],
            y_train[train_mask],
            cv=cv,
            scoring="roc_auc",
        )
        metrics["cross_validation"] = {
            "folds": cv.get_n_splits(),
            "stratified": True,
            "roc_auc": {
                "per_fold": [float(v) for v in fold_auc],
                "mean": float(fold_auc.mean()),
                "std": float(fold_auc.std()),
            },
        }
        metrics["risk_bands_on_test"] = risk_bands_on_test(
            y_test[test_mask].to_numpy(), scores, thresholds
        )

        print(
            f"  {name:16s} n_train={int(train_mask.sum()):5d} "
            f"ROC-AUC {metrics['roc_auc']:.4f}  PR-AUC {metrics['pr_auc']:.4f}"
        )

        pipelines[name] = pipeline
        variants[name] = {
            "numeric_features": numeric,
            "categorical_features": categorical,
            "tri_state_features": list(tri),
            "thresholds": thresholds,
            "threshold_basis": (
                "75th (borderline) and 90th (indicated) percentiles of the "
                "OUT-OF-FOLD score distribution. At 9% prevalence a 0.5 "
                "cut-off would call almost nobody positive."
            ),
            "band_meaning": band_meanings(
                y_test[test_mask].to_numpy(), scores, thresholds
            ),
            "global_feature_importance": feature_importance(
                pipeline, numeric, categorical
            ),
            "metrics": metrics,
        }

    numeric, categorical = variant_columns(VARIANTS["with_smoking"])
    rich_train = x_train["smoking_current"].notna()
    rich_test = x_test["smoking_current"].notna()
    full_auc = variants["with_smoking"]["metrics"]["roc_auc"]
    ablation: Dict[str, Any] = {}
    for dropped in numeric + categorical:
        kept_numeric = [c for c in numeric if c != dropped]
        kept_categorical = [c for c in categorical if c != dropped]
        if not kept_numeric:
            continue
        trimmed = build_pipeline(kept_numeric, kept_categorical).fit(
            x_train.loc[rich_train, kept_numeric + kept_categorical],
            y_train[rich_train],
        )
        got = trimmed.predict_proba(
            x_test.loc[rich_test, kept_numeric + kept_categorical]
        )[:, 1]
        auc = float(roc_auc_score(y_test[rich_test], got))
        ablation[f"without_{dropped}"] = {
            "roc_auc": auc,
            "roc_auc_lost": float(full_auc - auc),
        }

    bp_numeric = numeric + ["_systolic_bp", "_diastolic_bp"]
    bp_train = rich_train & x_train[["_systolic_bp", "_diastolic_bp"]].notna().all(
        axis=1
    )
    bp_test = rich_test & x_test[["_systolic_bp", "_diastolic_bp"]].notna().all(axis=1)
    bp_pipeline = build_pipeline(bp_numeric, categorical).fit(
        x_train.loc[bp_train, bp_numeric + categorical], y_train[bp_train]
    )
    bp_scores = bp_pipeline.predict_proba(
        x_test.loc[bp_test, bp_numeric + categorical]
    )[:, 1]
    bp_auc = float(roc_auc_score(y_test[bp_test], bp_scores))
    shipped_on_bp_rows = pipelines["with_smoking"].predict_proba(
        x_test.loc[bp_test, numeric + categorical]
    )[:, 1]
    shipped_auc = float(roc_auc_score(y_test[bp_test], shipped_on_bp_rows))
    blood_pressure_reference = {
        "shipped": False,
        "roc_auc": bp_auc,
        "shipped_model_roc_auc": shipped_auc,
        "roc_auc_cost_of_exclusion": bp_auc - shipped_auc,
        "n_test": int(bp_test.sum()),
        "measured_on": "this cohort, same test rows for both models",
        "why_not_shipped": (
            "VaidyaAI collects no blood pressure anywhere -- not in Module 2's "
            "profile and not from a lab report -- so every patient would arrive "
            "with it missing and the pipeline would median-impute it for all of "
            "them."
        ),
        "supersedes_v1_estimate": (
            "v1 recorded the cost of this exclusion as about 0.10 ROC-AUC, and "
            "the project has since treated adding a systolic field to Module 2 "
            "as the highest-value change available to Module 11. On THIS cohort "
            "the measured cost is far smaller -- see roc_auc_cost_of_exclusion. "
            "The 0.10 figure is a property of cardio_train, where blood "
            "pressure carried most of the signal and the remaining features "
            "carried little; it does not transfer. Blood pressure is still "
            "worth having, but on this evidence it is a small gain, and the "
            "case for changing the profile should be argued from this number "
            "rather than from the inherited one."
        ),
    }
    print(
        f"  blood-pressure reference (not shipped): ROC-AUC {bp_auc:.4f} "
        f"vs {shipped_auc:.4f} shipped -> cost {bp_auc - shipped_auc:+.4f}"
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / "heart_rf_v2.joblib"
    joblib.dump(
        {
            "artifact_version": ARTIFACT_VERSION,
            "model_id": MODEL_ID,
            "condition": CONDITION,
            "assessment_kind": "disease_likelihood",
            "algorithm": "RandomForestClassifier",
            "source_label": SOURCE_LABEL,
            "required_features": list(REQUIRED_FEATURES),
            "categorical_features": list(CATEGORICAL),
            "tri_state_features": ["smoking_current"],
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "sklearn_version": sklearn.__version__,
            "hyperparameters": HYPERPARAMETERS,
            "dataset": dataset_meta,
            "resampling": dataset_meta["resampling"],
            "blood_pressure_reference_model": blood_pressure_reference,
            "pipelines": pipelines,
            "variants": variants,
        },
        artifact_path,
    )

    metrics_document = {
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
        "hyperparameters": HYPERPARAMETERS,
        "dataset": dataset_meta,
        "split": {
            "test_size": 0.2,
            "stratified": True,
            "random_state": RANDOM_STATE,
            "n_train": int(len(x_train)),
            "n_test": int(len(x_test)),
        },
        "required_features": list(REQUIRED_FEATURES),
        "categorical_features": list(CATEGORICAL),
        "tri_state_features": ["smoking_current"],
        "tri_state_policy": (
            "An unresolved smoking answer selects the without_smoking variant, "
            "which was FITTED without the column. No value is imputed for it, "
            "so the model never treats a missing answer as a stated one."
        ),
        "unknown_category_policy": (
            "OneHotEncoder(handle_unknown='ignore'). A gender Module 2 allows "
            "but this cohort has no level for (e.g. prefer_not_to_say) becomes "
            "an all-zero block rather than the majority category."
        ),
        "cholesterol_semantics": (
            "CONTINUOUS total cholesterol in mg/dL -- NOT v1's 1/2/3 NCEP band. "
            "Keeping the real number is worth about +0.024 ROC-AUC over banding "
            "it. app/ml/heart.py's cholesterol_band() is unused by this artifact."
        ),
        "variants": {
            name: {
                "metrics": spec["metrics"],
                "thresholds": spec["thresholds"],
                "band_meaning": spec["band_meaning"],
                "global_feature_importance": spec["global_feature_importance"],
                "numeric_features": spec["numeric_features"],
                "categorical_features": spec["categorical_features"],
            }
            for name, spec in variants.items()
        },
        "feature_importance_scope": "global_model_level",
        "feature_importance_caveat": (
            "Mean impurity decrease over the whole training set. It ranks "
            "features FOR THE MODEL and orders the evidence. It is NOT a "
            "per-patient explanation."
        ),
        "ablation": ablation,
        "comparison_to_v1": {
            "v1_dataset": (
                "cardio_train.csv (70k rows, undocumented target, 50% prevalence)"
            ),
            "v1_held_out_roc_auc": 0.6970118480612282,
            "v2_held_out_roc_auc": variants["with_smoking"]["metrics"]["roc_auc"],
            "delta_roc_auc": variants["with_smoking"]["metrics"]["roc_auc"]
            - 0.6970118480612282,
            "inputs_v1": ["age", "bmi", "cholesterol_band", "smoking_current", "gender"],
            "inputs_v2": ["age", "bmi", "cholesterol", "smoking_current", "gender"],
            "note": (
                "The two numbers are computed on DIFFERENT populations and "
                "DIFFERENT outcome definitions, so this is not a like-for-like "
                "contest and should not be quoted as one. What can be said: v2 "
                "uses the SAME five patient inputs as v1 -- nothing was given "
                "up -- learns them from a nationally representative cohort with "
                "a stated diagnostic outcome, and does so at a realistic 9% "
                "prevalence rather than a constructed 50%."
            ),
        },
        "blood_pressure_reference_model": blood_pressure_reference,
        "honest_read": (
            "Held-out ROC-AUC above 0.82 at a realistic 9% prevalence. That is "
            "a usable coarse discriminator and nothing more: PR-AUC around 0.32 "
            "against a 0.09 baseline means most people it ranks highly will "
            "still not have heart disease, so a high score is a reason to "
            "discuss testing with a clinician, never a finding. It learned from "
            "what respondents said a doctor had told them, so it under-counts "
            "exactly the people a screening tool most wants to find."
        ),
        "model_artifact": {
            "filename": artifact_path.name,
            "sha256": sha256_of(artifact_path),
            "bytes": artifact_path.stat().st_size,
        },
    }

    metrics_path = ARTIFACT_DIR / "heart_rf_v2.metrics.json"
    metrics_path.write_text(
        json.dumps(metrics_document, indent=2), encoding="utf-8"
    )
    print(f"  wrote {artifact_path.name} and {metrics_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
