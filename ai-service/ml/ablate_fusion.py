"""Does fusion earn its place? Rule-only vs model-only vs fused.

WHY THIS EXISTS
===============

The central architectural claim of VaidyaAI is that a deterministic rule engine
and a condition-specific model are better combined than used alone. That claim
was asserted and never measured. A reviewer of the manuscript identified the
omission as the most important missing experiment, and they were right.

WHAT MAKES IT MEASURABLE HERE
=============================

The diabetes dataset carries `hba1c`, `blood_glucose` AND the outcome label, so
the platform's own threshold rule and its trained forest can both be evaluated
on the same held-out patients against the same ground truth. That is exactly
the comparison the architecture rests on.

⚠ THIS IS NOT A CLINICAL VALIDATION. The label is the dataset's, not a
clinician's, and the rule being tested is partly the criterion by which such
labels are usually assigned -- see the leakage ablation. What this experiment
can settle is narrower and still worth settling: given these three decision
procedures over identical inputs, does combining them change the error profile?

PROTOCOL
========

The split is reproduced exactly as `train_diabetes.py` creates it -- same file,
de-duplicated before splitting, stratified 80/20 at random_state 42 -- and the
SHIPPED model artifact is loaded rather than retrained, so the model arm is the
one actually deployed.

Rule arm: the platform's own thresholds. HbA1c >= 6.5 % is diabetes-range;
5.7-6.4 % is the prediabetes band. Glucose is treated under the unknown-timing
policy the rule engine applies when a report does not establish that a sample
was fasting: >= 200 mg/dL is diabetes-range and >= 140 mg/dL is the 2-hour
post-load impaired boundary. Using the post-load boundary for a sample of
unknown timing is the platform's deliberate choice against over-calling.

Model arm: the shipped probability, banded by the two published operating
thresholds.

Fused arm: the platform's fusion rule -- the maximum risk over contributing
sources on the ordering low < medium < high.

⚠ WRITES NOTHING INTO ml/artifacts/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

DATASET = SERVICE_ROOT / "datasets" / "raw" / "diabetes_prediction_dataset.csv"
MODEL = SERVICE_ROOT / "ml" / "artifacts" / "diabetes_rf_v1.joblib"
METRICS = SERVICE_ROOT / "ml" / "artifacts" / "diabetes_rf_v1.metrics.json"

RANDOM_STATE = 42
TEST_SIZE = 0.20

HBA1C_DIABETES = 6.5
HBA1C_PREDIABETES = 5.7
GLUCOSE_DIABETES_UNKNOWN_TIMING = 200.0
GLUCOSE_IMPAIRED_UNKNOWN_TIMING = 140.0

BANDS = {"low": 0, "medium": 1, "high": 2}


def normalise_smoking(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().replace({"no info": "no_info"})


def load_frame() -> pd.DataFrame:
    raw = pd.read_csv(DATASET)
    frame = raw.drop_duplicates().reset_index(drop=True)
    frame = frame.rename(
        columns={"HbA1c_level": "hba1c", "blood_glucose_level": "blood_glucose"}
    )
    frame["smoking_history"] = normalise_smoking(frame["smoking_history"])
    frame["gender"] = frame["gender"].astype(str).str.strip().str.lower()
    return frame


def rule_band(row: pd.Series) -> int:
    """The platform's threshold rule, as a band."""
    a1c = row["hba1c"]
    glu = row["blood_glucose"]
    if a1c >= HBA1C_DIABETES or glu >= GLUCOSE_DIABETES_UNKNOWN_TIMING:
        return BANDS["high"]
    if a1c >= HBA1C_PREDIABETES or glu >= GLUCOSE_IMPAIRED_UNKNOWN_TIMING:
        return BANDS["medium"]
    return BANDS["low"]


def model_band(prob: float, t_high: float, t_low: float) -> int:
    if prob >= t_high:
        return BANDS["high"]
    if prob >= t_low:
        return BANDS["medium"]
    return BANDS["low"]


