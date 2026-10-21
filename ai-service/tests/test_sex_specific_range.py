import pytest

from app.services.sex_specific_range import (
    bounds_for_sex,
    parse_sex_specific_range,
)


@pytest.mark.parametrize(
    "raw,female,male",
    [
        ("F:11 - 15 M:12 - 16", (11.0, 15.0), (12.0, 16.0)),
        ("F: 36 - 46 M: 40 - 50", (36.0, 46.0), (40.0, 50.0)),
        ("Female: 12.0-15.0 Male: 13.0-17.0", (12.0, 15.0), (13.0, 17.0)),
        ("MALE 13 - 17 FEMALE 12 - 15", (12.0, 15.0), (13.0, 17.0)),
        ("F 11 to 15 M 12 to 16", (11.0, 15.0), (12.0, 16.0)),
        ("F:11–15 M:12–16", (11.0, 15.0), (12.0, 16.0)),
    ],
)
def test_reads_one_interval_per_sex(raw, female, male):
    parsed = parse_sex_specific_range(raw)
    assert parsed == {"female": female, "male": male}


def test_order_of_the_two_labels_does_not_matter():
    assert parse_sex_specific_range("M:12 - 16 F:11 - 15") == {
        "female": (11.0, 15.0),
        "male": (12.0, 16.0),
    }


@pytest.mark.parametrize(
    "raw,why",
    [
        (None, "nothing printed"),
        ("", "empty"),
        ("   ", "whitespace"),
        (12.5, "not a string"),
        ("12 - 16", "no labels"),
        ("11 - 15, 12 - 16", "two intervals, neither labelled"),
        ("M:12 - 16", "only one sex"),
        ("F: 36 - 46", "only one sex"),
        ("Normal : < 5.7", "band, not an interval"),
        ("Normal 5.7 - 6.4 Prediabetes 6.5 - 7.0 Diabetes 7.1 - 9.0", "band table"),
        ("F:11 - 15 M:12 - 16 F:10 - 14", "three intervals"),
        ("M:12 - 16 M:13 - 17", "repeated label"),
        ("F:15 - 11 M:12 - 16", "inverted"),
    ],
)
def test_refuses(raw, why):
    assert parse_sex_specific_range(raw) is None, why


def test_a_letter_inside_a_unit_is_not_a_sex_label():
    assert parse_sex_specific_range("mm/hr 0 - 20") is None
    assert parse_sex_specific_range("fl 80 - 100") is None
    assert parse_sex_specific_range("0 - 20 mm/hr") is None


def test_selects_the_interval_for_the_patients_sex():
    raw = "F:11 - 15 M:12 - 16"
    assert bounds_for_sex(raw, "male") == (12.0, 16.0)
    assert bounds_for_sex(raw, "female") == (11.0, 15.0)
    assert bounds_for_sex(raw, "MALE") == (12.0, 16.0)


@pytest.mark.parametrize("sex", [None, "", "other", "unknown", 1, "  "])
def test_an_unknown_sex_selects_nothing(sex):
    assert bounds_for_sex("F:11 - 15 M:12 - 16", sex) is None


def test_the_real_test_3_rows():
    haemoglobin = bounds_for_sex("F:11 - 15 M:12 - 16", "male")
    pcv = bounds_for_sex("F: 36 - 46 M: 40 - 50", "male")
    assert haemoglobin == (12.0, 16.0)
    assert pcv == (40.0, 50.0)
    assert haemoglobin[0] <= 12.5 <= haemoglobin[1]
    assert 37.9 < pcv[0]
