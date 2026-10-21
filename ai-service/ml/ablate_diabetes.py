from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

DATASET = SERVICE_ROOT / "datasets" / "raw" / "diabetes_prediction_dataset.csv"

RANDOM_STATE = 42
TEST_SIZE = 0.20
CV_FOLDS = 5

REQUIRED_FEATURES = ("hba1c", "blood_glucose")
OPTIONAL_NUMERIC = ("age", "bmi")
CATEGORICAL = ("gender", "smoking_history")
TRI_STATE = ("hypertension", "heart_disease")

HYPERPARAMETERS = {
    "n_estimators": 200,
    "min_samples_leaf": 50,
    "class_weight": "balanced_subsample",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

ARMS: Dict[str, Tuple[str, ...]] = {
    "full": (),
    "no_hba1c": ("hba1c",),
    "no_blood_glucose": ("blood_glucose",),
    "no_hba1c_no_blood_glucose": ("hba1c", "blood_glucose"),
}


def normalise_smoking(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().replace({"no info": "no_info"})


def load_frame() -> pd.DataFrame:
    if not DATASET.exists():
        raise SystemExit(f"dataset not found: {DATASET}")
    raw = pd.read_csv(DATASET)
    frame = raw.drop_duplicates().reset_index(drop=True)
    frame = frame.rename(
        columns={"HbA1c_level": "hba1c", "blood_glucose_level": "blood_glucose"}
    )
    frame["smoking_history"] = normalise_smoking(frame["smoking_history"])
    frame["gender"] = frame["gender"].astype(str).str.strip().str.lower()
    return frame


def build_pipeline(numeric: List[str], categorical: List[str]) -> Pipeline:
    return Pipeline(
        steps=[
            (
                "prepare",
                ColumnTransformer(
                    transformers=[
                        ("num", SimpleImputer(strategy="median"), numeric),
                        (
                            "cat",
                            Pipeline(
                                steps=[
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


def calibration_bins(y_true: np.ndarray, prob: np.ndarray, bins: int = 10) -> List[Dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    out: List[Dict] = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (prob >= lo) & (prob < hi) if i < bins - 1 else (prob >= lo) & (prob <= hi)
        n = int(mask.sum())
        out.append(
            {
                "bin": f"{lo:.1f}-{hi:.1f}",
                "patients": n,
                "mean_predicted": float(prob[mask].mean()) if n else None,
                "observed_rate": float(y_true[mask].mean()) if n else None,
            }
        )
    return out


def evaluate(name: str, dropped: Tuple[str, ...], frame: pd.DataFrame) -> Dict:
    numeric = [
        c
        for c in list(REQUIRED_FEATURES) + list(OPTIONAL_NUMERIC) + list(TRI_STATE)
        if c not in dropped
    ]
    categorical = [c for c in CATEGORICAL if c not in dropped]

    y = frame["diabetes"].astype(int)
    X = frame.drop(columns=["diabetes"])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )

    pipe = build_pipeline(numeric, categorical)
    pipe.fit(X_train, y_train)
    prob = pipe.predict_proba(X_test)[:, 1]
    y_arr = y_test.to_numpy()

    predicted = (prob >= 0.5).astype(int)
    tp = int(((predicted == 1) & (y_arr == 1)).sum())
    tn = int(((predicted == 0) & (y_arr == 0)).sum())
    fp = int(((predicted == 1) & (y_arr == 0)).sum())
    fn = int(((predicted == 0) & (y_arr == 1)).sum())

    return {
        "arm": name,
        "dropped": list(dropped),
        "features_used": {"numeric": numeric, "categorical": categorical},
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "test_prevalence": float(y_arr.mean()),
        "roc_auc": float(roc_auc_score(y_arr, prob)),
        "pr_auc_average_precision": float(average_precision_score(y_arr, prob)),
        "brier_score": float(brier_score_loss(y_arr, prob)),
        "at_threshold_0.5": {
            "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
            "sensitivity": tp / (tp + fn) if (tp + fn) else None,
            "specificity": tn / (tn + fp) if (tn + fp) else None,
            "precision": tp / (tp + fp) if (tp + fp) else None,
            "npv": tn / (tn + fn) if (tn + fn) else None,
        },
        "calibration": calibration_bins(y_arr, prob),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="where to write the JSON result")
    args = parser.parse_args()

    frame = load_frame()
    results = {
        "experiment": "diabetes feature-removal ablation and calibration",
        "protocol": (
            "Identical to ml/train_diabetes.py: same CSV, de-duplicated before "
            "splitting, stratified 80/20 at random_state 42, same pipeline and "
            "hyperparameters, 'both' tri-state variant. Only the dropped "
            "columns vary. Metrics at the conventional 0.5 cut-off."
        ),
        "writes_to_artifacts": False,
        "dataset_rows_used": int(len(frame)),
        "arms": [],
    }
    for name, dropped in ARMS.items():
        print(f"training arm: {name} ...", flush=True)
        res = evaluate(name, dropped, frame)
        results["arms"].append(res)
        print(
            f"   ROC-AUC {res['roc_auc']:.4f}  PR-AUC "
            f"{res['pr_auc_average_precision']:.4f}  Brier {res['brier_score']:.4f}",
            flush=True,
        )

    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("written:", args.out)


if __name__ == "__main__":
    main()
