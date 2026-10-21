from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import app.services.report_comparator as comparator
from app.data.feature_catalog import CANONICAL_FEATURES
from app.schemas.comparison import (
    ABN_CENSORED_INCONCLUSIVE,
    ABN_NO_REFERENCE_OR_FLAG,
    ABN_NO_USABLE_VALUE,
    ABN_RANGE_UNIT_NOT_COMPARABLE,
    ABN_UNKNOWN_FLAG,
    BASIS_NOT_DETERMINABLE,
    BASIS_PRINTED_FLAG,
    BASIS_REFERENCE_RANGE,
    BASIS_REFERENCE_RANGE_CONVERTED,
    CATEGORY_CHANGED_DIRECTION_ONLY,
    CATEGORY_IMPROVED,
    CATEGORY_NEWLY_ABNORMAL,
    CATEGORY_NEWLY_NORMAL,
    CATEGORY_NOT_CLASSIFIABLE,
    CATEGORY_UNCHANGED,
    CATEGORY_VALUES,
    CATEGORY_WORSENED,
    CHANGE_IMPROVED,
    CHANGE_UNCHANGED,
    CHANGE_WORSENED,
    COMPARISON_CHANGE_CLASSIFIED,
    COMPARISON_IN_NEITHER,
    COMPARISON_ONLY_IN_BASELINE,
    COMPARISON_ONLY_IN_COMPARISON,
    COMPARISON_OUTCOME_VALUES,
    INHERITED_REFUSAL_OUTCOMES,
    NOT_DETERMINABLE_BASELINE,
    NOT_DETERMINABLE_BOTH,
    NOT_DETERMINABLE_COMPARISON,
    SELECTION_EXPLICIT,
    SELECTION_FIRST_VS_LATEST,
    TRANSITION_CLASSIFIED,
    TRANSITION_NEWLY_ABNORMAL,
    TRANSITION_NEWLY_NORMAL,
    TRANSITION_REMAINED_ABNORMAL,
    TRANSITION_REMAINED_NORMAL,
    AbnormalityState,
    ParameterComparison,
    ReportComparisonRequest,
)
from app.schemas.timeline import (
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_TREND_CLASSIFIED,
    OUTCOME_UNIT_MISMATCH,
    OUTCOME_VALUES,
    TREND_VALUES,
    TimelineTrendsRequest,
)
from app.services.report_comparator import compare_reports
from app.services.trend_analyzer import analyse_trends
from tests.trend_payloads import (
    CREATININE_UMOL_CONVERSION,
    rejection,
    report,
    vf,
)


def compare(reports: List[Dict[str, Any]], **kwargs: Any):
    options = kwargs.pop("options", None)
    request: Dict[str, Any] = {"reports": reports}
    request.update(kwargs)
    if options:
        request["options"] = options
    return compare_reports(ReportComparisonRequest(**request))


def pair_of(baseline: Dict[str, Any], comparison: Dict[str, Any], **kwargs: Any):
    return compare(
        [
            report("r1", "2024-01-01T00:00:00Z", baseline),
            report("r2", "2024-06-01T00:00:00Z", comparison),
        ],
        **kwargs,
    )


def cholesterol(value: float, **provenance: Any) -> Dict[str, Any]:
    provenance.setdefault("reference_high", 200.0)
    provenance.setdefault("reference_range_raw", "< 200")
    provenance.setdefault("reference_unit", "mg/dl")
    return vf("cholesterol", value, "mg/dl", **provenance)


def vitamin_d(value: float, **provenance: Any) -> Dict[str, Any]:
    provenance.setdefault("reference_low", 30.0)
    provenance.setdefault("reference_high", 100.0)
    provenance.setdefault("reference_range_raw", "30 - 100")
    return vf("vitamin_d", value, "ng/ml", **provenance)


def test_a_reading_crossing_its_own_reports_printed_bound_is_newly_abnormal():
    parameter = pair_of(
        {"cholesterol": cholesterol(190.0)}, {"cholesterol": cholesterol(240.0)}
    ).parameters["cholesterol"]

    assert parameter.baseline.abnormal is False
    assert parameter.baseline.basis == BASIS_REFERENCE_RANGE
    assert parameter.comparison.abnormal is True
    assert parameter.transition_outcome == TRANSITION_CLASSIFIED
    assert parameter.transition == TRANSITION_NEWLY_ABNORMAL
    assert parameter.category == CATEGORY_NEWLY_ABNORMAL
    assert parameter.outcome == COMPARISON_CHANGE_CLASSIFIED
    assert parameter.change_class == CHANGE_WORSENED
    assert parameter.significant is True


