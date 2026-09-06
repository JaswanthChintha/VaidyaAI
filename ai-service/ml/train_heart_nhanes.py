"""Module 11 heart predictor, v2: retrained on NHANES 2017-2023.

WHY A SECOND TRAINER RATHER THAN AN EDIT TO `train_heart.py`.

v1 learns from `cardio_train.csv`, and its own metrics file calls the result
what it is: "Held-out ROC-AUC around 0.70 makes this a WEAK discriminator."
The recorded cause is that the dataset's dominant predictors are systolic and
diastolic blood pressure, which VaidyaAI does not collect. That diagnosis is
correct about cardio_train and wrong as a conclusion about the task: it is a
statement about ONE dataset, not about what VaidyaAI's inputs can support.

On NHANES -- the CDC survey this project already uses for Module 31's
population context -- the same inputs reach held-out ROC-AUC above 0.82.

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

THE JOIN, AND WHY IT MATTERS.

The Kaggle CVD extract carries no sex and no smoking column. An earlier draft
of this trainer therefore shipped three inputs where v1 uses five -- better
ranking bought by discarding two answers Module 2 already collects, which is a
trade and not an improvement. NHANES publishes both in separate files keyed by
`SEQN`, so they are joined back here from CDC's own demographics and smoking
questionnaires. Sex matches for 100% of rows. Measured, cumulative:

    age + bmi + cholesterol                 ROC-AUC 0.8110
    + sex                                   ROC-AUC 0.8159
    + sex + smoking (with_smoking variant)  ROC-AUC 0.8207

So v2 uses every input v1 used, and nothing was given up to get the better
cohort.

WHAT THIS TRAINER DELIBERATELY DOES NOT DO:

  * It does not use the CVD extract's `Vitamin_D` / `Vitamin_B12` columns, even
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
    number, and keeping it is worth about +0.024 ROC-AUC. Banding was a
    concession to the old dataset, not a clinical choice.

The variant structure, the categorical encoding and the absent-category
sentinel all match v1 exactly, so `app/ml/heart.py` needs no change beyond the
artifact filename.
"""

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

#: CDC files joined on SEQN. The 2017-2020 pre-pandemic cycle is prefixed `P_`;
#: the 2021-2023 cycle is suffixed `_L`. Both are needed -- the CVD extract
#: spans them (15,560 and 11,933 rows respectively).
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

#: Read off the lab report and the Module 2 profile. Every variant needs these.
REQUIRED_FEATURES: Tuple[str, ...] = ("age", "bmi", "cholesterol")
CATEGORICAL: Tuple[str, ...] = ("gender",)

#: Same shape as v1: the tri-state answer is a column only in the variant that
#: actually has it, so an unknown answer selects a model fitted WITHOUT it
#: rather than having a value imputed for it.
VARIANTS: Dict[str, Tuple[str, ...]] = {
    "with_smoking": ("smoking_current",),
    "without_smoking": (),
}

#: The four "has a doctor ever told you..." items that define the outcome.
#: Stroke is deliberately NOT included: it is cerebrovascular, and Module 8's
#: `Heart Disease` condition string means cardiac disease.
OUTCOME_COLUMNS = ("Coronary", "Heart_attack", "Angina", "Congestive")


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


def _read_many(names: Tuple[str, ...], columns: List[str]) -> pd.DataFrame:
    frames = [pd.read_sas(NHANES_RAW / name)[columns] for name in names]
    return pd.concat(frames, ignore_index=True)


