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
    PrintedLimitThreshold,
    RiskFactorDefinition,
    ThresholdRule,
    resolve_threshold,
    sample_timing,
    uses_printed_limit,
)
from app.data.egfr import (
    EGFR_FEATURE,
    EGFR_METHOD,
    EGFR_UNIT,
    SOURCE_CALCULATED,
    ckd_epi_2021,
    reported_egfr,
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
NOTE_FACTOR_NOT_COUNTED = "not counted as a cardiovascular risk factor"

NOTE_FACTOR_NOT_MET = "criterion not met -- "
NOTE_BELOW_MIN_AGE = (
    "the thresholds for this topic are adult reference values and were not "
    "applied to a recorded age below eighteen years"
)
NOTE_UNREADABLE = (
    "part of the document could not be read, so this value may be missing "
    "rather than absent from the report"
)
NOTE_EGFR_METHOD = (
    "calculated from creatinine, age and sex with the CKD-EPI 2021 equation; "
    "one estimate from one sample, which does not by itself stage kidney "
    "function"
)
NOTE_EGFR_INPUT = "used to calculate the estimated filtration rate"

ALL_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
    NOTE_EXTREME_LOW,
    NOTE_AGE_UNKNOWN,
    NOTE_NOT_AVAILABLE,
    NOTE_FACTOR_COUNTED,
    NOTE_FACTOR_NOT_COUNTED,
    NOTE_FACTOR_NOT_MET,
    NOTE_BELOW_MIN_AGE,
    NOTE_UNREADABLE,
    NOTE_EGFR_METHOD,
    NOTE_EGFR_INPUT,
)


class FeatureView:

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
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


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


def _decision(
    condition: str,
    status: DecisionStatus,
    risk: Optional[RiskLevel],
    evidence: List[EvidenceItem],
    recommendation_codes: Tuple[str, ...],
    metadata: Dict[str, Any],
) -> ClinicalDecision:
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
    return {
        "rule_id": rule_id,
        "rule_version": rule_version,
        "rule_table_version": RULE_TABLE_VERSION,
        "engine_version": ENGINE_VERSION,
        "condition": condition,
        "deterministic": True,
    }


def _input_notes(views: List[FeatureView]) -> Tuple[List[str], List[str]]:
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
    definition = FEATURES.get(feature)
    return EvidenceItem(
        feature=feature,
        value=None,
        unit=definition.canonical_unit if definition else None,
        note=note,
    )


def _sex_of(views: Dict[str, FeatureView]) -> Optional[str]:
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

    if rule.derived is not None:
        return _evaluate_derived_rule(rule, view, views, sex, age, warnings, metadata)

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
        reference_high = _as_float(view.reference_high)
        threshold, note = resolve_threshold(band.threshold, sex, age, reference_high)
        if band.comparator is not None and threshold is not None:
            if not COMPARATORS[band.comparator](view.numeric, threshold):
                continue

        extra_notes: List[str] = []
        if note:
            extra_notes.append(note)
        contextual = isinstance(band.threshold, ContextualThreshold) or (
            isinstance(band.threshold, PrintedLimitThreshold)
            and isinstance(band.threshold.fallback, ContextualThreshold)
            and not uses_printed_limit(band.threshold, reference_high)
        )
        if (
            isinstance(band.threshold, ContextualThreshold)
            and age is None
            and band.threshold.paediatric
        ):
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

    return None


def _evaluate_derived_rule(
    rule: ThresholdRule,
    view: FeatureView,
    views: Dict[str, FeatureView],
    sex: Optional[str],
    age: Optional[float],
    warnings: List[str],
    metadata: Dict[str, Any],
) -> Optional[ClinicalDecision]:
    if rule.derived != EGFR_FEATURE:
        warnings.append(f"{rule.id} was not applied: unknown derived value")
        return None
    if age is None or sex is None:
        warnings.append(
            f"{rule.id} was not applied: the estimated filtration rate needs a "
            "recorded age and a sex recorded as male or female"
        )
        return None
    if rule.min_age_years is not None and age < rule.min_age_years:
        warnings.append(
            f"{rule.id} was not applied: the equation is validated in adults only"
        )
        return None

    raw = ckd_epi_2021(view.numeric, age, sex)
    if raw is None:
        warnings.append(
            f"{rule.id} was not applied: no estimate could be calculated from "
            "the recorded values"
        )
        return None
    value = reported_egfr(raw)

    used: List[FeatureView] = [view] + [
        views[name] for name in rule.context_features if name in views
    ]
    for band in rule.bands:
        threshold = None if band.threshold is None else float(band.threshold)
        if band.comparator is not None and threshold is not None:
            if not COMPARATORS[band.comparator](value, threshold):
                continue

        notes = [band.label, NOTE_EGFR_METHOD]
        if view.questionable:
            notes.append(NOTE_QUESTIONABLE)
        evidence = [
            EvidenceItem(
                feature=EGFR_FEATURE,
                value=value,
                unit=EGFR_UNIT,
                threshold=threshold,
                comparator=band.comparator,
                note="; ".join(notes),
                source_stage=SOURCE_CALCULATED,
            ),
            _context_evidence(view, NOTE_EGFR_INPUT),
        ]
        for name in rule.context_features:
            if name in views:
                evidence.append(_context_evidence(views[name], NOTE_EGFR_INPUT))

        questionable, extreme = _input_notes(used)
        metadata.update(
            {
                "band_label": band.label,
                "comparator": band.comparator,
                "threshold": threshold,
                "threshold_is_contextual": False,
                "derived": rule.derived,
                "derived_value": value,
                "derived_value_unrounded": round(raw, 2),
                "derived_unit": EGFR_UNIT,
                "derived_method": EGFR_METHOD,
                "features_used": [v.name for v in used],
                "questionable_inputs": questionable,
                "clinically_extreme_inputs": extreme,
                "sex_established": True,
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

    return None


def _factor_holds(
    factor: RiskFactorDefinition,
    view: FeatureView,
    sex: Optional[str],
    age: Optional[float],
) -> Tuple[bool, Optional[float], Optional[str]]:
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
        criterion = factor.label if holds else f"{NOTE_FACTOR_NOT_MET}{factor.label}"
        notes = [criterion, NOTE_FACTOR_COUNTED if holds else NOTE_FACTOR_NOT_COUNTED]
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


def evaluate_rules(
    validated: Any = None, *, engineered: Any = None
) -> RuleEvaluationData:
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

    for condition, definition in C.CONDITIONS.items():
        if condition in assessed:
            continue
        inputs = CONDITION_INPUTS.get(condition, ())
        if not inputs:
            continue
        if not definition.always_assessed and not definition.report_when_unread:
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
