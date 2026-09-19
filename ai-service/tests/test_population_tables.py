"""Module 31 -- the population data layer: policy, loader guards, shipped tables.

Module 31 turns a patient's number into a factual claim about a real surveyed
population. There is no model in that path and no reviewer downstream of it: if
a shipped table drifts, the service keeps answering, confidently, with a wrong
percentile. So the tables themselves are the thing under test here, and they
are asserted AGAINST THE SHIPPED JSON READ DIRECTLY FROM DISK rather than
through `app.population.tables`. A defect in the loader therefore cannot hide a
defect in the data, and vice versa.

What this file covers:

  * `policy.py` -- the reason codes, the DELIBERATE exclusions, and the promise
    that every code a patient can be shown has reviewed wording.
  * `tables.py`'s import-time guards -- proven by INJECTING each failure, not
    merely by observing that the shipped tables pass. A guard nobody has seen
    fail is a guard nobody has tested.
  * every shipped distribution -- grids, cohorts, age bands, units and
    provenance. A table that loses its source, digest or citation fails this
    suite; the loader does not check those, so this file is the only thing that
    does.

No network, no API key, no model. Everything here is data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.unit_conversions import conversion_for, is_known_unit, normalize_unit
from app.population import policy as P
from app.population import tables as T
from app.population.policy import (
    EXCLUDED_FEATURES,
    GENERAL_LIMITATIONS,
    POLICY,
    REASON_CODES,
    REASON_MESSAGES,
    PopulationReason,
)
from app.population.tables import (
    COVERED_FEATURES,
    DISTRIBUTIONS_DIR,
    SUPPORTED_SCHEMA_VERSION,
    TABLE_SEXES,
    TABLES,
    PopulationTableError,
    excluded_reason,
    has_table,
    inventory,
    reason_message,
    table_for,
)

# --------------------------------------------------------------------------
# The shipped JSON, read from disk. Deliberately NOT via `tables.TABLES`.
# --------------------------------------------------------------------------

TABLE_PATHS: List[Path] = sorted(DISTRIBUTIONS_DIR.glob("*.json"))
TABLE_NAMES: List[str] = [p.stem for p in TABLE_PATHS]

#: The features recorded as table-backed. Hard-coded rather than derived from
#: the directory so that a table silently disappearing from `distributions/`
#: is a FAILURE and not a smaller passing run.
#:
#: WAS SEVEN, IS NINETEEN. The twelve complete-blood-count tables were built
#: from `CBC_J.xpt` -- the same NHANES file, cycle and analytic sample that
#: `hemoglobin` already came from, so they cost no new download and no new
#: cohort definition. Listing them here EXPLICITLY is the whole point of the
#: paragraph above: deriving this from the directory would make a lost table
#: a quieter, smaller, still-green run.
EXPECTED_COVERED = [
    "hba1c",
    "hemoglobin",
    "vitamin_d",
    "vitamin_b12",
    "creatinine",
    "cholesterol",
    "bmi",
    # ---- the complete blood count, NHANES 2017-2018 cycle J ----
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
]

#: The one grid every table publishes, from PROVENANCE.md.
EXPECTED_GRID = [1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0, 97.5, 99.0]

EXPECTED_AGE_BANDS = [
    ("20-29 years", 20, 29),
    ("30-39 years", 30, 39),
    ("40-49 years", 40, 49),
    ("50-59 years", 50, 59),
    ("60-69 years", 60, 69),
    ("70-79 years", 70, 79),
    ("80 years and over", 80, None),
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _raw(name: str) -> Dict[str, Any]:
    return json.loads((DISTRIBUTIONS_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture()
def scratch_table(tmp_path: Path):
    """Write a (possibly tampered) copy of a shipped table and load it.

    Used to PROVE each loader guard by making it fire. The shipped files are
    never touched: `mutate` receives a fresh deep copy parsed from disk.
    """

    def _make(feature: str, mutate=None, filename: str | None = None):
        raw = _raw(feature)
        if mutate is not None:
            mutate(raw)
        path = tmp_path / (filename or f"{feature}.json")
        path.write_text(json.dumps(raw), encoding="utf-8")
        return T._load_table(path)

    return _make


# --------------------------------------------------------------------------
# policy.py -- reason codes and their wording
# --------------------------------------------------------------------------


def test_reason_codes_are_unique_and_self_named():
    """A code whose value differs from its attribute name is a silent trap.

    Consumers branch on the STRING, and `REASON_CODES` is built by scanning
    `vars(PopulationReason)`, so a mismatch would ship a code no consumer can
    predict from the source.
    """
    assert len(REASON_CODES) == len(set(REASON_CODES))
    for name, value in vars(PopulationReason).items():
        if name.isupper():
            assert value == name, f"{name} carries the value {value!r}"
            assert value in REASON_CODES


def test_every_reason_code_the_service_can_emit_has_reviewed_wording():
    """A code with no wording reaches a patient as a bare identifier.

    This is `tables._check_reason_messages()`, re-run here so the promise is
    asserted by the suite and not only by the import that happens to precede
    it.
    """
    assert set(REASON_MESSAGES) == set(REASON_CODES)
    for code in REASON_CODES:
        assert reason_message(code).strip()


def test_reason_message_refuses_to_invent_wording_for_an_unknown_code():
    """The fallback is an exception, not a plausible sentence."""
    with pytest.raises(PopulationTableError):
        reason_message("NOT_A_REASON_CODE")


@pytest.mark.parametrize("code", sorted(REASON_CODES))
def test_no_reason_message_makes_a_clinical_claim(code):
    """Module 8 owns "is this in range"; Module 31 owns "how common is this".

    Every refusal sentence is a statement about the SURVEY, never about the
    patient's health, so none of them may carry a risk word, a normal/abnormal
    judgement or a recommendation.
    """
    text = REASON_MESSAGES[code].lower()
    for banned in (
        "risk",
        "normal",
        "abnormal",
        "healthy",
        "unhealthy",
        "should",
        "recommend",
        "diagnos",
        "treat",
        "danger",
        "deficien",
        "elevated",
    ):
        assert banned not in text, f"{code} says {banned!r}"


# --------------------------------------------------------------------------
# The deliberate exclusions
# --------------------------------------------------------------------------


@pytest.mark.parametrize("feature", ["blood_glucose", "triglycerides"])
def test_the_fasting_dependent_analytes_stay_excluded_for_the_stated_reason(feature):
    """These two are EXCLUDED, not missing, and the reason must not drift.

    Fasting status is recorded nowhere in the VaidyaAI pipeline. Comparing a
    random glucose or a post-prandial triglyceride against a fasting survey
    population produces, in the policy file's own words, "a percentile that
    looks precise and is wrong". If a future edit ships a table for either,
    this test is what stops it going out unnoticed.
    """
    assert feature in EXCLUDED_FEATURES
    assert not has_table(feature), f"{feature} must not gain a table"
    assert table_for(feature) is None
    code, message = excluded_reason(feature)
    assert code == PopulationReason.NO_VERIFIED_DISTRIBUTION
    assert "fasting" in message.lower()
    assert message == EXCLUDED_FEATURES[feature]["message"]


@pytest.mark.parametrize(
    "feature", ["hypertension", "heart_disease", "smoking_history", "gender", "age"]
)
def test_the_non_measurements_are_excluded_as_not_continuous(feature):
    """A tri-state boolean or a category has no distribution to sit in.

    `age` and `gender` additionally are the things a cohort is MATCHED on, so
    giving either a percentile would be circular.
    """
    code, message = excluded_reason(feature)
    assert code == PopulationReason.FEATURE_NOT_CONTINUOUS
    assert message.strip()


def test_every_canonical_feature_is_either_table_backed_or_explicitly_excluded():
    """The promise `policy.py` makes above EXCLUDED_FEATURES, asserted.

    A feature in neither list would simply never appear in a response, which
    from outside is indistinguishable from having been forgotten.
    """
    for name in CANONICAL_FEATURES:
        assert has_table(name) or name in EXCLUDED_FEATURES, name
    assert set(COVERED_FEATURES) & set(EXCLUDED_FEATURES) == set()
    assert set(COVERED_FEATURES) | set(EXCLUDED_FEATURES) == set(CANONICAL_FEATURES)


def test_the_covered_set_is_exactly_the_tables_that_were_built():
    """Named explicitly so a table vanishing from `distributions/` fails."""
    assert sorted(COVERED_FEATURES) == sorted(EXPECTED_COVERED)
    assert sorted(TABLES) == sorted(EXPECTED_COVERED)
    assert sorted(TABLE_NAMES) == sorted(EXPECTED_COVERED)
    # Catalogue order, so responses are ordered by the catalogue not the disk.
    assert list(COVERED_FEATURES) == [
        n for n in CANONICAL_FEATURES if n in EXPECTED_COVERED
    ]


# --------------------------------------------------------------------------
# The catalogue-completeness guard -- PROVEN BY INJECTION
# --------------------------------------------------------------------------


def test_catalogue_cover_guard_passes_as_shipped():
    T._check_catalogue_cover()
    T._check_reason_messages()


def test_a_new_canonical_feature_with_no_decision_fails_the_import_guard(monkeypatch):
    """THE guard that stops a feature silently vanishing from responses.

    Injecting a canonical feature that has neither a distribution table nor an
    `EXCLUDED_FEATURES` entry must stop the process, because the alternative is
    a feature that never appears in a population response and looks exactly
    like one that was forgotten.
    """
    monkeypatch.setattr(
        T, "CANONICAL_FEATURES", tuple(CANONICAL_FEATURES) + ("fake_analyte",)
    )
    with pytest.raises(PopulationTableError) as excinfo:
        T._check_catalogue_cover()
    assert "fake_analyte" in str(excinfo.value)


def test_an_exclusion_for_a_feature_the_catalogue_dropped_fails_the_guard(monkeypatch):
    """A stale exclusion hides the fact that nothing is being excluded."""
    monkeypatch.setattr(
        T,
        "EXCLUDED_FEATURES",
        {**EXCLUDED_FEATURES, "retired_analyte": {"reason_code": "X", "message": "y"}},
    )
    with pytest.raises(PopulationTableError) as excinfo:
        T._check_catalogue_cover()
    assert "retired_analyte" in str(excinfo.value)


def test_an_exclusion_carrying_an_unknown_reason_code_fails_the_guard(monkeypatch):
    """A code no consumer can branch on is not a machine-readable refusal."""
    broken = {k: dict(v) for k, v in EXCLUDED_FEATURES.items()}
    broken["blood_glucose"]["reason_code"] = "MADE_UP_CODE"
    monkeypatch.setattr(T, "EXCLUDED_FEATURES", broken)
    with pytest.raises(PopulationTableError):
        T._check_catalogue_cover()


def test_an_exclusion_with_no_message_fails_the_guard(monkeypatch):
    """A refusal a patient cannot read is not a refusal."""
    broken = {k: dict(v) for k, v in EXCLUDED_FEATURES.items()}
    broken["triglycerides"]["message"] = "   "
    monkeypatch.setattr(T, "EXCLUDED_FEATURES", broken)
    with pytest.raises(PopulationTableError):
        T._check_catalogue_cover()


def test_a_reason_code_with_no_patient_wording_fails_the_import_guard(monkeypatch):
    monkeypatch.setattr(T, "REASON_CODES", tuple(REASON_CODES) + ("BRAND_NEW_CODE",))
    with pytest.raises(PopulationTableError) as excinfo:
        T._check_reason_messages()
    assert "BRAND_NEW_CODE" in str(excinfo.value)


def test_wording_for_a_code_that_no_longer_exists_fails_the_import_guard(monkeypatch):
    monkeypatch.setattr(
        T, "REASON_MESSAGES", {**REASON_MESSAGES, "GHOST_CODE": "orphaned copy"}
    )
    with pytest.raises(PopulationTableError) as excinfo:
        T._check_reason_messages()
    assert "GHOST_CODE" in str(excinfo.value)


def test_the_guards_raise_rather_than_assert_so_python_dash_o_cannot_strip_them():
    """`python -O` removes `assert`. These guarantees must survive it.

    `PopulationTableError` deriving from `RuntimeError` (not
    `AssertionError`) is the observable form of that decision.
    """
    assert issubclass(PopulationTableError, RuntimeError)
    assert not issubclass(PopulationTableError, AssertionError)
    with pytest.raises(PopulationTableError):
        T._require(False, "boom")


# --------------------------------------------------------------------------
# Loader guards -- each proven by feeding the loader a tampered copy
# --------------------------------------------------------------------------


def test_a_well_formed_copy_still_loads(scratch_table):
    """The negative tests below only mean something if the positive one holds."""
    table = scratch_table("hba1c")
    assert table.feature == "hba1c"
    assert len(table.cohorts) == 14


def test_a_cohort_whose_values_decrease_is_refused(scratch_table):
    """A quantile function cannot decrease. If it does, the table is wrong."""

    def mutate(raw):
        raw["cohorts"][0]["percentile_values"][5] = 0.0

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("hba1c", mutate)
    assert "monotone" in str(excinfo.value)


def test_a_cohort_out_of_step_with_the_grid_is_refused(scratch_table):
    """An index-misaligned table reports a wrong band for EVERY value."""

    def mutate(raw):
        raw["cohorts"][0]["percentile_values"].pop()

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("bmi", mutate)
    assert "cut-points" in str(excinfo.value)


def test_a_non_increasing_percentile_grid_is_refused(scratch_table):
    def mutate(raw):
        raw["percentile_grid"][3] = raw["percentile_grid"][2]

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate)


def test_a_grid_reaching_the_sample_extremes_is_refused(scratch_table):
    """The 0th and 100th are the sample's min and max, not cut-points."""

    def mutate(raw):
        raw["percentile_grid"][0] = 0.0

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate)