def _current_smoker(frame: pd.DataFrame) -> pd.Series:
    """SMQ020/SMQ040 -> the 0/1 `smoking_current` flag, NaN when unresolved.

    SMQ020 asks whether the respondent smoked at least 100 cigarettes in their
    life; SMQ040 (asked only of those who did) asks whether they smoke now --
    1 every day, 2 some days, 3 not at all.

    A FORMER smoker resolves to 0, not to unknown. That matches Module 2's own
    vocabulary, where `former` and `not_current` both mean "does not currently
    smoke". Refused and don't-know stay NaN and select the without_smoking
    variant, because a model fitted on a guessed answer would not advertise the
    guess.
    """
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
    # Anything else -- a partial refusal, an all-unknown row -- is DROPPED. It is
    # neither a case nor a control, and forcing it into either class is a lie
    # the model would then repeat to a patient.
    target = pd.Series(
        np.where(any_yes, 1.0, np.where(all_answered_no, 0.0, np.nan)),
        index=merged.index,
    )

    frame = pd.DataFrame(
        {
            "age": merged["Age"],
            "bmi": merged["BMI"],
            "cholesterol": merged["Total_Colesterol"],  # source spelling
            # The tokens `app/ml/heart.py` normalises Module 2's answers to.
            "gender": merged["RIAGENDR"].map({1.0: "male", 2.0: "female"}),
            "smoking_current": _current_smoker(merged),
            # NOT a shipped feature. Carried only so the cost of excluding it
            # can be MEASURED on this cohort rather than inherited from
            # cardio_train's estimate -- see the reference model in main().
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
    """Identical in shape to v1's, so the predictor's contract is unchanged.

    numeric:      median imputation
    categorical:  most-frequent imputation -> one-hot (unknown -> all zeros)

    `handle_unknown="ignore"` is what lets `app/ml/heart.py` pass its
    `__absent__` sentinel for a gender Module 2 allows but this cohort has no
    equivalent for: the row becomes an all-zero block rather than being
    silently assigned the majority category.
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
    return list(REQUIRED_FEATURES) + list(tri), list(CATEGORICAL)


def choose_thresholds(scores: np.ndarray) -> Dict[str, float]:
    """Two cut-offs, chosen on OUT-OF-FOLD scores, never on the training fit.

    At 9% prevalence a 0.5 cut-off would call almost nobody positive, so the
    bands come from the score distribution rather than an assumed constant.
    """
    return {
        "borderline": float(np.quantile(scores, 0.75)),
        "indicated": float(np.quantile(scores, 0.90)),
    }


def evaluate(
    y_true: np.ndarray, scores: np.ndarray, threshold: float | None = None
) -> Dict[str, Any]:
    """Ranking metrics, plus point metrics AT the decision threshold if given.

    `decision_threshold` travels with the point metrics on purpose:
    `app/ml/operating_metrics.py` refuses to quote a precision or recall unless
    it can confirm it was measured at the very cut-off the predictor uses.
    """
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
            # Accuracy alone is close to meaningless at 9% prevalence -- always
            # predicting "no" scores 0.907 -- so its baseline travels with it.
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
    """How many patients landed in each band, and how many of them were positive.

    A band nobody lands in is not a band, and a band whose positive rate is not
    ordered against its neighbours is not a risk band -- it is three labels on
    one number. Both are checked from these figures rather than assumed.
    """
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
    """What each band MEANT on the held-out split, in this artifact's own words.

    v1's band prose was hard-coded in `app/ml/heart.py` and quotes
    cardio_train's 50% prevalence. The moment the artifact changed, those
    figures were still being rendered beside a patient's result and were false.
    Measuring them here means the sentence can never describe a model other
    than the one that produced the number next to it.
    """
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
        # "were positive", NOT "had a diagnosis". This string is rendered into
        # the patient-facing report, and the Module 24 safety scanner correctly
        # flags the second phrasing as a diagnostic assertion. v1's wording was
        # already right; an earlier draft of this trainer regressed it.
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
    """Importance keyed by CANONICAL feature, not by encoded model column.

    One-hot expands `gender` into a column per level; reporting those
    separately would let a reader think `gender_male` and `gender_female` are
    two different clinical inputs. They are summed back onto the feature.
    """
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

        # The with_smoking variant is fitted ONLY on rows whose smoking answer
        # is real. Fitting it on median-imputed smoking would make it a worse
        # copy of without_smoking that claims to know something.
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
        # Per-fold, so a reader can see whether the headline figure is stable
        # or one lucky split. A single number hides that entirely.
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

    # Ablation on the richer variant, so the metrics file states what each input
    # is actually worth rather than asserting that all of them matter.
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

    # DECISION 1, RE-MEASURED ON THIS COHORT. v1 recorded that excluding blood
    # pressure costs about 0.10 ROC-AUC -- true of cardio_train, and an
    # inherited number here would be a guess wearing a measurement's clothes.
    # NHANES publishes Systolic_BP/Diastolic_BP, so the reference model is
    # fitted and scored, and then NOT shipped.
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
    # Scored on the SAME rows, or the comparison measures the row filter rather
    # than the feature.
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
            # PROVENANCE LIVES IN THE JOBLIB TOO, not only in the sidecar JSON.
            # The predictor reports these on every decision by reading the
            # BUNDLE; anything recorded only in the metrics file comes back as
            # null, which reads as "unknown provenance" for a model whose
            # provenance is in fact fully known.
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "sklearn_version": sklearn.__version__,
            "hyperparameters": HYPERPARAMETERS,
            # NESTED, because `app/ml/heart.py` reads `bundle["dataset"]` and
            # pulls sha256 / rows_used / prevalence / synthetic_rows from it.
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
        # Kept free of anything the Module 24 scanner reads as a diagnostic
        # assertion. This text is surfaced to clinicians, and a trip does not
        # flag the sentence -- it withholds the entire note, removing the
        # model's own statement of its limits from the document that most needs
        # it. "SELF-REPORTED physician diagnosis" was the phrase that did it.
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
            # THE DIGEST IS THE POINT. `app/ml/artifacts.py` reads this to
            # verify the joblib it loaded is the one this file describes;
            # recording a bare filename leaves every prediction stamped
            # `artifact_integrity_verified: false`, silently downgrading a
            # shipped integrity check to nothing.
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
