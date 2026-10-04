"""Estimated glomerular filtration rate -- the CKD-EPI 2021 creatinine equation.

This is a CLINICIAN-AUDITABLE data file, like `clinical_rules.py`: the whole
equation and its constants are here, in one function, so a reviewer can check
it against the paper without reading the rule engine.

Source: Inker LA, Eneanya ND, Coresh J, et al. "New Creatinine- and Cystatin
C-Based Equations to Estimate GFR without Race." N Engl J Med 2021;385:1737-49.
The 2021 refit removed the race coefficient; it is the equation the NKF-ASN
task force recommends for adults in the United States.

    eGFR = 142 * min(Scr/k, 1)^a * max(Scr/k, 1)^-1.200 * 0.9938^age  [* 1.012 if female]

    k = 0.7 (female) / 0.9 (male)
    a = -0.241 (female) / -0.302 (male)
    Scr = serum creatinine in mg/dL, age in years

WHAT THIS DOES NOT DO
---------------------

* It does not guess. With no age, an age under 18, or a sex that is not
  recorded as male or female, there is no estimate -- `None`, never a number
  computed on an assumed value. The equation is sex-specific and validated in
  adults only.
* It does not stage. KDIGO stages chronic kidney disease from eGFR together
  with urine albumin, and only when the finding persists for at least three
  months. One estimate from one sample is a prompt to look further.
"""

from __future__ import annotations

import math
from typing import Optional

#: The name a calculated eGFR carries in rule evidence. NOT a catalogue feature:
#: nothing reads it off a report, so it never enters the results table, the
#: timeline or the population comparison.
EGFR_FEATURE = "egfr"

#: Evidence `source_stage` for a value this platform calculated rather than
#: read. Kept distinct from `lab_report` so no screen can present it as printed.
SOURCE_CALCULATED = "calculated"

EGFR_UNIT = "mL/min/1.73 m²"

EGFR_DISPLAY_NAME = "eGFR (estimated from creatinine, age and sex)"

EGFR_METHOD = "CKD-EPI 2021 creatinine equation (race-free)"

#: The equation is validated in adults only.
EGFR_MIN_AGE_YEARS = 18

_KAPPA = {"female": 0.7, "male": 0.9}
_ALPHA = {"female": -0.241, "male": -0.302}
_FEMALE_FACTOR = 1.012


def ckd_epi_2021(
    creatinine_mg_dl: Optional[float],
    age_years: Optional[float],
    sex: Optional[str],
) -> Optional[float]:
    """The unrounded eGFR in mL/min/1.73 m², or None when it cannot be estimated."""
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
    """Rounded to a whole number, as laboratories report it.

    Half rounds UP (59.5 -> 60), not to even: the comparison against the
    guideline cut-offs is made on the number the reader is shown, so a value
    displayed as 60 is never flagged as "below 60".
    """
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
