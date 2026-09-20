"""Reading an interval a laboratory printed once per sex.

⚠ EVERY "ACCEPTS" FIXTURE BELOW IS COPIED FROM A REAL STORED REPORT, not
invented to suit the parser. `Test 3.pdf` prints both of the first two
verbatim, and they are the reason this module exists: PCV 37.9 % rendered to
the reader as "not checked" while sitting below the male interval printed
beside it on the same line.

The refusals carry the weight here. A wrong interval is worse than no
interval -- it produces a confident verdict that is false -- so anything this
module is not certain of must come back None.
"""

import pytest

from app.services.sex_specific_range import (
    bounds_for_sex,
    parse_sex_specific_range,
)


# --------------------------------------------------------------------------
# What it reads
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,female,male",
    [
        # BOTH VERBATIM FROM `Test 3.pdf`, spacing included.
        ("F:11 - 15 M:12 - 16", (11.0, 15.0), (12.0, 16.0)),
        ("F: 36 - 46 M: 40 - 50", (36.0, 46.0), (40.0, 50.0)),
        # Spellings the same laboratories use elsewhere.
        ("Female: 12.0-15.0 Male: 13.0-17.0", (12.0, 15.0), (13.0, 17.0)),
        ("MALE 13 - 17 FEMALE 12 - 15", (12.0, 15.0), (13.0, 17.0)),
        ("F 11 to 15 M 12 to 16", (11.0, 15.0), (12.0, 16.0)),
        # An en dash, which PDF extraction produces routinely.
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


# --------------------------------------------------------------------------
# What it refuses -- the half that matters
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,why",
    [
        (None, "nothing printed"),
        ("", "empty"),
        ("   ", "whitespace"),
        (12.5, "not a string"),
        # A BARE INTERVAL IS NOT SEX-SPECIFIC and is already handled upstream
        # by `printed_range_is_only_a_range`.
        ("12 - 16", "no labels"),
        ("11 - 15, 12 - 16", "two intervals, neither labelled"),
        # ONE SIDE ONLY. The other half may simply have failed to transcribe,
        # and a lone `M:` says nothing about a female reader.
        ("M:12 - 16", "only one sex"),
        ("F: 36 - 46", "only one sex"),
        # A BAND TABLE, which is what the upstream gate exists to refuse. It
        # must not slip through here either.
        ("Normal : < 5.7", "band, not an interval"),
        ("Normal 5.7 - 6.4 Prediabetes 6.5 - 7.0 Diabetes 7.1 - 9.0", "band table"),
        # THREE labelled intervals is a table this module does not understand.
        ("F:11 - 15 M:12 - 16 F:10 - 14", "three intervals"),
        # The same label twice is not one interval per sex.
        ("M:12 - 16 M:13 - 17", "repeated label"),
        # AN INVERTED INTERVAL IS A MISREAD. If one side transcribed wrongly
        # the other is not to be trusted either, so the whole text is refused.
        ("F:15 - 11 M:12 - 16", "inverted"),
    ],
)
def test_refuses(raw, why):
    assert parse_sex_specific_range(raw) is None, why


def test_a_letter_inside_a_unit_is_not_a_sex_label():
    """⚠ `\\b` ANCHORS ARE LOAD-BEARING. Without them the `m` of `mm/hr` and
    the `f` of `fl` open an interval, and a bare range acquires a sex."""
    assert parse_sex_specific_range("mm/hr 0 - 20") is None
    assert parse_sex_specific_range("fl 80 - 100") is None
    assert parse_sex_specific_range("0 - 20 mm/hr") is None


# --------------------------------------------------------------------------
# Choosing the side
# --------------------------------------------------------------------------


def test_selects_the_interval_for_the_patients_sex():
    raw = "F:11 - 15 M:12 - 16"
    assert bounds_for_sex(raw, "male") == (12.0, 16.0)
    assert bounds_for_sex(raw, "female") == (11.0, 15.0)
    assert bounds_for_sex(raw, "MALE") == (12.0, 16.0)


@pytest.mark.parametrize("sex", [None, "", "other", "unknown", 1, "  "])
def test_an_unknown_sex_selects_nothing(sex):
    """⚠ NOT AN OVERSIGHT, AND `other` IS THE POINT OF IT.

    `normalize_gender` returns `male`, `female` or `other`. The report prints
    two intervals and neither is addressed to a reader who is neither, so
    choosing one would be this service inventing a comparison the laboratory
    never made. The row stays uncompared, exactly as it is today.
    """
    assert bounds_for_sex("F:11 - 15 M:12 - 16", sex) is None


def test_the_real_test_3_rows():
    """The two rows that prompted this, with the values they carry.

    PCV is the one that matters: the reader was shown "not checked" for a
    value that is below the interval printed on the same line.
    """
    haemoglobin = bounds_for_sex("F:11 - 15 M:12 - 16", "male")
    pcv = bounds_for_sex("F: 36 - 46 M: 40 - 50", "male")
    assert haemoglobin == (12.0, 16.0)
    assert pcv == (40.0, 50.0)
    # 12.5 is INSIDE the printed male interval; 37.9 is BELOW it.
    assert haemoglobin[0] <= 12.5 <= haemoglobin[1]
    assert 37.9 < pcv[0]
