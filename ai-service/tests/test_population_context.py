from __future__ import annotations

import json
import math
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pytest

from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.unit_conversions import conversion_for
from app.data.validation_rules import rule_for
from app.population.policy import (
    DISCLAIMER,
    EXCLUDED_FEATURES,
    GENERAL_LIMITATIONS,
    PER_FEATURE_DOES_NOT_MEAN,
    PER_FEATURE_MEANS,
    REASON_MESSAGES,
    WHAT_THIS_DOES_NOT_MEAN,
    WHAT_THIS_MEANS,
    PopulationReason,
)
from app.population.tables import COVERED_FEATURES, TABLE_SEXES, TABLES
from app.schemas.features import FeatureProvenance
from app.schemas.population import (
    POSITION_AT_OR_ABOVE_HIGHEST,
    POSITION_BELOW_LOWEST,
    POSITION_BETWEEN,
    PercentileBand,
    PopulationComparison,
    PopulationContextRequest,
    PopulationFeatureContext,
)
from app.schemas.repository import FeatureSnapshot, StoredFeature
import app.services.population_context as population_context_module
from app.services.population_context import population_context, population_document


def ask(
    measurements: List[Dict[str, Any]],
    age: Optional[float] = 45,
    gender: Optional[str] = "male",
    **kwargs: Any,
):
    return population_context(
        PopulationContextRequest(
            age=age, gender=gender, measurements=measurements, **kwargs
        )
    )


def one(
    feature: str,
    value: Any = 6.8,
    unit: Optional[str] = "%",
    age: Optional[float] = 45,
    gender: Optional[str] = "male",
    **kwargs: Any,
) -> PopulationFeatureContext:
    data = ask(
        [{"feature": feature, "value": value, "unit": unit}],
        age=age,
        gender=gender,
        **kwargs,
    )
    return data.features[feature]


def stored(name: str, value: Any, unit: Optional[str] = None) -> StoredFeature:
    return StoredFeature(
        name=name,
        value=value,
        unit=unit,
        source="lab_report",
        provenance=FeatureProvenance(source="lab_report"),
    )


def numbers_in(blob: Any) -> List[float]:
    found: List[float] = []
    if isinstance(blob, dict):
        for value in blob.values():
            found.extend(numbers_in(value))
    elif isinstance(blob, list):
        for value in blob:
            found.extend(numbers_in(value))
    elif isinstance(blob, bool):
        pass
    elif isinstance(blob, (int, float)):
        found.append(float(blob))
    return found


def rederive(value: float, grid: List[float], values: List[float]):
    reached = sum(1 for published in values if published <= value)
    if reached == 0:
        return None, grid[0], f"below the {_ord(grid[0])} percentile"
    if reached >= len(grid):
        return grid[-1], None, f"at or above the {_ord(grid[-1])} percentile"
    low, high = grid[reached - 1], grid[reached]
    return low, high, f"between the {_ord(low)} and the {_ord(high)} percentile"


def _ord(percentile: float) -> str:
    if percentile != int(percentile):
        return f"{percentile:g}th"
    whole = int(percentile)
    if 10 <= whole % 100 <= 20:
        return f"{whole}th"
    return f"{whole}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(whole % 10, 'th') }"


def _possible_band_in_table_unit(feature: str):
    rule = rule_for(feature)
    table_unit = TABLES[feature].unit
    if rule is None or not rule.is_numeric:
        return None, None

    def to_table(bound):
        if bound is None:
            return None
        return population_context_module._to_table_unit(
            feature, float(bound), str(rule.unit), table_unit
        )

    return to_table(rule.possible_low), to_table(rule.possible_high)


def _just_below(feature: str, lowest_published: float) -> float:
    low, _high = _possible_band_in_table_unit(feature)
    candidate = lowest_published - 1.0
    if low is None:
        return candidate
    return candidate if candidate > low else (low + lowest_published) / 2.0


def _just_above(feature: str, highest_published: float) -> float:
    _low, high = _possible_band_in_table_unit(feature)
    candidate = highest_published + 1.0
    if high is None:
        return candidate
    return candidate if candidate < high else (highest_published + high) / 2.0


GOOD_VALUE: Dict[str, float] = {
    "hba1c": 5.5,
    "hemoglobin": 14.0,
    "vitamin_d": 70.0,
    "vitamin_b12": 450.0,
    "creatinine": 0.9,
    "cholesterol": 190.0,
    "bmi": 27.0,
    "hematocrit": 42.0,
    "rbc_count": 4.7,
    "mcv": 89.0,
    "mch": 30.0,
    "mchc": 33.5,
    "wbc_count": 7.0,
    "neutrophils": 58.0,
    "lymphocytes": 30.0,
    "monocytes": 7.5,
    "eosinophils": 2.5,
    "basophils": 0.7,
    "platelet_count": 250.0,
}

