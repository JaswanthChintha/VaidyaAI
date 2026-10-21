from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from app.data import conditions as C
from app.data.feature_catalog import is_valid_value as catalog_is_valid_value
from app.data.recommendation_catalog import (
    INFORMATION_INCOMPLETE,
    NOT_A_DIAGNOSIS,
    UNREADABLE_DOCUMENT_RECHECK,
    recommendations as resolve_recommendations,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)

STAGE_ML = "ml"
ML_MODULE = 9


class PredictorError(RuntimeError):
    pass


NOTE_NOT_AVAILABLE = "this value was not available in the submitted report"
NOTE_REQUIRED_MISSING = (
    "the model needs this value and it was not available, so no prediction was "
    "made"
)
NOTE_UNREADABLE = (
    "part of the document could not be read, so this value may be missing "
    "rather than absent from the report"
)

REASON_REQUIRED_MISSING = "required_features_missing"
REASON_REQUIRED_IMPUTED = "required_features_not_measured"
REASON_MODEL_UNAVAILABLE = "model_unavailable"

BASE_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_NOT_AVAILABLE,
    NOTE_REQUIRED_MISSING,
    NOTE_UNREADABLE,
)


@dataclass(frozen=True)
class SufficiencyReport:

    sufficient: bool
    required: Tuple[str, ...]
    present: Tuple[str, ...]
    missing: Tuple[str, ...]
    optional_present: Tuple[str, ...] = ()
    optional_missing: Tuple[str, ...] = ()
    reason: Optional[str] = None

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "required_features": list(self.required),
            "required_present": list(self.present),
            "required_missing": list(self.missing),
            "optional_present": list(self.optional_present),
            "optional_missing": list(self.optional_missing),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PredictionContext:

    questionable: frozenset = frozenset()
    clinically_extreme: frozenset = frozenset()
    units: Mapping[str, Optional[str]] = None
    partial_document: bool = False

    def unit_for(self, feature: str) -> Optional[str]:
        if not self.units:
            return None
        return self.units.get(feature)


EMPTY_CONTEXT = PredictionContext()


