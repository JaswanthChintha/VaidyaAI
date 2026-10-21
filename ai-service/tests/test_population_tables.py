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


TABLE_PATHS: List[Path] = sorted(DISTRIBUTIONS_DIR.glob("*.json"))
TABLE_NAMES: List[str] = [p.stem for p in TABLE_PATHS]

EXPECTED_COVERED = [
    "hba1c",
    "hemoglobin",
    "vitamin_d",
    "vitamin_b12",
    "creatinine",
    "cholesterol",
    "bmi",
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

    def _make(feature: str, mutate=None, filename: str | None = None):
        raw = _raw(feature)
        if mutate is not None:
            mutate(raw)
        path = tmp_path / (filename or f"{feature}.json")
        path.write_text(json.dumps(raw), encoding="utf-8")
        return T._load_table(path)

    return _make


def test_reason_codes_are_unique_and_self_named():
    assert len(REASON_CODES) == len(set(REASON_CODES))
    for name, value in vars(PopulationReason).items():
        if name.isupper():
            assert value == name, f"{name} carries the value {value!r}"
            assert value in REASON_CODES


def test_every_reason_code_the_service_can_emit_has_reviewed_wording():
    assert set(REASON_MESSAGES) == set(REASON_CODES)
    for code in REASON_CODES:
        assert reason_message(code).strip()


def test_reason_message_refuses_to_invent_wording_for_an_unknown_code():
    with pytest.raises(PopulationTableError):
        reason_message("NOT_A_REASON_CODE")


@pytest.mark.parametrize("code", sorted(REASON_CODES))
def test_no_reason_message_makes_a_clinical_claim(code):
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


@pytest.mark.parametrize("feature", ["blood_glucose", "triglycerides"])
def test_the_fasting_dependent_analytes_stay_excluded_for_the_stated_reason(feature):
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
    code, message = excluded_reason(feature)
    assert code == PopulationReason.FEATURE_NOT_CONTINUOUS
    assert message.strip()


def test_every_canonical_feature_is_either_table_backed_or_explicitly_excluded():
    for name in CANONICAL_FEATURES:
        assert has_table(name) or name in EXCLUDED_FEATURES, name
    assert set(COVERED_FEATURES) & set(EXCLUDED_FEATURES) == set()
    assert set(COVERED_FEATURES) | set(EXCLUDED_FEATURES) == set(CANONICAL_FEATURES)


def test_the_covered_set_is_exactly_the_tables_that_were_built():
    assert sorted(COVERED_FEATURES) == sorted(EXPECTED_COVERED)
    assert sorted(TABLES) == sorted(EXPECTED_COVERED)
    assert sorted(TABLE_NAMES) == sorted(EXPECTED_COVERED)
    assert list(COVERED_FEATURES) == [
        n for n in CANONICAL_FEATURES if n in EXPECTED_COVERED
    ]


def test_catalogue_cover_guard_passes_as_shipped():
    T._check_catalogue_cover()
    T._check_reason_messages()


def test_a_new_canonical_feature_with_no_decision_fails_the_import_guard(monkeypatch):
    monkeypatch.setattr(
        T, "CANONICAL_FEATURES", tuple(CANONICAL_FEATURES) + ("fake_analyte",)
    )
    with pytest.raises(PopulationTableError) as excinfo:
        T._check_catalogue_cover()
    assert "fake_analyte" in str(excinfo.value)


def test_an_exclusion_for_a_feature_the_catalogue_dropped_fails_the_guard(monkeypatch):
    monkeypatch.setattr(
        T,
        "EXCLUDED_FEATURES",
        {**EXCLUDED_FEATURES, "retired_analyte": {"reason_code": "X", "message": "y"}},
    )
    with pytest.raises(PopulationTableError) as excinfo:
        T._check_catalogue_cover()
    assert "retired_analyte" in str(excinfo.value)


def test_an_exclusion_carrying_an_unknown_reason_code_fails_the_guard(monkeypatch):
    broken = {k: dict(v) for k, v in EXCLUDED_FEATURES.items()}
    broken["blood_glucose"]["reason_code"] = "MADE_UP_CODE"
    monkeypatch.setattr(T, "EXCLUDED_FEATURES", broken)
    with pytest.raises(PopulationTableError):
        T._check_catalogue_cover()


def test_an_exclusion_with_no_message_fails_the_guard(monkeypatch):
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
    assert issubclass(PopulationTableError, RuntimeError)
    assert not issubclass(PopulationTableError, AssertionError)
    with pytest.raises(PopulationTableError):
        T._require(False, "boom")


def test_a_well_formed_copy_still_loads(scratch_table):
    table = scratch_table("hba1c")
    assert table.feature == "hba1c"
    assert len(table.cohorts) == 14


def test_a_cohort_whose_values_decrease_is_refused(scratch_table):

    def mutate(raw):
        raw["cohorts"][0]["percentile_values"][5] = 0.0

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("hba1c", mutate)
    assert "monotone" in str(excinfo.value)


def test_a_cohort_out_of_step_with_the_grid_is_refused(scratch_table):

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

    def mutate(raw):
        raw["percentile_grid"][0] = 0.0

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate)


def test_overlapping_age_bands_are_refused(scratch_table):

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
    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("bmi", filename="cholesterol.json")
    assert "file name" in str(excinfo.value)


def test_an_unrecognised_schema_version_is_refused(scratch_table):
    def mutate(raw):
        raw["schema_version"] = SUPPORTED_SCHEMA_VERSION + 1

    with pytest.raises(PopulationTableError):
        scratch_table("bmi", mutate)