COVERED = sorted(COVERED_FEATURES)


def good(feature: str, **overrides: Any) -> Dict[str, Any]:
    payload = {
        "feature": feature,
        "value": GOOD_VALUE[feature],
        "unit": TABLES[feature].unit,
    }
    payload.update(overrides)
    return payload


def test_the_comparison_object_cannot_carry_a_reason_and_the_parent_no_value():
    comparison_fields = set(PopulationComparison.model_fields)
    assert "reason_code" not in comparison_fields
    assert "message" not in comparison_fields
    assert comparison_fields.isdisjoint({"available", "reason", "unavailable_reason"})

    parent_fields = set(PopulationFeatureContext.model_fields)
    assert parent_fields == {
        "feature",
        "available",
        "comparison",
        "reason_code",
        "message",
    }
    assert parent_fields & {"value", "percentile", "band", "cohort", "unit"} == set()

    assert PopulationComparison.model_config["extra"] == "forbid"
    assert PopulationFeatureContext.model_config["extra"] == "forbid"


@pytest.mark.parametrize(
    "case",
    [
        ({"feature": "hba1c", "gender": "other"}, "SEX_COHORT_NOT_AVAILABLE"),
        ({"feature": "hba1c", "age": None}, "AGE_NOT_PROVIDED"),
        ({"feature": "hba1c", "age": 12}, "AGE_BELOW_ADULT_TABLE"),
        ({"feature": "hba1c", "value": "Not Detected"}, "VALUE_NOT_NUMERIC"),
        ({"feature": "hba1c", "unit": None}, "UNIT_NOT_PROVIDED"),
        ({"feature": "hba1c", "unit": "bananas"}, "UNIT_NOT_RECOGNISED"),
        ({"feature": "hba1c", "unit": "mg/dl"}, "UNIT_NOT_CONVERTIBLE"),
        ({"feature": "blood_glucose", "unit": "mg/dl", "value": 100},
         "NO_VERIFIED_DISTRIBUTION"),
        ({"feature": "hypertension", "value": 1, "unit": None},
         "FEATURE_NOT_CONTINUOUS"),
        ({"feature": "banana", "value": 1, "unit": "%"}, "UNKNOWN_FEATURE"),
    ],
)
def test_an_unavailable_entry_holds_no_number_anywhere_in_it(case):
    kwargs, expected = case
    entry = one(**kwargs)
    assert entry.available is False
    assert entry.reason_code == expected
    assert entry.comparison is None
    assert entry.message.strip()

    blob = json.loads(entry.model_dump_json())
    assert blob["comparison"] is None
    assert numbers_in(blob) == [], f"{expected} entry carries {numbers_in(blob)}"
    text = json.dumps(blob).lower()
    for forbidden in ("percentile_values", "cohort_id", "lower_percentile", "band"):
        assert forbidden not in text


def test_the_validator_rejects_an_available_entry_with_no_comparison():
    with pytest.raises(ValueError, match="no comparison"):
        PopulationFeatureContext(feature="hba1c", available=True, comparison=None)


def test_the_validator_rejects_an_unavailable_entry_with_no_reason():
    with pytest.raises(ValueError, match="reason_code"):
        PopulationFeatureContext(feature="hba1c", available=False)
    with pytest.raises(ValueError):
        PopulationFeatureContext(
            feature="hba1c", available=False, reason_code="AGE_NOT_PROVIDED"
        )
    with pytest.raises(ValueError):
        PopulationFeatureContext(feature="hba1c", available=False, message="because")


def test_the_validator_rejects_an_unavailable_entry_that_carries_a_comparison():
    entry = one(**good("hba1c"))
    assert entry.comparison is not None
    with pytest.raises(ValueError, match="NO comparison"):
        PopulationFeatureContext(
            feature="hba1c",
            available=False,
            comparison=entry.comparison,
            reason_code="AGE_NOT_PROVIDED",
            message="x",
        )


def test_the_validator_rejects_an_answer_that_also_carries_an_excuse():
    entry = one(**good("hba1c"))
    with pytest.raises(ValueError, match="must not also"):
        PopulationFeatureContext(
            feature="hba1c",
            available=True,
            comparison=entry.comparison,
            reason_code="AGE_NOT_PROVIDED",
            message="x",
        )


