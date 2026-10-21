from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from app.data.feature_catalog import FEATURES
from app.data.unit_conversions import normalize_unit
from app.data.validation_rules import (
    LOW_CONFIDENCE_THRESHOLD,
    QUESTIONABLE_FLAGS,
    FlagCode,
    RejectionCode,
    ValidationRule,
    rule_for,
)
from app.schemas.features import (
    STAGE_FEATURE_ENGINEERING,
    FeatureProvenance,
    StageWarning,
)
from app.schemas.validation import (
    STAGE_VALIDATION,
    STATUS_QUESTIONABLE,
    STATUS_VALID,
    VALIDATION_MODULE,
    EngineeredFeaturesInput,
    FeatureValidationData,
    FeatureValidationSummary,
    IncomingFeature,
    RejectedFeature,
    ValidatedFeature,
    ValidationFinding,
)

VALIDATION_POLICY = (
    "A value is rejected only when it is physiologically impossible (a "
    "suspected extraction error) or structurally unusable (wrong type, or a "
    "unit Module 5 could not convert). A value is NEVER rejected for being "
    "abnormal; an abnormal-but-possible value is returned as valid and tagged "
    "clinically_extreme."
)


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _units_agree(feature_unit: Optional[str], canonical: Optional[str]) -> bool:
    if canonical is None or feature_unit is None:
        return True
    left = normalize_unit(feature_unit)
    right = normalize_unit(canonical)
    if left is None or right is None:
        return str(feature_unit).strip().lower() == str(canonical).strip().lower()
    return left == right


def _finding(
    code: str,
    message: str,
    *,
    severity: str = "warning",
    bound: Optional[str] = None,
    limit: Optional[float] = None,
    observed: Any = None,
    basis: Optional[str] = None,
) -> ValidationFinding:
    if observed is not None and not isinstance(observed, (bool, int, float, str)):
        observed = repr(observed)
    return ValidationFinding(
        code=code,
        message=message,
        severity=severity,
        bound=bound,
        limit=limit,
        observed=observed,
        basis=basis,
    )


def _default_provenance(feature: IncomingFeature, name: str) -> FeatureProvenance:
    definition = FEATURES.get(name)
    source = feature.source or (definition.source if definition else "unknown")
    return FeatureProvenance(source=source)


def _check_type(
    rule: ValidationRule, value: Any
) -> Optional[ValidationFinding]:
    if rule.value_type in ("number", "integer"):
        number = _numeric(value)
        if number is None:
            return _finding(
                RejectionCode.NOT_A_NUMBER,
                f"'{rule.feature}' must be numeric, but the value is not a "
                "number. It was not guessed at or converted.",
                severity="error",
                observed=value,
            )
        if math.isnan(number) or math.isinf(number):
            return _finding(
                RejectionCode.NON_FINITE_VALUE,
                f"'{rule.feature}' is not a finite number.",
                severity="error",
                observed=str(value),
            )
        if rule.value_type == "integer" and not float(number).is_integer():
            return _finding(
                RejectionCode.NOT_AN_INTEGER,
                f"'{rule.feature}' is recorded in whole units, but a "
                "fractional value was supplied. It was not rounded.",
                severity="error",
                observed=value,
            )
        return None

    if rule.value_type == "boolean":
        if not isinstance(value, bool):
            return _finding(
                RejectionCode.NOT_A_BOOLEAN,
                f"'{rule.feature}' is a tri-state boolean; a present value "
                "must be exactly true or false. This value was NOT interpreted "
                "and was NOT defaulted to false -- doing so would fabricate a "
                "clinical finding.",
                severity="error",
                observed=value,
            )
        return None

    if rule.value_type == "category":
        categories = FEATURES[rule.feature].categories
        if not isinstance(value, str) or value not in categories:
            return _finding(
                RejectionCode.UNKNOWN_CATEGORY,
                f"'{rule.feature}' must be one of: {', '.join(categories)}.",
                severity="error",
                observed=value,
                basis=rule.basis,
            )
        return None

    return None