def test_a_table_unit_this_service_cannot_convert_into_is_refused(scratch_table):

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

    def mutate(raw):
        raw["dropped_cohorts"] = [
            {"sex": "male", "age_band": "20-29", "n_unweighted": 9}
        ]

    with pytest.raises(PopulationTableError) as excinfo:
        scratch_table("hba1c", mutate)
    assert "overlaps" in str(excinfo.value)


def test_a_dropped_band_in_an_unparseable_format_is_refused(scratch_table):

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
    monkeypatch.setattr(T, "DISTRIBUTIONS_DIR", tmp_path / "gone")
    with pytest.raises(PopulationTableError):
        T._load_all()


def test_an_empty_distributions_directory_stops_the_service(monkeypatch, tmp_path):
    monkeypatch.setattr(T, "DISTRIBUTIONS_DIR", tmp_path)
    with pytest.raises(PopulationTableError):
        T._load_all()


def test_the_shipped_tables_are_exactly_the_expected_ones_and_nothing_else():
    assert len(TABLE_PATHS) == len(EXPECTED_COVERED)
    assert sorted(TABLE_NAMES) == sorted(EXPECTED_COVERED)


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_shipped_grid_is_the_published_eleven_point_grid(name):
    raw = _raw(name)
    assert raw["percentile_grid"] == EXPECTED_GRID
    assert all(b > a for a, b in zip(EXPECTED_GRID, EXPECTED_GRID[1:]))
    assert 0.0 < EXPECTED_GRID[0] and EXPECTED_GRID[-1] < 100.0


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_cohort_is_index_aligned_with_the_grid_and_never_decreases(name):
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
        assert values[0] >= 0, f"{name}/{cell['cohort_id']}: negative quantile"


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_every_table_publishes_all_fourteen_cells_exactly_once(name):
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
    raw = _raw(name)
    floor = raw["method"]["min_cell_unweighted_n"]
    assert floor == 100
    for cell in raw["cohorts"]:
        assert cell["n_unweighted"] >= floor, f"{name}/{cell['cohort_id']}"
        assert cell["weighted_population"] > 0


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_declared_analytic_sample_is_the_sum_of_the_published_cells(name):
    raw = _raw(name)
    assert raw["counts"]["analytic_sample"] == sum(
        c["n_unweighted"] for c in raw["cohorts"]
    )
    assert raw["counts"]["analytic_sample"] <= raw["counts"]["merged_records"]


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_table_unit_is_a_unit_this_service_can_convert_a_value_into(name):
    raw = _raw(name)
    unit = raw["unit"]
    assert normalize_unit(unit) == unit, "must be the normalised spelling"
    assert is_known_unit(unit)
    assert conversion_for(name, unit) is not None
    assert FEATURES[name].value_type in ("number", "integer")


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_the_table_unit_matches_the_feature_catalogue_except_for_vitamin_d(name):
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


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
@pytest.mark.parametrize("age", [0, 1, 12, 17, 19, 19.9])
def test_no_cell_is_returned_for_a_child_or_adolescent(name, age):
    table = TABLES[name]
    for sex in TABLE_SEXES:
        assert table.cohort_for(sex, age) is None
        assert table.dropped_for(sex, age) is None


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
def test_no_cell_is_returned_for_a_sex_the_survey_did_not_stratify_on(name):
    table = TABLES[name]
    for sex in ("other", "prefer_not_to_say", "OTHER", "", "unknown"):
        assert table.cohort_for(sex, 45) is None


@pytest.mark.parametrize("name", sorted(EXPECTED_COVERED))
@pytest.mark.parametrize("age", [20, 29, 30, 45, 79, 80, 95, 120])
def test_exactly_one_cell_matches_any_adult_age(name, age):
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


def test_the_vitamin_d_table_is_never_rescaled_the_patients_value_moves():
    table = TABLES["vitamin_d"]
    assert table.unit == "nmol/l"
    assert FEATURES["vitamin_d"].canonical_unit == "ng/ml"

    conversion = conversion_for("vitamin_d", "nmol/l")
    assert conversion is not None
    assert conversion.to_unit == "ng/ml"
    assert conversion.invert(30.0) == pytest.approx(74.88, abs=0.01)
    assert conversion.apply(74.88) == pytest.approx(30.0, abs=0.01)

    raw = _raw("vitamin_d")
    every_value = [v for c in raw["cohorts"] for v in c["percentile_values"]]
    assert max(every_value) > 100, "nmol/L values; a rescaled table would be ~2.5x lower"
    assert TABLES["vitamin_d"].cohorts[0].percentile_values == tuple(
        raw["cohorts"][0]["percentile_values"]
    )


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
    joined = " ".join(GENERAL_LIMITATIONS).lower()
    assert "nhanes" in joined
    assert "pregnant" in joined
    assert "adults aged 20" in joined
    assert "band" in joined


def test_the_inventory_publishes_provenance_and_the_exclusions_together():
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
    inv = inventory()
    blob = json.dumps(inv).lower()
    for token in ("patient_ref", "snapshot_id", "patient_name", "value_raw"):
        assert token not in blob
    for name in COVERED_FEATURES:
        table = inv["tables"][name]
        assert set(table["cohort_sample_sizes"]) == {
            c.cohort_id for c in TABLES[name].cohorts
        }
        assert "percentile_values" not in table
        assert "records" not in table


def test_policy_is_data_only_and_has_no_import_time_side_effects():
    source = Path(P.__file__).read_text(encoding="utf-8")
    assert "\ndef " not in source, "policy.py grew a function"
    assert "\nif " not in source, "policy.py grew a branch"