def test_an_unknown_reason_code_is_rejected_by_the_schema():
    with pytest.raises(ValueError):
        PopulationFeatureContext(
            feature="hba1c",
            available=False,
            reason_code="INVENTED_CODE",
            message="x",
        )


def test_a_whole_response_with_nothing_matchable_contains_no_number_at_all():
    data = ask(
        [good(name) for name in COVERED], age=None, gender="prefer_not_to_say"
    )
    blob = json.loads(data.model_dump_json())
    assert data.summary.available == 0
    assert data.summary.unavailable == len(COVERED)
    for entry in blob["features"].values():
        assert entry["comparison"] is None
        assert numbers_in(entry) == []
    text = json.dumps(blob)
    for cohort_id in (c.cohort_id for c in TABLES["hba1c"].cohorts):
        assert cohort_id not in text, "an unmatched cohort leaked into the response"


def test_the_band_model_has_no_field_a_single_percentile_could_go_in():
    assert set(PercentileBand.model_fields) == {
        "position",
        "lower_percentile",
        "upper_percentile",
        "lower_value",
        "upper_value",
        "label",
    }
    assert PercentileBand.model_config["extra"] == "forbid"


def test_the_service_contains_no_interpolation_arithmetic():
    import inspect

    import app.services.population_context as service

    source = inspect.getsource(service)
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    for banned in ("interpolat", "np.interp", "numpy"):
        assert banned not in body.lower().replace(
            "no interpolation", ""
        ).replace("interpolated", "").replace("interpolation", ""), banned
    assert "bisect_right" in body


@pytest.mark.parametrize("feature", COVERED)
def test_the_band_can_be_re_derived_by_hand_from_the_responses_own_grid(feature):
    table = TABLES[feature]
    unit = table.unit
    checked = 0
    for cohort in table.cohorts:
        gender = cohort.sex
        age = cohort.age_min
        published = list(cohort.percentile_values)
        probes: List[float] = [
            _just_below(feature, published[0]),
            _just_above(feature, published[-1]),
        ]
        for index, value in enumerate(published):
            probes.append(value)
            probes.append(round(value - 0.01, 4))
            probes.append(round(value + 0.01, 4))
            if index + 1 < len(published):
                probes.append(round((value + published[index + 1]) / 2, 4))
        _low, _high = _possible_band_in_table_unit(feature)
        probes = [
            p
            for p in probes
            if (_low is None or p >= _low) and (_high is None or p <= _high)
        ]
        for probe in probes:
            entry = one(
                feature=feature, value=probe, unit=unit, age=age, gender=gender
            )
            assert entry.available, f"{feature}/{cohort.cohort_id}/{probe}"
            comparison = entry.comparison
            assert comparison.cohort.cohort_id == cohort.cohort_id
            assert comparison.cohort_percentile_values == published
            assert comparison.percentile_grid == list(table.percentile_grid)

            low, high, label = rederive(
                comparison.value,
                comparison.percentile_grid,
                comparison.cohort_percentile_values,
            )
            band = comparison.band
            assert band.lower_percentile == low, f"{feature}/{probe}"
            assert band.upper_percentile == high, f"{feature}/{probe}"
            assert band.label == label
            checked += 1
    assert checked > 300


@pytest.mark.parametrize("feature", COVERED)
def test_every_reported_band_edge_is_a_published_cut_point(feature):
    table = TABLES[feature]
    grid = list(table.percentile_grid)
    for cohort in table.cohorts:
        values = list(cohort.percentile_values)
        for probe in (
            _just_below(feature, values[0]),
            values[3],
            (values[5] + values[6]) / 2,
            _just_above(feature, values[-1]),
        ):
            band = one(
                feature=feature,
                value=probe,
                unit=table.unit,
                age=cohort.age_min,
                gender=cohort.sex,
            ).comparison.band
            for edge in (band.lower_percentile, band.upper_percentile):
                assert edge is None or edge in grid
            for edge in (band.lower_value, band.upper_value):
                assert edge is None or edge in values


