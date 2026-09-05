"""The ML Prediction Engine -- iterate the registry, collect decisions.

    predict_all(validated=...)  ->  MLPredictionData  ->  Module 15  ->  16

Framework-independent: no FastAPI, no I/O beyond loading a cached artifact, no
global state other than the default registry (which can be overridden per
call). Module 15 imports and calls this exactly as it calls
`evaluate_rules()`.

==========================================================================
THE ENGINE KNOWS NOTHING ABOUT ANY PARTICULAR PREDICTOR
==========================================================================

The entire dispatch is::

    for predictor in registry:
        decisions.append(predictor.predict(values, context=context))

There is no `if predictor.name == "diabetes_rf"` anywhere in this file, and
there never should be. That is what makes Modules 11 and 12 a one-line change
in `app/ml/registry.py` -- and `tests/test_ml_registry.py` proves it by running
this engine over a fake predictor for a condition that does not exist yet.

A predictor that raises is CONTAINED, not propagated: one broken model must not
take down the analysis of every other condition. The failure becomes a warning
plus an INSUFFICIENT_DATA decision, which carries `risk=None` and therefore
cannot be mistaken for a clean result.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger, safe_meta
from app.data import conditions as C
from app.ml.base import (
    ML_MODULE,
    STAGE_ML,
    Predictor,
    SufficiencyReport,
    highest_risk,
)
from app.ml.features import INPUT_NONE, build_feature_bundle
from app.ml.registry import PredictorRegistry, default_registry
from app.schemas.decisions import ClinicalDecision, DecisionStatus
from app.schemas.features import StageWarning
from app.schemas.ml import (
    MLPredictionData,
    MLPredictionSummary,
    PredictorRunSummary,
)

logger = get_logger(__name__)

#: Bumped when the ENGINE's behaviour changes, independently of any model.
ML_ENGINE_VERSION = "1.0.0"

ML_ENGINE_POLICY = (
    "Condition-specific predictors are registered dynamically and iterated. A "
    "predictor lacking its required inputs returns INSUFFICIENT_DATA with "
    "risk=None rather than predicting on imputed defaults, and a value the "
    "patient never supplied is never encoded as a negative finding. Every "
    "decision that ran carries the model's probability of the positive class "
    "as its confidence. Recommendations come only from the reviewed "
    "catalogue, by code."
)


def predict_all(
    validated: Any = None,
    *,
    engineered: Any = None,
    registry: Optional[PredictorRegistry] = None,
) -> MLPredictionData:
    """Run every registered predictor and return `ClinicalDecision[]`.

    `validated` -- Module 6's `FeatureValidationData`, a `ValidatedFeaturesInput`
    or the equivalent dict. PREFERRED.

    `engineered` -- Module 5's `FeatureEngineeringData` or the equivalent dict.
    Passed through `validate_features()` in-process first, so a model still
    only ever sees validated values and no plausibility logic is duplicated.

    `registry` -- defaults to the process registry. Tests and Module 15 may
    pass their own.

    When both feature inputs are given, `validated` wins.
    """
    registry = registry if registry is not None else default_registry()
    bundle = build_feature_bundle(validated, engineered=engineered)
    context = bundle.context()

    warnings: List[str] = list(bundle.warnings)
    ranked: List[Tuple[int, int, ClinicalDecision]] = []
    runs: List[PredictorRunSummary] = []

    for index, predictor in enumerate(registry):
        decision, run = _run_one(predictor, bundle.values, context, warnings)
        runs.append(run)
        ranked.append((C.condition_rank(predictor.condition), index, decision))

    ranked.sort(key=lambda item: (item[0], item[1]))
    decisions = [decision for _, _, decision in ranked]

    if not registry:
        warnings.append(
            "no ML predictors are registered, so no machine-learning decision "
            "was produced"
        )
    if not bundle.values and bundle.input_kind != INPUT_NONE:
        warnings.append(
            "no usable features were supplied, so every predictor reported "
            "insufficient information"
        )
    if bundle.partial_document:
        warnings.append(
            "the source document was only partially readable, so a predictor "
            "that reported insufficient information may be missing a value the "
            "report actually contained"
        )

    all_warnings = list(bundle.upstream_warnings) + [
        StageWarning(stage=STAGE_ML, module=ML_MODULE, message=message)
        for message in warnings
    ]

    return MLPredictionData(
        decisions=decisions,
        warnings=warnings,
        upstream_warnings=bundle.upstream_warnings,
        all_warnings=all_warnings,
        upstream=bundle.upstream,
        upstream_summary=bundle.upstream_summary,
        summary=_summarise(decisions, runs, bundle),
        metadata={
            "engine_version": ML_ENGINE_VERSION,
            "policy": ML_ENGINE_POLICY,
            "predictors_registered": [p.name for p in registry],
            "conditions_covered": list(registry.conditions()),
            "input_kind": bundle.input_kind,
        },
    )


def _run_one(
    predictor: Predictor,
    values: Dict[str, Any],
    context,
    warnings: List[str],
) -> Tuple[ClinicalDecision, PredictorRunSummary]:
    """One predictor, with its failure contained."""
    report = predictor.check_sufficiency(values)
    try:
        decision = predictor.predict(values, context=context)
    except Exception as exc:  # noqa: BLE001 - contained deliberately
        # Type only in the log. A model exception message can echo input values,
        # which are medical data and must never reach the logs.
        logger.error(
            "predictor_failed %s",
            safe_meta(predictor=predictor.name, error_type=type(exc).__name__),
        )
        warnings.append(
            f"the {predictor.name} predictor could not complete, so no "
            f"machine-learning decision was produced for {predictor.condition}"
        )
        decision = predictor.insufficient_decision(
            SufficiencyReport(
                sufficient=False,
                required=tuple(predictor.required_features),
                present=(),
                missing=tuple(report.missing) or tuple(predictor.required_features),
                reason="predictor_error",
            ),
            context,
            extra_metadata={
                "predictor_error": True,
                "predictor_error_type": type(exc).__name__,
            },
        )

    assessed = decision.status is not DecisionStatus.INSUFFICIENT_DATA
    if not assessed and not predictor.is_available():
        warnings.append(
            f"the {predictor.name} model artifact is not available, so "
            f"{predictor.condition} was not assessed by machine learning"
        )

    run = PredictorRunSummary(
        name=predictor.name,
        condition=predictor.condition,
        source=predictor.source_label,
        version=predictor.version,
        available=predictor.is_available(),
        assessed=assessed,
        skipped_reason=(
            None if assessed else str(decision.metadata.get("skipped_reason") or "")
            or None
        ),
        required_features=list(predictor.required_features),
        required_missing=list(report.missing),
        probability_positive=(
            decision.metadata.get("probability_positive") if assessed else None
        ),
    )
    return decision, run


def _summarise(
    decisions: List[ClinicalDecision],
    runs: List[PredictorRunSummary],
    bundle,
) -> MLPredictionSummary:
    used: List[str] = []
    for decision in decisions:
        for name in decision.metadata.get("features_observed", ()):
            if name not in used:
                used.append(name)
    return MLPredictionSummary(
        decision_count=len(decisions),
        flagged_count=sum(1 for d in decisions if d.is_flagged),
        indicated_count=sum(
            1 for d in decisions if d.status is DecisionStatus.INDICATED
        ),
        borderline_count=sum(
            1 for d in decisions if d.status is DecisionStatus.BORDERLINE
        ),
        not_indicated_count=sum(
            1 for d in decisions if d.status is DecisionStatus.NOT_INDICATED
        ),
        insufficient_data_count=sum(1 for d in decisions if not d.was_assessed),
        # RiskLevel.highest() returns None for an empty list, so "nothing
        # assessed" never silently becomes "Low".
        highest_risk=highest_risk(decisions),
        predictors_registered=len(runs),
        predictors_run=sum(1 for r in runs if r.assessed),
        predictors_skipped=sum(1 for r in runs if not r.assessed),
        conditions_assessed=sorted(
            {d.condition for d in decisions if d.was_assessed}, key=C.condition_rank
        ),
        conditions_flagged=sorted(
            {d.condition for d in decisions if d.is_flagged}, key=C.condition_rank
        ),
        features_used=used,
        questionable_features_used=[n for n in used if n in bundle.questionable],
        partial_document=bundle.partial_document,
        input_kind=bundle.input_kind,
        predictor_runs=runs,
    )


__all__ = ["ML_ENGINE_POLICY", "ML_ENGINE_VERSION", "predict_all"]
