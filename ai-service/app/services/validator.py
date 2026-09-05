"""Module 6 -- Medical Feature Validation Engine.

Extracted values are not correct merely because OCR produced them. This module
takes Module 5's canonical, unit-normalised features and decides, per feature,
whether the value is BELIEVABLE and USABLE.

It performs, per the specification:

  * data-type validation      -- a number where a number belongs, a real
                                 boolean where a tri-state boolean belongs, a
                                 known token where a category belongs
  * numeric validation        -- finite, and integral where required
  * range validation          -- against the physiologically possible band
  * unit consistency          -- a value Module 5 could NOT convert
                                 (`canonical_unit: false`) is never used as-is
  * missing-value handling    -- absent stays absent; UNKNOWN never becomes
                                 false; a partially unreadable document is
                                 flagged so absence is not read as a negative
  * physiologically unreasonable value detection
  * feature-specific validation via the reviewable rule table

--------------------------------------------------------------------------
THE LINE THIS MODULE MUST NOT CROSS
--------------------------------------------------------------------------

It validates PLAUSIBILITY AND USABILITY. It does not diagnose, and it never
rejects a value for being abnormal -- abnormal findings are the whole product.

    blood_glucose 400 mg/dL   -> VALID, tagged `clinically_extreme`
    blood_glucose 40000 mg/dL -> REJECTED as an extraction error

The two bands that encode that distinction live in
`app/data/validation_rules.py`, with the clinical basis of every bound.

--------------------------------------------------------------------------
INVARIANTS
--------------------------------------------------------------------------

* NEVER invent, repair, rescale or clamp a value. Values are passed through
  untouched, flagged untouched, or rejected untouched.
* NEVER drop an upstream warning, and never flatten its origin. Module 4's
  warnings stay `stage="extraction"`, Module 5's stay
  `stage="feature_engineering"`, Module 6 adds `stage="validation"`.
* NEVER coerce an absent tri-state boolean to false.
* `valid` and `rejected` are disjoint; `questionable` is a subset view of
  `valid`.
"""

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

