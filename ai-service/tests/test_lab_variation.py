"""The hand-written variation table, and the one claim it must never make.

This file exists mostly to hold ONE assertion: that no row claims to be
verified. Everything else here protects the lookup.
"""

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
    """THE ASSERTION THIS FILE IS FOR.

    `verified=True` may only be set by a human who has compared the row to its
    cited source. Nothing in this repository sets it, and if a future change
    flips a row without that having happened, this is the test that says so --
    loudly, because the flag is what a reader is told about provenance.

    IF YOU ARE HERE BECAUSE THIS TEST FAILED: the question is not whether the
    number looks right. It is whether somebody opened the source named in that
    row and compared it. If they did, update this test with who and when.
    """
    unverified = [row.test for row in TABLE if not row.verified]
    assert len(unverified) == len(TABLE), (
        "a row is marked verified; see this test's docstring before changing it"
    )


def test_every_row_names_a_source_to_check_it_against():
    # A figure with no source is the thing the table was built to replace. A
    # row without one would be a model answer with better manners.
    for row in TABLE:
        assert row.source and len(row.source) > 20, row.test


def test_every_row_passes_the_same_cv_gate_as_the_model():
    """A typo in a hand-written table is MORE dangerous than a hallucination.

    It would reach a patient carrying the authority of having been reviewed.
    So the table is not exempt from the check that a CV is the right kind of
    quantity.
    """
    low, high = CV_PERMITTED
    for row in TABLE:
        assert low <= row.analytical_cv_pct <= high, row.test
        assert low <= row.within_subject_cv_pct <= high, row.test


def test_no_two_rows_claim_the_same_printed_name():
    # A collision would make a test's threshold depend on declaration order.
    assert duplicate_aliases() == ()


def test_every_row_declares_a_polarity_this_service_understands():
    from app.services.lab_polarity import _POLARITY_WORDS

    for row in TABLE:
        assert row.polarity in _POLARITY_WORDS, row.test
    # And never `unknown`: a row that cannot say which way is worse has no
    # business in a table whose purpose is to answer that.
    for row in TABLE:
        assert row.polarity != "unknown", row.test


@pytest.mark.parametrize(
    "printed,expected",
    [
        # The real spellings off this account's two reports, which is the
        # whole reason the lookup folds to a sorted word set.
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


# --------------------------------------------------------------------------
# THE ASSAY METHOD IS NOT PART OF THE TEST NAME
# --------------------------------------------------------------------------
#
# FOUND BY RE-ANALYSING A REPORT, 2026-09-19. The same PDF extracted twice
# gave `ESR` one day and `ESR WESTGARD` the next -- the method line folded
# into the name, because extraction is a model call and is not deterministic.
#
# The series still joined, because Module 36 matched the two spellings. But
# this lookup is exact, so three tests silently stopped finding their rows and
# went back to asking the model for their CVa/CVi -- a threshold that moves
# between page loads, which is the whole defect this table was built to end.


@pytest.mark.parametrize(
    "printed,expected",
    [
        # THE THREE THAT BROKE, exactly as the re-extraction stored them.
        ("ESR WESTGARD", "esr"),
        ("SGPT PHOTOMETRIC", "alanine_aminotransferase"),
        ("C-REACTIVE PROTEIN(CRP) Immunoturbidimetric", "c_reactive_protein"),
        # Both spellings of the immunoturbidimetric method appear in the wild:
        # the report prints one and the model returned the other.
        ("C-REACTIVE PROTEIN(CRP) Immunoturbidometric", "c_reactive_protein"),
        # Methods this platform has not seen yet, but will.
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
        # DIRECT AND CALCULATED LDL ARE DIFFERENT MEASUREMENTS, and
        # `LDL Cholesterol, Direct` is in the real stored data. Stripping
        # `direct` would make two different things one -- the same failure the
        # qualifier guard in Module 36 exists to prevent.
        "LDL Cholesterol, Direct",
        "Free Frimbulin",
        "Total Frimbulin",
    ],
)
def test_a_word_that_changes_the_measurement_is_never_stripped(printed):
    from app.data.lab_variation import _without_method

    assert _without_method(printed) == fold(printed), printed


def test_the_exact_fold_wins_so_the_fallback_cannot_divert_a_listed_name():
    """A listed alias must never be re-routed by the method fallback."""
    for alias in ("ESR", "SGPT", "C-REACTIVE PROTEIN(CRP)", "TSH", "MCV"):
        assert variation_for(alias) is not None, alias


def test_a_name_made_only_of_method_words_matches_nothing():
    # Matching it to anything would be worse than reaching the model.
    assert variation_for("PHOTOMETRIC HPLC") is None
    assert variation_for("WESTGARD") is None


def test_fold_itself_is_unchanged_because_the_backend_shares_its_rule():
    """THE INVARIANT THE FIX WAS SHAPED AROUND.

    `fold` must stay the same rule as `labSeriesService.nameKey`, which its
    own docstring promises. The stripping lives in the LOOKUP instead, so the
    two services cannot come to disagree about which names are one test --
    silently, and in only one of them.
    """
    from app.data.lab_variation import _without_method

    assert fold("ESR WESTGARD") == "esr westgard"
    assert _without_method("ESR WESTGARD") == "esr"


def test_an_unknown_test_falls_through_rather_than_matching_the_nearest():
    # NOT a fuzzy match. A name this table has never seen must reach the model,
    # not the closest-looking row -- that is how one test's threshold lands on
    # another test's panel.
    assert variation_for("Frimbulator Factor") is None
    assert variation_for("") is None
    assert variation_for(None) is None


def test_the_fold_ignores_case_order_and_punctuation_only():
    assert fold("CRP (C-REACTIVE PROTEIN)") == fold("c-reactive protein(crp)")
    # But it does NOT ignore a different word -- free and total are different
    # tests, and folding must not erase the difference.
    assert fold("Free Frimbulin") != fold("Total Frimbulin")


def test_the_recorded_arithmetic_reproduces_from_the_row():
    """A reviewer must be able to recompute every threshold from the row.

    ESR is the example because it is the row a reader objected to: 35 -> 45 is
    a 28.6 % rise against this figure, so `stable` is arithmetically right and
    the argument is about the figure, which is exactly where it belongs.
    """
    row = variation_for("ESR")
    assert round(reference_change_value(row.analytical_cv_pct, row.within_subject_cv_pct)) == 62


def test_the_provisional_rows_say_so_in_their_source():
    # ESR, eosinophils and basophils are the three weakest rows and each one
    # says so where a reviewer will read it, rather than in a comment.
    for name in ("ESR", "EOSINOPHILS", "BASOPHILS"):
        row = variation_for(name)
        assert "provisional" in row.source.lower() or "vary widely" in row.source.lower()


def test_no_row_carries_a_reference_range():
    """NOT ONE BOUND. 6v records an invented range reaching a patient.

    The interval a value is judged against is the one the patient's own
    laboratory printed, and this table is deliberately incapable of supplying
    one -- asserted on the dataclass rather than on the rows, so a field added
    later fails here.
    """
    fields = set(LabVariation.__dataclass_fields__)
    for forbidden in ("reference_low", "reference_high", "optimal_low", "optimal_high"):
        assert forbidden not in fields