def test_an_unknown_baseline_is_not_determinable_never_newly_abnormal():
    parameter = pair_of(
        {"cholesterol": vf("cholesterol", 190.0, "mg/dl")},
        {"cholesterol": cholesterol(240.0)},
    ).parameters["cholesterol"]

    assert parameter.baseline.abnormal is None
    assert parameter.baseline.basis == BASIS_NOT_DETERMINABLE
    assert parameter.baseline.reason_code == ABN_NO_REFERENCE_OR_FLAG
    assert parameter.transition_outcome == NOT_DETERMINABLE_BASELINE
    assert parameter.transition is None
    assert parameter.category != CATEGORY_NEWLY_ABNORMAL
    assert parameter.category != CATEGORY_UNCHANGED
    assert parameter.category == CATEGORY_WORSENED
    assert "could not be established for the baseline report" in parameter.reason
    assert "It is not assumed to be inside." in parameter.baseline.reason


def test_an_unknown_comparison_side_is_equally_refused():
    parameter = pair_of(
        {"cholesterol": cholesterol(190.0)},
        {"cholesterol": vf("cholesterol", 240.0, "mg/dl")},
    ).parameters["cholesterol"]

    assert parameter.comparison.abnormal is None
    assert parameter.transition_outcome == NOT_DETERMINABLE_COMPARISON
    assert parameter.transition is None
    assert parameter.category != CATEGORY_NEWLY_ABNORMAL


def test_neither_side_known_is_not_determinable_both():
    parameter = pair_of(
        {"cholesterol": vf("cholesterol", 190.0, "mg/dl")},
        {"cholesterol": vf("cholesterol", 240.0, "mg/dl")},
    ).parameters["cholesterol"]

    assert parameter.baseline.abnormal is None
    assert parameter.comparison.abnormal is None
    assert parameter.transition_outcome == NOT_DETERMINABLE_BOTH
    assert parameter.transition is None


def test_newly_normal_is_the_exact_mirror_and_held_to_the_same_bar():
    parameter = pair_of(
        {"vitamin_d": vitamin_d(22.0)}, {"vitamin_d": vitamin_d(35.0)}
    ).parameters["vitamin_d"]

    assert parameter.baseline.abnormal is True
    assert parameter.comparison.abnormal is False
    assert parameter.transition == TRANSITION_NEWLY_NORMAL
    assert parameter.category == CATEGORY_NEWLY_NORMAL
    assert parameter.change_class == CHANGE_IMPROVED


def test_newly_normal_is_refused_when_the_baseline_side_is_unknown():
    parameter = pair_of(
        {"vitamin_d": vf("vitamin_d", 22.0, "ng/ml")},
        {"vitamin_d": vitamin_d(35.0)},
    ).parameters["vitamin_d"]

    assert parameter.transition_outcome == NOT_DETERMINABLE_BASELINE
    assert parameter.transition is None
    assert parameter.category != CATEGORY_NEWLY_NORMAL


def test_remained_abnormal_and_remained_normal_are_distinguished():
    stayed_high = pair_of(
        {"cholesterol": cholesterol(240.0)}, {"cholesterol": cholesterol(260.0)}
    ).parameters["cholesterol"]
    stayed_fine = pair_of(
        {"cholesterol": cholesterol(190.0)}, {"cholesterol": cholesterol(191.0)}
    ).parameters["cholesterol"]

    assert stayed_high.transition == TRANSITION_REMAINED_ABNORMAL
    assert stayed_fine.transition == TRANSITION_REMAINED_NORMAL
    assert stayed_fine.category == CATEGORY_UNCHANGED


@pytest.mark.parametrize(
    "baseline_features,expected_code",
    [
        pytest.param({}, ABN_NO_USABLE_VALUE, id="no_reading_at_all"),
        pytest.param(
            {"cholesterol": vf("cholesterol", 190.0, "mg/dl")},
            ABN_NO_REFERENCE_OR_FLAG,
            id="reading_but_no_range_or_flag",
        ),
        pytest.param(
            {
                "cholesterol": vf(
                    "cholesterol",
                    100.0,
                    "mg/dl",
                    censored="left",
                    reference_low=50.0,
                    reference_high=200.0,
                )
            },
            ABN_CENSORED_INCONCLUSIVE,
            id="censored_reading_unsettled",
        ),
    ],
)
def test_each_not_determinable_reason_code_is_reachable_and_reported(
    baseline_features, expected_code
):
    parameter = pair_of(
        baseline_features, {"cholesterol": cholesterol(240.0)}
    ).parameters["cholesterol"]

    assert parameter.baseline.abnormal is None
    assert parameter.baseline.reason_code == expected_code
    assert parameter.transition is None
    assert parameter.category != CATEGORY_NEWLY_ABNORMAL