class Predictor(abc.ABC):

    name: str = ""

    condition: str = ""

    source_label: str = "Machine Learning Model"

    required_features: Tuple[str, ...] = ()

    optional_features: Tuple[str, ...] = ()

    version: str = "1.0.0"


    def __init__(self) -> None:
        if not str(self.name).strip():
            raise PredictorError(f"{type(self).__name__}: `name` must be set")
        if not C.is_canonical_condition(self.condition):
            raise PredictorError(
                f"{type(self).__name__}: condition {self.condition!r} is not in "
                "app/data/conditions.py. Import the constant; do not spell it "
                "out. Module 16 groups by this exact string."
            )
        if not self.required_features:
            raise PredictorError(
                f"{type(self).__name__}: `required_features` is empty, so the "
                "information-sufficiency check (spec Module 12) can never "
                "refuse. A predictor that can never skip will happily predict "
                "on nothing but imputed defaults."
            )
        overlap = set(self.required_features) & set(self.optional_features)
        if overlap:
            raise PredictorError(
                f"{type(self).__name__}: {sorted(overlap)} listed as both "
                "required and optional"
            )


    @property
    def features_used(self) -> Tuple[str, ...]:
        return tuple(self.required_features) + tuple(self.optional_features)

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "condition": self.condition,
            "source": self.source_label,
            "source_kind": DecisionSourceKind.MACHINE_LEARNING.value,
            "version": self.version,
            "required_features": list(self.required_features),
            "optional_features": list(self.optional_features),
            "available": self.is_available(),
            "unavailable_reason": self.unavailable_reason(),
            "artifact_integrity": self.artifact_integrity(),
        }

    def artifact_integrity(self) -> Dict[str, Any]:
        return {}

    def is_available(self) -> bool:
        return True

    def unavailable_reason(self) -> Optional[str]:
        return None


    @staticmethod
    def _is_present(value: Any, feature: Optional[str] = None) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if feature is None:
            return True
        return catalog_is_valid_value(feature, value)

    def check_sufficiency(self, features: Mapping[str, Any]) -> SufficiencyReport:
        present = tuple(
            name for name in self.required_features
            if self._is_present(features.get(name), name)
        )
        missing = tuple(
            name for name in self.required_features if name not in present
        )
        optional_present = tuple(
            name for name in self.optional_features
            if self._is_present(features.get(name), name)
        )
        optional_missing = tuple(
            name for name in self.optional_features if name not in optional_present
        )
        return SufficiencyReport(
            sufficient=not missing,
            required=tuple(self.required_features),
            present=present,
            missing=missing,
            optional_present=optional_present,
            optional_missing=optional_missing,
            reason=None if not missing else REASON_REQUIRED_MISSING,
        )


    def predict(
        self,
        features: Mapping[str, Any],
        *,
        context: Optional[PredictionContext] = None,
    ) -> ClinicalDecision:
        context = context or EMPTY_CONTEXT
        values = dict(features or {})

        if not self.is_available():
            return self._unavailable_decision(values, context)

        report = self.check_sufficiency(values)
        if not report.sufficient:
            return self.insufficient_decision(report, context)

        decision = self._predict(values, context)
        self._audit(decision)

        substituted = self._required_but_not_measured(decision)
        if substituted:
            return self._substituted_input_decision(substituted, context)
        return decision


    def _required_but_not_measured(self, decision: ClinicalDecision) -> Tuple[str, ...]:
        metadata = decision.metadata or {}
        if decision.status is DecisionStatus.INSUFFICIENT_DATA:
            return ()
        not_measured = set()
        for key in ("features_imputed", "features_not_asserted"):
            entries = metadata.get(key)
            if isinstance(entries, (list, tuple, set, frozenset)):
                not_measured.update(str(n) for n in entries)
        return tuple(
            name for name in self.required_features if name in not_measured
        )

    def _substituted_input_decision(
        self, substituted: Sequence[str], context: PredictionContext
    ) -> ClinicalDecision:
        substituted = tuple(substituted)
        report = SufficiencyReport(
            sufficient=False,
            required=tuple(self.required_features),
            present=tuple(
                n for n in self.required_features if n not in substituted
            ),
            missing=substituted,
            reason=REASON_REQUIRED_IMPUTED,
        )
        return self.insufficient_decision(
            report,
            context,
            extra_metadata={
                "required_features_substituted": list(substituted),
                "substitution_policy": (
                    "A required input did not reach the model as a measured "
                    "value; it would have been filled with a training-cohort "
                    "median. The prediction was discarded rather than reported."
                ),
            },
        )

    @abc.abstractmethod
    def _predict(
        self, features: Mapping[str, Any], context: PredictionContext
    ) -> ClinicalDecision:
        pass


    def insufficient_decision(
        self,
        report: SufficiencyReport,
        context: Optional[PredictionContext] = None,
        *,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ClinicalDecision:
        context = context or EMPTY_CONTEXT
        note = NOTE_UNREADABLE if context.partial_document else NOTE_NOT_AVAILABLE
        evidence = [
            EvidenceItem(
                feature=name,
                value=None,
                unit=context.unit_for(name),
                note=NOTE_REQUIRED_MISSING if not context.partial_document else note,
                source_stage="not_available",
            )
            for name in report.missing
        ]
        codes = (INFORMATION_INCOMPLETE,)
        if context.partial_document:
            codes += (UNREADABLE_DOCUMENT_RECHECK,)

        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": True,
            "skipped_reason": report.reason or "information_insufficient",
            "sufficiency": report.as_metadata(),
            "partial_document": context.partial_document,
            "policy": (
                "The model was NOT run. A prediction made from imputed "
                "stand-ins for its required inputs would not be as reliable as "
                "one made from the inputs it was trained on, and would not "
                "advertise the difference."
            ),
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        return ClinicalDecision(
            condition=self.condition,
            status=DecisionStatus.INSUFFICIENT_DATA,
            risk=None,
            confidence=None,
            source=self.source_label,
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            evidence=evidence,
            recommendations=resolve_recommendations(codes + (NOT_A_DIAGNOSIS,)),
            metadata=metadata,
        )

    def _unavailable_decision(
        self, features: Mapping[str, Any], context: PredictionContext
    ) -> ClinicalDecision:
        report = SufficiencyReport(
            sufficient=False,
            required=tuple(self.required_features),
            present=(),
            missing=tuple(self.required_features),
            reason=REASON_MODEL_UNAVAILABLE,
        )
        return self.insufficient_decision(
            report,
            context,
            extra_metadata={
                "model_unavailable": True,
                "model_unavailable_reason": self.unavailable_reason(),
            },
        )


    def _audit(self, decision: Any) -> None:
        if not isinstance(decision, ClinicalDecision):
            raise PredictorError(
                f"{type(self).__name__}._predict returned "
                f"{type(decision).__name__}, not a ClinicalDecision"
            )
        if decision.condition != self.condition:
            raise PredictorError(
                f"{type(self).__name__} emitted condition "
                f"{decision.condition!r} but is registered for "
                f"{self.condition!r}. Module 16 groups by this string, so the "
                "mismatch would prevent fusion without raising anything."
            )
        if decision.source_kind is not DecisionSourceKind.MACHINE_LEARNING:
            raise PredictorError(
                f"{type(self).__name__} emitted source_kind "
                f"{decision.source_kind.value!r}; an ML predictor must emit "
                f"{DecisionSourceKind.MACHINE_LEARNING.value!r}"
            )
        if (
            decision.status is not DecisionStatus.INSUFFICIENT_DATA
            and decision.confidence is None
        ):
            raise PredictorError(
                f"{type(self).__name__} emitted an assessed ML decision with "
                "confidence=None"
            )


    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} condition={self.condition!r}>"


def highest_risk(decisions: Sequence[ClinicalDecision]) -> Optional[RiskLevel]:
    return RiskLevel.highest([d.risk for d in decisions if d.risk is not None])


__all__ = [
    "BASE_NOTE_FRAGMENTS",
    "EMPTY_CONTEXT",
    "ML_MODULE",
    "NOTE_NOT_AVAILABLE",
    "NOTE_REQUIRED_MISSING",
    "NOTE_UNREADABLE",
    "STAGE_ML",
    "PredictionContext",
    "Predictor",
    "REASON_MODEL_UNAVAILABLE",
    "REASON_REQUIRED_IMPUTED",
    "REASON_REQUIRED_MISSING",
    "PredictorError",
    "SufficiencyReport",
    "highest_risk",
]
