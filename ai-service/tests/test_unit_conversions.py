from __future__ import annotations

import math

import pytest

from app.data.unit_conversions import (
    CONVERSIONS,
    UNIT_ALIASES,
    UnitConversion,
    accepted_units,
    conversion_for,
    is_known_unit,
    normalize_unit,
)


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("mg/dL", "mg/dl"),
        ("mg / dL", "mg/dl"),
        ("MG/DL", "mg/dl"),
        ("mgs/dl", "mg/dl"),
        ("mg%", "mg/dl"),
        ("mg/100mL", "mg/dl"),
        ("g/dL", "g/dl"),
        ("gm/dl", "g/dl"),
        ("gm%", "g/dl"),
        ("g%", "g/dl"),
        ("g/L", "g/l"),
        ("mmol/L", "mmol/l"),
        ("µmol/L", "umol/l"),
        ("μmol/L", "umol/l"),
        ("umol/l", "umol/l"),
        ("mcmol/L", "umol/l"),
        ("nmol/L", "nmol/l"),
        ("pmol/L", "pmol/l"),
        ("ng/mL", "ng/ml"),
        ("ng/L", "ng/l"),
        ("pg/mL", "pg/ml"),
        ("µg/L", "ug/l"),
        ("mcg/L", "ug/l"),
        ("%", "%"),
        ("percent", "%"),
        ("mmol/mol", "mmol/mol"),
        ("kg/m²", "kg/m2"),
        ("kg/m2", "kg/m2"),
        ("years", "years"),
        ("yrs", "years"),
    ],
)
def test_unit_spellings_normalise(printed, expected):
    assert normalize_unit(printed) == expected


@pytest.mark.parametrize("blank", [None, "", "   ", "\t"])
def test_blank_units_normalise_to_none(blank):
    assert normalize_unit(blank) is None


def test_unknown_unit_is_not_silently_canonicalised():
    key = normalize_unit("IU/mL")
    assert key == "iu/ml"
    assert is_known_unit(key) is False
    for feature in CONVERSIONS:
        assert conversion_for(feature, key) is None


def test_ng_per_litre_is_not_confused_with_ng_per_millilitre():
    assert normalize_unit("ng/L") != normalize_unit("ng/mL")


@pytest.mark.parametrize(
    "feature,unit",
    [
        ("hba1c", "%"),
        ("blood_glucose", "mg/dl"),
        ("hemoglobin", "g/dl"),
        ("vitamin_d", "ng/ml"),
        ("vitamin_b12", "pg/ml"),
        ("creatinine", "mg/dl"),
        ("cholesterol", "mg/dl"),
        ("triglycerides", "mg/dl"),
        ("bmi", "kg/m2"),
        ("age", "years"),
    ],
)
def test_canonical_unit_is_an_identity_conversion(feature, unit):
    conv = conversion_for(feature, unit)
    assert conv is not None
    assert conv.is_identity
    assert conv.apply(12.34) == 12.34


FORWARD_CASES = [
    ("hba1c", "mmol/mol", 48.0, 6.54304, 1e-9),
    ("hba1c", "mmol/mol", 31.0, 4.98788, 1e-9),
    ("hba1c", "mmol/mol", 0.0, 2.152, 1e-12),
    ("blood_glucose", "mmol/l", 5.5, 99.0858, 1e-9),
    ("blood_glucose", "mmol/l", 1.0, 18.0156, 1e-9),
    ("blood_glucose", "g/l", 1.12, 112.0, 1e-9),
    ("blood_glucose", "mg/l", 1120.0, 112.0, 1e-9),
    ("hemoglobin", "g/l", 142.0, 14.2, 1e-9),
    ("hemoglobin", "mmol/l", 8.8, 14.18076, 1e-9),
    ("vitamin_d", "nmol/l", 75.0, 30.048075, 1e-9),
    ("vitamin_d", "ug/l", 35.0, 35.0, 1e-12),
    ("vitamin_b12", "pmol/l", 300.0, 406.611, 1e-9),
    ("vitamin_b12", "ng/l", 450.0, 450.0, 1e-12),
    ("creatinine", "umol/l", 88.4017, 1.0, 1e-5),
    ("creatinine", "umol/l", 100.0, 1.1312, 1e-9),
    ("creatinine", "mmol/l", 0.1, 1.1312, 1e-9),
    ("creatinine", "mg/l", 10.0, 1.0, 1e-9),
    ("creatinine", "ug/dl", 1000.0, 1.0, 1e-9),
    ("cholesterol", "mmol/l", 5.17, 199.900, 1e-2),
    ("cholesterol", "mmol/l", 1.0, 38.6654, 1e-9),
    ("cholesterol", "g/l", 1.9, 190.0, 1e-9),
    ("cholesterol", "mg/l", 1900.0, 190.0, 1e-9),
    ("triglycerides", "mmol/l", 1.7, 150.569, 1e-3),
    ("triglycerides", "mmol/l", 1.0, 88.57, 1e-9),
    ("triglycerides", "g/l", 1.5, 150.0, 1e-9),
    ("triglycerides", "mg/l", 1500.0, 150.0, 1e-9),
]


