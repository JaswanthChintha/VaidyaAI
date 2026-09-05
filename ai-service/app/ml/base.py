"""The predictor interface every ML predictor implements (spec Modules 9, 12).

Modules 11 (Heart) and 12 (Kidney) subclass `Predictor` and implement ONE
method, `_predict`. Everything that makes a predictor safe -- the information
sufficiency check, the `INSUFFICIENT_DATA` skip, the canonical-condition
check, and the `ClinicalDecision` invariant checks -- lives here and is
inherited, not re-implemented.

==========================================================================
WHY `predict()` IS A TEMPLATE METHOD AND NOT ABSTRACT
==========================================================================

`predict()` is CONCRETE and subclasses must not override it. It:

    1. runs `check_sufficiency()`
    2. RETURNS an INSUFFICIENT_DATA decision itself when inputs are missing --
       the subclass is never even called
    3. otherwise calls the subclass's `_predict()`
    4. then AUDITS what came back

Spec Module 12: "If insufficient kidney-related information is available, the
predictor can skip the prediction rather than blindly producing a result...
a machine-learning model trained using multiple parameters should not
automatically be interpreted as equally reliable when only a small subset of
those parameters is available."

If that check were left to each subclass, a future predictor would eventually
forget it and would silently predict on median-imputed defaults. Structuring it
as a template method means the ONLY way to reach a model is through the
sufficiency gate. A subclass author cannot opt out by omission -- only by
deliberately overriding a method the ABC documents as final, which is a
reviewable act rather than an oversight.

Step 4 matters just as much. `app/schemas/decisions.py` enforces its own
invariants, but it cannot know that THIS predictor was supposed to emit
"Diabetes" rather than "diabetes", or that a predictor registered as ML must
not return a `CLINICAL_RULE` decision. The audit closes that gap, so a
Module 11/12 author gets a loud failure instead of a decision that quietly
never fuses in Module 16.
"""

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

#: The stage identifier the ML layer stamps on its own warnings, matching
#: `STAGE_RULES = "rules"` in `app/schemas/rules.py`.
STAGE_ML = "ml"
ML_MODULE = 9


class PredictorError(RuntimeError):
    """A predictor is misconfigured or broke its own output contract."""


# --------------------------------------------------------------------------
# Fixed, user-facing note fragments
# --------------------------------------------------------------------------
#
# These reach a reader through Module 20, so their wording is fixed here rather
# than formatted from arbitrary strings, and `tests/` scans every one of them
# with the recommendation catalogue's safety scanner -- the same treatment
# Module 8 gives its own note fragments.

NOTE_NOT_AVAILABLE = "this value was not available in the submitted report"
NOTE_REQUIRED_MISSING = (
    "the model needs this value and it was not available, so no prediction was "
    "made"
)
NOTE_UNREADABLE = (
    "part of the document could not be read, so this value may be missing "
    "rather than absent from the report"
)

#: Machine-readable skip reasons. `skipped_reason` in decision metadata holds
#: one of these; Module 17's `_explain_ml` renders it.
REASON_REQUIRED_MISSING = "required_features_missing"
REASON_REQUIRED_IMPUTED = "required_features_not_measured"
REASON_MODEL_UNAVAILABLE = "model_unavailable"

BASE_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_NOT_AVAILABLE,
    NOTE_REQUIRED_MISSING,
    NOTE_UNREADABLE,
)


# --------------------------------------------------------------------------
# Information sufficiency
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SufficiencyReport:
    """The outcome of the information-sufficiency check (spec Module 12).

    Frozen and structured rather than a bare bool so that the reason a
    predictor skipped survives into the decision's metadata and can be shown to
    a reader ("this needs HbA1c and it was not in the report") instead of the
    topic simply vanishing from the output.
    """

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


# --------------------------------------------------------------------------
# Prediction context
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PredictionContext:
    """Everything a predictor may know BESIDES the feature values.

    Kept separate from the value map so that `predict(features)` stays a plain
    "give me the numbers" call for direct callers and tests, while the HTTP
    path can still pass the document-quality signals a decision needs to be
    honest about itself.
    """

    #: Features Module 6 marked `questionable` (assumed unit, censored value,
    #: low extraction confidence). Usable, but the decision should say so.
    questionable: frozenset = frozenset()
    #: Features Module 6 marked `clinically_extreme`. TRUST, not doubt.
    clinically_extreme: frozenset = frozenset()
    #: Canonical units, by feature name, as Module 5/6 resolved them.
    units: Mapping[str, Optional[str]] = None  # type: ignore[assignment]
    #: Module 4 could not read part of the source document. An absent feature
    #: may then mean UNREAD rather than not-present.
    partial_document: bool = False

    def unit_for(self, feature: str) -> Optional[str]:
        if not self.units:
            return None
        return self.units.get(feature)