def test_a_censored_reading_cannot_be_called_newly_abnormal():
    parameter = pair_of(
        {
            "cholesterol": vf(
                "cholesterol",
                100.0,
                "mg/dl",
                censored="left",
                reference_low=50.0,
                reference_high=200.0,
            )
        },
        {"cholesterol": cholesterol(240.0)},
    ).parameters["cholesterol"]

    assert parameter.baseline.reason_code == ABN_CENSORED_INCONCLUSIVE
    assert parameter.transition is None
    assert parameter.category != CATEGORY_NEWLY_ABNORMAL


def test_a_printed_marker_is_used_when_no_interval_was_printed():
    parameter = pair_of(
        {"cholesterol": vf("cholesterol", 190.0, "mg/dl", flag="normal")},
        {"cholesterol": vf("cholesterol", 240.0, "mg/dl", flag="high")},
    ).parameters["cholesterol"]

    assert parameter.baseline.basis == BASIS_PRINTED_FLAG
    assert parameter.baseline.abnormal is False
    assert parameter.comparison.abnormal is True
    assert parameter.transition == TRANSITION_NEWLY_ABNORMAL
    assert any("marker printed beside it" in w for w in parameter.warnings)


def test_a_marker_this_service_does_not_recognise_is_never_read_as_normal():
    request = ReportComparisonRequest(
        reports=[
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"cholesterol": vf("cholesterol", 190.0, "mg/dl", flag="normal")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {"cholesterol": vf("cholesterol", 240.0, "mg/dl", flag="high")},
            ),
        ]
    )
    assert request.reports[0].validated is not None
    provenance = request.reports[0].validated.valid["cholesterol"].provenance
    assert provenance is not None
    provenance.flag = "borderline"

    parameter = compare_reports(request).parameters["cholesterol"]
    assert parameter.baseline.abnormal is None
    assert parameter.baseline.reason_code == ABN_UNKNOWN_FLAG
    assert parameter.transition is None
    assert parameter.category != CATEGORY_NEWLY_ABNORMAL
    assert set(comparator.FLAG_ABNORMAL) == {"normal", "low", "high", "critical"}


def test_a_flag_disagreeing_with_the_printed_range_keeps_both_and_warns():
    data = pair_of(
        {"cholesterol": cholesterol(190.0, flag="high")},
        {"cholesterol": cholesterol(240.0)},
    )
    parameter = data.parameters["cholesterol"]

    assert parameter.baseline.abnormal is False
    assert parameter.baseline.printed_flag == "high"
    assert parameter.baseline.flag_disagrees_with_range is True
    assert any("imply different answers" in w for w in parameter.warnings)
    assert any("imply different answers" in w for w in data.warnings)


def test_the_tri_state_cannot_be_expressed_inconsistently():
    common = dict(report_id="r1", date="2024-01-01T00:00:00Z", reason="x")
    with pytest.raises(Exception):
        AbnormalityState(
            abnormal=False, basis=BASIS_NOT_DETERMINABLE, reason_code="X", **common
        )
    with pytest.raises(Exception):
        AbnormalityState(abnormal=None, basis=BASIS_REFERENCE_RANGE, **common)
    with pytest.raises(Exception):
        AbnormalityState(abnormal=None, basis=BASIS_NOT_DETERMINABLE, **common)
    state = AbnormalityState(
        abnormal=None,
        basis=BASIS_NOT_DETERMINABLE,
        reason_code=ABN_NO_USABLE_VALUE,
        **common,
    )
    assert state.abnormal is None
    assert state.value is None


def test_a_category_may_not_assert_more_than_its_axes_support():
    base = dict(
        feature="cholesterol",
        description="d",
        value_type="number",
        outcome=COMPARISON_IN_NEITHER,
        baseline=AbnormalityState(
            report_id="r1",
            date="2024-01-01T00:00:00Z",
            abnormal=None,
            basis=BASIS_NOT_DETERMINABLE,
            reason_code=ABN_NO_USABLE_VALUE,
            reason="x",
        ),
        comparison=AbnormalityState(
            report_id="r2",
            date="2024-06-01T00:00:00Z",
            abnormal=None,
            basis=BASIS_NOT_DETERMINABLE,
            reason_code=ABN_NO_USABLE_VALUE,
            reason="x",
        ),
        transition_outcome=NOT_DETERMINABLE_BOTH,
        reason="x",
    )
    with pytest.raises(Exception):
        ParameterComparison(category=CATEGORY_NEWLY_ABNORMAL, **base)
    with pytest.raises(Exception):
        ParameterComparison(category=CATEGORY_UNCHANGED, **base)
    ok = ParameterComparison(category=CATEGORY_NOT_CLASSIFIABLE, **base)
    assert ok.transition is None