@pytest.mark.parametrize("feature,unit,value,expected,tol", FORWARD_CASES)
def test_conversion_forward_direction(feature, unit, value, expected, tol):
    conv = conversion_for(feature, unit)
    assert conv is not None, f"no conversion for {feature} from {unit}"
    assert conv.apply(value) == pytest.approx(expected, abs=tol)


@pytest.mark.parametrize("feature,unit,value,expected,tol", FORWARD_CASES)
def test_conversion_reverse_direction(feature, unit, value, expected, tol):
    conv = conversion_for(feature, unit)
    assert conv is not None
    assert conv.invert(conv.apply(value)) == pytest.approx(value, abs=1e-9)


def test_creatinine_umol_to_mgdl_is_the_88_fold_factor():
    conv = conversion_for("creatinine", "umol/l")
    assert 1.0 / conv.factor == pytest.approx(88.4017, abs=1e-3)


def test_glucose_mmol_to_mgdl_is_the_18_fold_factor():
    conv = conversion_for("blood_glucose", "mmol/l")
    assert conv.factor == pytest.approx(18.0156, abs=1e-4)
    assert 1.0 / conv.factor == pytest.approx(0.0555, abs=1e-4)


def test_vitamin_d_nmol_to_ngml_is_the_2_5_fold_factor():
    conv = conversion_for("vitamin_d", "nmol/l")
    assert 1.0 / conv.factor == pytest.approx(2.496, abs=1e-3)


def test_vitamin_b12_pmol_to_pgml_is_the_1_36_fold_factor():
    conv = conversion_for("vitamin_b12", "pmol/l")
    assert conv.factor == pytest.approx(1.36, abs=0.01)
    assert 1.0 / conv.factor == pytest.approx(0.7378, abs=1e-3)


def test_hba1c_ifcc_conversion_is_affine_not_a_ratio():
    conv = conversion_for("hba1c", "mmol/mol")
    assert conv.offset == pytest.approx(2.152)
    assert conv.apply(0.0) != 0.0


def test_every_conversion_targets_the_features_canonical_unit():
    from app.data.feature_catalog import FEATURES

    for feature, table in CONVERSIONS.items():
        canonical = FEATURES[feature].canonical_unit
        assert canonical is not None, feature
        for unit_key, conv in table.items():
            assert conv.from_unit == unit_key, (feature, unit_key)
            assert conv.to_unit == canonical, (feature, unit_key)


def test_every_conversion_key_is_a_known_unit_spelling():
    for feature, table in CONVERSIONS.items():
        for unit_key in table:
            assert is_known_unit(unit_key), (feature, unit_key)


def test_no_conversion_has_a_zero_factor():
    for feature, table in CONVERSIONS.items():
        for unit_key, conv in table.items():
            assert conv.factor != 0.0, (feature, unit_key)
            assert math.isfinite(conv.factor)
            assert math.isfinite(conv.offset)


def test_every_non_identity_conversion_documents_its_basis():
    for table in CONVERSIONS.values():
        for conv in table.values():
            assert conv.basis, conv