EMPTY_CONTEXT = PredictionContext()


# --------------------------------------------------------------------------
# The interface
# --------------------------------------------------------------------------


class Predictor(abc.ABC):
    """A condition-specific ML predictor (spec Module 9).

    A subclass declares four things and implements one method::

        class KidneyPredictor(Predictor):
            name = "kidney_rf"
            condition = C.KIDNEY_DISEASE          # byte-for-byte canonical
            source_label = "Random Forest"
            required_features = ("creatinine",)
            optional_features = ("age", "hemoglobin", "hypertension")

            def _predict(self, features, context):
                ...
                return ClinicalDecision(...)

    `_predict` is only ever reached with every `required_features` entry
    present, so it never has to defend itself against an empty input map.
    """

    #: Stable machine identifier, unique within a registry. Used as the
    #: registry key and recorded in decision metadata.
    name: str = ""

    #: MUST be a constant imported from `app/data/conditions.py`. Module 16
    #: groups decisions by this exact string; a private spelling silently
    #: prevents fusion with the rule engine's decision about the same topic.
    condition: str = ""

    #: Human-readable producer, e.g. "Random Forest". Becomes
    #: `ClinicalDecision.source`.
    source_label: str = "Machine Learning Model"

    #: Without ALL of these the predictor SKIPS. See the class docstring.
    required_features: Tuple[str, ...] = ()

    #: Used when present, imputed or omitted when not. Never a reason to skip.
    optional_features: Tuple[str, ...] = ()

    #: Bumped by the subclass when its behaviour changes.
    version: str = "1.0.0"

    # -- construction-time self-check -------------------------------------

    def __init__(self) -> None:
        if not str(self.name).strip():
            raise PredictorError(f"{type(self).__name__}: `name` must be set")
        if not C.is_canonical_condition(self.condition):
            # The single most valuable check in this file. A drifted condition
            # string breaks Module 16 SILENTLY -- nothing raises, the user just
            # sees two unfused cards -- so it is turned into a loud failure at
            # construction time.
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

    # -- introspection ----------------------------------------------------

    @property
    def features_used(self) -> Tuple[str, ...]:
        return tuple(self.required_features) + tuple(self.optional_features)

    def describe(self) -> Dict[str, Any]:
        """Registry-introspection payload. No PHI, no values -- shape only."""
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
            # Integration audit D3, operator-facing half. A predictor backed by
            # a persisted artifact reports whether that artifact still matches
            # the metrics document its thresholds and published numbers come
            # from, so a substituted joblib is visible from the introspection
            # endpoint and not only from a decision's metadata.
            "artifact_integrity": self.artifact_integrity(),
        }

    def artifact_integrity(self) -> Dict[str, Any]:
        """The artifact<->metrics digest check. `{}` for a predictor with none."""
        return {}

    def is_available(self) -> bool:
        """False when the predictor cannot run at all (e.g. missing artifact).

        Default True. A predictor backed by a persisted model overrides this so
        a deployment mistake is visible through the introspection endpoint
        instead of only showing up as every patient getting INSUFFICIENT_DATA.
        """
        return True

    def unavailable_reason(self) -> Optional[str]:
        return None

    # -- sufficiency ------------------------------------------------------

    @staticmethod
    def _is_present(value: Any, feature: Optional[str] = None) -> bool:
        """A feature counts as present only when it carries a USABLE value.

        `None` is absent. An empty/whitespace string is absent. `False` and
        `0` and `0.0` are PRESENT -- an explicit "no" is information, and
        collapsing it into absence is the same class of bug as collapsing
        absence into "no".

        TYPE AWARENESS (integration audit D1). When `feature` names a
        catalogued feature, the value is additionally checked against that
        feature's DECLARED `value_type` in `app/data/feature_catalog.py`.
        Without that check the gate answered a different question from the one
        it exists to ask: `"Negative"` is not None, so creatinine counted as
        present, the sufficiency gate passed, and the pipeline's numeric
        imputer then median-filled creatinine from the training cohort. The
        model would report `Indicated / High / 0.99` for a patient whose
        creatinine was never measured -- the precise outcome Module 12's skip
        exists to prevent.

        So: a numeric feature needs a real, finite number (never a `bool`,
        never `NaN`, never `inf`, never `"1.2 mg/dL"`); a boolean feature needs
        a real `bool`, matching the tri-state rule that an unparsed token means
        "the patient never said"; a categorical feature needs a value that
        normalises to a recognised category.

        `feature` is optional so that the loose, type-agnostic form remains
        available to callers that genuinely have no feature name in hand.
        """
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if feature is None:
            return True
        return catalog_is_valid_value(feature, value)

    def check_sufficiency(self, features: Mapping[str, Any]) -> SufficiencyReport:
        """Default rule: every `required_features` entry must be present.

        Overridable for a predictor whose rule is genuinely different (e.g.
        "any two of these four"). An override must still return a
        `SufficiencyReport`; `predict()` acts on `sufficient` either way.
        """
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

    # -- the template method ----------------------------------------------

    def predict(
        self,
        features: Mapping[str, Any],
        *,
        context: Optional[PredictionContext] = None,
    ) -> ClinicalDecision:
        """Produce exactly one `ClinicalDecision`. DO NOT OVERRIDE.

        Subclasses implement `_predict`. See the module docstring for why the
        sufficiency gate and the output audit live here instead.
        """
        context = context or EMPTY_CONTEXT
        values = dict(features or {})

        if not self.is_available():
            return self._unavailable_decision(values, context)

        report = self.check_sufficiency(values)
        if not report.sufficient:
            return self.insufficient_decision(report, context)

        decision = self._predict(values, context)
        self._audit(decision)

        # BELT AND BRACES (integration audit D1, second layer). The gate above
        # asks whether the CALLER supplied each required input. This asks the
        # only question that actually matters: did the MODEL receive it? Every
        # predictor already records, per feature, whether the value reached the
        # pipeline (`observed`/`banded`) or was left to the median imputer
        # (`imputed`) or excluded from the matrix (`not_asserted`). Comparing
        # that record against `required_features` costs nothing and catches any
        # future path -- a new value type, a new column mapping, a subclass
        # that reads a feature under a different name -- by which a required
        # input could silently become a cohort median.
        substituted = self._required_but_not_measured(decision)
        if substituted:
            return self._substituted_input_decision(substituted, context)
        return decision

    # -- the post-vector assertion ----------------------------------------

    def _required_but_not_measured(self, decision: ClinicalDecision) -> Tuple[str, ...]:
        """Required features the model did NOT receive a measured value for.

        Read off the decision's own trace metadata rather than recomputed, so
        what this checks and what the decision claims cannot drift apart.
        """
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
        """Skip, loudly, because a required input reached the model imputed.

        Reached only when `_predict` produced a real prediction whose own trace
        shows a required feature was median-filled or excluded. The prediction
        is DISCARDED rather than published with a caveat: its probability was
        computed from a stand-in for the value the reader will assume was
        measured, and no caveat undoes a number.
        """
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
        """Run the model. Reached only when sufficiency passed.

        MUST return a `ClinicalDecision` with `condition == self.condition`,
        `source_kind = MACHINE_LEARNING` and a non-None `confidence`. `predict`
        checks all three.
        """

    # -- the skip ---------------------------------------------------------

    def insufficient_decision(
        self,
        report: SufficiencyReport,
        context: Optional[PredictionContext] = None,
        *,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ClinicalDecision:
        """The INSUFFICIENT_DATA decision every predictor skips with.

        `risk=None` is required by `decisions.py` and is the whole point: a
        topic that could not be assessed must never render as a reassuring
        "Low". `confidence=None` is likewise correct and is the one case
        `decisions.py` permits for an ML decision -- no model ran, so there is
        no probability, and 0.0 would be a lie about a model that never
        executed.

        Emitting a decision at all, rather than staying silent, is deliberate:
        `app/data/conditions.py` marks the three fusion conditions
        `always_assessed` precisely so Module 16 can tell "not assessed" from
        "assessed and nothing found".
        """
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
        """A predictor whose model could not be loaded still says something.

        It reports INSUFFICIENT_DATA -- risk=None, confidence=None -- because
        that is the only honest status: nothing was assessed. The distinct
        `skipped_reason` keeps a deployment fault from being mistaken for a
        thin report, and `is_available()` surfaces it on the introspection
        endpoint too.
        """
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

    # -- the audit --------------------------------------------------------

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
            # decisions.py already forbids this, so reaching here means the
            # object was built by some path that bypassed validation.
            raise PredictorError(
                f"{type(self).__name__} emitted an assessed ML decision with "
                "confidence=None"
            )

    # -- niceties ---------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} name={self.name!r} condition={self.condition!r}>"


def highest_risk(decisions: Sequence[ClinicalDecision]) -> Optional[RiskLevel]:
    """Convenience wrapper over `RiskLevel.highest`, used by the engine summary."""
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