@pytest.mark.parametrize("feature", COVERED)
def test_the_three_positions_are_reported_exactly_where_they_are_true(feature):
    table = TABLES[feature]
    cohort = table.cohorts[0]
    values = list(cohort.percentile_values)
    grid = list(table.percentile_grid)

    def band_for(probe):
        return one(
            feature=feature,
            value=probe,
            unit=table.unit,
            age=cohort.age_min,
            gender=cohort.sex,
        ).comparison.band

    below = band_for(_just_below(feature, values[0]))
    assert below.position == POSITION_BELOW_LOWEST
    assert below.lower_percentile is None and below.lower_value is None
    assert below.upper_percentile == grid[0] and below.upper_value == values[0]
    assert below.label == f"below the {_ord(grid[0])} percentile"

    top = band_for(_just_above(feature, values[-1]))
    assert top.position == POSITION_AT_OR_ABOVE_HIGHEST
    assert top.upper_percentile is None and top.upper_value is None
    assert top.lower_percentile == grid[-1] and top.lower_value == values[-1]

    assert band_for(values[-1]).position == POSITION_AT_OR_ABOVE_HIGHEST
    assert band_for(values[0]).position == POSITION_BETWEEN
    _tied_upper = max(g for g, v in zip(grid, values) if v == values[0])
    assert band_for(values[0]).lower_percentile == _tied_upper


def test_the_value_reported_is_the_value_that_was_bracketed_after_conversion():
    entry = one(feature="vitamin_d", value=30, unit="ng/mL", age=45, gender="male")
    comparison = entry.comparison
    assert comparison.unit == "nmol/l"
    assert comparison.value == pytest.approx(74.88, abs=0.005)
    assert comparison.submitted.value == 30.0
    assert comparison.submitted.unit == "ng/ml"
    low, high, label = rederive(
        comparison.value,
        comparison.percentile_grid,
        comparison.cohort_percentile_values,
    )
    assert (comparison.band.lower_percentile, comparison.band.upper_percentile) == (
        low,
        high,
    )
    assert comparison.band.label == label
    cohort = TABLES["vitamin_d"].cohort_for("male", 45)
    assert comparison.cohort_percentile_values == list(cohort.percentile_values)


def test_a_value_already_in_the_tables_unit_reports_no_conversion():
    entry = one(feature="vitamin_d", value=74.88, unit="nmol/L")
    assert entry.comparison.submitted is None
    assert entry.comparison.value == 74.88
    entry = one(**good("hba1c"))
    assert entry.comparison.submitted is None


def test_an_affine_unit_conversion_is_applied_through_the_audited_table():
    entry = one(feature="hba1c", value=48, unit="mmol/mol")
    conversion = conversion_for("hba1c", "mmol/mol")
    expected = round(conversion.apply(48.0), 4)
    assert entry.comparison.value == pytest.approx(expected, abs=1e-6)
    assert entry.comparison.unit == "%"
    assert entry.comparison.submitted.unit == "mmol/mol"


@pytest.mark.parametrize(
    "gender", ["other", "prefer_not_to_say", None, "", "martian", "nonbinary", "X"]
)
@pytest.mark.parametrize("feature", COVERED)
def test_a_stated_gender_is_never_coerced_to_force_a_lookup(gender, feature):
    entry = one(**good(feature), gender=gender, age=45)
    assert entry.available is False
    assert entry.reason_code == PopulationReason.SEX_COHORT_NOT_AVAILABLE
    assert entry.comparison is None
    assert numbers_in(json.loads(entry.model_dump_json())) == []


@pytest.mark.parametrize(
    "gender", ["other", "prefer_not_to_say", None, "martian", ""]
)
def test_the_subject_echo_never_claims_a_stratum_it_does_not_have(gender):
    data = ask([good("hba1c")], gender=gender, age=45)
    assert data.subject.sex_cohort is None
    assert data.subject.sex_cohort_available is False
    assert data.subject.sex_cohort not in TABLE_SEXES
    assert any("never reassigned" in w for w in data.warnings)


def test_a_recognised_gender_with_no_stratum_is_distinguished_from_an_unread_one():
    for gender in ("other", "prefer_not_to_say"):
        subject = ask([good("hba1c")], gender=gender).subject
        assert subject.gender_recognised is True
        assert subject.gender == gender
        assert subject.sex_cohort_available is False
    subject = ask([good("hba1c")], gender="martian").subject
    assert subject.gender_recognised is False
    assert subject.gender is None
    assert subject.sex_cohort_available is False


@pytest.mark.parametrize("gender", ["male", "Male", "MALE", "m", "M", "female", "F"])
def test_the_module_2_vocabulary_is_accepted_in_the_spellings_it_stores(gender):
    subject = ask([good("hba1c")], gender=gender).subject
    assert subject.sex_cohort in TABLE_SEXES
    assert subject.sex_cohort_available is True


@pytest.mark.parametrize("feature", COVERED)
def test_a_missing_age_refuses_rather_than_borrowing_an_all_adults_group(feature):
    entry = one(**good(feature), age=None, gender="female")
    assert entry.reason_code == PopulationReason.AGE_NOT_PROVIDED
    assert entry.comparison is None


