from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional


UNIT_ALIASES: Dict[str, str] = {
    "mg/dl": "mg/dl",
    "mgs/dl": "mg/dl",
    "mg/100ml": "mg/dl",
    "mg%": "mg/dl",
    "mgpercent": "mg/dl",
    "mgdl": "mg/dl",
    "milligram/dl": "mg/dl",
    "milligrams/dl": "mg/dl",
    "milligrams/decilitre": "mg/dl",
    "milligrams/deciliter": "mg/dl",
    "g/dl": "g/dl",
    "gm/dl": "g/dl",
    "gms/dl": "g/dl",
    "gm/100ml": "g/dl",
    "g%": "g/dl",
    "gm%": "g/dl",
    "gdl": "g/dl",
    "gram/dl": "g/dl",
    "grams/dl": "g/dl",
    "grams/decilitre": "g/dl",
    "grams/deciliter": "g/dl",
    "gram%": "g/dl",
    "grams%": "g/dl",
    "g/l": "g/l",
    "gm/l": "g/l",
    "mg/l": "mg/l",
    "gram/l": "g/l",
    "grams/l": "g/l",
    "milligram/l": "mg/l",
    "milligrams/l": "mg/l",
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
    "10^3/ul": "10^3/ul",
    "10^3/l": "10^3/ul",
    "103/ul": "10^3/ul",
    "10e3/ul": "10^3/ul",
    "x10^3/ul": "10^3/ul",
    "thou/ul": "10^3/ul",
    "thousand/ul": "10^3/ul",
    "k/ul": "10^3/ul",
    "10^9/l": "10^3/ul",
    "109/l": "10^3/ul",
    "10e9/l": "10^3/ul",
    "x10^9/l": "10^3/ul",
    "10^6/ul": "10^6/ul",
    "106/ul": "10^6/ul",
    "10e6/ul": "10^6/ul",
    "x10^6/ul": "10^6/ul",
    "mill/ul": "10^6/ul",
    "million/ul": "10^6/ul",
    "m/ul": "10^6/ul",
    "10^12/l": "10^6/ul",
    "1012/l": "10^6/ul",
    "10e12/l": "10^6/ul",
    "x10^12/l": "10^6/ul",
    "fl": "fl",
    "femtolitre": "fl",
    "femtoliter": "fl",
    "um3": "fl",
    "u3": "fl",
    "cu micron": "fl",
    "pg": "pg",
    "picogram": "pg",
    "picogramme": "pg",
    "pgm": "pg",
    "millions/cumm": "10^6/ul",
    "million/cumm": "10^6/ul",
    "mill/cumm": "10^6/ul",
    "millions/cu mm": "10^6/ul",
    "millions/cmm": "10^6/ul",
    "mil/cumm": "10^6/ul",
    "cells/cumm": "cells/cumm",
    "cells/cu mm": "cells/cumm",
    "cells/cmm": "cells/cumm",
    "cell/cumm": "cells/cumm",
    "/cumm": "cells/cumm",
    "cumm": "cells/cumm",
    "cmm": "cells/cumm",
    "lakhs/cumm": "lakhs/cumm",
    "lakh/cumm": "lakhs/cumm",
    "lacs/cumm": "lakhs/cumm",
    "lac/cumm": "lakhs/cumm",
    "lakhs/cu mm": "lakhs/cumm",
    "lakhs/cmm": "lakhs/cumm",
    "u/l": "u/l",
    "iu/l": "u/l",
    "units/l": "u/l",
    "unit/l": "u/l",
    "u/litre": "u/l",
    "iu/litre": "u/l",
    "u/ltr": "u/l",
    "iu/ltr": "u/l",
}


def _unit_key_raw(unit: str) -> str:
    text = unicodedata.normalize("NFKD", unit)
    text = text.replace("µ", "u").replace("μ", "u")
    text = text.replace("²", "2")
    text = text.lower()
    text = text.replace(" per ", "/")
    text = "".join(c for c in text if c.isalnum() or c in "/%^")
    text = text.strip("./ ")
    while "//" in text:
        text = text.replace("//", "/")
    return text


def normalize_unit(unit: Optional[str]) -> Optional[str]:
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


@dataclass(frozen=True)
class UnitConversion:

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


MW_GLUCOSE = 180.156
MW_CREATININE = 113.12
MW_CHOLESTEROL = 386.654
MW_TRIGLYCERIDE = 885.7
MW_25OH_VITAMIN_D = 400.64
MW_COBALAMIN = 1355.37
MW_HAEMOGLOBIN_PER_HEME = 16114.5
MW_BILIRUBIN = 584.66


