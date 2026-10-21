from __future__ import annotations

import pytest

from app.data.lab_variation import (
    TABLE,
    LabVariation,
    duplicate_aliases,
    fold,
    variation_for,
)
from app.data.trend_polarity import reference_change_value
from app.services.lab_polarity import CV_PERMITTED


def test_no_row_claims_to_be_verified():
    unverified = [row.test for row in TABLE if not row.verified]
    assert len(unverified) == len(TABLE), (
        "a row is marked verified; see this test's docstring before changing it"
    )


def test_every_row_names_a_source_to_check_it_against():
    for row in TABLE:
        assert row.source and len(row.source) > 20, row.test


def test_every_row_passes_the_same_cv_gate_as_the_model():
    low, high = CV_PERMITTED
    for row in TABLE:
        assert low <= row.analytical_cv_pct <= high, row.test
        assert low <= row.within_subject_cv_pct <= high, row.test


def test_no_two_rows_claim_the_same_printed_name():
    assert duplicate_aliases() == ()


def test_every_row_declares_a_polarity_this_service_understands():
    from app.services.lab_polarity import _POLARITY_WORDS

    for row in TABLE:
        assert row.polarity in _POLARITY_WORDS, row.test
    for row in TABLE:
        assert row.polarity != "unknown", row.test


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("C-REACTIVE PROTEIN(CRP)", "c_reactive_protein"),
        ("CRP (C-REACTIVE PROTEIN)", "c_reactive_protein"),
        ("Polymorphs", "neutrophils"),
        ("NEUTROPHILS", "neutrophils"),
        ("T.RBC", "rbc_count"),
        ("RBC COUNT", "rbc_count"),
        ("WBC Count", "wbc_count"),
        ("TOTAL WBC COUNT", "wbc_count"),
        ("TSH", "tsh"),
        ("TSH (Thyroid Stim Hormone)", "tsh"),
        ("SGPT", "alanine_aminotransferase"),
        ("PCV", "haemoglobin_a_note"),
    ],
)
def test_the_printed_names_on_real_reports_find_their_row(printed, expected):
    row = variation_for(printed)
    assert row is not None, printed
    assert row.test == expected


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("ESR WESTGARD", "esr"),
        ("SGPT PHOTOMETRIC", "alanine_aminotransferase"),
        ("C-REACTIVE PROTEIN(CRP) Immunoturbidimetric", "c_reactive_protein"),
        ("C-REACTIVE PROTEIN(CRP) Immunoturbidometric", "c_reactive_protein"),
        ("TSH ECLIA", "tsh"),
        ("PLATELET COUNT impedance", "platelet_count"),
    ],
)
def test_a_method_printed_after_the_name_still_finds_the_row(printed, expected):
    row = variation_for(printed)
    assert row is not None, printed
    assert row.test == expected


@pytest.mark.parametrize(
    "printed",
    [
        "LDL Cholesterol, Direct",
        "Free Frimbulin",
        "Total Frimbulin",
    ],
)
def test_a_word_that_changes_the_measurement_is_never_stripped(printed):
    from app.data.lab_variation import _without_method

    assert _without_method(printed) == fold(printed), printed


def test_the_exact_fold_wins_so_the_fallback_cannot_divert_a_listed_name():
    for alias in ("ESR", "SGPT", "C-REACTIVE PROTEIN(CRP)", "TSH", "MCV"):
        assert variation_for(alias) is not None, alias


def test_a_name_made_only_of_method_words_matches_nothing():
    assert variation_for("PHOTOMETRIC HPLC") is None
    assert variation_for("WESTGARD") is None


def test_fold_itself_is_unchanged_because_the_backend_shares_its_rule():
    from app.data.lab_variation import _without_method

    assert fold("ESR WESTGARD") == "esr westgard"
    assert _without_method("ESR WESTGARD") == "esr"


def test_an_unknown_test_falls_through_rather_than_matching_the_nearest():
    assert variation_for("Frimbulator Factor") is None
    assert variation_for("") is None
    assert variation_for(None) is None


def test_the_fold_ignores_case_order_and_punctuation_only():
    assert fold("CRP (C-REACTIVE PROTEIN)") == fold("c-reactive protein(crp)")
    assert fold("Free Frimbulin") != fold("Total Frimbulin")


def test_the_recorded_arithmetic_reproduces_from_the_row():
    row = variation_for("ESR")
    assert round(reference_change_value(row.analytical_cv_pct, row.within_subject_cv_pct)) == 62


def test_every_row_cites_the_figure_it_stores():
    import re

    for row in TABLE:
        if row.test == "esr":
            continue
        match = re.search(r"CVi median ([0-9.]+) %", row.source)
        assert match, f"{row.test}: source names no CVi median"
        assert float(match.group(1)) == row.within_subject_cv_pct, row.test


def test_every_row_cites_a_page_a_reviewer_can_open():
    for row in TABLE:
        if row.test == "esr":
            continue
        assert "biologicalvariation.eu/meta_by_analyte/" in row.source, row.test
        assert "read 2026-" in row.source, row.test


def test_every_row_says_its_CVa_IS_NOT_from_that_source():
    for row in TABLE:
        if row.test == "esr":
            continue
        assert "CVa IS NOT FROM THIS SOURCE" in row.source, row.test


def test_ESR_says_its_named_source_does_not_contain_it():
    row = variation_for("ESR")
    assert "NO SOURCE" in row.source
    assert "NO ENTRY" in row.source
    assert "biologicalvariation.eu/meta_by_analyte/" not in row.source


def test_the_weakest_rows_show_their_weakness_rather_than_asserting_it():
    for name in ("EOSINOPHILS", "BASOPHILS"):
        row = variation_for(name)
        assert "(CI " in row.source, name
        import re

        lo, hi = re.search(r"\(CI ([0-9.]+)-([0-9.]+) %\)", row.source).groups()
        assert float(hi) - float(lo) > 10.0, f"{name}: interval no longer wide"

    esr = variation_for("ESR")
    assert "NO SOURCE" in esr.source
    assert "THIS IS THE ROW TO SETTLE FIRST" in esr.source


def test_no_row_carries_a_reference_range():
    fields = set(LabVariation.__dataclass_fields__)
    for forbidden in ("reference_low", "reference_high", "optimal_low", "optimal_high"):
        assert forbidden not in fields