@pytest.mark.parametrize("age", [0, 0.5, 2, 10, 15, 17, 19, 19.99])
@pytest.mark.parametrize("feature", COVERED)
def test_a_child_is_never_scored_against_an_adult_table(age, feature):
    entry = one(**good(feature), age=age)
    assert entry.reason_code == PopulationReason.AGE_BELOW_ADULT_TABLE
    assert entry.reason_code != PopulationReason.AGE_OUTSIDE_TABLE_RANGE
    assert entry.comparison is None
    assert "adults only" in entry.message.lower()


@pytest.mark.parametrize(
    "age",
    [
        20,
        20.0,
        45,
        79,
        80,
        99,
        120,
        130,
        20.5,
        29.5,
        29.999,
        30.5,
        79.9,
        80.5,
    ],
)
def test_every_adult_age_including_the_open_top_band_finds_a_cohort(age):
    entry = one(**good("hba1c"), age=age)
    assert entry.available is True
    cohort = entry.comparison.cohort
    completed = math.floor(age)
    assert cohort.age_min <= completed
    assert cohort.age_max is None or completed <= cohort.age_max


def test_a_fractional_age_lands_in_the_same_cohort_as_its_completed_year():
    for fractional, whole in ((20.5, 20), (29.5, 29), (30.9, 30), (79.9, 79), (80.5, 80)):
        fractional_entry = one(**good("hba1c"), age=fractional)
        whole_entry = one(**good("hba1c"), age=whole)
        assert fractional_entry.available is True
        assert (
            fractional_entry.comparison.cohort.cohort_id
            == whole_entry.comparison.cohort.cohort_id
        ), f"age {fractional} did not match age {whole}"

    assert one(**good("hba1c"), age=19.99).reason_code == (
        PopulationReason.AGE_BELOW_ADULT_TABLE
    )


@pytest.mark.parametrize(
    "value", [None, "", "   ", "Not Detected", "negative", [], {}, True, False]
)
def test_a_value_that_is_not_a_finite_number_is_refused(value):
    entry = one(feature="hba1c", value=value, unit="%")
    assert entry.reason_code == PopulationReason.VALUE_NOT_NUMERIC
    assert entry.comparison is None


def test_a_feature_with_no_submitted_value_at_all_is_refused_not_omitted():
    data = ask(
        [good("hba1c")],
        options={"include_all_canonical": True},
    )
    assert set(data.features) == set(CANONICAL_FEATURES)
    assert data.features["hba1c"].available is True
    assert (
        data.features["creatinine"].reason_code == PopulationReason.VALUE_NOT_NUMERIC
    )
    assert data.features["blood_glucose"].reason_code == (
        PopulationReason.NO_VERIFIED_DISTRIBUTION
    )


@pytest.mark.parametrize(
    "unit,expected",
    [
        (None, PopulationReason.UNIT_NOT_PROVIDED),
        ("", PopulationReason.UNIT_NOT_PROVIDED),
        ("   ", PopulationReason.UNIT_NOT_PROVIDED),
        ("bananas", PopulationReason.UNIT_NOT_RECOGNISED),
        ("!!", PopulationReason.UNIT_NOT_RECOGNISED),
        ("mg/dl", PopulationReason.UNIT_NOT_CONVERTIBLE),
        ("g/dl", PopulationReason.UNIT_NOT_CONVERTIBLE),
    ],
)
def test_the_three_unit_refusals_stay_distinct(unit, expected):
    entry = one(feature="hba1c", value=6.8, unit=unit)
    assert entry.reason_code == expected
    assert entry.comparison is None


@pytest.mark.parametrize("feature", ["blood_glucose", "triglycerides"])
def test_the_fasting_dependent_analytes_are_refused_with_their_own_wording(feature):
    entry = one(feature=feature, value=100, unit="mg/dl", age=45, gender="male")
    assert entry.available is False
    assert entry.reason_code == PopulationReason.NO_VERIFIED_DISTRIBUTION
    assert entry.message == EXCLUDED_FEATURES[feature]["message"]
    assert "fasting" in entry.message.lower()
    assert entry.message != REASON_MESSAGES[PopulationReason.NO_VERIFIED_DISTRIBUTION]


@pytest.mark.parametrize(
    "feature", ["hypertension", "heart_disease", "smoking_history", "age", "gender"]
)
def test_a_non_measurement_is_refused_as_not_continuous(feature):
    entry = one(feature=feature, value=1, unit=None, age=45, gender="male")
    assert entry.reason_code == PopulationReason.FEATURE_NOT_CONTINUOUS
    assert entry.message == EXCLUDED_FEATURES[feature]["message"]