def test_unit_alias_targets_are_themselves_aliases():
    for target in set(UNIT_ALIASES.values()):
        assert UNIT_ALIASES.get(target) == target


def test_accepted_units_returns_a_copy():
    units = accepted_units("creatinine")
    units.clear()
    assert conversion_for("creatinine", "umol/l") is not None


def test_formula_states_the_direction():
    conv = conversion_for("creatinine", "umol/l")
    assert conv.formula.startswith("mg/dl = umol/l x")
    hba1c = conversion_for("hba1c", "mmol/mol")
    assert "+" in hba1c.formula


def test_unit_conversion_dataclass_is_frozen():
    conv = UnitConversion("a", "b", 2.0)
    with pytest.raises(Exception):
        conv.factor = 3.0


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("Grams/dL", "g/dl"),
        ("grams/dl", "g/dl"),
        ("Gram/dL", "g/dl"),
        ("Grams%", "g/dl"),
        ("grams per dL", "g/dl"),
        ("Milligrams/dL", "mg/dl"),
        ("milligrams per decilitre", "mg/dl"),
        ("Micrograms/L", "ug/l"),
        ("nanograms/mL", "ng/ml"),
        ("picograms/mL", "pg/ml"),
        ("millimoles/L", "mmol/l"),
        ("micromoles/L", "umol/l"),
    ],
)
def test_a_unit_spelled_out_in_words_resolves_to_the_canonical_spelling(printed, expected):
    assert normalize_unit(printed) == expected


def test_the_abbreviated_spellings_still_resolve_exactly_as_before():
    for printed, expected in (
        ("g/dL", "g/dl"),
        ("gms/dl", "g/dl"),
        ("gm%", "g/dl"),
        ("mg/dl", "mg/dl"),
        ("mg%", "mg/dl"),
        ("mcg/dl", "ug/dl"),
        ("%", "%"),
        ("kg/m2", "kg/m2"),
    ):
        assert normalize_unit(printed) == expected, printed


def test_an_unrecognised_unit_is_still_refused_and_never_guessed_at():
    canonical = set(UNIT_ALIASES.values())
    for nonsense in ("furlongs/fortnight", "bananas", "gg/dl"):
        assert normalize_unit(nonsense) not in canonical, nonsense


@pytest.mark.parametrize(
    "feature,printed,value,expected,why",
    [
        (
            "rbc_count",
            "Millions/Cumm",
            4.2,
            4.2,
            "1 cumm = 1 uL, so millions/cumm IS 10^6/uL -- identity",
        ),
        (
            "wbc_count",
            "Cells/cumm",
            9300.0,
            9.3,
            "a bare count per cubic millimetre, /1000",
        ),
        (
            "platelet_count",
            "Lakhs/cumm",
            3.03,
            303.0,
            "1 lakh = 100,000",
        ),
        (
            "platelet_count",
            "Cells/cumm",
            303000.0,
            303.0,
            "the same platelet count printed the other way round",
        ),
    ],
)
def test_the_units_test_3_actually_prints_convert_correctly(
    feature, printed, value, expected, why
):
    key = normalize_unit(printed)
    assert is_known_unit(key), f"{printed!r} is not a recognised unit"
    conv = conversion_for(feature, key)
    assert conv is not None, f"{feature} cannot accept {printed!r}: {why}"
    assert conv.apply(value) == pytest.approx(expected), why


def test_a_lakh_is_a_hundred_thousand_and_getting_it_wrong_is_invisible():
    from app.data.validation_rules import rule_for

    conv = conversion_for("platelet_count", normalize_unit("Lakhs/cumm"))
    assert conv.apply(3.03) == pytest.approx(303.0)
    assert conv.apply(1.5) == pytest.approx(150.0)
    assert conv.apply(4.5) == pytest.approx(450.0)

    rule = rule_for("platelet_count")
    assert rule.possible_low <= 3.03 <= rule.possible_high, (
        "if this ever fails, the possible band has started catching the "
        "mis-scale and this test's premise needs revisiting"
    )
