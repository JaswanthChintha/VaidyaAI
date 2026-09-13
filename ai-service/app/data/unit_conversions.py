"""Unit normalisation and conversion factors -- Module 5 (Feature Engineering).

SAFETY-CRITICAL FILE. A wrong factor here silently corrupts every downstream
clinical rule, ML prediction and explanation. Every entry below states:

  * the source unit and the canonical target unit,
  * the DIRECTION of the conversion,
  * the arithmetic basis (molar mass or decimal prefix) it was derived from.

Conversion model
----------------
Every conversion is affine::

    canonical_value = raw_value * factor + offset

`offset` is 0.0 for every unit except HbA1c IFCC (mmol/mol), which needs the
NGSP/IFCC master equation.

Nothing in this file judges whether a value is plausible -- that is Module 6.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional

# --------------------------------------------------------------------------
# Unit string normalisation
# --------------------------------------------------------------------------

# Raw unit spellings seen on real reports -> a single normalised key.
# The left-hand side is already lower-cased and whitespace-stripped by
# `_unit_key_raw`; this table only resolves *spelling*, never *scale*.
UNIT_ALIASES: Dict[str, str] = {
    # mass / volume -- mg per decilitre
    "mg/dl": "mg/dl",
    "mgs/dl": "mg/dl",
    "mg/100ml": "mg/dl",
    "mg%": "mg/dl",  # Indian labs commonly print "mg%" for mg/dL
    "mgpercent": "mg/dl",
    "mgdl": "mg/dl",
    "milligram/dl": "mg/dl",
    "milligrams/dl": "mg/dl",
    "milligrams/decilitre": "mg/dl",
    "milligrams/deciliter": "mg/dl",
    # grams per decilitre
    "g/dl": "g/dl",
    "gm/dl": "g/dl",
    "gms/dl": "g/dl",
    "gm/100ml": "g/dl",
    "g%": "g/dl",
    "gm%": "g/dl",
    "gdl": "g/dl",
    # SPELLED OUT IN FULL. A real report printed "Grams/dL" for a
    # haemoglobin of 12.5 -- the same unit as `g/dl` in words -- and the
    # value was REJECTED as NON_CANONICAL_UNIT. That cost the whole Anemia
    # assessment: `Insufficient Data`, on a report that measured it.
    # `_unit_key_raw` turns " per " into "/", so each of these also covers
    # the "grams per decilitre" spelling.
    "gram/dl": "g/dl",
    "grams/dl": "g/dl",
    "grams/decilitre": "g/dl",
    "grams/deciliter": "g/dl",
    "gram%": "g/dl",
    "grams%": "g/dl",
    # grams / milligrams per litre
    "g/l": "g/l",
    "gm/l": "g/l",
    "mg/l": "mg/l",
    "gram/l": "g/l",
    "grams/l": "g/l",
    "milligram/l": "mg/l",
    "milligrams/l": "mg/l",
    # micro / nano / pico per volume
    "ug/l": "ug/l",
    "mcg/l": "ug/l",
    "ug/dl": "ug/dl",
    "mcg/dl": "ug/dl",
    "microgram/l": "ug/l",
    "micrograms/l": "ug/l",
    "microgram/dl": "ug/dl",
    "micrograms/dl": "ug/dl",
    "ng/ml": "ng/ml",
    "ngml": "ng/ml",
    "ng/l": "ng/l",
    "pg/ml": "pg/ml",
    "pgml": "pg/ml",
    "nanogram/ml": "ng/ml",
    "nanograms/ml": "ng/ml",
    "picogram/ml": "pg/ml",
    "picograms/ml": "pg/ml",
    # molar
    "mmol/l": "mmol/l",
    "mmoll": "mmol/l",
    "umol/l": "umol/l",
    "mcmol/l": "umol/l",
    "nmol/l": "nmol/l",
    "pmol/l": "pmol/l",
    "mmol/mol": "mmol/mol",
    "millimol/l": "mmol/l",
    "millimols/l": "mmol/l",
    "millimoles/l": "mmol/l",
    "micromol/l": "umol/l",
    "micromoles/l": "umol/l",
    "nanomoles/l": "nmol/l",
    "picomoles/l": "pmol/l",
    # dimensionless / other
    "%": "%",
    "percent": "%",
    "percentage": "%",
    "pct": "%",
    "kg/m2": "kg/m2",
    "kg/m^2": "kg/m2",
    "kgm2": "kg/m2",
    "kg/msq": "kg/m2",
    "years": "years",
    "year": "years",
    "yrs": "years",
    "yr": "years",
    "y": "years",
}


def _unit_key_raw(unit: str) -> str:
    """Lower-case, de-accent and squeeze a printed unit into a lookup key."""
    text = unicodedata.normalize("NFKD", unit)
    # Micro sign (U+00B5) and Greek mu (U+03BC) both appear in lab exports.
    text = text.replace("µ", "u").replace("μ", "u")
    text = text.replace("²", "2")  # superscript two, e.g. kg/m²
    text = text.lower()
    text = text.replace(" per ", "/")
    # Drop every character that is not alphanumeric, '/', '%', '^' or '.'
    text = "".join(c for c in text if c.isalnum() or c in "/%^")
    text = text.strip("./ ")
    while "//" in text:
        text = text.replace("//", "/")
    return text


def normalize_unit(unit: Optional[str]) -> Optional[str]:
    """Return the canonical *spelling* of a printed unit, or None.

    Returns None when `unit` is absent/blank. Returns the squeezed key
    unchanged when the spelling is not in `UNIT_ALIASES` -- callers must treat
    an unknown key as UNRECOGNISED and must never assume it is canonical.
    """
    if unit is None:
        return None
    if not isinstance(unit, str):
        return None
    key = _unit_key_raw(unit)
    if not key:
        return None
    return UNIT_ALIASES.get(key, key)


def is_known_unit(unit_key: Optional[str]) -> bool:
    return unit_key is not None and unit_key in set(UNIT_ALIASES.values())


# --------------------------------------------------------------------------
# Conversions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitConversion:
    """`canonical = raw * factor + offset`, from `from_unit` to `to_unit`."""

    from_unit: str
    to_unit: str
    factor: float
    offset: float = 0.0
    basis: str = ""

    @property
    def is_identity(self) -> bool:
        return self.factor == 1.0 and self.offset == 0.0

    def apply(self, value: float) -> float:
        return value * self.factor + self.offset

    def invert(self, canonical_value: float) -> float:
        """Canonical -> source unit. Used by tests to check both directions."""
        return (canonical_value - self.offset) / self.factor

    @property
    def formula(self) -> str:
        if self.offset:
            return (
                f"{self.to_unit} = {self.from_unit} x {self.factor:g} "
                f"+ {self.offset:g}"
            )
        return f"{self.to_unit} = {self.from_unit} x {self.factor:g}"


def _identity(unit: str) -> UnitConversion:
    return UnitConversion(unit, unit, 1.0, 0.0, basis="already canonical")


# --- Molar masses used below (g/mol), for auditability -------------------
MW_GLUCOSE = 180.156  # C6H12O6
MW_CREATININE = 113.12  # C4H7N3O
MW_CHOLESTEROL = 386.654  # C27H46O
MW_TRIGLYCERIDE = 885.7  # triolein, the conventional clinical basis
MW_25OH_VITAMIN_D = 400.64  # 25-hydroxycholecalciferol, C27H44O2
MW_COBALAMIN = 1355.37  # cyanocobalamin, C63H88CoN14O14P
MW_HAEMOGLOBIN_PER_HEME = 16114.5  # tetramer 64458 / 4


# CONVERSIONS[canonical_feature][normalised_source_unit] -> UnitConversion
#
# Read each row as: "to get the canonical value, multiply the printed value by
# `factor` (then add `offset`)". The inverse factor is given in the comment so
# the arithmetic can be checked in either direction.
CONVERSIONS: Dict[str, Dict[str, UnitConversion]] = {
    # ---------------------------------------------------------------- hba1c
    # Canonical: % (NGSP / DCCT-aligned).
    "hba1c": {
        "%": _identity("%"),
        # IFCC mmol/mol -> NGSP %. Master equation:
        #   NGSP% = 0.09148 x IFCC + 2.152
        # Check: 48 mmol/mol -> 0.09148*48 + 2.152 = 6.543 % (published 6.5 %).
        # Inverse: IFCC = (NGSP% - 2.152) / 0.09148
        "mmol/mol": UnitConversion(
            "mmol/mol",
            "%",
            0.09148,
            2.152,
            basis="NGSP/IFCC master equation (affine, not a simple ratio)",
        ),
    },
    # -------------------------------------------------------- blood_glucose
    # Canonical: mg/dL.
    "blood_glucose": {
        "mg/dl": _identity("mg/dl"),
        # 1 mmol/L = 180.156 mg/L = 18.0156 mg/dL. Inverse: x 0.05551.
        # Check: 5.5 mmol/L -> 99.09 mg/dL; 112 mg/dL -> 6.217 mmol/L.
        "mmol/l": UnitConversion(
            "mmol/l", "mg/dl", 18.0156, basis=f"MW glucose {MW_GLUCOSE} g/mol / 10"
        ),
        # 1 g/L = 1000 mg/L = 100 mg/dL. Inverse: x 0.01.
        "g/l": UnitConversion("g/l", "mg/dl", 100.0, basis="decimal prefix"),
        # 1 mg/L = 0.1 mg/dL. Inverse: x 10.
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    # ----------------------------------------------------------- hemoglobin
    # Canonical: g/dL.
    "hemoglobin": {
        "g/dl": _identity("g/dl"),
        # 1 g/L = 0.1 g/dL. Inverse: x 10. Check: 142 g/L -> 14.2 g/dL.
        "g/l": UnitConversion("g/l", "g/dl", 0.1, basis="decimal prefix"),
        # SI (Dutch/Nordic) haemoglobin is reported per heme:
        # 1 mmol/L = 16114.5 mg/mol/1000 -> 1.61145 g/dL. Inverse: x 0.6206.
        # Check: 8.8 mmol/L -> 14.18 g/dL.
        "mmol/l": UnitConversion(
            "mmol/l",
            "g/dl",
            1.61145,
            basis=f"MW Hb per heme {MW_HAEMOGLOBIN_PER_HEME} g/mol / 10000",
        ),
    },
    # ------------------------------------------------------------ vitamin_d
    # Canonical: ng/mL (25-hydroxyvitamin D).
    "vitamin_d": {
        "ng/ml": _identity("ng/ml"),
        # 1 ug/L == 1 ng/mL exactly (same scale, different spelling).
        "ug/l": UnitConversion("ug/l", "ng/ml", 1.0, basis="identical magnitude"),
        # 1 nmol/L = 400.64 ng/L = 0.400641 ng/mL. Inverse: x 2.496.
        # Check: 75 nmol/L -> 30.05 ng/mL; 35 ng/mL -> 87.4 nmol/L.
        "nmol/l": UnitConversion(
            "nmol/l",
            "ng/ml",
            0.400641,
            basis=f"MW 25-OH-D {MW_25OH_VITAMIN_D} g/mol; 1 ng/mL = 2.496 nmol/L",
        ),
    },
    # ---------------------------------------------------------- vitamin_b12
    # Canonical: pg/mL.
    "vitamin_b12": {
        "pg/ml": _identity("pg/ml"),
        # 1 ng/L == 1 pg/mL exactly.
        "ng/l": UnitConversion("ng/l", "pg/ml", 1.0, basis="identical magnitude"),
        # 1 pmol/L = 1355.37 pg/L = 1.35537 pg/mL. Inverse: x 0.7378.
        # Check: 300 pmol/L -> 406.6 pg/mL.
        "pmol/l": UnitConversion(
            "pmol/l",
            "pg/ml",
            1.35537,
            basis=f"MW cobalamin {MW_COBALAMIN} g/mol; 1 pg/mL = 0.7378 pmol/L",
        ),
    },
    # ----------------------------------------------------------- creatinine
    # Canonical: mg/dL.
    "creatinine": {
        "mg/dl": _identity("mg/dl"),
        # 1 umol/L = 113.12 ug/L = 0.011312 mg/dL. Inverse: x 88.4017.
        # Check: 88.4 umol/L -> 1.0000 mg/dL; 1.0 mg/dL -> 88.40 umol/L.
        "umol/l": UnitConversion(
            "umol/l",
            "mg/dl",
            0.011312,
            basis=f"MW creatinine {MW_CREATININE} g/mol; 1 mg/dL = 88.4017 umol/L",
        ),
        # 1 mmol/L = 1000 umol/L -> 11.312 mg/dL.
        "mmol/l": UnitConversion(
            "mmol/l", "mg/dl", 11.312, basis="1000 x the umol/L factor"
        ),
        # 1 mg/L = 0.1 mg/dL.
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
        # 1 ug/dL = 0.001 mg/dL.
        "ug/dl": UnitConversion("ug/dl", "mg/dl", 0.001, basis="decimal prefix"),
    },
    # ---------------------------------------------------------- cholesterol
    # Canonical: mg/dL (total cholesterol).
    "cholesterol": {
        "mg/dl": _identity("mg/dl"),
        # 1 mmol/L = 386.654 mg/L = 38.6654 mg/dL. Inverse: x 0.02586.
        # Check: 5.17 mmol/L -> 199.9 mg/dL; 190 mg/dL -> 4.914 mmol/L.
        "mmol/l": UnitConversion(
            "mmol/l",
            "mg/dl",
            38.6654,
            basis=f"MW cholesterol {MW_CHOLESTEROL} g/mol / 10",
        ),
        "g/l": UnitConversion("g/l", "mg/dl", 100.0, basis="decimal prefix"),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    # -------------------------------------------------------- triglycerides
    # Canonical: mg/dL.
    "triglycerides": {
        "mg/dl": _identity("mg/dl"),
        # 1 mmol/L = 885.7 mg/L = 88.57 mg/dL. Inverse: x 0.01129.
        # Check: 1.7 mmol/L -> 150.6 mg/dL; 150 mg/dL -> 1.694 mmol/L.
        "mmol/l": UnitConversion(
            "mmol/l",
            "mg/dl",
            88.57,
            basis=f"MW triolein {MW_TRIGLYCERIDE} g/mol / 10",
        ),
        "g/l": UnitConversion("g/l", "mg/dl", 100.0, basis="decimal prefix"),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    # ------------------------------------------- patient-profile features --
    "bmi": {"kg/m2": _identity("kg/m2")},
    "age": {"years": _identity("years")},
}


def conversion_for(feature: str, unit_key: Optional[str]) -> Optional[UnitConversion]:
    """Look up the conversion for a feature + normalised unit key.

    Returns None when the unit is unknown FOR THIS FEATURE. Callers must not
    fall back to the identity conversion -- an unrecognised unit is reported,
    never assumed.
    """
    if unit_key is None:
        return None
    return CONVERSIONS.get(feature, {}).get(unit_key)


def accepted_units(feature: str) -> Dict[str, UnitConversion]:
    return dict(CONVERSIONS.get(feature, {}))
