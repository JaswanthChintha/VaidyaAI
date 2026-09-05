"""What a model actually achieves AT THE THRESHOLD IT USES.

ONE code path for all three predictors, because this exact thing has now gone
wrong twice in the same way and the second time was caused by fixing the first
one model at a time.

--------------------------------------------------------------------------
WHY THIS FILE EXISTS
--------------------------------------------------------------------------

`ModelLimitations.recall_at_operating_threshold` is described on its own schema
as "the single most important number on this object", because a model's
discrimination (ROC-AUC) says nothing about how much it MISSES at the cut-off
it actually applies. Module 11 flags roughly 27% of true positives: an
unflagged heart result from it rules nothing out, and a clinician who reads a
low probability as reassurance has been misled.

Twice, that number failed to reach the document:

  6o D8   `app/ml/heart.py` published only `{borderline, indicated}`, so the
          recall its artifact recorded never left the artifact and the
          "rules nothing out" caveat could never fire.
  6p      The fix carried `indicated_recall_achieved` for heart and kidney and
          stopped there, on the stated grounds that "Module 10's artifact does
          not record it". THAT WAS FALSE. Module 10 records recall AND
          precision AND accuracy AND the majority-class baseline; it simply
          records them under `metrics.positive_class` rather than under
          `thresholds`. So the diabetes model went on reporting a probability
          against a 0.795 cut-off with no statement that it catches ~70% of
          true positives and lifts accuracy 5.6 points over a 91% baseline --
          with `metrics_available: True` and no absent-code, so nothing
          signalled the gap.

Both failures were per-model reasoning about a cross-model question. Hence one
reader, used by all three, that knows every place an artifact may put these
numbers.

--------------------------------------------------------------------------
THE RULE THAT MAKES THE FALLBACK SAFE
--------------------------------------------------------------------------

`metrics.positive_class.{precision,recall}` are measured at
`metrics.decision_threshold`, which is NOT necessarily the threshold the
service applies. Reading them as "at the operating threshold" is therefore
only legitimate when those two thresholds are the same number -- and in every
shipped artifact they are, because the metrics block is computed at the
selected cut-off. When they diverge, the numbers describe a DIFFERENT
operating point and are refused: a precision measured at 0.5 presented as the
precision at 0.795 would be a fabricated performance claim in a clinician-
facing document, which is the worst version of "absence became a value".

`thresholds.indicated_*_achieved`, where an artifact publishes it, is
preferred: it is the out-of-fold estimate the threshold was SELECTED on, and
it is what the selection procedure itself reported.

A number that is absent stays absent. Nothing here interpolates, substitutes
across variants, or borrows from another model.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional

#: Two thresholds are "the same cut-off" within this tolerance. They are read
#: from one artifact and are normally bit-identical; the tolerance exists so a
#: JSON round-trip cannot silently turn a match into a refusal.
THRESHOLD_MATCH_TOLERANCE = 1e-9


def _finite(value: Any) -> Optional[float]:
    """`float(value)` when it is a real, finite number -- otherwise None.

    `bool` is excluded deliberately: `True` is an `int` in Python and a
    performance figure of 1.0 conjured from a flag would be both wrong and
    very hard to spot.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def operating_metrics(spec: Mapping[str, Any]) -> dict:
    """The achieved figures at the Indicated threshold, for one variant.

    `spec` is one entry of the artifact's `variants` map. Returns only the keys
    it could establish, so a caller can `**`-merge it into a thresholds dict
    without ever writing a null. An artifact that records nothing yields `{}`.
    """
    thresholds = _mapping(spec.get("thresholds"))
    metrics = _mapping(spec.get("metrics"))

    indicated = _finite(thresholds.get("indicated"))

    # 1. What the threshold-selection procedure itself reported, where the
    #    artifact publishes it. This is the primary source: it is the number
    #    the cut-off was chosen against.
    recall = _finite(thresholds.get("indicated_recall_achieved"))
    precision = _finite(thresholds.get("indicated_precision_achieved"))

    # 2. Otherwise the held-out test figures -- but ONLY if they were measured
    #    at this very threshold. See the module docstring.
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
    """Accuracy and its baseline, for one variant.

    Accuracy alone is close to meaningless on an imbalanced set -- Module 10's
    0.968 sits against a 0.912 majority-class baseline, a lift of 5.6 points --
    so the two are read together and either both are carried or the one that is
    present is carried alone and the other stays absent. They are NOT derived
    from each other.
    """
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
