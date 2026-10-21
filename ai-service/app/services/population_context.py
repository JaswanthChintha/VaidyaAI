from __future__ import annotations

from bisect import bisect_right
from typing import Any, Dict, List, Optional, Sequence

from app.core.logging import get_logger, safe_meta
from app.data.feature_catalog import (
    CANONICAL_FEATURES,
    FEATURES,
    is_finite_number,
    normalize_gender,
)
from app.data.validation_rules import rule_for
from app.data.unit_conversions import conversion_for, is_known_unit, normalize_unit
from app.population.policy import (
    DISCLAIMER,
    GENERAL_LIMITATIONS,
    PER_FEATURE_DOES_NOT_MEAN,
    PER_FEATURE_MEANS,
    VERSION,
    WHAT_THIS_DOES_NOT_MEAN,
    WHAT_THIS_MEANS,
    PopulationReason,
)
from app.population.tables import (
    COVERED_FEATURES,
    TABLE_SEXES,
    Cohort,
    PopulationTable,
    excluded_reason,
    inventory,
    reason_message,
    table_for,
)
from app.schemas.population import (
    POSITION_AT_OR_ABOVE_HIGHEST,
    POSITION_BELOW_LOWEST,
    POSITION_BETWEEN,
    MatchedCohort,
    PercentileBand,
    PopulationComparison,
    PopulationContextData,
    PopulationContextRequest,
    PopulationFeatureContext,
    PopulationMeasurementInput,
    PopulationSummary,
    SubjectContext,
    SubmittedValue,
)

logger = get_logger(__name__)

POPULATION_SERVICE_VERSION = "1.0.0"

_VALUE_DECIMALS = 4

_FEATURE_LABELS: Dict[str, str] = {
    "hba1c": "HbA1c",
    "hemoglobin": "haemoglobin",
    "vitamin_d": "vitamin D",
    "vitamin_b12": "vitamin B12",
    "creatinine": "creatinine",
    "cholesterol": "total cholesterol",
    "bmi": "BMI",
}


def _label_for(feature: str) -> str:
    return _FEATURE_LABELS.get(feature, feature.replace("_", " "))


def _ordinal(percentile: float) -> str:
    if percentile != int(percentile):
        return f"{percentile:g}th"
    whole = int(percentile)
    if 10 <= whole % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(whole % 10, "th")
    return f"{whole}{suffix}"


def _band_label(lower: Optional[float], upper: Optional[float]) -> str:
    if lower is None and upper is not None:
        return f"below the {_ordinal(upper)} percentile"
    if upper is None and lower is not None:
        return f"at or above the {_ordinal(lower)} percentile"
    return (
        f"between the {_ordinal(lower)} and the "
        f"{_ordinal(upper)} percentile"
    )


def _bracket(
    value: float, grid: Sequence[float], values: Sequence[float]
) -> PercentileBand:
    index = bisect_right(list(values), value) - 1
    if index < 0:
        return PercentileBand(
            position=POSITION_BELOW_LOWEST,
            lower_percentile=None,
            upper_percentile=grid[0],
            lower_value=None,
            upper_value=values[0],
            label=_band_label(None, grid[0]),
        )
    if index >= len(grid) - 1:
        return PercentileBand(
            position=POSITION_AT_OR_ABOVE_HIGHEST,
            lower_percentile=grid[-1],
            upper_percentile=None,
            lower_value=values[-1],
            upper_value=None,
            label=_band_label(grid[-1], None),
        )
    return PercentileBand(
        position=POSITION_BETWEEN,
        lower_percentile=grid[index],
        upper_percentile=grid[index + 1],
        lower_value=values[index],
        upper_value=values[index + 1],
        label=_band_label(grid[index], grid[index + 1]),
    )


def _unavailable(feature: str, reason_code: str) -> PopulationFeatureContext:
    return PopulationFeatureContext(
        feature=feature,
        available=False,
        comparison=None,
        reason_code=reason_code,
        message=reason_message(reason_code),
    )


def _excluded(feature: str) -> Optional[PopulationFeatureContext]:
    entry = excluded_reason(feature)
    if entry is None:
        return None
    reason_code, message = entry
    return PopulationFeatureContext(
        feature=feature,
        available=False,
        comparison=None,
        reason_code=reason_code,
        message=message,
    )


def _to_table_unit(
    feature: str, value: float, unit_key: str, table_unit: str
) -> Optional[float]:
    if unit_key == table_unit:
        return value
    to_canonical = conversion_for(feature, unit_key)
    if to_canonical is None:
        return None
    from_table_unit = conversion_for(feature, table_unit)
    if from_table_unit is None:
        return None
    return from_table_unit.invert(to_canonical.apply(value))