CONVERSIONS: Dict[str, Dict[str, UnitConversion]] = {
    "hba1c": {
        "%": _identity("%"),
        "mmol/mol": UnitConversion(
            "mmol/mol",
            "%",
            0.09148,
            2.152,
            basis="NGSP/IFCC master equation (affine, not a simple ratio)",
        ),
    },
    "blood_glucose": {
        "mg/dl": _identity("mg/dl"),
        "mmol/l": UnitConversion(
            "mmol/l", "mg/dl", 18.0156, basis=f"MW glucose {MW_GLUCOSE} g/mol / 10"
        ),
        "g/l": UnitConversion("g/l", "mg/dl", 100.0, basis="decimal prefix"),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    "hemoglobin": {
        "g/dl": _identity("g/dl"),
        "g/l": UnitConversion("g/l", "g/dl", 0.1, basis="decimal prefix"),
        "mmol/l": UnitConversion(
            "mmol/l",
            "g/dl",
            1.61145,
            basis=f"MW Hb per heme {MW_HAEMOGLOBIN_PER_HEME} g/mol / 10000",
        ),
    },
    "vitamin_d": {
        "ng/ml": _identity("ng/ml"),
        "ug/l": UnitConversion("ug/l", "ng/ml", 1.0, basis="identical magnitude"),
        "nmol/l": UnitConversion(
            "nmol/l",
            "ng/ml",
            0.400641,
            basis=f"MW 25-OH-D {MW_25OH_VITAMIN_D} g/mol; 1 ng/mL = 2.496 nmol/L",
        ),
    },
    "vitamin_b12": {
        "pg/ml": _identity("pg/ml"),
        "ng/l": UnitConversion("ng/l", "pg/ml", 1.0, basis="identical magnitude"),
        "pmol/l": UnitConversion(
            "pmol/l",
            "pg/ml",
            1.35537,
            basis=f"MW cobalamin {MW_COBALAMIN} g/mol; 1 pg/mL = 0.7378 pmol/L",
        ),
    },
    "creatinine": {
        "mg/dl": _identity("mg/dl"),
        "umol/l": UnitConversion(
            "umol/l",
            "mg/dl",
            0.011312,
            basis=f"MW creatinine {MW_CREATININE} g/mol; 1 mg/dL = 88.4017 umol/L",
        ),
        "mmol/l": UnitConversion(
            "mmol/l", "mg/dl", 11.312, basis="1000 x the umol/L factor"
        ),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
        "ug/dl": UnitConversion("ug/dl", "mg/dl", 0.001, basis="decimal prefix"),
    },
    "cholesterol": {
        "mg/dl": _identity("mg/dl"),
        "mmol/l": UnitConversion(
            "mmol/l",
            "mg/dl",
            38.6654,
            basis=f"MW cholesterol {MW_CHOLESTEROL} g/mol / 10",
        ),
        "g/l": UnitConversion("g/l", "mg/dl", 100.0, basis="decimal prefix"),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    "triglycerides": {
        "mg/dl": _identity("mg/dl"),
        "mmol/l": UnitConversion(
            "mmol/l",
            "mg/dl",
            88.57,
            basis=f"MW triolein {MW_TRIGLYCERIDE} g/mol / 10",
        ),
        "g/l": UnitConversion("g/l", "mg/dl", 100.0, basis="decimal prefix"),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    "hematocrit": {
        "%": _identity("%"),
    },
    "rbc_count": {"10^6/ul": _identity("10^6/ul")},
    "mcv": {"fl": _identity("fl")},
    "mch": {"pg": _identity("pg")},
    "mchc": {
        "g/dl": _identity("g/dl"),
        "%": UnitConversion(
            "%",
            "g/dl",
            1.0,
            basis=(
                "MCHC only: mass of haemoglobin per volume of packed red "
                "cells, assuming red-cell density 1 g/mL and negligible "
                "plasma haemoglobin. NOT a general %/g/dL equivalence -- a "
                "% on a differential count is a proportion of the white "
                "cell count and is a different quantity entirely."
            ),
        ),
        "g/l": UnitConversion("g/l", "g/dl", 0.1, basis="decimal prefix"),
    },
    "wbc_count": {
        "10^3/ul": _identity("10^3/ul"),
        "cells/cumm": UnitConversion(
            "cells/cumm",
            "10^3/ul",
            0.001,
            basis="1 cumm (cubic millimetre) = 1 uL; /1000 to reach 10^3/uL",
        ),
    },
    "neutrophils": {"%": _identity("%")},
    "lymphocytes": {"%": _identity("%")},
    "monocytes": {"%": _identity("%")},
    "eosinophils": {"%": _identity("%")},
    "basophils": {"%": _identity("%")},
    "platelet_count": {
        "10^3/ul": _identity("10^3/ul"),
        "cells/cumm": UnitConversion(
            "cells/cumm",
            "10^3/ul",
            0.001,
            basis="1 cumm = 1 uL; /1000 to reach 10^3/uL",
        ),
        "lakhs/cumm": UnitConversion(
            "lakhs/cumm",
            "10^3/ul",
            100.0,
            basis=(
                "1 lakh = 100,000 and 1 cumm = 1 uL, so lakhs/cumm x 100 "
                "gives 10^3/uL. Indian reporting convention."
            ),
        ),
    },
    "alt": {"u/l": _identity("u/l")},
    "ast": {"u/l": _identity("u/l")},
    "bilirubin_total": {
        "mg/dl": _identity("mg/dl"),
        "umol/l": UnitConversion(
            "umol/l",
            "mg/dl",
            0.058467,
            basis=f"MW bilirubin {MW_BILIRUBIN} g/mol; 1 mg/dL = 17.104 umol/L",
        ),
        "mg/l": UnitConversion("mg/l", "mg/dl", 0.1, basis="decimal prefix"),
    },
    "bmi": {"kg/m2": _identity("kg/m2")},
    "age": {"years": _identity("years")},
}


def conversion_for(feature: str, unit_key: Optional[str]) -> Optional[UnitConversion]:
    if unit_key is None:
        return None
    return CONVERSIONS.get(feature, {}).get(unit_key)


def accepted_units(feature: str) -> Dict[str, UnitConversion]:
    return dict(CONVERSIONS.get(feature, {}))