def test_overlapping_age_bands_are_refused(scratch_table):
    """Overlap would make the answer depend on the JSON's own ordering.

    Two runs could then compare the same patient against two different
    populations -- the same words over a different claim.
    """

    def mutate(raw):
        for cell in raw["cohorts"]:
            if cell["cohort_id"] == "male_30_39":
                cell["age_min"] = 25

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("hemoglobin", mutate)
    assert "overlapping" in str(excinfo.value)


def test_an_open_band_that_is_not_last_is_refused(scratch_table):
    def mutate(raw):
        for cell in raw["cohorts"]:
            if cell["cohort_id"] == "male_20_29":
                cell["age_max"] = None

    with pytest.raises(PopulationTableError):
        scratch_table("hemoglobin", mutate)


def test_a_table_naming_a_feature_the_catalogue_does_not_have_is_refused(
    scratch_table,
):
    def mutate(raw):
        raw["feature"] = "not_a_feature"

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate, filename="not_a_feature.json")


def test_a_table_whose_declared_feature_disagrees_with_its_filename_is_refused(
    scratch_table,
):
    """The filename is the key the service looks a table up by."""
    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("bmi", filename="cholesterol.json")
    assert "file name" in str(excinfo.value)


def test_an_unrecognised_schema_version_is_refused(scratch_table):
    def mutate(raw):
        raw["schema_version"] = SUPPORTED_SCHEMA_VERSION + 1

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate)