#: Documentation string returned by the endpoint and by `rules_document()`
#: consumers, stating the policy in one line.
VALIDATION_POLICY = (
    "A value is rejected only when it is physiologically impossible (a "
    "suspected extraction error) or structurally unusable (wrong type, or a "
    "unit Module 5 could not convert). A value is NEVER rejected for being "
    "abnormal; an abnormal-but-possible value is returned as valid and tagged "
    "clinically_extreme."
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _numeric(value: Any) -> Optional[float]:
    """The value as a float, or None if it is not a real number.

    `bool` is excluded deliberately: in Python `True == 1`, and a boolean that
    slipped into a numeric feature must be caught, not silently measured.
    """
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
    # `observed` is constrained to a JSON scalar by the schema; anything else
    # (a dict, a list) is rendered as text rather than dropped, so the reason
    # for a rejection is never lost.
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
    """A minimal provenance when the caller supplied none.

    Nothing is invented: only the source, which the catalog already fixes for
    every canonical feature.
    """
    definition = FEATURES.get(name)
    source = feature.source or (definition.source if definition else "unknown")
    return FeatureProvenance(source=source)


# --------------------------------------------------------------------------
# Per-feature checks
# --------------------------------------------------------------------------


def _check_type(
    rule: ValidationRule, value: Any
) -> Optional[ValidationFinding]:
    """Data-type and numeric validation. Returns a finding on failure."""
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
        # TRI-STATE. Reaching here means the feature is PRESENT, so only a
        # real boolean is acceptable. An unknown value is expressed by the
        # feature being ABSENT, never by a placeholder, and a string such as
        # "yes" is rejected rather than interpreted -- Module 5 owns that
        # interpretation, and anything it could not interpret must not be
        # silently resolved here.
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
    """Range validation.

    Returns `(rejection_or_None, extreme_flags, extreme_direction)`.

    The possible band decides REJECTION (a suspected extraction error). The
    extreme band decides only a FLAG -- the value stays valid and usable.
    """
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
    """Flags that leave a feature usable but less trustworthy."""
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
    # Only the feature's OWN page matters here. A document with an unreadable
    # page elsewhere does not make a cleanly-read row less trustworthy -- that
    # is a document-level warning, raised once, and its real consequence is
    # that ABSENT features may be UNREAD. Flagging every row of such a document
    # would drown the signal. But a value claimed to come from a page Module 4
    # says it could not read is self-contradictory, and that IS suspicious.
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


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


def _coerce_input(engineered: Any) -> EngineeredFeaturesInput:
    if isinstance(engineered, EngineeredFeaturesInput):
        return engineered
    if engineered is None:
        return EngineeredFeaturesInput()
    if isinstance(engineered, dict):
        return EngineeredFeaturesInput.model_validate(engineered)
    # A `FeatureEngineeringData` (or anything else pydantic) from an in-process
    # call to `engineer_features()`.
    dump = getattr(engineered, "model_dump", None)
    if callable(dump):
        return EngineeredFeaturesInput.model_validate(dump())
    return EngineeredFeaturesInput.model_validate(engineered)


def _carried_warnings(data: EngineeredFeaturesInput) -> List[StageWarning]:
    """Every upstream warning, origins intact.

    `all_warnings` is authoritative when present. The fallback exists because
    dropping upstream warnings has ALREADY happened once on the 4->5 boundary:
    a caller that forwards only `upstream_warnings` / `warnings` must not lose
    them here.
    """
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
    """Validate Module 5's engineered feature set.

    Framework-independent: no FastAPI, no I/O, no global state. Accepts a
    `FeatureEngineeringData` straight from `engineer_features()`, an
    `EngineeredFeaturesInput`, or a plain dict (Module 5's `data` object as
    JSON), so Module 7, Module 8 and the ML layer can call it directly.

    Raises `pydantic.ValidationError` only if the input does not satisfy the
    Module 5 contract at all. Individual bad VALUES never raise -- they are
    rejected per-feature, with a reason, so the rest of the payload survives.
    """
    data = _coerce_input(engineered)

    pages_unreadable = list(data.upstream.pages_unreadable)
    partial_document = bool(pages_unreadable)
    extraction_confidence = data.upstream.extraction_confidence

    valid: Dict[str, ValidatedFeature] = {}
    questionable: Dict[str, ValidatedFeature] = {}
    rejected: Dict[str, RejectedFeature] = {}
    extreme_names: List[str] = []
    warnings: List[str] = []

    # Catalog order, not caller order, so the output is stable.
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

        # -- the feature name itself -------------------------------------
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

        # -- unit consistency --------------------------------------------
        # Module 5 emits `canonical_unit: false` when the printed unit was not
        # recognised and the value was therefore NOT converted. Its magnitude
        # is meaningless, so no range check can rescue it and no conversion is
        # attempted here. This is the explicit unit-consistency rejection.
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

        # -- data type / numeric validation ------------------------------
        type_finding = _check_type(rule, feature.value)
        if type_finding is not None:
            reject(type_finding)
            continue

        # -- unit mismatch (defensive; Module 5 should never produce this) --
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

        # -- range validation --------------------------------------------
        flags: List[ValidationFinding] = []
        direction: Optional[str] = None
        if rule.is_numeric:
            number = _numeric(feature.value)
            assert number is not None  # guaranteed by _check_type
            range_finding, extreme_flags, direction = _check_range(rule, number)
            if range_finding is not None:
                reject(range_finding)
                continue
            flags.extend(extreme_flags)

        # -- usable, but how much do we trust it? ------------------------
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

    # -- document-level observations -------------------------------------
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

    # -- warnings: carried forward with origins intact --------------------
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
        # Carried forward from Module 5 unchanged. A rejected feature is NOT
        # added to `missing_features`: "we read a value and refused it" and
        # "there was no value" are different facts, and `rejected` already
        # records the first.
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
    """The plain `{name: value}` map of everything usable.

    A convenience for the ML layer. Questionable features ARE included -- they
    are usable by definition; a caller that wants to exclude them can consult
    `result.questionable`.
    """
    return {name: feature.value for name, feature in result.valid.items()}


__all__ = [
    "STAGE_VALIDATION",
    "VALIDATION_POLICY",
    "usable_features",
    "validate_features",
]