def test_abnormality_is_per_report_so_a_unit_mismatch_still_answers_it():
    parameter = pair_of(
        {
            "creatinine": vf(
                "creatinine", 1.0, "mg/dl", reference_low=0.7, reference_high=1.3
            )
        },
        {
            "creatinine": vf(
                "creatinine", 200.0, "umol/l", reference_low=62.0, reference_high=106.0
            )
        },
    ).parameters["creatinine"]

    assert parameter.outcome == OUTCOME_UNIT_MISMATCH
    assert parameter.change_class is None
    assert parameter.baseline.abnormal is False
    assert parameter.comparison.abnormal is True
    assert parameter.transition == TRANSITION_NEWLY_ABNORMAL
    assert parameter.category == CATEGORY_NEWLY_ABNORMAL


def test_a_parameter_present_in_one_report_only_is_not_unchanged():
    data = pair_of(
        {"cholesterol": cholesterol(190.0)}, {"hba1c": vf("hba1c", 6.0, "%")}
    )
    parameter = data.parameters["cholesterol"]

    assert parameter.outcome == COMPARISON_ONLY_IN_BASELINE
    assert parameter.change_class is None
    assert parameter.change is None
    assert parameter.significant is None
    assert parameter.category == CATEGORY_NOT_CLASSIFIABLE
    assert "not an unchanged reading" in parameter.reason

    row = next(row for row in data.table if row.feature == "cholesterol")
    assert row.previous == 190.0
    assert row.current is None
    assert row.absolute_change is None
    assert row.percent_change is None
    assert row.symbol is None
    assert row.significant is None


def test_only_in_comparison_is_the_mirror_and_also_not_unchanged():
    data = pair_of(
        {"hba1c": vf("hba1c", 6.0, "%")}, {"cholesterol": cholesterol(240.0)}
    )
    parameter = data.parameters["cholesterol"]
    assert parameter.outcome == COMPARISON_ONLY_IN_COMPARISON
    assert parameter.change_class is None

    row = next(row for row in data.table if row.feature == "cholesterol")
    assert row.previous is None
    assert row.current == 240.0


def test_a_rejected_reading_is_the_reason_the_side_is_missing():
    data = compare(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"creatinine": vf("creatinine", 1.0, "mg/dl")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {},
                rejected={"creatinine": rejection("creatinine")},
            ),
        ]
    )
    parameter = data.parameters["creatinine"]
    assert parameter.outcome == COMPARISON_ONLY_IN_BASELINE
    assert "physiologically possible" in parameter.reason
    assert "9999" not in json.dumps(data.model_dump(mode="json"))


def test_a_feature_in_neither_report_is_in_neither_not_unchanged():
    data = pair_of(
        {"cholesterol": cholesterol(190.0)},
        {"cholesterol": cholesterol(240.0)},
        options={"include_all_canonical": True},
    )
    assert data.parameters["hemoglobin"].outcome == COMPARISON_IN_NEITHER
    assert data.parameters["hemoglobin"].change_class is None
    assert data.parameters["hemoglobin"].category == CATEGORY_NOT_CLASSIFIABLE
    assert data.summary.unchanged == 0


def test_fewer_than_two_reports_compares_nothing_and_says_so():
    data = compare(
        [report("r1", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(190.0)})]
    )
    assert data.pair is None
    assert data.parameters == {}
    assert data.table == []
    assert data.summary.features_examined == 0
    assert data.summary.headline == (
        "Fewer than two reports were supplied, so there is nothing to compare."
    )
    assert any("needs two" in warning for warning in data.warnings)

    empty = compare([])
    assert empty.pair is None
    assert any("No reports" in warning for warning in empty.warnings)


def test_unchanged_is_earned_from_the_stability_band_not_assigned():
    parameter = pair_of(
        {"cholesterol": cholesterol(190.0)}, {"cholesterol": cholesterol(191.0)}
    ).parameters["cholesterol"]

    assert parameter.change_class == CHANGE_UNCHANGED
    assert parameter.significant is False
    assert parameter.stability is not None
    assert parameter.stability.exceeded is False
    assert parameter.stability.significant_change_pct == 17.0
    assert parameter.direction == "rising"


