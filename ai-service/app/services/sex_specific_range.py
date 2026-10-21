from __future__ import annotations

import math
import re
from typing import Dict, Optional, Tuple

__all__ = [
    "SEX_SPECIFIC_PATTERN",
    "bounds_for_sex",
    "parse_sex_specific_range",
]


_NUMBER = r"\d+(?:\.\d+)?"

SEX_SPECIFIC_PATTERN = re.compile(
    r"\b(?P<label>female|male|[fm])\b\s*[:\-]?\s*"
    r"(?P<low>" + _NUMBER + r")\s*(?:-|–|—|to)\s*(?P<high>" + _NUMBER + r")",
    re.IGNORECASE,
)


def _sex_of(label: str) -> Optional[str]:
    key = label.strip().lower()
    if key in ("f", "female"):
        return "female"
    if key in ("m", "male"):
        return "male"
    return None


def parse_sex_specific_range(raw: object) -> Optional[Dict[str, Tuple[float, float]]]:
    if not isinstance(raw, str) or not raw.strip():
        return None

    found: Dict[str, Tuple[float, float]] = {}
    matches = list(SEX_SPECIFIC_PATTERN.finditer(raw))

    if len(matches) != 2:
        return None

    for match in matches:
        sex = _sex_of(match.group("label"))
        if sex is None:
            return None
        if sex in found:
            return None
        try:
            low = float(match.group("low"))
            high = float(match.group("high"))
        except ValueError:
            return None
        if not math.isfinite(low) or not math.isfinite(high):
            return None
        if low > high:
            return None
        found[sex] = (low, high)

    if "female" not in found or "male" not in found:
        return None
    return found


def bounds_for_sex(raw: object, sex: object) -> Optional[Tuple[float, float]]:
    parsed = parse_sex_specific_range(raw)
    if parsed is None:
        return None
    if not isinstance(sex, str):
        return None
    return parsed.get(sex.strip().lower())
