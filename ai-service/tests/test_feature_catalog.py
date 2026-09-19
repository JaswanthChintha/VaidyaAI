"""Test-name normalisation and the clinician-auditable synonym table.

Every synonym in the table must map to its own feature, and the guards that
stop urine/CSF results and lipid sub-fractions being folded into blood
features must hold.
"""

from __future__ import annotations

import pytest

from app.data.feature_catalog import (
    CANONICAL_FEATURES,
    FEATURE_SYNONYMS,
    FEATURES,
    LAB_FEATURES,
    PROFILE_FEATURES,
    SOURCE_LAB_REPORT,
    SOURCE_PATIENT_PROFILE,
    SYNONYM_INDEX,
    UnmappedReason,
    lookup_test_name,
    normalize_gender,
    normalize_smoking_history,
    normalize_test_name,
    normalize_tristate_boolean,
    strip_qualifiers,
)

# --------------------------------------------------------------------------
# The canonical feature set matches the specification
# --------------------------------------------------------------------------

SPEC_FEATURES = [
    "hba1c",
    "blood_glucose",
    "hemoglobin",
    "vitamin_d",
    "vitamin_b12",
    "creatinine",
    "cholesterol",
    "triglycerides",
    "bmi",
    "age",
    "hypertension",
    "heart_disease",
    "smoking_history",
]


@pytest.mark.parametrize("name", SPEC_FEATURES)
def test_every_spec_feature_exists(name):
    assert name in CANONICAL_FEATURES
    assert FEATURES[name].name == name


def test_lab_and_profile_features_are_disjoint_and_complete():
    assert set(LAB_FEATURES) & set(PROFILE_FEATURES) == set()
    assert set(LAB_FEATURES) | set(PROFILE_FEATURES) == set(CANONICAL_FEATURES)
    assert set(LAB_FEATURES) == {
        "hba1c",
        "blood_glucose",
        "hemoglobin",
        "vitamin_d",
        "vitamin_b12",
        "creatinine",
        "cholesterol",
        "triglycerides",
        # ---- the complete blood count, added with the Module 31 tables ----
        # Listed one per line rather than derived, so that a feature
        # disappearing from the catalogue fails here instead of shrinking a
        # still-green set comparison.
        "hematocrit",
        "rbc_count",
        "mcv",
        "mch",
        "mchc",
        "wbc_count",
        "neutrophils",
        "lymphocytes",
        "monocytes",
        "eosinophils",
        "basophils",
        "platelet_count",
    }


def test_profile_features_are_sourced_from_the_patient_profile():
    for name in PROFILE_FEATURES:
        assert FEATURES[name].source == SOURCE_PATIENT_PROFILE
    for name in LAB_FEATURES:
        assert FEATURES[name].source == SOURCE_LAB_REPORT


def test_only_lab_features_have_a_synonym_table():
    assert set(FEATURE_SYNONYMS) == set(LAB_FEATURES)


# --------------------------------------------------------------------------
# Name normalisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("HbA1c", "hba1c"),
        ("Hb A1c", "hb a1c"),
        ("  HbA1c  ", "hba1c"),
        ("HB-A1C", "hb a1c"),
        ("Vitamin D (25-OH)", "vitamin d 25 oh"),
        ("Haemoglobin", "hemoglobin"),
        ("Glycosylated Haemoglobin", "glycosylated hemoglobin"),
        ("TOTAL CHOLESTEROL", "total cholesterol"),
        ("Créatinine", "creatinine"),
        ("Vitamin  B12", "vitamin b12"),
    ],
)
def test_normalize_test_name(printed, expected):
    assert normalize_test_name(printed) == expected


def test_strip_qualifiers_removes_method_and_specimen_words():
    assert strip_qualifiers("serum creatinine level") == "creatinine"
    assert strip_qualifiers("total cholesterol serum") == "total cholesterol"
    # A single remaining token is never stripped away to nothing.
    assert strip_qualifiers("serum") == "serum"


# --------------------------------------------------------------------------
# Every synonym in the table resolves to its own feature
# --------------------------------------------------------------------------

ALL_SYNONYMS = [
    (feature, syn.term)
    for feature, syns in FEATURE_SYNONYMS.items()
    for syn in syns
]