def test_a_name_the_service_does_not_know_still_gets_an_answer():
    data = ask([{"feature": "banana", "value": 1, "unit": "%"}])
    assert data.features["banana"].reason_code == PopulationReason.UNKNOWN_FEATURE
    assert data.features["banana"].comparison is None


def test_coverage_is_decided_before_anything_about_the_request():
    entry = one(feature="triglycerides", value="junk", unit=None, age=None, gender="x")
    assert entry.reason_code == PopulationReason.NO_VERIFIED_DISTRIBUTION


def test_the_cohort_is_decided_before_the_value_and_the_unit():
    data = ask(
        [
            {"feature": "hba1c", "value": "junk", "unit": "bananas"},
            {"feature": "bmi", "value": None, "unit": None},
        ],
        age=None,
        gender="male",
    )
    assert {e.reason_code for e in data.features.values()} == {
        PopulationReason.AGE_NOT_PROVIDED
    }


def test_sex_is_decided_before_age():
    entry = one(**good("hba1c"), age=None, gender="other")
    assert entry.reason_code == PopulationReason.SEX_COHORT_NOT_AVAILABLE
    entry = one(**good("hba1c"), age=10, gender="other")
    assert entry.reason_code == PopulationReason.SEX_COHORT_NOT_AVAILABLE


def test_the_value_is_decided_before_the_unit():
    entry = one(feature="hba1c", value="junk", unit="bananas")
    assert entry.reason_code == PopulationReason.VALUE_NOT_NUMERIC


@pytest.mark.parametrize("feature", COVERED)
def test_the_matched_cohort_is_always_the_one_the_table_would_return(feature):
    table = TABLES[feature]
    for cohort in table.cohorts:
        for age in [cohort.age_min, cohort.age_max or 99]:
            comparison = one(
                **good(feature), age=age, gender=cohort.sex
            ).comparison
            assert comparison.cohort.cohort_id == cohort.cohort_id
            assert comparison.cohort.sex == cohort.sex
            assert comparison.cohort.n_unweighted == cohort.n_unweighted
            assert comparison.cohort.age_min == cohort.age_min
            assert comparison.cohort.age_max == cohort.age_max


def test_a_male_and_a_female_of_the_same_age_get_different_haemoglobin_cohorts():
    male = one(**good("hemoglobin"), age=45, gender="male").comparison
    female = one(**good("hemoglobin"), age=45, gender="female").comparison
    assert male.cohort.cohort_id != female.cohort.cohort_id
    assert male.cohort_percentile_values != female.cohort_percentile_values
    assert male.value == female.value


def test_the_policy_says_out_loud_that_no_unmatched_cohort_is_offered():
    document = population_document()
    assert "no all-adults cohort" in document["matching"].lower()
    assert "no nearest-band fallback" in document["matching"].lower()
    assert "no percentile is interpolated" in document["method"].lower()
    assert "no comparison object at all" in document["absence_policy"].lower()
    assert document["check_order"][0] == "feature coverage"


BANNED_IN_POSITIVE_COPY = (
    "risk",
    "normal",
    "abnormal",
    "healthy",
    "unhealthy",
    "should",
    "recommend",
    "advis",
    "diagnos",
    "treat",
    "danger",
    "deficien",
    "elevated",
    "concerning",
)


@pytest.mark.parametrize("feature", COVERED)
def test_the_per_feature_copy_states_only_how_common_a_value_is(feature):
    comparison = one(**good(feature)).comparison
    for text in (comparison.what_this_means, comparison.band.label):
        lowered = text.lower()
        for banned in BANNED_IN_POSITIVE_COPY:
            assert banned not in lowered, f"{feature}: {text!r} says {banned!r}"
    assert comparison.what_this_means.startswith("Of people of this age and sex")

    assert "at or below" in comparison.what_this_means
    assert "lower than yours" not in comparison.what_this_means


@pytest.mark.parametrize("feature", COVERED)
def test_every_emitted_sentence_comes_from_policy_py(feature):
    comparison = one(**good(feature)).comparison

    label = population_context_module._label_for(feature)
    assert comparison.what_this_means == PER_FEATURE_MEANS.format(label=label)
    assert comparison.what_this_does_not_mean == PER_FEATURE_DOES_NOT_MEAN.format(
        label=label
    )
    assert re.fullmatch(
        r"(between the [\d.]+(st|nd|rd|th) and the [\d.]+(st|nd|rd|th) percentile"
        r"|below the [\d.]+(st|nd|rd|th) percentile"
        r"|at or above the [\d.]+(st|nd|rd|th) percentile)",
        comparison.band.label,
    ), comparison.band.label


