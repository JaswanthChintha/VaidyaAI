"""The recommendation catalogue and its safety scanner.

This is the file that stops VaidyaAI emitting medical advice. The tests here
have two jobs:

  1. prove the catalogue itself is clean, and
  2. prove the scanner that checks it ACTUALLY DETECTS violations -- a scanner
     that matched nothing would pass job 1 vacuously while providing no safety
     at all.
"""

from __future__ import annotations

import pytest

from app.data import recommendation_catalog as rc
from app.data.clinical_rules import COMPOSITE_RULES, THRESHOLD_RULES
from app.schemas.decisions import Recommendation
from app.services.rule_engine import ALL_NOTE_FRAGMENTS


# --------------------------------------------------------------------------
# The structural mechanism
# --------------------------------------------------------------------------


def test_recommendations_can_only_be_built_from_a_code():
    rec = rc.recommendation(rc.DISCUSS_WITH_CLINICIAN)
    assert isinstance(rec, Recommendation)
    assert rec.code == rc.DISCUSS_WITH_CLINICIAN
    assert rec.text == rc.RECOMMENDATIONS[rc.DISCUSS_WITH_CLINICIAN].text


def test_an_unknown_code_raises_and_never_falls_back_to_text():
    with pytest.raises(rc.UnknownRecommendationError):
        rc.recommendation("TAKE_TWO_AND_CALL_ME")


def test_recommendation_helper_takes_no_text_parameter():
    """The API shape IS the safety property: there is no string to inject."""
    import inspect

    parameters = inspect.signature(rc.recommendation).parameters
    assert list(parameters) == ["code"]


def test_recommendations_deduplicates_and_preserves_order():
    codes = (
        rc.DISCUSS_WITH_CLINICIAN,
        rc.NOT_A_DIAGNOSIS,
        rc.DISCUSS_WITH_CLINICIAN,
    )
    resolved = rc.recommendations(codes)
    assert [r.code for r in resolved] == [
        rc.DISCUSS_WITH_CLINICIAN,
        rc.NOT_A_DIAGNOSIS,
    ]


# --------------------------------------------------------------------------
# The catalogue is clean
# --------------------------------------------------------------------------


def test_no_catalogue_text_contains_unsafe_language():
    for code, entry in rc.RECOMMENDATIONS.items():
        assert rc.scan_text(entry.text) == [], f"{code}: {entry.text!r}"


def test_every_entry_records_why_it_exists_and_uses_a_known_category():
    for code, entry in rc.RECOMMENDATIONS.items():
        assert entry.basis.strip(), code
        assert entry.category in rc.CATEGORIES, code
        assert entry.code == code


def test_no_catalogue_text_contains_a_digit():
    """A number in educational text is nearly always a dose or a target.

    The single exception is the analyte's own name, "vitamin B12", which is
    stripped before the check rather than used to weaken it.
    """
    for code, entry in rc.RECOMMENDATIONS.items():
        text = entry.text.replace("B12", "B-twelve")
        assert not any(ch.isdigit() for ch in text), code


def test_rule_band_labels_are_scanned_too():
    """Band labels reach the reader via EvidenceItem.note."""
    for rule in THRESHOLD_RULES:
        for band in rule.bands:
            assert rc.scan_text(band.label) == [], f"{rule.id}: {band.label!r}"
    for rule in COMPOSITE_RULES:
        for band in rule.bands:
            assert rc.scan_text(band.label) == [], f"{rule.id}: {band.label!r}"
        for factor in rule.factors:
            assert rc.scan_text(factor.label) == [], f"{rule.id}: {factor.label!r}"


def test_engine_note_fragments_are_safe():
    for fragment in ALL_NOTE_FRAGMENTS:
        assert rc.scan_text(fragment) == [], fragment


# --------------------------------------------------------------------------
# The scanner is NOT vacuous
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Start metformin as advised.", "medication_name"),
        ("A statin is usually offered.", "medication_name"),
        ("Consider a vitamin D supplement.", "supplementation_advice"),
        ("Take 500 mg in the morning.", "dose_quantity"),
        ("Take 2000 IU each morning.", "dose_quantity"),
        ("The usual dose is small.", "dose_word"),
        ("Take it twice a day.", "dose_frequency"),
        ("Your doctor will prescribe something.", "treatment_instruction"),
        ("This is the standard treatment.", "treatment_instruction"),
        ("Begin therapy immediately.", "treatment_instruction"),
        ("You should take something for this.", "self_administration"),
        ("You have diabetes.", "diagnostic_assertion"),
        ("This is a diagnosis of anaemia.", "diagnostic_assertion"),
        ("This result confirms the problem.", "certainty_claim"),
        ("You will definitely be fine.", "certainty_claim"),
        ("This proves the condition.", "certainty_claim"),
        ("You will develop kidney failure.", "certainty_claim"),
        ("There is no need to see a doctor.", "replaces_clinician"),
    ],
)
def test_scanner_detects_each_class_of_violation(text, expected):
    assert expected in rc.scan_text(text), text


def test_scanner_allows_a_laboratory_concentration_but_not_a_dose():
    # "126 mg/dL" is a threshold; "500 mg" is a dose. The distinction is what
    # lets a rule band cite its threshold without weakening the scanner.
    assert "dose_quantity" not in rc.scan_text("at or above 126 mg/dL")
    assert "dose_quantity" in rc.scan_text("take 500 mg")


def test_assert_safe_raises_on_unsafe_text():
    with pytest.raises(rc.UnsafeRecommendationError):
        rc.assert_safe("Take metformin 500 mg twice a day.", "test")


def test_import_time_check_rejects_an_unsafe_entry():
    """Adding unsafe wording must break the import, not the report."""
    original = dict(rc.RECOMMENDATIONS)
    try:
        rc.RECOMMENDATIONS["BAD"] = rc.CatalogEntry(
            code="BAD",
            text="Take metformin 500 mg twice a day.",
            category=rc.CATEGORY_LIFESTYLE,
            basis="planted by a test",
        )
        with pytest.raises(rc.UnsafeRecommendationError):
            rc._self_check()
    finally:
        rc.RECOMMENDATIONS.clear()
        rc.RECOMMENDATIONS.update(original)


def test_import_time_check_rejects_an_entry_with_no_basis():
    original = dict(rc.RECOMMENDATIONS)
    try:
        rc.RECOMMENDATIONS["BAD"] = rc.CatalogEntry(
            code="BAD",
            text="A perfectly harmless sentence about nothing.",
            category=rc.CATEGORY_LIFESTYLE,
            basis="   ",
        )
        with pytest.raises(ValueError):
            rc._self_check()
    finally:
        rc.RECOMMENDATIONS.clear()
        rc.RECOMMENDATIONS.update(original)


def test_catalog_document_lists_the_forbidden_pattern_names():
    document = rc.catalog_document()
    assert "medication_name" in document["forbidden_patterns"]
    assert set(document["recommendations"]) == set(rc.RECOMMENDATIONS)