@pytest.mark.parametrize("feature,term", ALL_SYNONYMS)
def test_every_synonym_maps_to_its_feature(feature, term):
    match, reason = lookup_test_name(term)
    assert reason is None, f"{term!r} was rejected: {reason}"
    assert match is not None
    assert match.feature == feature, f"{term!r} mapped to {match.feature}"


@pytest.mark.parametrize("feature,term", ALL_SYNONYMS)
def test_every_synonym_is_case_and_punctuation_insensitive(feature, term):
    for variant in (term.upper(), term.lower(), f"  {term}  ", term.replace(" ", "-")):
        match, _ = lookup_test_name(variant)
        assert match is not None, f"variant {variant!r} of {term!r} did not map"
        assert match.feature == feature


def test_synonym_index_has_no_cross_feature_collisions():
    # Building the index raises on collision; assert the built index is sane.
    for key, match in SYNONYM_INDEX.items():
        assert match.feature in FEATURE_SYNONYMS
        assert normalize_test_name(key) == key


# --------------------------------------------------------------------------
# The spec's own example, plus real observed Module 4 names
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "printed",
    [
        "HbA1c",
        "Hb A1c",
        "Glycated Hemoglobin",
        "Glycosylated Hemoglobin",
        "Glycated Haemoglobin",
        "HBA1C",
        "hba1c",
        "Hb  A1c ",
    ],
)
def test_spec_example_hba1c_synonyms(printed):
    match, _ = lookup_test_name(printed)
    assert match is not None and match.feature == "hba1c"


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("Vitamin D (25-OH)", "vitamin_d"),
        ("Haemoglobin", "hemoglobin"),
        ("Fasting Blood Glucose", "blood_glucose"),
        ("Total Cholesterol", "cholesterol"),
        ("Creatinine", "creatinine"),
        ("Serum Creatinine", "creatinine"),
        ("S. Creatinine", "creatinine"),
        ("Vitamin B12 (Cobalamin)", "vitamin_b12"),
        ("Triglycerides (TG)", "triglycerides"),
        ("Cholesterol, Total", "cholesterol"),
        ("Creatinine (Jaffe)", "creatinine"),
        ("Vitamin D, 25-Hydroxy", "vitamin_d"),
        ("HAEMOGLOBIN (Hb)", "hemoglobin"),
        ("Blood Sugar - Fasting", "blood_glucose"),
    ],
)
def test_real_world_printed_names(printed, expected):
    match, reason = lookup_test_name(printed)
    assert match is not None, f"{printed!r} unmapped ({reason})"
    assert match.feature == expected


def test_hemoglobin_a1c_is_not_confused_with_hemoglobin():
    a1c, _ = lookup_test_name("Haemoglobin A1c")
    hb, _ = lookup_test_name("Haemoglobin")
    assert a1c.feature == "hba1c"
    assert hb.feature == "hemoglobin"


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "printed",
    [
        "Urine Creatinine",
        "24 Hour Urine Creatinine",
        "Urinary Glucose",
        "CSF Glucose",
        "Urine Ketones",
        "Stool Occult Blood",
    ],
)
def test_non_blood_specimens_are_never_mapped(printed):
    match, reason = lookup_test_name(printed)
    assert match is None
    assert reason in (
        UnmappedReason.NON_BLOOD_SPECIMEN,
        UnmappedReason.NO_SYNONYM,
    )


def test_urine_creatinine_is_rejected_as_a_specimen_mismatch():
    match, reason = lookup_test_name("Urine Creatinine")
    assert match is None
    assert reason == UnmappedReason.NON_BLOOD_SPECIMEN


@pytest.mark.parametrize(
    "printed",
    ["HDL Cholesterol", "LDL Cholesterol", "VLDL Cholesterol", "Non-HDL Cholesterol"],
)
def test_lipid_subfractions_are_not_total_cholesterol(printed):
    match, reason = lookup_test_name(printed)
    assert match is None
    assert reason == UnmappedReason.DISTINCT_ANALYTE