def _is_physiologically_possible(feature: str, value: float, unit_key: str) -> bool:
    rule = rule_for(feature)
    if rule is None or not rule.is_numeric:
        return True
    if rule.possible_low is None and rule.possible_high is None:
        return True

    canonical = value
    if unit_key != rule.unit:
        conversion = conversion_for(feature, unit_key)
        if conversion is None:
            return True
        canonical = conversion.apply(value)

    if not is_finite_number(canonical):
        return False
    if rule.possible_low is not None and canonical < rule.possible_low:
        return False
    if rule.possible_high is not None and canonical > rule.possible_high:
        return False
    return True


def _unit_refusal(feature: str, unit: Optional[str]) -> Optional[str]:
    if unit is None or not str(unit).strip():
        return PopulationReason.UNIT_NOT_PROVIDED
    unit_key = normalize_unit(str(unit))
    if unit_key is None or not is_known_unit(unit_key):
        return PopulationReason.UNIT_NOT_RECOGNISED
    if conversion_for(feature, unit_key) is None:
        return PopulationReason.UNIT_NOT_CONVERTIBLE
    return None


def _matched_cohort(cohort: Cohort) -> MatchedCohort:
    return MatchedCohort(
        cohort_id=cohort.cohort_id,
        sex=cohort.sex,
        age_band_label=cohort.age_band_label,
        age_min=cohort.age_min,
        age_max=cohort.age_max,
        n_unweighted=cohort.n_unweighted,
        weighted_population=cohort.weighted_population,
        weighted_mean=cohort.weighted_mean,
    )


def _cohort_refusal(
    table: PopulationTable, sex: Optional[str], age: Optional[float]
) -> Optional[str]:
    if sex is None:
        return PopulationReason.SEX_COHORT_NOT_AVAILABLE
    if age is None:
        return PopulationReason.AGE_NOT_PROVIDED
    if table.cohort_for(sex, age) is not None:
        return None
    if table.dropped_for(sex, age) is not None:
        return PopulationReason.COHORT_TOO_SMALL_TO_PUBLISH
    if age < table.min_age:
        return PopulationReason.AGE_BELOW_ADULT_TABLE
    return PopulationReason.AGE_OUTSIDE_TABLE_RANGE


def _subject(request: PopulationContextRequest) -> SubjectContext:
    age = request.age
    age_source = "request" if age is not None else None
    raw_gender: Optional[str] = request.gender
    gender_source = "request" if raw_gender is not None else None

    snapshot = request.snapshot
    if snapshot is not None:
        if age is None:
            stored_age = snapshot.features.get("age")
            if stored_age is not None and is_finite_number(stored_age.value):
                age = float(stored_age.value)
                age_source = "snapshot"
        if raw_gender is None:
            stored_gender = snapshot.features.get("gender")
            if stored_gender is not None and stored_gender.value is not None:
                raw_gender = str(stored_gender.value)
                gender_source = "snapshot"

    normalised = normalize_gender(raw_gender) if raw_gender is not None else None
    sex_cohort = normalised if normalised in TABLE_SEXES else None

    return SubjectContext(
        age=age,
        age_source=age_source,
        gender=normalised,
        gender_source=gender_source if raw_gender is not None else None,
        gender_recognised=normalised is not None,
        sex_cohort=sex_cohort,
        sex_cohort_available=sex_cohort is not None,
    )


def _measurements(
    request: PopulationContextRequest,
) -> Dict[str, PopulationMeasurementInput]:
    if request.snapshot is None:
        return {m.feature: m for m in request.measurements}
    return {
        name: PopulationMeasurementInput(
            feature=name,
            value=stored.value,
            unit=stored.unit,
        )
        for name, stored in request.snapshot.features.items()
    }


def _context_for_feature(
    feature: str,
    submitted: Optional[PopulationMeasurementInput],
    subject: SubjectContext,
) -> PopulationFeatureContext:
    if feature not in CANONICAL_FEATURES:
        return _unavailable(feature, PopulationReason.UNKNOWN_FEATURE)

    excluded = _excluded(feature)
    if excluded is not None:
        return excluded

    table = table_for(feature)
    if table is None:
        return _unavailable(feature, PopulationReason.NO_VERIFIED_DISTRIBUTION)

    cohort_problem = _cohort_refusal(table, subject.sex_cohort, subject.age)
    if cohort_problem is not None:
        return _unavailable(feature, cohort_problem)

    if submitted is None or not is_finite_number(submitted.value):
        return _unavailable(feature, PopulationReason.VALUE_NOT_NUMERIC)

    unit_problem = _unit_refusal(feature, submitted.unit)
    if unit_problem is not None:
        return _unavailable(feature, unit_problem)

    unit_key = normalize_unit(str(submitted.unit))
    raw_value = float(submitted.value)

    if not _is_physiologically_possible(feature, raw_value, str(unit_key)):
        return _unavailable(
            feature, PopulationReason.VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE
        )

    converted = _to_table_unit(feature, raw_value, str(unit_key), table.unit)
    if converted is None:
        return _unavailable(feature, PopulationReason.UNIT_NOT_CONVERTIBLE)
    value = round(converted, _VALUE_DECIMALS)

    cohort = table.cohort_for(
        str(subject.sex_cohort), float(subject.age)
    )
    assert cohort is not None
    band = _bracket(value, table.percentile_grid, cohort.percentile_values)

    label = _label_for(feature)
    return PopulationFeatureContext(
        feature=feature,
        available=True,
        comparison=PopulationComparison(
            value=value,
            unit=table.unit,
            submitted=(
                None
                if unit_key == table.unit
                else SubmittedValue(value=raw_value, unit=str(unit_key))
            ),
            band=band,
            cohort=_matched_cohort(cohort),
            percentile_grid=list(table.percentile_grid),
            cohort_percentile_values=list(cohort.percentile_values),
            what_this_means=PER_FEATURE_MEANS.format(label=label),
            what_this_does_not_mean=PER_FEATURE_DOES_NOT_MEAN.format(label=label),
            table=table.reference(),
            table_notes=list(table.notes),
        ),
        reason_code=None,
        message=None,
    )


def population_context(request: PopulationContextRequest) -> PopulationContextData:
    subject = _subject(request)
    submitted = _measurements(request)

    if request.options.include_all_canonical:
        wanted: List[str] = list(CANONICAL_FEATURES)
    else:
        wanted = [name for name in CANONICAL_FEATURES if name in submitted]
    wanted += sorted(name for name in submitted if name not in CANONICAL_FEATURES)

    features: Dict[str, PopulationFeatureContext] = {}
    reason_counts: Dict[str, int] = {}
    available = 0
    for name in wanted:
        entry = _context_for_feature(name, submitted.get(name), subject)
        features[name] = entry
        if entry.available:
            available += 1
        elif entry.reason_code is not None:
            code = entry.reason_code
            reason_counts[code] = reason_counts.get(code, 0) + 1

    warnings: List[str] = []
    if subject.age is None:
        warnings.append(
            "No age was supplied, so no age-matched group could be chosen for "
            "any parameter."
        )
    if not subject.sex_cohort_available:
        warnings.append(
            "No population group could be matched on sex. The published "
            "survey groups are male and female only, and a stated gender is "
            "never reassigned to make a comparison possible."
        )

    logger.info(
        "population_context %s",
        safe_meta(
            module=31,
            features_examined=len(features),
            available=available,
            unavailable=len(features) - available,
            age_present=subject.age is not None,
            sex_cohort_matched=subject.sex_cohort_available,
            source="snapshot" if request.snapshot is not None else "measurements",
        ),
    )

    return PopulationContextData(
        patient_ref=request.patient_ref,
        policy_version=VERSION,
        subject=subject,
        features=features,
        summary=PopulationSummary(
            features_examined=len(features),
            available=available,
            unavailable=len(features) - available,
            reason_codes=dict(sorted(reason_counts.items())),
        ),
        what_this_means=WHAT_THIS_MEANS,
        what_this_does_not_mean=WHAT_THIS_DOES_NOT_MEAN,
        limitations=list(GENERAL_LIMITATIONS),
        disclaimer=DISCLAIMER,
        warnings=warnings,
    )


def population_document() -> Dict[str, Any]:
    return {
        "service_version": POPULATION_SERVICE_VERSION,
        "policy_version": VERSION,
        "covered_features": list(COVERED_FEATURES),
        "method": (
            "The value is converted into the table's unit through "
            "app/data/unit_conversions.py, then bracketed between the two "
            "adjacent published percentile cut-points of the matched (sex, "
            "age band) cohort. No percentile is interpolated and no model is "
            "called."
        ),
        "matching": (
            "One cohort, matched on sex AND age band. No all-adults cohort, "
            "no nearest-band fallback, no extrapolation. An unmatched request "
            "returns a reason code."
        ),
        "absence_policy": (
            "available=false carries no comparison object at all, so there is "
            "no value, no percentile and no band anywhere in that entry -- "
            "only a reason code and reviewed wording."
        ),
        "check_order": [
            "feature coverage",
            "cohort match (sex, then age)",
            "value is a finite number",
            "unit is present, recognised and convertible",
        ],
        "tables": inventory(),
    }


__all__ = [
    "POPULATION_SERVICE_VERSION",
    "population_context",
    "population_document",
]