def test_a_table_unit_this_service_cannot_convert_into_is_refused(scratch_table):
    """A unit typo silently compares a value against a distribution of
    something else, which is the worst failure this module has."""

    def mutate(raw):
        raw["unit"] = "mmol/l"

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate)


def test_a_table_unit_written_in_a_non_normalised_spelling_is_refused(scratch_table):
    def mutate(raw):
        raw["unit"] = "mg/dL"

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("cholesterol", mutate)
    assert "normalised" in str(excinfo.value)


def test_a_cohort_representing_nobody_is_refused(scratch_table):
    def mutate(raw):
        raw["cohorts"][0]["n_unweighted"] = 0

    with pytest.raises(PopulationTableError):
        scratch_table("creatinine", mutate)


def test_a_cohort_with_a_sex_the_tables_do_not_stratify_on_is_refused(scratch_table):
    def mutate(raw):
        raw["cohorts"][0]["sex"] = "other"

    with pytest.raises(PopulationTableError):
        scratch_table("creatinine", mutate)


def test_a_dropped_band_that_is_also_published_is_refused(scratch_table):
    """`dropped_for()` and `cohort_for()` would both answer, and the service
    would silently have to choose."""

    def mutate(raw):
        raw["dropped_cohorts"] = [
            {"sex": "male", "age_band": "20-29", "n_unweighted": 9}
        ]

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("hba1c", mutate)
    assert "overlaps" in str(excinfo.value)