@pytest.mark.parametrize(
    # ⚠ "Platelet Count" WAS IN THIS LIST AND IS NOT UNKNOWN ANY MORE. It is
    # a canonical feature with a population table and a knowledge document,
    # so asserting that it maps to nothing would now be satisfied only by
    # removing the mapping. The remaining five are still genuinely unmapped;
    # TSH and ESR are known gaps recorded in MEMORY.md.
    "printed", ["Sodium", "Potassium", "TSH", "ESR", "Bilirubin"]
)
def test_unknown_tests_report_no_canonical_feature(printed):
    match, reason = lookup_test_name(printed)
    assert match is None
    assert reason == UnmappedReason.NO_SYNONYM


@pytest.mark.parametrize("printed", ["", "   ", "\t"])
def test_empty_test_names_are_reported(printed):
    match, reason = lookup_test_name(printed)
    assert match is None
    assert reason == UnmappedReason.EMPTY_TEST_NAME


# --------------------------------------------------------------------------
# Glucose specificity ranking
# --------------------------------------------------------------------------


def test_fasting_glucose_outranks_postprandial_and_random():
    fasting, _ = lookup_test_name("Fasting Blood Glucose")
    plain, _ = lookup_test_name("Glucose")
    random_, _ = lookup_test_name("Random Blood Sugar")
    pp, _ = lookup_test_name("Post Prandial Blood Sugar")
    assert fasting.preference > plain.preference > random_.preference > pp.preference


# --------------------------------------------------------------------------
# Patient-profile vocabularies
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("never", "never"),
        ("Never", "never"),
        ("former", "former"),
        ("current", "current"),
        ("ever", "ever"),
        ("not_current", "not_current"),
        ("not current", "not_current"),
        ("no_info", "no_info"),
        ("No Info", "no_info"),
        ("ex-smoker", "former"),
        ("non smoker", "never"),
    ],
)
def test_smoking_history_categories(printed, expected):
    assert normalize_smoking_history(printed) == expected


def test_unrecognised_smoking_history_is_not_guessed():
    assert normalize_smoking_history("sometimes on weekends") is None


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("male", "male"),
        ("Female", "female"),
        ("other", "other"),
        ("prefer_not_to_say", "prefer_not_to_say"),
        ("prefer not to say", "prefer_not_to_say"),
        ("M", "male"),
        ("f", "female"),
    ],
)
def test_gender_categories(printed, expected):
    assert normalize_gender(printed) == expected


def test_unrecognised_gender_is_not_guessed():
    assert normalize_gender("banana") is None


# --------------------------------------------------------------------------
# Tri-state booleans -- absent is NOT false
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("false", False),
        ("Yes", True),
        ("no", False),
        (1, True),
        (0, False),
    ],
)
def test_tristate_boolean_recognised_values(raw, expected):
    value, recognised = normalize_tristate_boolean(raw)
    assert recognised is True
    assert value is expected


@pytest.mark.parametrize("raw", [None, "", "unknown", "no info", "not known"])
def test_tristate_boolean_unknown_is_none_not_false(raw):
    value, recognised = normalize_tristate_boolean(raw)
    assert recognised is True
    assert value is None
    assert value is not False


def test_tristate_boolean_garbage_is_reported_not_guessed():
    value, recognised = normalize_tristate_boolean("maybe-ish")
    assert recognised is False
    assert value is None


# --------------------------------------------------------------------------
# Comma-separated qualifiers
# --------------------------------------------------------------------------
#
# A REAL REPORT PRINTED "GLYCOSYLATED HEMOGLOBIN, HbA1c" AND IT MAPPED TO
# NOTHING. Both halves are independently valid synonyms of `hba1c`, and the
# parenthetical form of the same name -- "Glycosylated Hemoglobin (HbA1c)" --
# already worked; only the comma form did not. On a report whose only test was
# that one, the analysis produced zero features and every row of the dashboard
# read "Not measured", which reads as the platform having lost the results
# rather than as never having understood the name.


def test_a_comma_separated_qualifier_maps_like_the_parenthetical_one():
    from app.data.feature_catalog import lookup_test_name

    comma, _ = lookup_test_name("GLYCOSYLATED HEMOGLOBIN, HbA1c")
    paren, _ = lookup_test_name("Glycosylated Hemoglobin (HbA1c)")
    assert comma is not None
    assert paren is not None
    assert comma.feature == paren.feature == "hba1c"
    # Not an exact match: the printed name is not the synonym, part of it is.
    assert comma.exact is False


