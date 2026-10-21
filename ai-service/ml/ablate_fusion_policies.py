from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List

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
VALIDATION_SIZE = 0.20

HBA1C_DIABETES = 6.5
HBA1C_PREDIABETES = 5.7
GLUCOSE_DIABETES = 200.0
GLUCOSE_IMPAIRED = 140.0

LOW, MED, HIGH = 0, 1, 2


def normalise_smoking(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().replace({"no info": "no_info"})


def load_frame() -> pd.DataFrame:
    f = pd.read_csv(DATASET).drop_duplicates().reset_index(drop=True)
    f = f.rename(columns={"HbA1c_level": "hba1c", "blood_glucose_level": "blood_glucose"})
    f["smoking_history"] = normalise_smoking(f["smoking_history"])
    f["gender"] = f["gender"].astype(str).str.strip().str.lower()
    return f


def rule_bands(X: pd.DataFrame) -> np.ndarray:
    a1c = X["hba1c"].to_numpy()
    glu = X["blood_glucose"].to_numpy()
    out = np.full(len(X), LOW)
    out[(a1c >= HBA1C_PREDIABETES) | (glu >= GLUCOSE_IMPAIRED)] = MED
    out[(a1c >= HBA1C_DIABETES) | (glu >= GLUCOSE_DIABETES)] = HIGH
    return out


def model_bands(prob: np.ndarray, t_high: float, t_low: float) -> np.ndarray:
    out = np.full(len(prob), LOW)
    out[prob >= t_low] = MED
    out[prob >= t_high] = HIGH
    return out


POLICIES: Dict[str, Callable[[np.ndarray, np.ndarray], np.ndarray]] = {
    "maximum_risk": lambda r, m: np.maximum(r, m),
    "corroborated_escalation": lambda r, m: np.where(
        (m == HIGH) | ((r == HIGH) & (m == MED)), HIGH, np.maximum(np.minimum(r, MED), m)
    ),
    "unanimous_high": lambda r, m: np.where(
        (r == HIGH) & (m == HIGH), HIGH, np.where((r >= MED) | (m >= MED), MED, LOW)
    ),
    "model_only": lambda r, m: m,
    "rule_only": lambda r, m: r,
}


def metrics(bands: np.ndarray, y: np.ndarray) -> Dict:
    flag = (bands == HIGH).astype(int)
    tp = int(((flag == 1) & (y == 1)).sum())
    tn = int(((flag == 0) & (y == 0)).sum())
    fp = int(((flag == 1) & (y == 0)).sum())
    fn = int(((flag == 0) & (y == 1)).sum())
    sens = tp / (tp + fn) if (tp + fn) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    npv = tn / (tn + fn) if (tn + fn) else 0.0
    f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else 0.0
    den = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = ((tp * tn - fp * fn) / den) if den else 0.0
    return {
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "sensitivity": sens, "specificity": spec, "precision": prec,
        "npv": npv, "f1": f1, "mcc": mcc,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--select-on", default="f1", choices=["f1", "mcc"])
    args = ap.parse_args()

    import joblib

    frame = load_frame()
    y_all = frame["diabetes"].astype(int)
    X_all = frame.drop(columns=["diabetes"])

    X_tr_full, X_test, y_tr_full, y_test = train_test_split(
        X_all, y_all, test_size=TEST_SIZE, stratify=y_all, random_state=RANDOM_STATE
    )
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_tr_full, y_tr_full, test_size=VALIDATION_SIZE,
        stratify=y_tr_full, random_state=RANDOM_STATE,
    )

    meta = json.loads(METRICS.read_text(encoding="utf-8"))
    th = meta["variants"]["both"]["thresholds"]
    t_high, t_low = float(th["indicated"]), float(th["borderline"])

    pipe = joblib.load(MODEL)["pipelines"]["both"]

    def arms(X: pd.DataFrame):
        p = pipe.predict_proba(X)[:, 1]
        return rule_bands(X), model_bands(p, t_high, t_low)

    r_val, m_val = arms(X_val)
    r_test, m_test = arms(X_test)
    yv, yt = y_val.to_numpy(), y_test.to_numpy()

    validation: List[Dict] = []
    for name, fn in POLICIES.items():
        mv = metrics(fn(r_val, m_val), yv)
        validation.append({"policy": name, **mv})
        print(f"[val ] {name:<26} F1 {mv['f1']:.3f}  MCC {mv['mcc']:.3f}  "
              f"sens {mv['sensitivity']:.3f}  spec {mv['specificity']:.3f}")

    fusion_only = [v for v in validation if v["policy"] not in ("model_only", "rule_only")]
    winner = max(fusion_only, key=lambda v: v[args.select_on])["policy"]
    print(f"\nselected on validation by {args.select_on}: {winner}\n")

    test = []
    for name in ("rule_only", "model_only", winner):
        mt = metrics(POLICIES[name](r_test, m_test), yt)
        test.append({"policy": name, **mt})
        print(f"[test] {name:<26} F1 {mt['f1']:.3f}  MCC {mt['mcc']:.3f}  "
              f"sens {mt['sensitivity']:.3f}  spec {mt['specificity']:.3f}  "
              f"prec {mt['precision']:.3f}")

    Path(args.out).write_text(json.dumps({
        "experiment": "fusion policy selection",
        "selection_metric": args.select_on,
        "selected_on": "validation split carved from the training portion",
        "reported_on": "held-out test split, untouched by training or selection",
        "writes_to_artifacts": False,
        "n_validation": int(len(yv)), "n_test": int(len(yt)),
        "validation": validation, "selected_policy": winner, "test": test,
    }, indent=2), encoding="utf-8")
    print("written:", args.out)


if __name__ == "__main__":
    main()
