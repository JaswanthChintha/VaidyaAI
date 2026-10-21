from __future__ import annotations

import math
from typing import Optional

EGFR_FEATURE = "egfr"

SOURCE_CALCULATED = "calculated"

EGFR_UNIT = "mL/min/1.73 m²"

EGFR_DISPLAY_NAME = "eGFR (estimated from creatinine, age and sex)"

EGFR_METHOD = "CKD-EPI 2021 creatinine equation (race-free)"

EGFR_MIN_AGE_YEARS = 18

_KAPPA = {"female": 0.7, "male": 0.9}
_ALPHA = {"female": -0.241, "male": -0.302}
_FEMALE_FACTOR = 1.012


def ckd_epi_2021(
    creatinine_mg_dl: Optional[float],
    age_years: Optional[float],
    sex: Optional[str],
) -> Optional[float]:
    if sex not in _KAPPA:
        return None
    if creatinine_mg_dl is None or age_years is None:
        return None
    try:
        scr = float(creatinine_mg_dl)
        age = float(age_years)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(scr) and math.isfinite(age)):
        return None
    if scr <= 0 or age < EGFR_MIN_AGE_YEARS:
        return None

    ratio = scr / _KAPPA[sex]
    value = (
        142.0
        * min(ratio, 1.0) ** _ALPHA[sex]
        * max(ratio, 1.0) ** -1.200
        * 0.9938 ** age
    )
    if sex == "female":
        value *= _FEMALE_FACTOR
    return value


def reported_egfr(value: float) -> int:
    return int(math.floor(value + 0.5))


__all__ = [
    "EGFR_DISPLAY_NAME",
    "EGFR_FEATURE",
    "EGFR_METHOD",
    "EGFR_MIN_AGE_YEARS",
    "EGFR_UNIT",
    "SOURCE_CALCULATED",
    "ckd_epi_2021",
    "reported_egfr",
]
