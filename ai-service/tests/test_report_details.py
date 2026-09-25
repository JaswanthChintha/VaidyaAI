"""The report's own sex and age are used in place of the profile's.

The owner's decision, 2026-09-25. Every analysis used the ACCOUNT PROFILE's
sex and age: `01-all-normal.pdf` prints "34 Years / Female" and was scored as
the profile's "20, male", male thresholds and all. A value the report prints,
and this service can read, now wins -- labelled `report_details`, a patient
DETAIL, never a measurement.
"""

from __future__ import annotations

import pytest

from app.data.feature_catalog import NOT_MEASURED_SOURCES, SOURCE_REPORT_DETAILS
from app.services.feature_engineer import engineer_features
from app.services.printed_identity import read_age_years, read_sex

HB = {
    "test_name": "HEMOGLOBIN",
    "value_raw": "12.5",
    "value_numeric": 12.5,
    "unit": "g/dL",
    "reference_range_raw": "F:11 -15 M:12- 16",
}


def extraction(sex=None, age=None, rows=(HB,)):
    return {
        "source": {"filename": "r.pdf"},
        "extracted_parameters": list(rows),
        "report_metadata": {"patient_sex": sex, "patient_age": age},
    }


PROFILE = {"age": 20, "gender": "male"}


def test_the_printed_sex_and_age_replace_the_profiles():
    data = engineer_features(profile=PROFILE, extraction=extraction("Female", "34 Years"))
    assert data.features["gender"].value == "female"
    assert data.features["age"].value == 34
    for name in ("gender", "age"):
        feature = data.features[name]
        assert feature.source == SOURCE_REPORT_DETAILS == "report_details"
        assert feature.provenance.source == "report_details"
    # Both values are named where they disagree, and it is warned about.
    assert "The profile gives male." in data.features["gender"].provenance.notes
    assert any("patient's sex as 'Female'; the profile gives male" in w for w in data.warnings)
    assert any("patient's age as '34 Years'; the profile gives 20" in w for w in data.warnings)
    assert data.summary.report_details_feature_count == 2
    assert data.summary.profile_feature_count == 0


def test_the_printed_sex_chooses_between_per_sex_printed_ranges():
    """Test 3 prints `F:11 -15 M:12- 16`; a woman's report must be read with F."""
    data = engineer_features(profile=PROFILE, extraction=extraction("F", "34"))
    hb = data.features["hemoglobin"]
    assert (hb.provenance.reference_low, hb.provenance.reference_high) == (11.0, 15.0)
    assert any("matching the sex on the report" in note for note in hb.provenance.notes)


def test_nothing_printed_means_the_profile_exactly_as_before():
    data = engineer_features(profile=PROFILE, extraction=extraction(None, None))
    assert data.features["gender"].source == "patient_profile"
    assert data.features["gender"].value == "male"
    assert data.features["age"].value == 20
    hb = data.features["hemoglobin"]
    assert (hb.provenance.reference_low, hb.provenance.reference_high) == (12.0, 16.0)
    assert any("matching the sex on the profile" in n for n in hb.provenance.notes)
    assert data.summary.report_details_feature_count == 0
    assert not any("report prints" in w for w in data.warnings)


def test_an_unreadable_printed_value_falls_back_to_the_profile_field_by_field():
    data = engineer_features(profile=PROFILE, extraction=extraction("Other", "34 Years"))
    assert data.features["gender"].source == "patient_profile"  # "Other" is not read
    assert data.features["age"].source == "report_details"


def test_agreeing_values_are_used_without_a_warning():
    data = engineer_features(profile=PROFILE, extraction=extraction("Male", "20 Years"))
    assert data.features["gender"].source == "report_details"
    assert not any("report prints" in w for w in data.warnings)
    assert not any("The profile gives" in n for n in data.features["age"].provenance.notes)


def test_printed_details_are_used_with_no_profile_at_all():
    data = engineer_features(profile=None, extraction=extraction("Female", "6 Months"))
    assert data.features["gender"].value == "female"
    assert data.features["age"].value == 0


def test_a_replaced_profile_value_is_not_reported_as_a_discarded_duplicate():
    """The report's value winning is the decided order, not a collision."""
    data = engineer_features(profile=PROFILE, extraction=extraction("Female", "34 Years"))
    assert not any(item.test_name in ("age", "gender") for item in data.unmapped)


@pytest.mark.parametrize(
    "raw, sex", [("Male", "male"), ("M", "male"), ("f.", "female"), ("Other", None), ("M/F", None), (None, None)]
)
def test_read_sex(raw, sex):
    assert read_sex(raw) == sex


@pytest.mark.parametrize(
    "raw, years",
    [("63 Years", 63), ("63", 63), ("34Y 2M", 34), ("6 Months", 0), ("adult", None), ("200 Years", None), (None, None)],
)
def test_read_age_years_rounds_down_to_whole_years(raw, years):
    assert read_age_years(raw) == years


def test_a_patient_detail_is_never_a_measurement():
    assert NOT_MEASURED_SOURCES == {"patient_profile", "report_details"}
    assert "lab_report" not in NOT_MEASURED_SOURCES


def test_the_clinician_narrative_does_not_list_a_printed_age_as_a_value():
    from app.services import clinician_narrative as cn

    rows = [
        {"feature": "age", "display_name": "Age", "value": 34, "unit": "years",
         "provenance": {"source": "report_details", "original_test_name": {"text": "age"}}},
        {"feature": "hemoglobin", "display_name": "Haemoglobin", "value": 12.5, "unit": "g/dl",
         "provenance": {"source": "lab_report", "original_test_name": {"text": "HEMOGLOBIN"}}},
    ]
    summary = {"laboratory": {"rows": rows}}
    strings = cn._value_strings(summary)
    assert not any("34" in s for s in strings)
    assert any("12.5" in s for s in strings)
    # The out-of-range list uses the same predicate.
    rows[0]["position"] = "above_reference_interval"
    assert not any("34" in s for s in cn._out_of_range(summary))