def test_the_negating_copy_only_ever_negates():
    for text in (
        WHAT_THIS_DOES_NOT_MEAN,
        PER_FEATURE_DOES_NOT_MEAN,
        DISCLAIMER,
        *GENERAL_LIMITATIONS,
    ):
        for sentence in re.split(r"(?<=[.;])\s+", text):
            lowered = sentence.lower()
            if any(word in lowered for word in ("normal", "healthy", "diagnos")):
                assert (
                    "not" in lowered or "cannot" in lowered
                ), f"unqualified judgement word in: {sentence!r}"


def test_the_response_repeats_the_reviewed_disclaimers_verbatim():
    data = ask([good("hba1c")])
    assert data.what_this_means == WHAT_THIS_MEANS
    assert data.what_this_does_not_mean == WHAT_THIS_DOES_NOT_MEAN
    assert data.disclaimer == DISCLAIMER
    assert data.limitations == list(GENERAL_LIMITATIONS)
    assert "not a medical assessment" in data.disclaimer.lower()


def test_module_31_never_mentions_the_reference_range_as_a_verdict():
    data = ask([good(name) for name in COVERED])
    blob = json.dumps(json.loads(data.model_dump_json())).lower()
    hits = 0
    for index in range(len(blob)):
        if blob.startswith("reference range", index):
            hits += 1
            sentence = blob[max(0, index - 150) : index + 150]
            assert "not" in sentence, sentence
    assert hits, "the disclaimer that this is not a reference range vanished"


def test_the_service_calls_no_model():
    import inspect

    import app.services.population_context as service

    source = inspect.getsource(service)
    for banned in ("gemini", "genai", "openai", "requests.", "httpx"):
        assert banned not in source.lower(), banned


def test_age_and_gender_are_read_from_a_snapshot_when_not_given_directly():
    snapshot = FeatureSnapshot(
        features={
            "age": stored("age", 55),
            "gender": stored("gender", "female"),
            "hba1c": stored("hba1c", 5.9, "%"),
        }
    )
    data = population_context(
        PopulationContextRequest(snapshot=snapshot, measurements=[])
    )
    assert data.subject.age == 55
    assert data.subject.age_source == "snapshot"
    assert data.subject.sex_cohort == "female"
    assert data.subject.gender_source == "snapshot"
    assert data.features["hba1c"].comparison.cohort.sex == "female"
    assert data.features["hba1c"].comparison.cohort.age_band_label == "50-59 years"


def test_an_explicitly_stated_age_and_gender_win_over_the_snapshots():
    snapshot = FeatureSnapshot(
        features={
            "age": stored("age", 25),
            "gender": stored("gender", "female"),
            "hba1c": stored("hba1c", 5.9, "%"),
        }
    )
    data = population_context(
        PopulationContextRequest(snapshot=snapshot, age=65, gender="male")
    )
    assert data.subject.age == 65
    assert data.subject.age_source == "request"
    assert data.subject.sex_cohort == "male"
    assert data.features["hba1c"].comparison.cohort.cohort_id == "male_60_69"


def test_a_snapshots_gender_of_other_is_not_coerced_either():
    snapshot = FeatureSnapshot(
        features={
            "age": stored("age", 40),
            "gender": stored("gender", "other"),
            "hba1c": stored("hba1c", 5.9, "%"),
        }
    )
    data = population_context(PopulationContextRequest(snapshot=snapshot))
    assert data.subject.sex_cohort_available is False
    assert data.features["hba1c"].reason_code == (
        PopulationReason.SEX_COHORT_NOT_AVAILABLE
    )


def test_a_feature_module_6_rejected_cannot_reach_a_percentile_lookup():
    snapshot = FeatureSnapshot(
        features={"age": stored("age", 40), "gender": stored("gender", "male")},
        unavailable={
            "hba1c": {
                "name": "hba1c",
                "availability": "rejected",
                "reason_code": "IMPLAUSIBLE",
                "reason": "out of range",
            }
        },
    )
    data = population_context(PopulationContextRequest(snapshot=snapshot))
    assert "hba1c" not in data.features
    assert set(data.features) == {"age", "gender"}
    assert data.summary.available == 0


def test_a_snapshot_value_with_no_stored_unit_is_refused_not_assumed():
    snapshot = FeatureSnapshot(
        features={
            "age": stored("age", 40),
            "gender": stored("gender", "male"),
            "hba1c": stored("hba1c", 5.9, None),
        }
    )
    data = population_context(PopulationContextRequest(snapshot=snapshot))
    assert data.features["hba1c"].reason_code == PopulationReason.UNIT_NOT_PROVIDED