def test_a_converted_reference_interval_is_not_converted_a_second_time():
    from app.services.feature_engineer import engineer_features
    from app.services.validator import validate_features

    def engineered_report(report_id: str, date: str, umol_value: float):
        engineered = engineer_features(
            [
                {
                    "test_name": "Creatinine",
                    "value_raw": str(umol_value),
                    "value_numeric": umol_value,
                    "unit": "umol/L",
                    "reference_range_raw": "62 - 106",
                    "reference_low": 62.0,
                    "reference_high": 106.0,
                    "confidence": 0.95,
                }
            ]
        )
        validated = validate_features(engineered)
        return {
            "report_id": report_id,
            "chrono_date": date,
            "validated": validated.model_dump(mode="json"),
        }

    data = compare(
        [
            engineered_report("r1", "2024-01-01T00:00:00Z", 88.4),
            engineered_report("r2", "2024-06-01T00:00:00Z", 92.0),
        ]
    )
    parameter = data.parameters["creatinine"]

    assert parameter.baseline.reference_low == pytest.approx(0.701344)
    assert parameter.baseline.reference_high == pytest.approx(1.199072)
    assert parameter.baseline.basis == BASIS_REFERENCE_RANGE_CONVERTED
    assert parameter.baseline.value == pytest.approx(1.0, abs=0.01)
    assert parameter.baseline.abnormal is False
    assert parameter.comparison.abnormal is False
    assert parameter.transition == TRANSITION_REMAINED_NORMAL
    assert parameter.category != CATEGORY_NEWLY_ABNORMAL
    assert parameter.baseline.reference_high > 0.1
    assert parameter.baseline.reference_low > 0.1


def test_the_helper_itself_refuses_to_double_convert():
    from app.schemas.features import ConversionDetail, FeatureProvenance

    conversion = ConversionDetail(**CREATININE_UMOL_CONVERSION)
    already_converted = FeatureProvenance(
        source="lab_report",
        reference_low=0.701344,
        reference_high=1.199072,
        reference_unit="mg/dl",
        reference_converted=True,
        unit_converted=True,
        conversion=conversion,
    )
    low, high, basis, formula = comparator.reference_interval(already_converted)
    assert (low, high) == (0.701344, 1.199072)
    assert basis == BASIS_REFERENCE_RANGE_CONVERTED
    assert formula == conversion.formula


def test_an_older_carrier_without_the_flag_is_still_converted_once():
    from app.schemas.features import ConversionDetail, FeatureProvenance

    legacy = FeatureProvenance(
        source="lab_report",
        reference_low=62.0,
        reference_high=106.0,
        reference_converted=False,
        unit_converted=True,
        conversion=ConversionDetail(**CREATININE_UMOL_CONVERSION),
    )
    low, high, basis, _ = comparator.reference_interval(legacy)
    assert low == pytest.approx(0.701344)
    assert high == pytest.approx(1.199072)
    assert basis == BASIS_REFERENCE_RANGE_CONVERTED


@pytest.mark.parametrize(
    "conversion_kwargs",
    [
        pytest.param({"factor": -1.0}, id="negative_factor"),
        pytest.param({"factor": 0.0}, id="zero_factor"),
        pytest.param({"factor": float("inf")}, id="non_finite_factor"),
    ],
)
def test_an_interval_that_cannot_be_carried_is_absent_not_approximated(
    conversion_kwargs,
):
    from app.schemas.features import ConversionDetail, FeatureProvenance

    detail = dict(CREATININE_UMOL_CONVERSION)
    detail.update(conversion_kwargs)
    provenance = FeatureProvenance(
        source="lab_report",
        reference_low=62.0,
        reference_high=106.0,
        unit_converted=True,
        conversion=ConversionDetail(**detail),
    )
    assert comparator.reference_interval(provenance) == (None, None, None, None)


def test_a_converted_carrier_with_no_recorded_conversion_refuses():
    from app.schemas.features import FeatureProvenance

    provenance = FeatureProvenance(
        source="lab_report",
        reference_low=62.0,
        unit_converted=True,
        conversion=None,
    )
    assert comparator.reference_interval(provenance) == (None, None, None, None)


def test_a_printed_interval_that_could_not_be_placed_gets_its_own_code():
    parameter = pair_of(
        {
            "creatinine": vf(
                "creatinine",
                1.0,
                "mg/dl",
                reference_low=62.0,
                reference_high=106.0,
                unit_converted=True,
            )
        },
        {"creatinine": vf("creatinine", 1.1, "mg/dl")},
    ).parameters["creatinine"]

    assert parameter.baseline.abnormal is None
    assert parameter.baseline.reason_code == ABN_RANGE_UNIT_NOT_COMPARABLE
    assert parameter.transition is None