def _check_range(
    rule: ValidationRule, number: float
) -> Tuple[Optional[ValidationFinding], List[ValidationFinding], Optional[str]]:
    if rule.possible_low is not None and number < rule.possible_low:
        return (
            _finding(
                RejectionCode.IMPLAUSIBLE_VALUE_LOW,
                f"'{rule.feature}' = {number:g} {rule.unit or ''}".strip()
                + f" is below the physiologically possible minimum of "
                f"{rule.possible_low:g}. This is treated as an extraction "
                "error, not as a clinical finding. The value was not altered.",
                severity="error",
                bound="possible_low",
                limit=rule.possible_low,
                observed=number,
                basis=rule.basis,
            ),
            [],
            None,
        )
    if rule.possible_high is not None and number > rule.possible_high:
        return (
            _finding(
                RejectionCode.IMPLAUSIBLE_VALUE_HIGH,
                f"'{rule.feature}' = {number:g} {rule.unit or ''}".strip()
                + f" is above the physiologically possible maximum of "
                f"{rule.possible_high:g}. This is treated as an extraction "
                "error, not as a clinical finding. The value was not altered.",
                severity="error",
                bound="possible_high",
                limit=rule.possible_high,
                observed=number,
                basis=rule.basis,
            ),
            [],
            None,
        )

    flags: List[ValidationFinding] = []
    direction: Optional[str] = None
    if rule.extreme_low is not None and number <= rule.extreme_low:
        direction = "low"
        flags.append(
            _finding(
                FlagCode.CLINICALLY_EXTREME_LOW,
                f"'{rule.feature}' = {number:g} is at or below the critical "
                f"low threshold of {rule.extreme_low:g}. The value is VALID "
                "and usable; it is flagged for clinical priority.",
                severity="info",
                bound="extreme_low",
                limit=rule.extreme_low,
                observed=number,
                basis=rule.basis,
            )
        )
    elif rule.extreme_high is not None and number >= rule.extreme_high:
        direction = "high"
        flags.append(
            _finding(
                FlagCode.CLINICALLY_EXTREME_HIGH,
                f"'{rule.feature}' = {number:g} is at or above the critical "
                f"high threshold of {rule.extreme_high:g}. The value is VALID "
                "and usable; it is flagged for clinical priority.",
                severity="info",
                bound="extreme_high",
                limit=rule.extreme_high,
                observed=number,
                basis=rule.basis,
            )
        )
    return None, flags, direction


def _confidence_flags(
    name: str, provenance: FeatureProvenance, pages_unreadable: List[int]
) -> List[ValidationFinding]:
    flags: List[ValidationFinding] = []

    if provenance.unit_assumed:
        flags.append(
            _finding(
                FlagCode.UNIT_ASSUMED,
                f"No unit was printed for '{name}'; the canonical unit was "
                "assumed upstream. A value that is plausible in the assumed "
                "unit may be wrong by orders of magnitude in the real one, so "
                "the range check on it is weaker than it appears.",
                severity="warning",
                observed=provenance.original_unit,
            )
        )
    if provenance.censored:
        side = "below" if provenance.censored == "left" else "above"
        flags.append(
            _finding(
                FlagCode.CENSORED_VALUE,
                f"'{name}' was reported as a censored result; the true value "
                f"is {side} the detection limit that is recorded here, not "
                "equal to it.",
                severity="warning",
                observed=provenance.original_value_raw,
            )
        )
    if provenance.derived:
        flags.append(
            _finding(
                FlagCode.DERIVED_VALUE,
                f"'{name}' was not read from the report; it was derived "
                f"upstream ({provenance.derived}).",
                severity="warning",
                observed=provenance.derived,
            )
        )
    if (
        provenance.confidence is not None
        and provenance.confidence <= LOW_CONFIDENCE_THRESHOLD
    ):
        flags.append(
            _finding(
                FlagCode.LOW_EXTRACTION_CONFIDENCE,
                f"The extraction confidence for '{name}' "
                f"({provenance.confidence:g}) is at or below "
                f"{LOW_CONFIDENCE_THRESHOLD:g}; the transcription of this row "
                "may be wrong.",
                severity="warning",
                limit=LOW_CONFIDENCE_THRESHOLD,
                observed=provenance.confidence,
            )
        )
    if provenance.page_number is not None and provenance.page_number in set(
        pages_unreadable
    ):
        flags.append(
            _finding(
                FlagCode.PARTIAL_DOCUMENT,
                f"'{name}' is attributed to page {provenance.page_number}, "
                "which Module 4 reported as unreadable. The attribution or the "
                "value may be unreliable.",
                severity="warning",
                observed=provenance.page_number,
            )
        )
    return flags