def test_a_dropped_band_in_an_unparseable_format_is_refused(scratch_table):
    """Silently failing to parse it would downgrade an honest
    COHORT_TOO_SMALL_TO_PUBLISH into the vaguer AGE_OUTSIDE_TABLE_RANGE."""

    def mutate(raw):
        raw["dropped_cohorts"] = [
            {"sex": "male", "age_band": "twenties", "n_unweighted": 9}
        ]

    with pytest.raises(PopulationTableError):
        scratch_table("hba1c", mutate)


def test_an_unreadable_or_non_json_table_is_refused(tmp_path: Path):
    path = tmp_path / "bmi.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PopulationTableError):
        T._load_table(path)


def test_a_missing_distributions_directory_stops_the_service(monkeypatch, tmp_path):
    """A table this file cannot vouch for must not be served at all."""
    monkeypatch.setattr(T, "DISTRIBUTIONS_DIR", tmp_path / "gone")
    with pytest.raises(PopulationTableError):
        T._load_all()


def test_an_empty_distributions_directory_stops_the_service(monkeypatch, tmp_path):
    monkeypatch.setattr(T, "DISTRIBUTIONS_DIR", tmp_path)
    with pytest.raises(PopulationTableError):
        T._load_all()


# --------------------------------------------------------------------------
# The shipped tables themselves, asserted against the JSON on disk
# --------------------------------------------------------------------------


def test_the_shipped_tables_are_exactly_the_expected_ones_and_nothing_else():
    assert len(TABLE_PATHS) == len(EXPECTED_COVERED)
    assert sorted(TABLE_NAMES) == sorted(EXPECTED_COVERED)


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_shipped_grid_is_the_published_eleven_point_grid(name):
    """One grid for all seven tables, exactly as PROVENANCE.md records it.

    The grid is what a reader re-derives the band from, so a drift here
    changes every band the module reports.
    """
    raw = _raw(name)
    assert raw["percentile_grid"] == EXPECTED_GRID
    assert all(b > a for a, b in zip(EXPECTED_GRID, EXPECTED_GRID[1:]))
    assert 0.0 < EXPECTED_GRID[0] and EXPECTED_GRID[-1] < 100.0


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_cohort_is_index_aligned_with_the_grid_and_never_decreases(name):
    """The two failure modes that silently shift every reported band."""
    raw = _raw(name)
    grid = raw["percentile_grid"]
    assert raw["cohorts"], f"{name}: publishes no cohorts"
    for cell in raw["cohorts"]:
        values = cell["percentile_values"]
        assert len(values) == len(grid), f"{name}/{cell['cohort_id']}"
        assert all(
            b >= a for a, b in zip(values, values[1:])
        ), f"{name}/{cell['cohort_id']}: quantiles decrease"
        assert all(isinstance(v, (int, float)) for v in values)
        # ⚠ ZERO IS A REAL RESULT FOR SOME ANALYTES, AND THIS ASSERTED `> 0`.
        #
        # It held for every table shipped before the complete blood count,
        # because a living person's haemoglobin, creatinine or BMI cannot be
        # zero. A DIFFERENTIAL PERCENTAGE CAN: the female 70-79 eosinophil
        # cohort publishes 0.0 at the 1st percentile, and that is not a
        # missing value or a floor artefact -- a real share of surveyed adults
        # had no eosinophils detected on the slide.
        #
        # The check that matters is that the value is not NEGATIVE, which
        # would be a sign error or a mis-parse. The physiological floor per
        # feature is Module 6's job and is asserted in validation_rules.py, so
        # duplicating it here would put the same judgement in two places.
        assert values[0] >= 0, f"{name}/{cell['cohort_id']}: negative quantile"


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_table_publishes_all_fourteen_cells_exactly_once(name):
    """Two sexes x seven age bands. MEMORY §6m: zero dropped cells."""
    raw = _raw(name)
    ids = [c["cohort_id"] for c in raw["cohorts"]]
    assert len(ids) == 14
    assert len(set(ids)) == 14
    seen = {(c["sex"], c["age_band_label"]) for c in raw["cohorts"]}
    assert seen == {
        (sex, label) for sex in TABLE_SEXES for label, _, _ in EXPECTED_AGE_BANDS
    }
    assert raw.get("dropped_cohorts") == []


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
@pytest.mark.parametrize("sex", TABLE_SEXES)
def test_age_bands_are_contiguous_from_twenty_and_open_at_the_top(name, sex):
    """Non-overlapping AND with no gap between them.

    The loader only checks that bands do not overlap. A GAP would be just as
    damaging in the other direction: an adult of a perfectly ordinary age
    would fall through into AGE_OUTSIDE_TABLE_RANGE and be told no comparison
    exists when one does. Nothing in `app/` checks for that, so this is the
    only place it is checked.
    """
    raw = _raw(name)
    bands = sorted(
        (c["age_min"], c["age_max"], c["age_band_label"])
        for c in raw["cohorts"]
        if c["sex"] == sex
    )
    assert [(label, lo, hi) for lo, hi, label in bands] == EXPECTED_AGE_BANDS
    previous_max = None
    for age_min, age_max, _label in bands:
        if previous_max is not None:
            assert age_min == previous_max + 1, f"{name}/{sex}: gap or overlap"
        previous_max = age_max
    assert bands[0][0] == 20, "adults only; a child is never scored here"
    assert bands[-1][1] is None, "NHANES top-codes age at 80; the top band is open"


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_published_cell_meets_the_builds_own_minimum_size(name):
    """A percentile estimated from a handful of people is worse than none."""
    raw = _raw(name)
    floor = raw["method"]["min_cell_unweighted_n"]
    assert floor == 100
    for cell in raw["cohorts"]:
        assert cell["n_unweighted"] >= floor, f"{name}/{cell['cohort_id']}"
        assert cell["weighted_population"] > 0


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_declared_analytic_sample_is_the_sum_of_the_published_cells(name):
    """No cell was dropped, so the counts must reconcile exactly.

    A mismatch would mean either an undeclared dropped cell or a count that
    describes a different analysis from the one shipped.
    """
    raw = _raw(name)
    assert raw["counts"]["analytic_sample"] == sum(
        c["n_unweighted"] for c in raw["cohorts"]
    )
    assert raw["counts"]["analytic_sample"] <= raw["counts"]["merged_records"]


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_table_unit_is_a_unit_this_service_can_convert_a_value_into(name):
    """Otherwise every lookup against the table is UNIT_NOT_CONVERTIBLE."""
    raw = _raw(name)
    unit = raw["unit"]
    assert normalize_unit(unit) == unit, "must be the normalised spelling"
    assert is_known_unit(unit)
    assert conversion_for(name, unit) is not None
    assert FEATURES[name].value_type in ("number", "integer")


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_table_unit_matches_the_feature_catalogue_except_for_vitamin_d(name):
    """Vitamin D is the ONE deliberate mismatch, and it is declared.

    NHANES publishes 25-hydroxyvitamin D in nmol/L; VaidyaAI's canonical unit
    is ng/mL. Every other table publishes in the canonical unit, and a new
    mismatch appearing silently is exactly the defect this asserts against.
    """
    raw = _raw(name)
    canonical = FEATURES[name].canonical_unit
    if name == "vitamin_d":
        assert raw["unit"] == "nmol/l"
        assert canonical == "ng/ml"
        assert "nmol/L" in raw["measurand"]
        assert "never rescaled" in raw["measurand"]
    else:
        assert raw["unit"] == canonical, f"{name}: table unit drifted"


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_table_carries_its_source_digest_and_citation(name):
    """A table that loses its provenance must fail this suite.

    The loader does NOT check any of this -- it copies `source` through
    verbatim -- so this test is the only thing standing between a percentile
    and an unattributable number. A claim about a real population that a
    reader cannot trace back to a named public file at a recorded digest is
    not evidence.
    """
    raw = _raw(name)
    source = raw["source"]
    for field in (
        "name",
        "publisher",
        "cycle",
        "cycle_label",
        "data_file",
        "data_file_url",
        "variable",
        "variable_label",
        "analytic_weight",
        "citation",
    ):
        assert str(source.get(field, "")).strip(), f"{name}: source.{field} missing"
    assert "NHANES" in source["name"] or "NHANES" in source["cycle_label"]
    assert source["analytic_weight"] == "WTMEC2YR"
    for digest_field in ("data_file_sha256", "demographics_file_sha256"):
        digest = source.get(digest_field, "")
        assert _SHA256.match(str(digest)), f"{name}: {digest_field} is not a sha256"
    assert source["data_file_url"].startswith("https://wwwn.cdc.gov/")


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_table_declares_how_it_was_derived_and_from_which_population(name):
    """"computed from published microdata" is not "transcribed from CDC".

    PROVENANCE.md is explicit that these must never be described as CDC-
    published percentile tables, and the declared population is what the
    limitations copy is answerable to.
    """
    raw = _raw(name)
    assert raw["derivation"] == "computed_by_vaidyaai_from_published_microdata"
    assert raw["built_on"].strip()
    population = raw["population"]
    assert population["adults_only"] is True
    assert population["min_age"] == 20
    assert population["pregnant_excluded"] is True
    assert "pregnant" in population["description"].lower()
    method = raw["method"]
    assert "weighted" in method["estimator"].lower()
    assert "no interpolation" in method["estimator"].lower()
    assert method["weight_variable"] == "WTMEC2YR"
    assert method["variance_estimated"] is False


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_loaded_table_reports_the_same_numbers_the_json_holds(name):
    """The loader must not repair, round or re-derive anything.

    A loader that quietly normalised a value would put a number in front of a
    patient that is not the number in the shipped, digest-recorded file.
    """
    raw = _raw(name)
    table = TABLES[name]
    assert table.unit == raw["unit"]
    assert list(table.percentile_grid) == raw["percentile_grid"]
    by_id = {c["cohort_id"]: c for c in raw["cohorts"]}
    assert {c.cohort_id for c in table.cohorts} == set(by_id)
    for cohort in table.cohorts:
        cell = by_id[cohort.cohort_id]
        assert list(cohort.percentile_values) == cell["percentile_values"]
        assert cohort.n_unweighted == cell["n_unweighted"]
        assert cohort.weighted_mean == cell["weighted_mean"]
        assert cohort.age_min == cell["age_min"]
        assert cohort.age_max == cell["age_max"]


# --------------------------------------------------------------------------
# Lookups: no fallback lives in the data layer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
@pytest.mark.parametrize("age", [0, 1, 12, 17, 19, 19.9])
def test_no_cell_is_returned_for_a_child_or_adolescent(name, age):
    """There is no nearest-band fallback in `cohort_for()` to reach for."""
    table = TABLES[name]
    for sex in TABLE_SEXES:
        assert table.cohort_for(sex, age) is None
        assert table.dropped_for(sex, age) is None


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_no_cell_is_returned_for_a_sex_the_survey_did_not_stratify_on(name):
    """`other` is not silently folded into the nearer published stratum."""
    table = TABLES[name]
    for sex in ("other", "prefer_not_to_say", "OTHER", "", "unknown"):
        assert table.cohort_for(sex, 45) is None


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
@pytest.mark.parametrize("age", [20, 29, 30, 45, 79, 80, 95, 120])
def test_exactly_one_cell_matches_any_adult_age(name, age):
    """Contiguity and disjointness together, exercised through the lookup."""
    table = TABLES[name]
    for sex in TABLE_SEXES:
        matches = [c for c in table.cohorts if c.sex == sex and c.covers(age)]
        assert len(matches) == 1, f"{name}/{sex}/{age}: {len(matches)} cells"
        assert table.cohort_for(sex, age) is matches[0]


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_min_age_is_twenty_and_the_table_has_no_upper_bound(name):
    table = TABLES[name]
    assert table.min_age == 20
    assert table.max_age is None


# --------------------------------------------------------------------------
# Vitamin D: the direction of the one conversion
# --------------------------------------------------------------------------


def test_the_vitamin_d_table_is_never_rescaled_the_patients_value_moves():
    """The published nmol/L numbers stay exactly as surveyed.

    Rescaling a published table would make every number in it something no
    NHANES participant was measured at. The audited conversion runs the other
    way: 30 ng/mL of the patient's becomes ~74.88 nmol/L before it is placed.
    """
    table = TABLES["vitamin_d"]
    assert table.unit == "nmol/l"
    assert FEATURES["vitamin_d"].canonical_unit == "ng/ml"

    conversion = conversion_for("vitamin_d", "nmol/l")
    assert conversion is not None
    assert conversion.to_unit == "ng/ml"
    # invert() takes ng/mL to nmol/L -- the direction the service uses.
    assert conversion.invert(30.0) == pytest.approx(74.88, abs=0.01)
    assert conversion.apply(74.88) == pytest.approx(30.0, abs=0.01)

    # And the table's own numbers are on the nmol/L scale, not the ng/mL one.
    raw = _raw("vitamin_d")
    every_value = [v for c in raw["cohorts"] for v in c["percentile_values"]]
    assert max(every_value) > 100, "nmol/L values; a rescaled table would be ~2.5x lower"
    assert TABLES["vitamin_d"].cohorts[0].percentile_values == tuple(
        raw["cohorts"][0]["percentile_values"]
    )