@pytest.mark.parametrize(
    "printed,feature",
    [
        ("Cholesterol, Total", "cholesterol"),
        ("Creatinine, Serum", "creatinine"),
        ("Glucose, Fasting", "blood_glucose"),
        ("Vitamin D, 25-Hydroxy", "vitamin_d"),
    ],
)
def test_ordinary_comma_qualifiers_still_reach_their_feature(printed, feature):
    from app.data.feature_catalog import lookup_test_name

    match, reason = lookup_test_name(printed)
    assert match is not None, reason
    assert match.feature == feature


@pytest.mark.parametrize("printed", ["Cholesterol, LDL", "Cholesterol, HDL", "Cholesterol, VLDL"])
def test_a_lipid_subfraction_is_still_refused_after_the_comma(printed):
    """THE CASE A WRONG GUESS WOULD BE CLINICALLY SERIOUS.

    `cholesterol` means TOTAL cholesterol. Folding an LDL value into it would
    put the wrong number under a threshold built for a different one. The
    distinct-analyte guard runs against the whole printed name before any
    candidate is tried, so the comma branch can never reach these.
    """
    from app.data.feature_catalog import lookup_test_name
    from app.data.feature_catalog import UnmappedReason

    match, reason = lookup_test_name(printed)
    assert match is None
    assert reason == UnmappedReason.DISTINCT_ANALYTE


def test_segments_naming_different_features_are_refused_not_guessed():
    """Two halves that disagree is a name this function does not understand."""
    from app.data.feature_catalog import lookup_test_name
    from app.data.feature_catalog import UnmappedReason

    match, reason = lookup_test_name("Haemoglobin, Glucose")
    assert match is None
    assert reason == UnmappedReason.NO_SYNONYM


def test_a_comma_name_with_no_known_segment_is_still_unmapped():
    from app.data.feature_catalog import lookup_test_name
    from app.data.feature_catalog import UnmappedReason

    match, reason = lookup_test_name("Widget Count, Deluxe")
    assert match is None
    assert reason == UnmappedReason.NO_SYNONYM


# ==========================================================================
# `description` IS A LABEL, AND IS RENDERED TO READERS
# ==========================================================================
#
# It reaches the comparison table, the clinician summary, the progress table
# and the explanation prompt, and it is fed to the RAG retriever as a search
# term. Four profile entries carried an internal note instead, and a patient
# comparing two reports was shown:
#
#     "Self-described gender as stored by Module 2."
#     "Smoking history, diabetes-dataset categories."
#
# -- a module number and the name of a training dataset. The `hypertension`
# and `heart_disease` entries would have printed
# "TRI-STATE: true / false / absent(unknown)" the moment they appeared.
#
# This is the fourth place this platform has leaked its own vocabulary onto a
# reader-facing surface (MEMORY.md 6u, 6w, 6af, 6an-e). Every previous fix was
# applied to the SURFACE. This one is at the source, so the guard belongs here
# too -- a scan of the table itself, which no rendering test can substitute
# for because a label is only wrong once someone renders it.


_FORBIDDEN_IN_A_LABEL = (
    "module",          # "as stored by Module 2"
    "tri-state",       # an implementation contract
    "dataset",         # "diabetes-dataset categories"
    "absent(unknown)",
    "true / false",
)


def test_no_feature_label_names_this_platform_s_own_machinery():
    from app.data.feature_catalog import FEATURES

    offenders = []
    for name, definition in FEATURES.items():
        lowered = definition.description.lower()
        for banned in _FORBIDDEN_IN_A_LABEL:
            if banned in lowered:
                offenders.append(f"{name}: {definition.description!r} contains {banned!r}")
    assert offenders == []


def test_every_feature_label_reads_as_a_name_not_a_sentence():
    """A label is a noun phrase. A full stop is the tell that a note crept in.

    Both of the strings this test was written for ended in one, and neither
    was a label: they were sentences explaining the field to a maintainer.
    """
    from app.data.feature_catalog import FEATURES

    offenders = [
        f"{name}: {d.description!r}"
        for name, d in FEATURES.items()
        if d.description.rstrip().endswith(".")
    ]
    assert offenders == []