def _coerce_input(engineered: Any) -> EngineeredFeaturesInput:
    if isinstance(engineered, EngineeredFeaturesInput):
        return engineered
    if engineered is None:
        return EngineeredFeaturesInput()
    if isinstance(engineered, dict):
        return EngineeredFeaturesInput.model_validate(engineered)
    dump = getattr(engineered, "model_dump", None)
    if callable(dump):
        return EngineeredFeaturesInput.model_validate(dump())
    return EngineeredFeaturesInput.model_validate(engineered)


def _carried_warnings(data: EngineeredFeaturesInput) -> List[StageWarning]:
    if data.all_warnings:
        return list(data.all_warnings)

    rebuilt: List[StageWarning] = list(data.upstream_warnings)
    seen = {(w.stage, w.message) for w in rebuilt}
    for message in data.warnings:
        key = (STAGE_FEATURE_ENGINEERING, message)
        if key not in seen:
            seen.add(key)
            rebuilt.append(
                StageWarning(
                    stage=STAGE_FEATURE_ENGINEERING, module=5, message=message
                )
            )
    return rebuilt


def validate_features(engineered: Any = None) -> FeatureValidationData:
    data = _coerce_input(engineered)

    pages_unreadable = list(data.upstream.pages_unreadable)
    partial_document = bool(pages_unreadable)
    extraction_confidence = data.upstream.extraction_confidence

    valid: Dict[str, ValidatedFeature] = {}
    questionable: Dict[str, ValidatedFeature] = {}
    rejected: Dict[str, RejectedFeature] = {}
    extreme_names: List[str] = []
    warnings: List[str] = []

    ordered_names = [n for n in FEATURES if n in data.features]
    ordered_names += [n for n in data.features if n not in FEATURES]

    for name in ordered_names:
        feature = data.features[name]
        provenance = feature.provenance or _default_provenance(feature, name)
        source = feature.source or provenance.source
        rule = rule_for(name)

        def reject(finding: ValidationFinding) -> None:
            rejected[name] = RejectedFeature(
                name=name,
                value=feature.value,
                unit=feature.unit,
                canonical_unit=feature.canonical_unit,
                source=source,
                provenance=provenance,
                reason_code=finding.code,
                reason=finding.message,
                findings=[finding],
            )
            warnings.append(f"Feature '{name}' was rejected: {finding.message}")

        if rule is None:
            reject(
                _finding(
                    RejectionCode.UNKNOWN_FEATURE,
                    f"'{name}' is not a canonical VaidyaAI feature and has no "
                    "validation rule, so it cannot be certified as usable.",
                    severity="error",
                    observed=feature.value,
                )
            )
            continue

        if rule.unit is not None and not feature.canonical_unit:
            reject(
                _finding(
                    RejectionCode.NON_CANONICAL_UNIT,
                    f"'{name}' was reported in a unit that could not be "
                    f"recognised, so it was never converted to the canonical "
                    f"{rule.unit}. The number cannot be compared against any "
                    "range and must not be used as if it were canonical. It "
                    "was not converted or guessed at here either.",
                    severity="error",
                    observed=feature.unit,
                    basis=rule.basis,
                )
            )
            continue

        type_finding = _check_type(rule, feature.value)
        if type_finding is not None:
            reject(type_finding)
            continue

        if rule.unit is not None and not _units_agree(feature.unit, rule.unit):
            reject(
                _finding(
                    RejectionCode.UNIT_MISMATCH,
                    f"'{name}' is marked as canonical but its unit "
                    f"({feature.unit!r}) is not the canonical {rule.unit!r}. A "
                    "silent unit mismatch is the most dangerous failure "
                    "available here, so the value is refused rather than "
                    "reinterpreted.",
                    severity="error",
                    observed=feature.unit,
                    basis=rule.basis,
                )
            )
            continue

        flags: List[ValidationFinding] = []
        direction: Optional[str] = None
        if rule.is_numeric:
            number = _numeric(feature.value)
            assert number is not None
            range_finding, extreme_flags, direction = _check_range(rule, number)
            if range_finding is not None:
                reject(range_finding)
                continue
            flags.extend(extreme_flags)

        flags.extend(_confidence_flags(name, provenance, pages_unreadable))

        is_questionable = any(f.code in QUESTIONABLE_FLAGS for f in flags)
        is_extreme = direction is not None

        entry = ValidatedFeature(
            name=name,
            value=feature.value,
            unit=feature.unit,
            canonical_unit=feature.canonical_unit,
            source=source,
            provenance=provenance,
            status=STATUS_QUESTIONABLE if is_questionable else STATUS_VALID,
            questionable=is_questionable,
            clinically_extreme=is_extreme,
            extreme_direction=direction,
            flags=flags,
        )
        valid[name] = entry
        if is_questionable:
            questionable[name] = entry
            codes = sorted({f.code for f in flags if f.code in QUESTIONABLE_FLAGS})
            warnings.append(
                f"Feature '{name}' is usable but flagged ({', '.join(codes)}); "
                "treat it with reduced confidence."
            )
        if is_extreme:
            extreme_names.append(name)
            warnings.append(
                f"Feature '{name}' is a valid but clinically extreme "
                f"({direction}) value and should be prioritised downstream."
            )

    if partial_document:
        pages = ", ".join(str(p) for p in pages_unreadable)
        warnings.append(
            f"The source document was only partially readable (page(s) "
            f"{pages} could not be read). A feature that is absent may be "
            "UNREAD rather than absent from the report; absence must not be "
            "interpreted as a negative finding."
        )
    if (
        extraction_confidence is not None
        and extraction_confidence <= LOW_CONFIDENCE_THRESHOLD
    ):
        warnings.append(
            f"Overall extraction confidence ({extraction_confidence:g}) is at "
            f"or below {LOW_CONFIDENCE_THRESHOLD:g}; every value from this "
            "document should be treated with reduced confidence."
        )
    if not data.features:
        warnings.append(
            "No engineered features were supplied to validation, so no value "
            "could be validated."
        )
    elif not valid:
        warnings.append(
            f"No feature survived validation: all {len(data.features)} "
            "supplied feature(s) were rejected."
        )

    upstream_warnings = _carried_warnings(data)
    own_warnings = [
        StageWarning(
            stage=STAGE_VALIDATION, module=VALIDATION_MODULE, message=message
        )
        for message in warnings
    ]
    all_warnings = upstream_warnings + own_warnings

    summary = FeatureValidationSummary(
        features_received=len(data.features),
        valid_count=len(valid),
        questionable_count=len(questionable),
        rejected_count=len(rejected),
        clinically_extreme_count=len(extreme_names),
        missing_count=len(data.missing_features),
        unmapped_count=len(data.unmapped),
        validation_warning_count=len(warnings),
        upstream_warning_count=len(upstream_warnings),
        pages_unreadable_count=len(pages_unreadable),
        extraction_confidence=extraction_confidence,
        partial_document=partial_document,
    )

    return FeatureValidationData(
        valid=valid,
        questionable=questionable,
        rejected=rejected,
        clinically_extreme=extreme_names,
        missing_features=list(data.missing_features),
        unmapped=list(data.unmapped),
        warnings=warnings,
        upstream_warnings=upstream_warnings,
        all_warnings=all_warnings,
        upstream=data.upstream,
        upstream_summary=data.summary,
        summary=summary,
    )


def usable_features(result: FeatureValidationData) -> Dict[str, Any]:
    return {name: feature.value for name, feature in result.valid.items()}


__all__ = [
    "STAGE_VALIDATION",
    "VALIDATION_POLICY",
    "usable_features",
    "validate_features",
]