def wilson(k: int, n: int):
    if n == 0:
        return None, None
    z = 1.959963985
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (centre - margin) / d, (centre + margin) / d


def score(name: str, bands: np.ndarray, y: np.ndarray) -> Dict:
    """Treat the HIGH band as the positive call; report the full stratification."""
    flag = (bands == BANDS["high"]).astype(int)
    tp = int(((flag == 1) & (y == 1)).sum())
    tn = int(((flag == 0) & (y == 0)).sum())
    fp = int(((flag == 1) & (y == 0)).sum())
    fn = int(((flag == 0) & (y == 1)).sum())
    sens = tp / (tp + fn) if (tp + fn) else None
    spec = tn / (tn + fp) if (tn + fp) else None
    prec = tp / (tp + fp) if (tp + fp) else None
    npv = tn / (tn + fn) if (tn + fn) else None
    f1 = (2 * prec * sens / (prec + sens)) if (prec and sens) else None
    denom = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = ((tp * tn - fp * fn) / denom) if denom else None
    strat: List[Dict] = []
    for label, idx in BANDS.items():
        mask = bands == idx
        n = int(mask.sum())
        strat.append(
            {
                "band": label,
                "patients": n,
                "observed_positive_rate": float(y[mask].mean()) if n else None,
            }
        )
    return {
        "arm": name,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "sensitivity": sens,
        "sensitivity_ci95": wilson(tp, tp + fn),
        "specificity": spec,
        "specificity_ci95": wilson(tn, tn + fp),
        "precision": prec,
        "precision_ci95": wilson(tp, tp + fp),
        "npv": npv,
        "f1": f1,
        "mcc": mcc,
        "band_stratification": strat,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import joblib

    frame = load_frame()
    y_all = frame["diabetes"].astype(int)
    X_all = frame.drop(columns=["diabetes"])
    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=TEST_SIZE, stratify=y_all, random_state=RANDOM_STATE
    )
    y = y_test.to_numpy()

    meta = json.loads(METRICS.read_text(encoding="utf-8"))
    thresholds = meta["variants"]["both"]["thresholds"]
    t_high = float(thresholds["indicated"])
    t_low = float(thresholds["borderline"])

    bundle = joblib.load(MODEL)
    # The bundle keeps metadata under `variants` and the fitted estimators
    # under `pipelines`; the deployed one for this arm is the `both` variant.
    pipe = bundle["pipelines"]["both"]
    prob = pipe.predict_proba(X_test)[:, 1]

    rule = X_test.apply(rule_band, axis=1).to_numpy()
    model = np.array([model_band(p, t_high, t_low) for p in prob])
    fused = np.maximum(rule, model)

    results = {
        "experiment": "rule-only vs model-only vs fused, diabetes",
        "protocol": (
            "Split reproduced exactly as ml/train_diabetes.py creates it; the "
            "SHIPPED model artifact is loaded, not retrained. Rule thresholds "
            "are the platform's own, under the unknown-sample-timing policy. "
            "Fusion is the maximum risk over sources, as implemented."
        ),
        "writes_to_artifacts": False,
        "n_test": int(len(y)),
        "test_prevalence": float(y.mean()),
        "model_thresholds": {"high": t_high, "medium": t_low},
        "arms": [
            score("rule_only", rule, y),
            score("model_only", model, y),
            score("fused", fused, y),
        ],
        "agreement": {
            "rule_and_model_agree_on_band": float((rule == model).mean()),
            "rule_high_model_not": int(((rule == 2) & (model != 2)).sum()),
            "model_high_rule_not": int(((model == 2) & (rule != 2)).sum()),
        },
    }

    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    for a in results["arms"]:
        print(
            f"{a['arm']:<12} sens {a['sensitivity']:.3f}  spec {a['specificity']:.3f}  "
            f"prec {a['precision']:.3f}  F1 {a['f1']:.3f}  MCC {a['mcc']:.3f}"
        )
    print("agreement:", results["agreement"])
    print("written:", args.out)


if __name__ == "__main__":
    main()