def test_the_same_request_twice_produces_the_same_answer():
    payload = dict(
        age=45,
        gender="male",
        measurements=[good(name) for name in COVERED],
    )
    first = population_context(PopulationContextRequest(**payload))
    second = population_context(PopulationContextRequest(**payload))
    exclude = {"generated_at"}
    assert first.model_dump(exclude=exclude) == second.model_dump(exclude=exclude)


def test_the_order_of_the_response_comes_from_the_catalogue_not_the_request():
    forward = ask([good("hba1c"), good("bmi"), good("creatinine")])
    backward = ask([good("creatinine"), good("bmi"), good("hba1c")])
    assert list(forward.features) == list(backward.features)
    assert list(forward.features) == [
        n for n in CANONICAL_FEATURES if n in {"hba1c", "bmi", "creatinine"}
    ]


def test_unknown_names_are_appended_in_a_stable_order_after_the_canonical_ones():
    data = ask(
        [
            {"feature": "zebra", "value": 1, "unit": "%"},
            good("hba1c"),
            {"feature": "aardvark", "value": 1, "unit": "%"},
        ]
    )
    assert list(data.features) == ["hba1c", "aardvark", "zebra"]


def test_the_summary_counts_agree_with_the_entries_they_summarise():
    data = ask(
        [good("hba1c"), good("bmi"), {"feature": "hemoglobin", "value": "x", "unit": None}],
    )
    assert data.summary.features_examined == len(data.features)
    assert data.summary.available == sum(
        1 for e in data.features.values() if e.available
    )
    assert data.summary.unavailable == sum(
        1 for e in data.features.values() if not e.available
    )
    counted: Dict[str, int] = {}
    for entry in data.features.values():
        if not entry.available:
            counted[entry.reason_code] = counted.get(entry.reason_code, 0) + 1
    assert data.summary.reason_codes == counted


def test_the_summary_carries_no_value_or_percentile():
    data = ask([good(name) for name in COVERED])
    blob = json.loads(data.model_dump_json())["summary"]
    assert set(blob) == {
        "features_examined",
        "available",
        "unavailable",
        "reason_codes",
    }


def test_nothing_about_the_patient_reaches_the_logs(caplog):
    with caplog.at_level(logging.INFO, logger="app.services.population_context"):
        ask(
            [{"feature": "hba1c", "value": 7.77, "unit": "%"}],
            age=53,
            gender="female",
            patient_ref="CANARY-PATIENT-REF",
        )
    text = " ".join(r.getMessage() for r in caplog.records)
    assert text, "the run logged nothing at all"
    for canary in ("CANARY-PATIENT-REF", "7.77", "53", "female"):
        assert canary not in text, f"{canary!r} reached the logs"
    assert "'module': 31" in text
    assert "age_present" in text


def test_the_patient_ref_is_echoed_and_never_used_for_anything():
    data = ask([good("hba1c")], patient_ref="ref-123")
    assert data.patient_ref == "ref-123"
    blob = json.loads(data.model_dump_json())
    assert json.dumps(blob["features"]).count("ref-123") == 0


def test_the_warnings_name_the_missing_field_rather_than_a_service_fault():
    data = ask([good("hba1c")], age=None, gender=None)
    assert any("No age was supplied" in w for w in data.warnings)
    assert any("male and female only" in w for w in data.warnings)
    matched = ask([good("hba1c")])
    assert matched.warnings == []


def test_a_physiologically_impossible_value_gets_no_band():
    for feature, value, unit in (
        ("hba1c", -3.0, "%"),
        ("hba1c", 500.0, "%"),
        ("bmi", -50.0, "kg/m2"),
        ("hemoglobin", 1e9, "g/dl"),
        ("creatinine", -1.0, "mg/dl"),
        ("vitamin_d", -5.0, "ng/ml"),
    ):
        entry = one(feature=feature, value=value, unit=unit)
        assert entry.available is False, f"{feature}={value} was given a band"
        assert entry.reason_code == (
            PopulationReason.VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE
        )
        assert entry.comparison is None
        assert numbers_in(entry.model_dump(mode="json")) == []


def test_the_plausibility_bound_is_checked_in_the_canonical_unit():
    assert one(feature="vitamin_d", value=300.0, unit="ng/ml").available is True
    entry = one(feature="vitamin_d", value=500.0, unit="ng/ml")
    assert entry.available is False
    assert entry.reason_code == PopulationReason.VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE
