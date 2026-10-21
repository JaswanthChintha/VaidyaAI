from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.data.feature_catalog import FEATURES
from app.ml.base import PredictionContext
from app.schemas.features import StageWarning, UpstreamExtraction
from app.schemas.rules import ValidatedFeaturesInput
from app.schemas.validation import (
    STAGE_VALIDATION,
    FeatureValidationSummary,
)
from app.services.validator import validate_features

INPUT_VALIDATED = "validated"
INPUT_ENGINEERED = "engineered"
INPUT_NONE = "none"


@dataclass
class FeatureBundle:

    values: Dict[str, Any] = field(default_factory=dict)
    units: Dict[str, Optional[str]] = field(default_factory=dict)
    questionable: Tuple[str, ...] = ()
    clinically_extreme: Tuple[str, ...] = ()
    missing_features: List[str] = field(default_factory=list)
    partial_document: bool = False
    input_kind: str = INPUT_NONE
    upstream_warnings: List[StageWarning] = field(default_factory=list)
    upstream: UpstreamExtraction = field(default_factory=UpstreamExtraction)
    upstream_summary: FeatureValidationSummary = field(
        default_factory=FeatureValidationSummary
    )
    warnings: List[str] = field(default_factory=list)

    def context(self) -> PredictionContext:
        return PredictionContext(
            questionable=frozenset(self.questionable),
            clinically_extreme=frozenset(self.clinically_extreme),
            units=dict(self.units),
            partial_document=self.partial_document,
        )


def _coerce_validated(source: Any) -> Optional[ValidatedFeaturesInput]:
    if source is None:
        return None
    if isinstance(source, ValidatedFeaturesInput):
        return source
    if hasattr(source, "model_dump"):
        return ValidatedFeaturesInput.model_validate(source.model_dump())
    if isinstance(source, dict):
        return ValidatedFeaturesInput.model_validate(source)
    return ValidatedFeaturesInput.model_validate(source)


def _carried_warnings(data: ValidatedFeaturesInput) -> List[StageWarning]:
    if data.all_warnings:
        return list(data.all_warnings)
    rebuilt: List[StageWarning] = list(data.upstream_warnings)
    seen = {(w.stage, w.message) for w in rebuilt}
    for message in data.warnings:
        key = (STAGE_VALIDATION, message)
        if key not in seen:
            seen.add(key)
            rebuilt.append(
                StageWarning(stage=STAGE_VALIDATION, module=6, message=message)
            )
    return rebuilt


def build_feature_bundle(
    validated: Any = None, *, engineered: Any = None
) -> FeatureBundle:
    input_kind = INPUT_NONE
    data = _coerce_validated(validated)
    if data is not None:
        input_kind = INPUT_VALIDATED
    elif engineered is not None:
        data = _coerce_validated(validate_features(engineered))
        input_kind = INPUT_ENGINEERED
    else:
        data = ValidatedFeaturesInput()

    bundle = FeatureBundle(
        input_kind=input_kind,
        missing_features=list(data.missing_features),
        partial_document=bool(data.upstream.pages_unreadable),
        upstream_warnings=_carried_warnings(data),
        upstream=data.upstream,
        upstream_summary=data.summary,
    )

    questionable: List[str] = []
    extreme: List[str] = []
    for name, incoming in data.valid.items():
        if name not in FEATURES:
            bundle.warnings.append(
                f"'{name}' is not a canonical feature and was ignored by the ML "
                "prediction engine"
            )
            continue
        bundle.values[name] = incoming.value
        definition = FEATURES.get(name)
        bundle.units[name] = (
            definition.canonical_unit if definition else incoming.unit
        )
        if incoming.questionable:
            questionable.append(name)
        if incoming.clinically_extreme:
            extreme.append(name)

    bundle.questionable = tuple(questionable)
    bundle.clinically_extreme = tuple(extreme)
    return bundle


__all__ = [
    "INPUT_ENGINEERED",
    "INPUT_NONE",
    "INPUT_VALIDATED",
    "FeatureBundle",
    "build_feature_bundle",
]