_COMPARATOR_SOURCE = Path(comparator.__file__).read_text(encoding="utf-8")
_COMPARATOR_TREE = ast.parse(_COMPARATOR_SOURCE)


def _identifiers(tree: ast.AST) -> set:
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.asname or node.name.split(".")[-1])
    return used


@pytest.mark.parametrize(
    "banned",
    [
        "POLARITY",
        "STABILITY",
        "stability_for",
        "direction_of_harm",
        "optimal_low",
        "optimal_high",
        "significant_change_pct",
        "min_absolute_change",
        "reference_change_value",
    ],
)
def test_module_29_owns_no_polarity_or_stability_table(banned):
    assert banned not in _identifiers(_COMPARATOR_TREE), (
        f"app/services/report_comparator.py now references {banned!r}. Module 29 "
        "must delegate every polarity and stability decision to Module 28's "
        "analyse_feature(); a second table here can disagree with the first."
    )


def test_module_29_reaches_module_28_only_through_the_declared_interface():
    imports = {
        alias.name
        for node in ast.walk(_COMPARATOR_TREE)
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.services.trend_analyzer"
        for alias in node.names
    }
    assert "analyse_feature" in imports
    assert not any(name.startswith("_") for name in imports), imports


def test_the_refusal_vocabulary_is_derived_from_module_28_not_retyped():
    expected = {
        code
        for code in OUTCOME_VALUES
        if code not in (OUTCOME_TREND_CLASSIFIED, OUTCOME_INSUFFICIENT_DATA)
    }
    assert set(INHERITED_REFUSAL_OUTCOMES) == expected
    assert expected <= set(COMPARISON_OUTCOME_VALUES)

    source = Path(
        __import__("app.schemas.comparison", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "INHERITED_REFUSAL_OUTCOMES"
    ]
    assert len(assignments) == 1
    value = assignments[0].value
    assert value is not None
    assert not isinstance(value, (ast.Tuple, ast.List)), (
        "INHERITED_REFUSAL_OUTCOMES is now a literal. It must be DERIVED from "
        "app.schemas.timeline.OUTCOME_VALUES so the two modules cannot drift."
    )
    assert "OUTCOME_VALUES" in _identifiers(value)


def test_the_trend_to_change_mapping_is_total_over_module_28s_labels():
    assert set(TREND_VALUES) == set(comparator._TREND_TO_CHANGE)
    assert set(comparator._TREND_TO_CHANGE.values()) == {
        CHANGE_IMPROVED,
        CHANGE_WORSENED,
        CHANGE_UNCHANGED,
    }


@pytest.mark.parametrize(
    "feature,values,unit",
    [
        ("hba1c", [6.2, 6.8], "%"),
        ("hba1c", [6.8, 6.2], "%"),
        ("hba1c", [6.2, 6.25], "%"),
        ("creatinine", [1.1, 1.0], "mg/dl"),
        ("creatinine", [0.9, 1.6], "mg/dl"),
        ("vitamin_d", [22.0, 35.0], "ng/ml"),
        ("vitamin_d", [95.0, 140.0], "ng/ml"),
        ("vitamin_d", [10.0, 150.0], "ng/ml"),
        ("cholesterol", [190.0, 240.0], "mg/dl"),
        ("triglycerides", [100.0, 300.0], "mg/dl"),
        ("blood_glucose", [90.0, 180.0], "mg/dl"),
        ("hemoglobin", [10.0, 14.0], "g/dl"),
        ("vitamin_b12", [150.0, 400.0], "pg/ml"),
    ],
)
def test_the_two_modules_agree_on_every_direction_they_both_answer(
    feature, values, unit
):
    reports = [
        report("r1", "2024-01-01T00:00:00Z", {feature: vf(feature, values[0], unit)}),
        report("r2", "2024-06-01T00:00:00Z", {feature: vf(feature, values[1], unit)}),
    ]
    trend = analyse_trends(TimelineTrendsRequest(reports=reports)).features[feature]
    parameter = compare(reports).parameters[feature]

    if trend.outcome == OUTCOME_TREND_CLASSIFIED:
        assert parameter.outcome == COMPARISON_CHANGE_CLASSIFIED
        assert parameter.change_class == comparator._TREND_TO_CHANGE[trend.trend]
    else:
        assert parameter.outcome == trend.outcome
        assert parameter.change_class is None
    assert parameter.direction == trend.direction
    assert parameter.significant == (
        trend.stability.exceeded if trend.stability else None
    )
    if trend.change is not None:
        assert parameter.change == trend.change
    assert parameter.polarity == trend.polarity


def test_the_default_pair_is_the_earliest_against_the_latest():
    data = compare(
        [
            report("r2", "2024-03-01T00:00:00Z", {"cholesterol": cholesterol(200.0)}),
            report("r3", "2024-06-01T00:00:00Z", {"cholesterol": cholesterol(240.0)}),
            report("r1", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(190.0)}),
        ]
    )
    assert data.pair is not None
    assert data.pair.selection == SELECTION_FIRST_VS_LATEST
    assert data.pair.baseline_report_id == "r1"
    assert data.pair.comparison_report_id == "r3"
    assert data.pair.intermediate_report_count == 1
    assert data.pair.chronological is True
    assert data.parameters["cholesterol"].change is not None
    assert data.parameters["cholesterol"].change.first_value == 190.0
    assert data.parameters["cholesterol"].change.last_value == 240.0