def test_every_feature_has_a_non_empty_label():
    """The floor. An empty label renders as nothing at all, which is worse
    than a clumsy one -- a row with no name is a row a reader cannot act on.
    """
    from app.data.feature_catalog import FEATURES

    assert [n for n, d in FEATURES.items() if not d.description.strip()] == []



# --------------------------------------------------------------------------
# THE PARENTHETICAL WHOSE GOOD HALF IS INSIDE THE BRACKETS
#
# Found on a real laboratory report, and the cost was not a missing row. The
# dashboard told a reader with a prediabetic-range HbA1c that the test was NOT
# ON THEIR REPORT, while the same page listed it among the tests the
# laboratory had flagged HIGH. An absence reported as a fact about the
# document, about a test that was in it.
# --------------------------------------------------------------------------


def test_the_misspelled_outer_half_no_longer_throws_away_the_good_inner_half():
    """The exact string off the report, not a tidied version of it.

    "GLYSOLATED" is the laboratory's own misspelling of GLYCOSYLATED, so the
    outer half matches nothing. The inner "( HBA1C)" -- leading space and all
    -- is an exact synonym, and every candidate before this branch either kept
    the parenthetical or discarded it without ever trying its contents.
    """
    from app.data.feature_catalog import lookup_test_name

    match, reason = lookup_test_name("GLYSOLATED HAEMOGLOBIN ( HBA1C)")
    assert reason is None
    assert match is not None
    assert match.feature == "hba1c"
    # NEVER `exact`: the printed name is not the synonym, a part of it is.
    assert match.exact is False


def test_segments_naming_different_features_are_refused():
    """THE AGREEMENT RULE, and the whole safety of the branch.

    The fixture is shaped to reach this branch and nothing else: the outer
    half is meaningless, so no earlier candidate can resolve it, and the two
    parentheticals name different features. A name this module does not
    understand is reported, never guessed at.
    """
    from app.data.feature_catalog import UnmappedReason, lookup_test_name

    match, reason = lookup_test_name("ZZZ (Creatinine) (HbA1c)")
    assert match is None
    assert reason == UnmappedReason.NO_SYNONYM


def test_a_lipid_subfraction_is_still_refused_before_any_segment_is_tried():
    """The case where a wrong guess would be clinically serious.

    Mapping an LDL value into TOTAL cholesterol puts a number against a
    threshold it was never measured for. `DISTINCT_ANALYTE_TOKENS` is checked
    against the WHOLE name above, so this returns before the parenthetical
    branch exists -- and it must stay above it.
    """
    from app.data.feature_catalog import UnmappedReason, lookup_test_name

    for name in ("Cholesterol (LDL)", "Cholesterol (HDL)", "Cholesterol (VLDL)"):
        match, reason = lookup_test_name(name)
        assert match is None, name
        assert reason == UnmappedReason.DISTINCT_ANALYTE, name


def test_a_parenthetical_that_names_nothing_stays_unmapped():
    """The branch may not turn "no idea" into a guess."""
    from app.data.feature_catalog import UnmappedReason, lookup_test_name

    match, reason = lookup_test_name("GLYSOLATED HAEMOGLOBIN (SPECIMEN 4)")
    assert match is None
    assert reason == UnmappedReason.NO_SYNONYM


def test_names_that_already_mapped_are_decided_exactly_as_before():
    """PURELY ADDITIVE, and this is what makes the change safe to ship.

    The branch runs only after all four candidates miss, so it can turn a
    refusal into a mapping and can never turn one mapping into another.
    `Creatinine (HbA1c)` is the case that proves it: the outer half is a valid
    synonym, so the candidate loop resolves it to creatinine and the agreement
    rule never sees it.
    """
    from app.data.feature_catalog import lookup_test_name

    assert lookup_test_name("Creatinine (HbA1c)")[0].feature == "creatinine"
    assert lookup_test_name("Glycosylated Haemoglobin (HbA1c)")[0].feature == "hba1c"
    # A bare synonym is still an EXACT match, which consumers rank on.
    bare = lookup_test_name("HbA1c")[0]
    assert bare.feature == "hba1c"
    assert bare.exact is True
