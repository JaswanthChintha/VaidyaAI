from __future__ import annotations

import math
from typing import Any, Mapping, Optional

THRESHOLD_MATCH_TOLERANCE = 1e-9


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def operating_metrics(spec: Mapping[str, Any]) -> dict:
    thresholds = _mapping(spec.get("thresholds"))
    metrics = _mapping(spec.get("metrics"))

    indicated = _finite(thresholds.get("indicated"))

    recall = _finite(thresholds.get("indicated_recall_achieved"))
    precision = _finite(thresholds.get("indicated_precision_achieved"))

    measured_at = _finite(metrics.get("decision_threshold"))
    same_cut_off = (
        indicated is not None
        and measured_at is not None
        and abs(indicated - measured_at) <= THRESHOLD_MATCH_TOLERANCE
    )
    if same_cut_off:
        positive = _mapping(metrics.get("positive_class"))
        if recall is None:
            recall = _finite(positive.get("recall"))
        if precision is None:
            precision = _finite(positive.get("precision"))

    out: dict = {}
    if recall is not None:
        out["indicated_recall_achieved"] = recall
    if precision is not None:
        out["indicated_precision_achieved"] = precision
    return out


def performance_figures(spec: Mapping[str, Any]) -> dict:
    metrics = _mapping(spec.get("metrics"))
    out: dict = {}
    accuracy = _finite(metrics.get("accuracy"))
    baseline = _finite(metrics.get("majority_class_baseline_accuracy"))
    if accuracy is not None:
        out["accuracy"] = accuracy
    if baseline is not None:
        out["majority_class_baseline_accuracy"] = baseline
    return out


__all__ = [
    "THRESHOLD_MATCH_TOLERANCE",
    "operating_metrics",
    "performance_figures",
]
