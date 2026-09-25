"""The patient's sex and age AS PRINTED on a report, read -- never guessed.

Module 4 copies `patient_sex` and `patient_age` exactly as printed. This reads
them into the two feature values the analysis uses. The rules are the
backend's (`backend/src/utils/printedIdentity.js`), restated here because
Module 5 runs before the backend sees a feature:

  sex   "Male", "M", "female", "F." ... -> "male" / "female". Anything else
        ("Other", "M/F", a digit) is NOT read, and the profile is used.
  age   "63 Years", "63Y", "63", "34Y 2M", "6 Months" -> whole years, rounded
        DOWN (the catalogue's `age` is an integer, as the profile's is).
        Nothing readable, or outside 0-130, is not read.

NEVER A NAME. Module 4 does not copy one.
"""

from __future__ import annotations

import math
import re
from typing import Optional

_SEX_WORDS = {
    "m": "male", "male": "male", "man": "male", "boy": "male",
    "f": "female", "female": "female", "woman": "female", "girl": "female",
}

_AGE_UNITS = (
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?|y)\b", re.IGNORECASE), 1.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:months?|mths?|mos?|m)\b", re.IGNORECASE), 1.0 / 12.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b", re.IGNORECASE), 7.0 / 365.25),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:days?|d)\b", re.IGNORECASE), 1.0 / 365.25),
)


def read_sex(raw: object) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    word = re.sub(r"[.\s]+$", "", raw.strip().lower())
    return _SEX_WORDS.get(word)


def read_age_years(raw: object) -> Optional[int]:
    """Whole years, or None when nothing could be read."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    years: Optional[float]
    if re.fullmatch(r"\d{1,3}", text):
        years = float(text)
    else:
        found = False
        total = 0.0
        for pattern, per in _AGE_UNITS:
            match = pattern.search(text)
            if match:
                found = True
                total += float(match.group(1)) * per
        years = total if found else None
    if years is None or not math.isfinite(years) or years < 0 or years > 130:
        return None
    return int(math.floor(years))
