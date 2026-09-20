"""Reference intervals a laboratory prints once per sex.

WHY THIS EXISTS
===============

Indian laboratory reports print sex-specific intervals as a matter of routine::

    HEMOGLOBIN   12.5 Grams/dL   F:11 - 15 M:12 - 16
    PCV          37.9 %          F: 36 - 46 M: 40 - 50

`printed_range_is_only_a_range` in `app/schemas/extraction.py` refuses any
printed text that is not a bare interval and nulls `reference_low` /
`reference_high`. That gate is CORRECT and is not relaxed here: it exists
because a band table -- "Normal < 5.7, Prediabetes 5.7-6.4" -- must never be
read as though it were one interval, and two intervals side by side are
exactly the shape it was written to refuse.

So the bounds arrive as `None` and the row has nothing to compare against.
On `Test 3.pdf` that made PCV render as "not checked" to the reader while the
value, 37.9 %, sits BELOW the male interval printed beside it on the same
line. An absence rendered as an absence, but the underlying result was out of
range and nobody was told.

THE PATIENT'S SEX IS ON THE PROFILE, so the interval can be chosen rather than
guessed. This module does only the reading; the caller supplies the sex and
decides what to do with the answer.

WHAT IT REFUSES, AND WHY THAT LIST IS LONG
==========================================

Everything here errs toward `None`, because a wrong interval is worse than no
interval: a value compared against the other sex's range produces a confident
verdict that is simply false, and this platform's standing rule is that an
absence must never become a negative result. So:

* BOTH sexes must be present. One labelled interval is not a sex-specific
  range -- it may be a footnote, or the other half may have failed to
  transcribe -- and a single interval found under a lone `M:` says nothing
  about what a female reader should be compared against.
* EXACTLY two intervals. Three or more is a band table with labels, not this.
* The label must be a WHOLE TOKEN. `m` inside `mm/hr` or `F` inside `FEV1` is
  not a sex label, so `\\b` anchors are load-bearing.
* Each interval must be `low <= high`, both finite.
* An unknown or absent sex selects NOTHING. `normalize_gender` also returns
  `other`, which has no interval printed beside it and must not silently fall
  back to either -- see `bounds_for_sex`.
"""

from __future__ import annotations

import math
import re
from typing import Dict, Optional, Tuple

__all__ = [
    "SEX_SPECIFIC_PATTERN",
    "bounds_for_sex",
    "parse_sex_specific_range",
]


#: A number as laboratories print one: `11`, `12.5`, `0.8`. No comparators and
#: no thousands separators -- a sex-specific interval that needs either is
#: outside what this module claims to read, and refusing is the right answer.
_NUMBER = r"\d+(?:\.\d+)?"

#: `F:11 - 15`, `Female 11-15`, `M: 12 to 16`, `MALE 12 – 16`.
#:
#: The label is anchored on both sides so that a stray `m` in a unit cannot
#: open an interval. The separator accepts the hyphen, both dashes a PDF
#: extractor may emit, and the word `to`.
#: ⚠ `female` AND `male` ARE SEPARATE ALTERNATIVES, AND THE SINGLE LETTER IS
#: LAST. A first draft wrote the label as `fe?male|[fm]`, which reads as
#: though it covers every spelling and does not: on `Male: 13.0-17.0` the long
#: alternative needs a leading `f`, so matching fell through to `[fm]`, and
#: the `\b` after it then failed because `a` follows `M`. The result was ONE
#: match instead of two on every report that spells the words out, and the
#: whole text was refused. Caught by the parametrised cases below, which is
#: why the real spellings are enumerated there rather than sampled.
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
    """`{"female": (low, high), "male": (low, high)}`, or None.

    None whenever the text is not unambiguously one interval per sex. See the
    module docstring for the full refusal list -- every one of them returns
    None rather than a partial answer, because a caller handed half of this
    would compare a value against the wrong sex's range.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None

    found: Dict[str, Tuple[float, float]] = {}
    matches = list(SEX_SPECIFIC_PATTERN.finditer(raw))

    # EXACTLY TWO. Three labelled intervals is a table this module does not
    # understand, and one is not a sex-specific range at all.
    if len(matches) != 2:
        return None

    for match in matches:
        sex = _sex_of(match.group("label"))
        if sex is None:
            return None
        # A repeated label means the text is not one interval per sex.
        if sex in found:
            return None
        try:
            low = float(match.group("low"))
            high = float(match.group("high"))
        except ValueError:  # pragma: no cover -- the pattern admits only numbers
            return None
        if not math.isfinite(low) or not math.isfinite(high):
            return None
        # AN INVERTED INTERVAL IS A MISREAD, NOT A RANGE. Refusing the whole
        # text is right: if one side transcribed wrongly the other is not to
        # be trusted either.
        if low > high:
            return None
        found[sex] = (low, high)

    if "female" not in found or "male" not in found:
        return None
    return found


def bounds_for_sex(raw: object, sex: object) -> Optional[Tuple[float, float]]:
    """The interval printed for `sex`, or None.

    ⚠ `other` AND `None` SELECT NOTHING, AND THAT IS NOT AN OVERSIGHT. The
    report prints two intervals and neither is addressed to a reader who is
    neither; choosing one would be this service inventing a comparison the
    laboratory did not make. The row keeps its printed text and stays
    uncompared, which is what it does today for every such row.
    """
    parsed = parse_sex_specific_range(raw)
    if parsed is None:
        return None
    if not isinstance(sex, str):
        return None
    return parsed.get(sex.strip().lower())