# --------------------------------------------------------------------------
# The policy document and the inventory
# --------------------------------------------------------------------------


def test_the_policy_declares_no_clinical_claim_and_no_model():
    assert POLICY["makes_clinical_claims"] is False
    assert POLICY["calls_an_llm"] is False
    assert POLICY["module"] == 31
    assert POLICY["matching"]["unmatched_cohort_offered"] is False
    assert POLICY["percentile_reporting"]["interpolated"] is False
    assert POLICY["percentile_reporting"]["style"] == (
        "band_between_published_grid_points"
    )
    assert set(POLICY["reason_codes"]) == set(REASON_CODES)


def test_the_limitations_state_what_the_reference_population_is_not():
    """A percentile against a US survey is not a percentile against the
    patient's own population, and the copy has to say so."""
    joined = " ".join(GENERAL_LIMITATIONS).lower()
    assert "nhanes" in joined
    assert "pregnant" in joined
    assert "adults aged 20" in joined
    assert "band" in joined


def test_the_inventory_publishes_provenance_and_the_exclusions_together():
    """A reviewer must be able to see what is covered AND what is not."""
    inv = inventory()
    assert list(inv["covered_features"]) == list(COVERED_FEATURES)
    assert set(inv["excluded_features"]) == set(EXCLUDED_FEATURES)
    for name, entry in inv["excluded_features"].items():
        assert entry["reason_code"] in REASON_CODES
        assert entry["message"] == EXCLUDED_FEATURES[name]["message"]
    for name in COVERED_FEATURES:
        table = inv["tables"][name]
        assert table["source"]["data_file_sha256"]
        assert table["source"]["citation"]
        assert table["cohort_count"] == 14
        assert table["percentile_grid"] == EXPECTED_GRID
        assert table["canonical_unit"] == FEATURES[name].canonical_unit


def test_the_inventory_carries_no_patient_data():
    """It is served by an endpoint; it must be safe to hand to a reviewer.

    The word "patient" DOES occur, in prose explaining that the patient's
    value is converted rather than the table rescaled. What must never occur
    is a field that could carry one: an identifier, a submitted value, or a
    per-person record.
    """
    inv = inventory()
    blob = json.dumps(inv).lower()
    for token in ("patient_ref", "snapshot_id", "patient_name", "value_raw"):
        assert token not in blob
    for name in COVERED_FEATURES:
        table = inv["tables"][name]
        # Only aggregates: sample sizes, weighted totals, published quantiles.
        assert set(table["cohort_sample_sizes"]) == {
            c.cohort_id for c in TABLES[name].cohorts
        }
        assert "percentile_values" not in table
        assert "records" not in table


def test_policy_is_data_only_and_has_no_import_time_side_effects():
    """`policy.py` is the clinician-reviewable layer: tables and strings.

    Control flow in it would mean a reviewer reading the strings is not
    reading what the patient will be shown.
    """
    source = Path(P.__file__).read_text(encoding="utf-8")
    assert "\ndef " not in source, "policy.py grew a function"
    assert "\nif " not in source, "policy.py grew a branch"