def test_an_explicitly_named_reverse_pair_is_honoured_and_warned_about():
    data = compare(
        [
            report("r1", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(190.0)}),
            report("r2", "2024-06-01T00:00:00Z", {"cholesterol": cholesterol(240.0)}),
        ],
        baseline_ref="r2",
        comparison_ref="r1",
    )
    assert data.pair is not None
    assert data.pair.selection == SELECTION_EXPLICIT
    assert data.pair.baseline_report_id == "r2"
    assert data.pair.chronological is False
    assert data.pair.days_between < 0
    assert any("NOT silently swapped" in warning for warning in data.warnings)
    assert data.parameters["cholesterol"].transition == TRANSITION_NEWLY_NORMAL


def test_naming_one_half_of_the_pair_is_refused():
    with pytest.raises(Exception):
        ReportComparisonRequest(
            reports=[
                report("r1", "2024-01-01T00:00:00Z", {}),
                report("r2", "2024-06-01T00:00:00Z", {}),
            ],
            baseline_ref="r1",
        )
    with pytest.raises(Exception):
        ReportComparisonRequest(
            reports=[report("r1", "2024-01-01T00:00:00Z", {})],
            baseline_ref="r1",
            comparison_ref="r1",
        )


def test_naming_a_report_that_was_not_supplied_is_an_error_not_a_fallback():
    from app.core.errors import BadRequestError

    with pytest.raises(BadRequestError) as excinfo:
        compare(
            [
                report("r1", "2024-01-01T00:00:00Z", {}),
                report("r2", "2024-06-01T00:00:00Z", {}),
            ],
            baseline_ref="r1",
            comparison_ref="does-not-exist",
        )
    assert excinfo.value.code == "COMPARISON_REPORT_NOT_FOUND"


def test_intermediate_reports_are_rendered_but_take_no_part_in_the_verdict():
    data = compare(
        [
            report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
            report("r2", "2024-03-01T00:00:00Z", {"hba1c": vf("hba1c", 9.0, "%")}),
            report("r3", "2024-06-01T00:00:00Z", {"hba1c": vf("hba1c", 6.2, "%")}),
        ]
    )
    parameter = data.parameters["hba1c"]
    assert parameter.change is not None
    assert parameter.change.first_value == 6.1
    assert parameter.change.last_value == 6.2
    assert parameter.change.step_count == 1
    assert [point.value for point in data.series["hba1c"].points] == [6.1, 9.0, 6.2]
    warned = " ".join(data.warnings).lower()
    assert "not included" in warned or "take no part" in warned
    assert "other report" in warned


def _stable_dump(data: Any) -> str:
    payload = data.model_dump(mode="json")
    payload.pop("generated_at", None)
    return json.dumps(payload, sort_keys=True)


def test_the_array_order_cannot_change_the_comparison():
    reports = [
        report("rc", "2024-06-01T00:00:00Z", {"cholesterol": cholesterol(240.0)}),
        report("ra", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(190.0)}),
        report("rb", "2024-03-01T00:00:00Z", {"cholesterol": cholesterol(200.0)}),
    ]
    dumps = {
        _stable_dump(compare(order))
        for order in (reports, list(reversed(reports)), reports[1:] + reports[:1])
    }
    assert len(dumps) == 1


