"""Module 31 -- Population Context and Percentile Analysis. The lookup.

`app/population/policy.py` holds the reason codes and every patient-facing
string; `app/population/tables.py` holds the published distributions and the
checks that they are usable. This file contains the one piece of arithmetic
Module 31 performs: bracketing a value between two adjacent published
cut-points.

It is framework-independent -- no FastAPI, no network, NO LLM, no clock except
`generated_at` -- so Module 27 (dashboard) and Module 32 (doctor summary) can
call `population_context()` in-process exactly as they call `evaluate_rules()`
and `analyse_trends()`.

--------------------------------------------------------------------------
THE FOUR RULES THIS FILE EXISTS TO ENFORCE
--------------------------------------------------------------------------

1. A BAND, NEVER A NUMBER. The value is bracketed between two of the eleven
   published cut-points and the band is reported. Grep this file: there is no
   division by a percentile range and no linear interpolation anywhere in it.
   The reported `value` is the exact number that was bracketed, and the
   cohort's cut-points are shipped alongside it, so the band can be re-derived
   by hand from the response.

2. MATCHED OR NOTHING. A cohort is (sex, age band). There is no all-adults
   fallback, no nearest-band fallback, and no "close enough" cell. When no
   cell matches, the answer is a reason code -- `tables.cohort_for()` returns
   `None` and this file turns that into words.

3. A UNIT IS NEVER ASSUMED. Every conversion goes through
   `app/data/unit_conversions.py`, whose factors carry their arithmetic basis.
   An absent, unrecognised, or unconvertible unit is a refusal.

4. NO CLINICAL CLAIM. Nothing here says normal, abnormal, high, low, risky or
   recommended. Every emitted string comes from `policy.py` or from provenance
   recorded in the shipped table; the only text this file assembles is the
   band label, which is built from two numbers.

--------------------------------------------------------------------------
THE ORDER THE REFUSAL REASONS ARE CHECKED IN, AND WHY
--------------------------------------------------------------------------

More than one reason can be true at once, so the order is a real decision and
it is fixed here:

    1. is this feature covered at all  (UNKNOWN_FEATURE, the EXCLUDED_FEATURES
       reason, NO_VERIFIED_DISTRIBUTION)
    2. is there a cohort               (SEX_COHORT_NOT_AVAILABLE, then the
       AGE_* codes, then COHORT_TOO_SMALL_TO_PUBLISH)
    3. is the value usable             (VALUE_NOT_NUMERIC)
    4. is the unit usable              (the UNIT_* codes)

Feature coverage comes first because it is a fact about the feature and does
not change if the caller fixes anything about this request. Cohort matching
comes before the per-value checks because when age or gender cannot be
matched, EVERY feature is unavailable for the same reason -- and one coherent
explanation is more use to a reader than a mixture of unit complaints and
cohort complaints that all resolve to the same missing field.

--------------------------------------------------------------------------
LOGGING
--------------------------------------------------------------------------

Counts and codes only, through `safe_meta`. No value, no unit, no age, no
gender and no identifier is ever logged from this module.
"""

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

#: Decimal places the converted value is rounded to before it is bracketed.
#: The SAME rounded number is reported and compared, so the band in the
#: response is always the band you get by comparing the response's own `value`
#: against its own `cohort_percentile_values`. Rounding after bracketing would
#: let those two disagree at a boundary.
_VALUE_DECIMALS = 4

#: Feature label used in the per-feature copy. The catalogue's own
#: description is a sentence; these are the noun phrases that fit
#: `PER_FEATURE_MEANS`. Kept beside the copy they are substituted into.
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
    """A noun phrase for the per-feature copy.

    Falls back to the canonical name with underscores opened out. Every
    currently covered feature has an explicit entry; the fallback exists so a
    newly covered feature reads awkwardly rather than crashing.
    """
    return _FEATURE_LABELS.get(feature, feature.replace("_", " "))


# --------------------------------------------------------------------------
# Band wording
# --------------------------------------------------------------------------


def _ordinal(percentile: float) -> str:
    """`1.0 -> '1st'`, `2.5 -> '2.5th'`, `50.0 -> '50th'`.

    Only whole numbers take st/nd/rd; a fractional cut-point such as 97.5 is
    always "th", which is how NCHS prints them.
    """
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
    # Both edges present: `_bracket` only produces the three cases, and
    # PercentileBand's validator refuses any other combination.
    return (
        f"between the {_ordinal(lower)} and the "  # type: ignore[arg-type]
        f"{_ordinal(upper)} percentile"  # type: ignore[arg-type]
    )


def _bracket(
    value: float, grid: Sequence[float], values: Sequence[float]
) -> PercentileBand:
    """Place `value` between two adjacent published cut-points.

    `values` is the cohort's published value at each cut-point, ascending
    (`tables.py` refuses a table where it is not). `bisect_right` gives the
    number of cut-points whose value is at or below `value`, so `index` is the
    highest cut-point the value has reached:

    * `index < 0`            -- below the lowest published value.
    * `index == len-1`       -- at or above the highest published value.
    * otherwise              -- between `grid[index]` and `grid[index + 1]`.

    Repeated values in `values` (two cut-points that rounded to the same
    number) are handled correctly by construction: `bisect_right` lands past
    the last equal entry, which is the highest cut-point the value can be said
    to have reached. Nothing is interpolated in any branch.
    """
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


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _unavailable(feature: str, reason_code: str) -> PopulationFeatureContext:
    """An entry with a reason and, structurally, nothing else."""
    return PopulationFeatureContext(
        feature=feature,
        available=False,
        comparison=None,
        reason_code=reason_code,
        message=reason_message(reason_code),
    )


def _excluded(feature: str) -> Optional[PopulationFeatureContext]:
    """The deliberate exclusion for this feature, with ITS OWN wording."""
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
    """Convert a value in `unit_key` into the table's unit, or `None`.

    Both legs go through the audited `CONVERSIONS` table: the caller's unit to
    the feature's canonical unit, then canonical to the table's unit by
    inverting the table unit's own conversion. `tables.py` guarantees at
    import that the second leg exists for every shipped table, so `None` here
    can only mean the CALLER's unit has no verified conversion for this
    feature.

    The two-leg route is why NHANES' nmol/L vitamin D table can be used
    without rescaling the table: the patient's ng/mL value moves, the
    published numbers never do.
    """
    if unit_key == table_unit:
        return value
    to_canonical = conversion_for(feature, unit_key)
    if to_canonical is None:
        return None
    from_table_unit = conversion_for(feature, table_unit)
    if from_table_unit is None:  # pragma: no cover - refused at import
        return None
    return from_table_unit.invert(to_canonical.apply(value))


def _is_physiologically_possible(feature: str, value: float, unit_key: str) -> bool:
    """Is `value` inside Module 6's possible band for `feature`?

    THE COMPARISON HAPPENS IN THE CANONICAL UNIT, which is the unit
    `validation_rules` states its bounds in -- NOT the table's unit, which for
    vitamin D is nmol/L while the canonical unit is ng/mL. Checking an
    already-table-converted number against canonical bounds would reject real
    values and accept impossible ones, so the caller's value is moved to
    canonical here and nowhere else.

    Returns True when there is nothing to check against: a feature with no
    rule, a non-numeric rule, a bound that is absent on the relevant side, or
    a unit with no verified conversion (which `_unit_refusal` has already
    turned into its own refusal by the time this runs). This function's job is
    to catch the impossible, not to invent a limit Module 6 never stated.
    """
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
    """The UNIT_* reason code for this unit, or `None` when it is usable.

    The three codes are kept apart because they need different fixes: nothing
    was sent, something was sent that no lab prints, and something real was
    sent that has no verified conversion for THIS analyte.
    """
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
    """The reason no cohort matches, or `None` when one does.

    Never extrapolates and never widens a band. `AGE_BELOW_ADULT_TABLE` is
    separated from `AGE_OUTSIDE_TABLE_RANGE` because scoring a child against
    an adult distribution is a clinical error, not merely a miss.
    """
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


# --------------------------------------------------------------------------
# Reading age and gender out of the request
# --------------------------------------------------------------------------


def _subject(request: PopulationContextRequest) -> SubjectContext:
    """Resolve age and sex cohort, recording where each came from.

    Explicit request fields win over a snapshot's stored values, because the
    caller stated them for THIS call. Neither is ever defaulted: an absent age
    stays absent, and a gender outside the published strata leaves
    `sex_cohort` `None` rather than being pushed into the nearer category.
    """
    age = request.age
    age_source = "request" if age is not None else None
    raw_gender: Optional[str] = request.gender
    gender_source = "request" if raw_gender is not None else None

    snapshot = request.snapshot
    if snapshot is not None:
        if age is None:
            stored_age = snapshot.features.get("age")
            if stored_age is not None and is_finite_number(stored_age.value):
                age = float(stored_age.value)  # type: ignore[arg-type]
                age_source = "snapshot"
        if raw_gender is None:
            stored_gender = snapshot.features.get("gender")
            if stored_gender is not None and stored_gender.value is not None:
                raw_gender = str(stored_gender.value)
                gender_source = "snapshot"

    normalised = normalize_gender(raw_gender) if raw_gender is not None else None
    # `other` and `prefer_not_to_say` ARE recognised Module 2 categories; they
    # simply have no published stratum. The two facts are reported separately
    # so a consumer can tell "we did not understand you" from "the survey has
    # no group for you", which are different things to say to a person.
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
    """The submitted values, keyed by feature, from whichever source was used.

    From a snapshot, only `features` is read. Its `unavailable` entries have
    no `value` field at all by construction (Module 7's guarantee), so a value
    Module 6 rejected cannot reach a percentile lookup through this door.
    """
    if request.snapshot is None:
        return {m.feature: m for m in request.measurements}
    return {
        name: PopulationMeasurementInput(
            feature=name,
            value=stored.value,
            # Module 5 stores the canonical unit; when it could not, `unit` is
            # whatever it saw, and the UNIT_* checks below will refuse it.
            unit=stored.unit,
        )
        for name, stored in request.snapshot.features.items()
    }


# --------------------------------------------------------------------------
# The one feature lookup
# --------------------------------------------------------------------------


def _context_for_feature(
    feature: str,
    submitted: Optional[PopulationMeasurementInput],
    subject: SubjectContext,
) -> PopulationFeatureContext:
    """Place one feature's value, or say exactly why it could not be placed.

    The check order is the one documented in the module docstring and is not
    incidental: coverage, then cohort, then value, then unit.
    """
    if feature not in CANONICAL_FEATURES:
        return _unavailable(feature, PopulationReason.UNKNOWN_FEATURE)

    excluded = _excluded(feature)
    if excluded is not None:
        return excluded

    table = table_for(feature)
    if table is None:
        # Unreachable while `tables._check_catalogue_cover()` holds: a
        # canonical feature with no table must have an EXCLUDED_FEATURES entry,
        # which was answered above. Kept so a future edit degrades to a
        # refusal rather than an AttributeError on a live request.
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

    # PLAUSIBILITY, BORROWED FROM MODULE 6 RATHER THAN RE-DECIDED HERE.
    #
    # This endpoint accepts raw `measurements`, not a validated snapshot, so
    # nothing upstream has necessarily applied Module 6's bounds. Without this
    # an HbA1c of -3 % returned `available: true` and "below the 1st
    # percentile", and a haemoglobin of 1e9 g/dL returned "at or above the
    # 99th". Both statements are true of the published grid and neither makes
    # a clinical claim -- which is precisely the problem: they launder a
    # nonsense input into something that reads like a finding.
    #
    # `validation_rules.rule_for` is the SAME table Module 6 rejects on, so
    # there is one definition of "physiologically possible" on this project
    # and not two that can drift (MEMORY.md 11). A feature with no rule, or no
    # bound on a side, is not second-guessed here.
    if not _is_physiologically_possible(feature, raw_value, str(unit_key)):
        return _unavailable(
            feature, PopulationReason.VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE
        )

    converted = _to_table_unit(feature, raw_value, str(unit_key), table.unit)
    if converted is None:  # pragma: no cover - _unit_refusal already checked
        return _unavailable(feature, PopulationReason.UNIT_NOT_CONVERTIBLE)
    value = round(converted, _VALUE_DECIMALS)

    # `_cohort_refusal` returned None, so a cell exists for this (sex, age).
    cohort = table.cohort_for(
        str(subject.sex_cohort), float(subject.age)  # type: ignore[arg-type]
    )
    assert cohort is not None  # narrowed above; kept for type checkers
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


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def population_context(request: PopulationContextRequest) -> PopulationContextData:
    """Place one patient's values in age- and sex-matched population groups.

    Deterministic and side-effect free: the same request produces the same
    answer, apart from `generated_at`. Calls no model and reads no clock other
    than that.
    """
    subject = _subject(request)
    submitted = _measurements(request)

    # Response key order comes from the CATALOGUE, not from the order the
    # caller listed the measurements in, so two calls with the same data in a
    # different order produce identical output.
    if request.options.include_all_canonical:
        wanted: List[str] = list(CANONICAL_FEATURES)
    else:
        wanted = [name for name in CANONICAL_FEATURES if name in submitted]
    # A name the caller sent that is not canonical still gets an answer --
    # UNKNOWN_FEATURE -- rather than vanishing from a response the caller
    # would otherwise read as "nothing to say about it".
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
    """The service's own method, machine-readable. No patient data.

    Served next to `POLICY` and the table inventory by
    `GET /api/v1/population/policy`, so a reviewer can see the method and the
    evidence behind it in one response.
    """
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
