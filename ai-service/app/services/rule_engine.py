"""Module 8 -- the Clinical Rule Engine.

Deterministic, transparent, threshold-based analysis. Every decision this
module emits is traceable to a threshold configured in
`app/data/clinical_rules.py`, and a clinician can audit that file without
reading a line of this one.

    Module 6 (validated features)  ->  Module 8  ->  ClinicalDecision[]
                                                     -> Module 15 -> Module 16

--------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO
--------------------------------------------------------------------------

No machine learning (Modules 9-12), no decision management (15), no fusion
(16), no feature storage (7), no retrieval, no LLM, no report generation. It
does not define a predictor registry. It compares numbers to thresholds and
explains itself.

--------------------------------------------------------------------------
THE FIVE INVARIANTS
--------------------------------------------------------------------------

1. RULES SEE ONLY `valid`. Module 6's `rejected` map is not even parsed -- see
   `app/schemas/rules.py`. A suspected extraction error can never reach a
   threshold comparison.

2. A RULE WITH NO INPUT DOES NOT FIRE. Absence never falls through to a
   "nothing found" verdict. Where a condition genuinely deserves to be
   mentioned anyway, an INSUFFICIENT_DATA decision is emitted -- which
   `decisions.py` forces to carry `risk=None`, so it cannot be mistaken for
   reassurance.

3. AN ABSENT TRI-STATE IS NEVER A NEGATIVE. `hypertension` and `heart_disease`
   are read only as POSITIVE risk factors, counted when the value is exactly
   `True`. Absent and `False` both simply fail to add a factor.

4. `clinically_extreme` IS TRUST, NOT DOUBT. It is carried into evidence and
   the summary as a prioritisation signal for Module 19. It never suppresses,
   discounts or re-weights a value.

5. NO UPSTREAM WARNING IS EVER DROPPED. Modules 4, 5 and 6 warnings are carried
   through with their origins intact and Module 8 appends its own under
   `stage="rules"`.

--------------------------------------------------------------------------
CONFIDENCE
--------------------------------------------------------------------------

Every decision carries `confidence=None`. Per `decisions.py`, that means "this
component produces no probability", which is exactly true of a threshold
comparison. It is NOT `0.0`, which would mean "a model ran and was maximally
unconfident" and would corrupt Module 16's confidence fusion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.data import conditions as C
from app.data.clinical_rules import (
    COMPARATORS,
    COMPOSITE_RULES,
    CONDITION_INPUTS,
    FACTOR_BOOLEAN_TRUE,
    FACTOR_CATEGORY,
    RULE_ENGINE_SOURCE,
    RULE_TABLE_VERSION,
    THRESHOLD_RULES,
    CompositeRule,
    ContextualThreshold,
    CountBand,
    RiskFactorDefinition,
    ThresholdRule,
    resolve_threshold,
    sample_timing,
)
from app.data.feature_catalog import FEATURES
from app.data.recommendation_catalog import (
    INFORMATION_INCOMPLETE,
    INPUT_QUALITY_CAVEAT,
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
from app.schemas.features import StageWarning
from app.schemas.rules import (
    RULES_MODULE,
    STAGE_RULES,
    RuleEvaluationData,
    RuleEvaluationSummary,
    ValidatedFeaturesInput,
)
from app.schemas.validation import STAGE_VALIDATION
from app.services.validator import validate_features

#: Bumped when the ENGINE's behaviour changes, independently of the rule table.
ENGINE_VERSION = "1.0.0"

RULE_ENGINE_POLICY = (
    "Deterministic threshold comparison against a reviewable table. A rule "
    "whose input is absent does not fire, and absence is never reported as a "
    "normal result. Rejected features are never read. Every decision carries "
    "confidence=None, which means 'no probability is produced' and is not the "
    "same as zero confidence."
)

INPUT_VALIDATED = "validated"
INPUT_ENGINEERED = "engineered"
INPUT_NONE = "none"


# --------------------------------------------------------------------------
# Fixed, user-facing note fragments
# --------------------------------------------------------------------------
#
# Evidence notes reach the reader through Module 20, so their wording is fixed
# here rather than formatted from arbitrary strings, and the test suite scans
# every one of them with the recommendation catalogue's safety scanner.

NOTE_QUESTIONABLE = (
    "this value was marked less reliable when the report was read"
)
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)
NOTE_EXTREME_LOW = (
    "this value is far below the usual range and was flagged for priority"
)
NOTE_AGE_UNKNOWN = (
    "age was not recorded, so the adult threshold was applied"
)
NOTE_NOT_AVAILABLE = "this value was not available in the submitted report"
NOTE_FACTOR_COUNTED = "counted as a cardiovascular risk factor"
NOTE_FACTOR_NOT_COUNTED = "present, but not counted as a cardiovascular risk factor"
NOTE_BELOW_MIN_AGE = (
    "the thresholds for this topic are adult reference values and were not "
    "applied to a recorded age below eighteen years"
)
NOTE_UNREADABLE = (
    "part of the document could not be read, so this value may be missing "
    "rather than absent from the report"
)

ALL_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
    NOTE_EXTREME_LOW,
    NOTE_AGE_UNKNOWN,
    NOTE_NOT_AVAILABLE,
    NOTE_FACTOR_COUNTED,
    NOTE_FACTOR_NOT_COUNTED,
    NOTE_BELOW_MIN_AGE,
    NOTE_UNREADABLE,
)


# --------------------------------------------------------------------------
# The engine's view of one usable feature
# --------------------------------------------------------------------------


class FeatureView:
    """A usable feature, flattened into what a rule needs.

    Built only from Module 6's `valid` map. There is no constructor path from
    `rejected`, because `rejected` is not parsed at all.
    """

    __slots__ = (
        "name",
        "value",
        "numeric",
        "unit",
        "questionable",
        "clinically_extreme",
        "extreme_direction",
        "reference_low",
        "reference_high",
        "source_stage",
        "timing",
    )

    def __init__(self, name: str, incoming: Any) -> None:
        self.name = name
        self.value = incoming.value
        self.numeric = _numeric(incoming.value)
        definition = FEATURES.get(name)
        self.unit = definition.canonical_unit if definition else incoming.unit
        self.questionable = bool(incoming.questionable)
        self.clinically_extreme = bool(incoming.clinically_extreme)
        self.extreme_direction = incoming.extreme_direction
        provenance = incoming.provenance
        self.reference_low = getattr(provenance, "reference_low", None)
        self.reference_high = getattr(provenance, "reference_high", None)
        self.source_stage = (
            incoming.source or getattr(provenance, "source", None) or None
        )
        self.timing = sample_timing(
            getattr(provenance, "original_test_name", None),
            getattr(provenance, "matched_synonym", None),
        )


def _numeric(value: Any) -> Optional[float]:
    """The value as a float, or None.

    `bool` is excluded deliberately: `True == 1` in Python, and a boolean that
    reached a numeric comparison must be caught, not silently measured.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_float(value: Any) -> Optional[float]:
    """Coerce to a real float for `EvidenceItem`'s StrictFloat fields."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# --------------------------------------------------------------------------
# Input coercion
# --------------------------------------------------------------------------


def _coerce_validated(value: Any) -> Optional[ValidatedFeaturesInput]:
    if value is None:
        return None
    if isinstance(value, ValidatedFeaturesInput):
        return value
    if isinstance(value, dict):
        return ValidatedFeaturesInput.model_validate(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return ValidatedFeaturesInput.model_validate(dump())
    return ValidatedFeaturesInput.model_validate(value)


def _carried_warnings(data: ValidatedFeaturesInput) -> List[StageWarning]:
    """Every upstream warning, origins intact.

    `all_warnings` is authoritative when present. The fallback exists because
    dropping upstream warnings has ALREADY been a real defect twice on this
    project: a caller that forwards only `upstream_warnings` / `warnings` must
    not lose them here.
    """
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


# --------------------------------------------------------------------------
# Decision construction
# --------------------------------------------------------------------------


def _decision(
    condition: str,
    status: DecisionStatus,
    risk: Optional[RiskLevel],
    evidence: List[EvidenceItem],
    recommendation_codes: Tuple[str, ...],
    metadata: Dict[str, Any],
) -> ClinicalDecision:
    """Build a `ClinicalDecision`.

    `confidence` is left at its default of None -- see the module docstring.
    Recommendations are resolved through the catalogue, which is the only way
    Module 8 can produce recommendation text at all.
    """
    return ClinicalDecision(
        condition=condition,
        status=status,
        risk=risk,
        source=RULE_ENGINE_SOURCE,
        source_kind=DecisionSourceKind.CLINICAL_RULE,
        evidence=evidence,
        recommendations=resolve_recommendations(recommendation_codes),
        metadata=metadata,
    )


def _base_metadata(rule_id: str, rule_version: str, condition: str) -> Dict[str, Any]:
    """Reproducibility context. Names, ids and thresholds only -- never values.

    A threshold is a configured constant, not patient information. A measured
    value IS patient information, so it lives only in `evidence`, which is the
    field designed to carry it.
    """
    return {
        "rule_id": rule_id,
        "rule_version": rule_version,
        "rule_table_version": RULE_TABLE_VERSION,
        "engine_version": ENGINE_VERSION,
        "condition": condition,
        "deterministic": True,
    }


def _input_notes(views: List[FeatureView]) -> Tuple[List[str], List[str]]:
    """`(questionable feature names, clinically extreme feature names)`."""
    questionable = [v.name for v in views if v.questionable]
    extreme = [v.name for v in views if v.clinically_extreme]
    return questionable, extreme


def _quality_codes(views: List[FeatureView]) -> Tuple[str, ...]:
    return (INPUT_QUALITY_CAVEAT,) if any(v.questionable for v in views) else ()


def _primary_evidence(
    view: FeatureView,
    threshold: Optional[float],
    comparator: Optional[str],
    label: str,
    extra_notes: List[str],
) -> EvidenceItem:
    notes = [label] + [n for n in extra_notes if n]
    if view.questionable:
        notes.append(NOTE_QUESTIONABLE)
    if view.clinically_extreme:
        notes.append(
            NOTE_EXTREME_LOW if view.extreme_direction == "low" else NOTE_EXTREME_HIGH
        )
    return EvidenceItem(
        feature=view.name,
        value=view.value,
        unit=view.unit,
        threshold=threshold,
        comparator=comparator,
        reference_low=_as_float(view.reference_low),
        reference_high=_as_float(view.reference_high),
        note="; ".join(notes),
        source_stage=view.source_stage,
    )


def _context_evidence(view: FeatureView, note: str) -> EvidenceItem:
    return EvidenceItem(
        feature=view.name,
        value=view.value,
        unit=view.unit,
        note=note,
        source_stage=view.source_stage,
    )


def _absent_evidence(feature: str, note: str) -> EvidenceItem:
    """Evidence that a value was NOT available.

    An INSUFFICIENT_DATA decision has to be able to say WHICH input it lacked,
    or Module 20 can only render "could not assess" with no reason.
    """
    definition = FEATURES.get(feature)
    return EvidenceItem(
        feature=feature,
        value=None,
        unit=definition.canonical_unit if definition else None,
        note=note,
    )


# --------------------------------------------------------------------------
# Threshold rules
# --------------------------------------------------------------------------


def _sex_of(views: Dict[str, FeatureView]) -> Optional[str]:
    """`'male'`, `'female'`, or None when sex was not established.

    `other` and `prefer_not_to_say` are Module 2's real stored answers and are
    respected: they are NOT coerced into a binary so that a threshold can be
    picked. They resolve to None, which selects the conservative branch of a
    `ContextualThreshold` and says so in the evidence.
    """
    view = views.get("gender")
    if view is None:
        return None
    return view.value if view.value in ("male", "female") else None


def _age_of(views: Dict[str, FeatureView]) -> Optional[float]:
    view = views.get("age")
    return view.numeric if view is not None else None


def _evaluate_threshold_rule(
    rule: ThresholdRule,
    views: Dict[str, FeatureView],
    sex: Optional[str],
    age: Optional[float],
    warnings: List[str],
) -> Optional[ClinicalDecision]:
    view = views.get(rule.feature)
    if view is None:
        # INVARIANT 2: no input, no decision. Never a fall-through to the
        # "nothing found" band.
        return None

    if rule.only_timing and view.timing not in rule.only_timing:
        return None

    metadata = _base_metadata(rule.id, rule.version, rule.condition)
    metadata["feature"] = rule.feature
    metadata["sample_timing"] = view.timing

    if view.numeric is None:
        warnings.append(
            f"{rule.id} was not applied: the value for '{rule.feature}' is not a "
            "number, so no threshold comparison is possible"
        )
        return None

    # Adult reference intervals must not be applied to a child.
    if (
        rule.min_age_years is not None
        and age is not None
        and age < rule.min_age_years
    ):
        metadata["skipped_reason"] = "below_minimum_age"
        metadata["min_age_years"] = rule.min_age_years
        evidence = [_absent_evidence(rule.feature, NOTE_BELOW_MIN_AGE)]
        if "age" in views:
            evidence.append(_context_evidence(views["age"], NOTE_BELOW_MIN_AGE))
        return _decision(
            rule.condition,
            DecisionStatus.INSUFFICIENT_DATA,
            None,
            evidence,
            (INFORMATION_INCOMPLETE, NOT_A_DIAGNOSIS),
            metadata,
        )

    used: List[FeatureView] = [view]
    for band in rule.bands:
        if band.only_when_sex_unknown and sex is not None:
            continue
        threshold, note = resolve_threshold(band.threshold, sex, age)
        if band.comparator is not None and threshold is not None:
            if not COMPARATORS[band.comparator](view.numeric, threshold):
                continue

        extra_notes: List[str] = []
        if note:
            extra_notes.append(note)
        contextual = isinstance(band.threshold, ContextualThreshold)
        if contextual and age is None and band.threshold.paediatric:
            extra_notes.append(NOTE_AGE_UNKNOWN)

        evidence = [
            _primary_evidence(
                view, threshold, band.comparator, band.label, extra_notes
            )
        ]
        for name in rule.context_features:
            context_view = views.get(name)
            if context_view is None or not contextual:
                continue
            used.append(context_view)
            evidence.append(
                _context_evidence(
                    context_view, "used to select the applicable threshold"
                )
            )

        questionable, extreme = _input_notes(used)
        metadata.update(
            {
                "band_label": band.label,
                "comparator": band.comparator,
                "threshold": threshold,
                "threshold_is_contextual": contextual,
                "features_used": [v.name for v in used],
                "questionable_inputs": questionable,
                "clinically_extreme_inputs": extreme,
                "sex_established": sex is not None,
            }
        )
        codes = (
            tuple(band.recommendations)
            + tuple(rule.always_recommend)
            + _quality_codes(used)
            + (NOT_A_DIAGNOSIS,)
        )
        return _decision(
            rule.condition, band.status, band.risk, evidence, codes, metadata
        )

    # Unreachable: `_self_check()` guarantees a final always-matching band.
    return None


# --------------------------------------------------------------------------
# The composite cardiovascular rule
# --------------------------------------------------------------------------


def _factor_holds(
    factor: RiskFactorDefinition,
    view: FeatureView,
    sex: Optional[str],
    age: Optional[float],
) -> Tuple[bool, Optional[float], Optional[str]]:
    """`(counted, resolved_threshold, threshold_note)`.

    INVARIANT 3 lives here: a boolean factor counts only when the value IS
    exactly `True`. A `False` returns False, and an ABSENT feature never
    reaches this function at all, so absence cannot be read as a negative.
    """
    if factor.kind == FACTOR_BOOLEAN_TRUE:
        return view.value is True, None, None
    if factor.kind == FACTOR_CATEGORY:
        return view.value in factor.categories, None, None
    threshold, note = resolve_threshold(factor.threshold, sex, age)
    if view.numeric is None or threshold is None or factor.comparator is None:
        return False, threshold, note
    return (
        COMPARATORS[factor.comparator](view.numeric, threshold),
        threshold,
        note,
    )


def _evaluate_composite_rule(
    rule: CompositeRule,
    views: Dict[str, FeatureView],
    sex: Optional[str],
    age: Optional[float],
    partial_document: bool,
) -> ClinicalDecision:
    metadata = _base_metadata(rule.id, rule.version, rule.condition)

    if (
        rule.min_age_years is not None
        and age is not None
        and age < rule.min_age_years
    ):
        metadata["skipped_reason"] = "below_minimum_age"
        metadata["min_age_years"] = rule.min_age_years
        return _decision(
            rule.condition,
            DecisionStatus.INSUFFICIENT_DATA,
            None,
            [_context_evidence(views["age"], NOTE_BELOW_MIN_AGE)],
            (INFORMATION_INCOMPLETE, NOT_A_DIAGNOSIS),
            metadata,
        )

    counted_ids: List[str] = []
    evaluable: List[str] = []
    missing: List[str] = []
    evidence: List[EvidenceItem] = []
    used: List[FeatureView] = []
    factor_codes: List[str] = []

    for factor in rule.factors:
        view = views.get(factor.feature)
        if view is None:
            missing.append(factor.feature)
            note = NOTE_UNREADABLE if partial_document else NOTE_NOT_AVAILABLE
            evidence.append(_absent_evidence(factor.feature, note))
            continue
        evaluable.append(factor.id)
        used.append(view)
        holds, threshold, note = _factor_holds(factor, view, sex, age)
        notes = [factor.label, NOTE_FACTOR_COUNTED if holds else NOTE_FACTOR_NOT_COUNTED]
        if note:
            notes.append(note)
        evidence.append(
            _primary_evidence(
                view,
                threshold,
                factor.comparator,
                "; ".join(notes),
                [],
            )
        )
        if holds:
            counted_ids.append(factor.id)
            factor_codes.extend(factor.recommendations)

    questionable, extreme = _input_notes(used)
    metadata.update(
        {
            "factors_counted": counted_ids,
            "factor_count": len(counted_ids),
            "factors_evaluable": evaluable,
            "features_missing": missing,
            "features_used": [v.name for v in used],
            "questionable_inputs": questionable,
            "clinically_extreme_inputs": extreme,
            "sex_established": sex is not None,
            "min_evaluable_inputs": rule.min_evaluable_inputs,
        }
    )

    # Too few inputs to tally honestly. A low count built from two features is
    # not reassurance, it is ignorance, so it must not be reported as LOW risk.
    if len(evaluable) < rule.min_evaluable_inputs:
        metadata["skipped_reason"] = "insufficient_inputs"
        codes = (INFORMATION_INCOMPLETE,)
        if partial_document:
            codes += (UNREADABLE_DOCUMENT_RECHECK,)
        return _decision(
            rule.condition,
            DecisionStatus.INSUFFICIENT_DATA,
            None,
            evidence,
            codes + _quality_codes(used) + (NOT_A_DIAGNOSIS,),
            metadata,
        )

    band = _select_count_band(rule, counted_ids)
    metadata["band_label"] = band.label
    codes = (
        tuple(band.recommendations)
        + tuple(factor_codes)
        + tuple(rule.always_recommend)
        + _quality_codes(used)
        + (NOT_A_DIAGNOSIS,)
    )
    return _decision(rule.condition, band.status, band.risk, evidence, codes, metadata)


def _select_count_band(rule: CompositeRule, counted_ids: List[str]) -> CountBand:
    for band in rule.bands:
        if band.requires_factor is not None:
            if band.requires_factor in counted_ids:
                return band
            continue
        if len(counted_ids) >= band.minimum_count:
            return band
    return rule.bands[-1]


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


def evaluate_rules(
    validated: Any = None, *, engineered: Any = None
) -> RuleEvaluationData:
    """Apply the clinical rule table and return `ClinicalDecision[]`.

    Framework-independent: no FastAPI, no I/O, no global state, so Module 15
    can call it in-process exactly as it calls `engineer_features()` and
    `validate_features()`.

    `validated` -- Module 6's `FeatureValidationData`, a `ValidatedFeaturesInput`
    or the equivalent dict. PREFERRED.

    `engineered` -- Module 5's `FeatureEngineeringData` or the equivalent dict,
    for use before validation has been run. It is passed through
    `validate_features()` in-process first, so the rules still only ever see
    validated values and no plausibility logic is duplicated here.

    When both are given, `validated` wins.
    """
    input_kind = INPUT_NONE
    data = _coerce_validated(validated)
    if data is not None:
        input_kind = INPUT_VALIDATED
    elif engineered is not None:
        data = _coerce_validated(validate_features(engineered))
        input_kind = INPUT_ENGINEERED
    else:
        data = ValidatedFeaturesInput()

    warnings: List[str] = []
    upstream_warnings = _carried_warnings(data)

    partial_document = bool(data.upstream.pages_unreadable)

    views: Dict[str, FeatureView] = {}
    for name, incoming in data.valid.items():
        if name not in FEATURES:
            warnings.append(
                f"'{name}' is not a canonical feature and was ignored by the rule "
                "engine"
            )
            continue
        views[name] = FeatureView(name, incoming)

    sex = _sex_of(views)
    age = _age_of(views)

    ranked: List[Tuple[int, int, ClinicalDecision]] = []
    rules_fired = 0

    for index, rule in enumerate(THRESHOLD_RULES):
        decision = _evaluate_threshold_rule(rule, views, sex, age, warnings)
        if decision is None:
            continue
        rules_fired += 1
        ranked.append((C.condition_rank(rule.condition), index, decision))

    for offset, composite in enumerate(COMPOSITE_RULES):
        decision = _evaluate_composite_rule(
            composite, views, sex, age, partial_document
        )
        rules_fired += 1
        ranked.append(
            (
                C.condition_rank(composite.condition),
                len(THRESHOLD_RULES) + offset,
                decision,
            )
        )

    assessed = {decision.condition for _, _, decision in ranked}

    # ---- conditions that must be mentioned even when nothing could be read --
    for condition, definition in C.CONDITIONS.items():
        if condition in assessed:
            continue
        inputs = CONDITION_INPUTS.get(condition, ())
        if not inputs:
            continue
        # An always-assessed condition is one Modules 10-12 will also emit.
        # Silence there would leave Module 16 unable to tell "not assessed"
        # from "nothing found". Everything else is only mentioned when the
        # document was partially unreadable, in which case absence may mean
        # UNREAD -- which must never read as normal.
        if not definition.always_assessed:
            if not (partial_document and definition.report_when_unread):
                continue
        note = NOTE_UNREADABLE if partial_document else NOTE_NOT_AVAILABLE
        metadata = _base_metadata(
            f"CONDITION_NOT_ASSESSABLE:{condition}", RULE_TABLE_VERSION, condition
        )
        metadata.update(
            {
                "skipped_reason": "no_usable_input",
                "features_required_any_of": list(inputs),
                "partial_document": partial_document,
            }
        )
        codes: Tuple[str, ...] = (INFORMATION_INCOMPLETE,)
        if partial_document:
            codes += (UNREADABLE_DOCUMENT_RECHECK,)
        ranked.append(
            (
                C.condition_rank(condition),
                len(THRESHOLD_RULES) + len(COMPOSITE_RULES),
                _decision(
                    condition,
                    DecisionStatus.INSUFFICIENT_DATA,
                    None,
                    [_absent_evidence(name, note) for name in inputs],
                    codes + (NOT_A_DIAGNOSIS,),
                    metadata,
                ),
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1]))
    decisions = [decision for _, _, decision in ranked]

    if not views:
        warnings.append(
            "no usable features were supplied, so no clinical rule could be "
            "applied"
        )
    if partial_document:
        warnings.append(
            "the source document was only partially readable, so a topic with no "
            "decision may be unassessed rather than unremarkable"
        )

    all_warnings = list(upstream_warnings) + [
        StageWarning(stage=STAGE_RULES, module=RULES_MODULE, message=message)
        for message in warnings
    ]

    return RuleEvaluationData(
        decisions=decisions,
        warnings=warnings,
        upstream_warnings=upstream_warnings,
        all_warnings=all_warnings,
        upstream=data.upstream,
        upstream_summary=data.summary,
        summary=_summarise(
            decisions,
            views,
            rules_fired=rules_fired,
            partial_document=partial_document,
            input_kind=input_kind,
        ),
        metadata={
            "engine_version": ENGINE_VERSION,
            "rule_table_version": RULE_TABLE_VERSION,
            "source": RULE_ENGINE_SOURCE,
            "policy": RULE_ENGINE_POLICY,
            "rules_evaluated": len(THRESHOLD_RULES) + len(COMPOSITE_RULES),
            "input_kind": input_kind,
        },
    )


def _summarise(
    decisions: List[ClinicalDecision],
    views: Dict[str, FeatureView],
    *,
    rules_fired: int,
    partial_document: bool,
    input_kind: str,
) -> RuleEvaluationSummary:
    risks = [d.risk for d in decisions if d.risk is not None]
    used: List[str] = []
    for decision in decisions:
        for name in decision.evidence_features():
            if name in views and name not in used:
                used.append(name)
    return RuleEvaluationSummary(
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
        # RiskLevel.highest() rather than a hand-written comparison: the
        # ordering is a property of the type (see decisions.py) and returns
        # None for an empty list, so "nothing assessed" never becomes "Low".
        highest_risk=RiskLevel.highest(risks),
        conditions_assessed=sorted(
            {d.condition for d in decisions if d.was_assessed},
            key=C.condition_rank,
        ),
        conditions_flagged=sorted(
            {d.condition for d in decisions if d.is_flagged}, key=C.condition_rank
        ),
        rules_evaluated=len(THRESHOLD_RULES) + len(COMPOSITE_RULES),
        rules_fired=rules_fired,
        features_used=used,
        questionable_features_used=[n for n in used if views[n].questionable],
        clinically_extreme_features_used=[
            n for n in used if views[n].clinically_extreme
        ],
        partial_document=partial_document,
        input_kind=input_kind,
    )


__all__ = [
    "ALL_NOTE_FRAGMENTS",
    "ENGINE_VERSION",
    "INPUT_ENGINEERED",
    "INPUT_NONE",
    "INPUT_VALIDATED",
    "RULE_ENGINE_POLICY",
    "FeatureView",
    "evaluate_rules",
]