def test_two_reports_sharing_a_date_still_choose_the_pair_deterministically():
    first = compare(
        [
            report("rB", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(240.0)}),
            report("rA", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(190.0)}),
        ]
    )
    second = compare(
        [
            report("rA", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(190.0)}),
            report("rB", "2024-01-01T00:00:00Z", {"cholesterol": cholesterol(240.0)}),
        ]
    )
    assert first.pair is not None
    assert first.pair.baseline_report_id == "rA"
    assert _stable_dump(first) == _stable_dump(second)
    assert any("same date" in warning for warning in first.warnings)


def test_a_crossing_outranks_the_change_axis_without_hiding_it():
    parameter = pair_of(
        {"cholesterol": cholesterol(190.0)}, {"cholesterol": cholesterol(240.0)}
    ).parameters["cholesterol"]
    assert parameter.category == CATEGORY_NEWLY_ABNORMAL
    assert parameter.change_class == CHANGE_WORSENED
    assert parameter.transition == TRANSITION_NEWLY_ABNORMAL


def test_a_measurable_move_with_no_declared_direction_is_its_own_category():
    parameter = pair_of(
        {"blood_glucose": vf("blood_glucose", 90.0, "mg/dl")},
        {"blood_glucose": vf("blood_glucose", 180.0, "mg/dl")},
    ).parameters["blood_glucose"]

    assert parameter.category == CATEGORY_CHANGED_DIRECTION_ONLY
    assert parameter.change_class is None
    assert parameter.change is not None
    assert parameter.change.absolute_change == 90.0
    assert parameter.direction == "rising"


def test_a_crossing_below_the_stability_band_is_reported_with_that_caveat():
    parameter = pair_of(
        {"cholesterol": cholesterol(199.0)}, {"cholesterol": cholesterol(201.0)}
    ).parameters["cholesterol"]

    assert parameter.transition == TRANSITION_NEWLY_ABNORMAL
    assert parameter.significant is False
    assert parameter.category == CATEGORY_NEWLY_ABNORMAL
    assert any("measurement variation" in w for w in parameter.warnings)


def test_the_table_is_in_catalogue_order_and_every_category_is_declared():
    data = pair_of(
        {
            "hba1c": vf("hba1c", 6.2, "%"),
            "cholesterol": cholesterol(190.0),
            "vitamin_d": vitamin_d(22.0),
        },
        {
            "hba1c": vf("hba1c", 6.8, "%"),
            "cholesterol": cholesterol(240.0),
            "vitamin_d": vitamin_d(35.0),
        },
    )
    order = [row.feature for row in data.table]
    assert order == [
        name for name in CANONICAL_FEATURES if name in set(order)
    ]
    for row in data.table:
        assert row.category in CATEGORY_VALUES
    assert [row.symbol for row in data.table] == ["↑", "↑", "↑"]


def test_the_summary_counts_and_lines_match_the_parameters():
    data = pair_of(
        {
            "hba1c": vf("hba1c", 6.2, "%"),
            "cholesterol": cholesterol(190.0),
            "vitamin_d": vitamin_d(22.0),
            "creatinine": vf("creatinine", 1.0, "mg/dl"),
        },
        {
            "hba1c": vf("hba1c", 6.8, "%"),
            "cholesterol": cholesterol(240.0),
            "vitamin_d": vitamin_d(35.0),
        },
    )
    summary = data.summary
    assert summary.features_examined == 4
    assert summary.newly_abnormal == 1
    assert summary.newly_normal == 1
    assert summary.worsened == 1
    assert summary.not_classifiable == 1
    assert sum(summary.categories.values()) == summary.features_examined
    assert sum(summary.outcomes.values()) == summary.features_examined
    assert sum(summary.transition_outcomes.values()) == summary.features_examined
    assert summary.headline.startswith("Comparing the report of 2024-01-01")
    assert any("newly abnormal" not in line for line in summary.lines)
    assert any("cholesterol" in line for line in summary.lines)


def test_every_string_the_comparator_emits_comes_from_a_scanned_template():
    from app.data.recommendation_catalog import scan_text

    for table in (
        comparator._TEMPLATES,
        comparator._WARNING_TEMPLATES,
        comparator._PARAMETER_WARNINGS,
    ):
        for key, template in table.items():
            assert not scan_text(template), f"{key} violates the safety scanner"
    assert not scan_text(comparator.DISCLAIMER)


def test_the_comparator_policy_document_states_the_rules_it_is_held_to():
    document = comparator.comparator_document()
    assert "analyse_feature" in document["method"]
    assert "NOT_DETERMINABLE" in document["newly_abnormal_rule"]
    assert "never a default" in document["unchanged_rule"]
    assert document["categories"] == list(CATEGORY_VALUES)
