"""Hand-written analytical and within-subject variation for laboratory tests.

WHY THIS FILE EXISTS. Module 35 obtained a test's CVa and CVi from the model,
per call. Two consequences a reader saw on the real page:

  1. THE FIGURES WERE NOT REPRODUCIBLE. EOSINOPHILS 5 -> 2 % was refused on
     one request and called `stable` on the next, with the data unchanged,
     because the model returned a different CVi. A threshold that decides
     whether a patient is shown "stable" cannot move between page loads.
  2. NOTHING COULD BE CHECKED. Every verdict said its figures were PENDING
     INDEPENDENT VERIFICATION, and there was nowhere for a reviewer to go and
     verify them -- the number existed only in that one answer.

So the figures move into a table, exactly as the assessed features' own bands
live in `trend_polarity.py`. A table can be read, reviewed, corrected and
diffed. A per-call answer cannot.

==========================================================================
READ THIS BEFORE TRUSTING A ROW: `verified=False` MEANS NOT VERIFIED
==========================================================================

EVERY ROW BELOW IS `verified=False`. The figures are literature-typical values
for the named test, recorded WITH the source they should be checked against --
they were not read off that source when this file was written, and until
somebody does that and flips the flag, they are exactly as unverified as the
model's answers were. What they are NOT any more is invisible, unstable or
uncheckable.

`verified=True` MAY ONLY BE SET BY A HUMAN WHO HAS COMPARED THE ROW TO ITS
`source`. Not by a model, not by this file's author, and not on the grounds
that the number looks reasonable. The flag exists to carry that one fact and
it is the only thing that separates a checked threshold from a plausible one.

WHAT THE FLAG CHANGES. Nothing about the arithmetic. `reference_change_value`
computes the same RCV either way. It changes what the page SAYS about where
the threshold came from, so a reader is never told a checked figure and an
unchecked one in the same words -- the distinction this project keeps having
to rebuild, most recently for the laboratory's marking versus its own.

==========================================================================
WHERE THE NUMBERS COME FROM, AND WHAT TO CHECK THEM AGAINST
==========================================================================

The standard sources for within-subject biological variation are:

  * The EFLM Biological Variation Database (biologicalvariation.eu), which is
    the current maintained compilation and supersedes the older lists.
  * Ricos C et al., "Current databases on biological variation", Scand J Clin
    Lab Invest 1999;59:491-500, and its later updates -- the source most of
    the widely quoted CVi figures ultimately trace back to.

A reviewer should take each row, find the test in the EFLM database, and
either correct the figures or set `verified=True`. CVa is the more local of
the two: analytical variation is a property of the ANALYSER, so a laboratory's
own internal quality-control figure is better than any published one, and a
row's CVa should be treated as a placeholder until this platform knows which
analyser produced the reading.

==========================================================================
WHAT IS DELIBERATELY NOT HERE
==========================================================================

  * NO REFERENCE RANGES. Not one bound. The interval a value is judged
    against is the one the patient's own laboratory printed, and 6v records an
    invented range reaching a patient already.
  * NO ASSESSED FEATURES. HbA1c, glucose, creatinine, cholesterol and the rest
    have their own hand-written bands in `trend_polarity.py` with their own
    arithmetic recorded. Two tables claiming a band for one feature is how
    they come to disagree, so this one covers ONLY tests that file does not.
  * NO TEST THIS PLATFORM HAS NOT SEEN ON A REAL REPORT. The rows below are
    the tests on the two reports this feature was built against. A test that
    is not here falls through to the model, which is the previous behaviour,
    and adding a row is how it stops doing that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

#: Polarity words, matching `lab_polarity._POLARITY_WORDS` exactly. Kept as
#: the same strings so a row can be handed straight to that module's own
#: translation rather than this file growing a second vocabulary.
POLARITY_HIGHER_IS_WORSE = "higher_is_worse"
POLARITY_HIGHER_IS_BETTER = "higher_is_better"
POLARITY_BEST_WITHIN_RANGE = "best_within_range"

_EFLM = (
    "EFLM Biological Variation Database (biologicalvariation.eu); cross-check "
    "against Ricos et al., Scand J Clin Lab Invest 1999;59:491-500 and updates"
)

_WORD = re.compile(r"[a-z0-9]+")


def fold(name: object) -> str:
    """A printed test name reduced to a sorted word set, for lookup only.

    THE SAME RULE `labSeriesService.nameKey` USES ON THE BACKEND, so that
    `CRP (C-REACTIVE PROTEIN)` and `C-REACTIVE PROTEIN(CRP)` find one row --
    which is the whole reason a lookup can work at all on printed names. It is
    deliberately NOT a fuzzy match: a name that does not fold to a listed
    alias falls through to the model rather than to the nearest row.
    """
    return " ".join(sorted(_WORD.findall(str(name or "").lower())))


@dataclass(frozen=True)
class LabVariation:
    """One test's variation figures, its polarity, and its provenance."""

    test: str
    polarity: str
    analytical_cv_pct: float
    within_subject_cv_pct: float
    source: str
    #: TRUE ONLY WHEN A HUMAN HAS COMPARED THIS ROW TO `source`. See the module
    #: docstring. Nothing in this repository sets it.
    verified: bool = False
    #: Names as laboratories actually print them, for `fold` to match on.
    aliases: Tuple[str, ...] = field(default_factory=tuple)


#: Every row: `verified=False`. See the module docstring before using one.
TABLE: Tuple[LabVariation, ...] = (
    LabVariation(
        test="c_reactive_protein",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=42.2,
        source=_EFLM,
        aliases=("CRP", "C-REACTIVE PROTEIN", "C-REACTIVE PROTEIN(CRP)", "CRP (C-REACTIVE PROTEIN)"),
    ),
    LabVariation(
        test="esr",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=10.0,
        within_subject_cv_pct=20.2,
        # ESR IS THE WEAKEST ROW IN THIS TABLE and the one a reviewer should
        # take first. It is a sedimentation observation rather than a measured
        # analyte, published biological-variation figures for it are sparse,
        # and the resulting threshold is wide enough to call almost any ESR
        # movement stable -- which is exactly the objection raised about
        # `ESR 35 -> 45 stable` on the real page.
        source=_EFLM + " -- SPARSE FOR ESR; treat this row as provisional",
        aliases=("ESR", "ERYTHROCYTE SEDIMENTATION RATE"),
    ),
    LabVariation(
        test="haemoglobin_a_note",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=2.8,
        source=_EFLM,
        # NOT `haemoglobin`. That feature is assessed and its polarity is
        # REFUSED ON PURPOSE in `trend_polarity.py`, because the range shifts
        # with sex, age and pregnancy and this service records none of them.
        # This row is PCV/haematocrit, which travels with it and is unassessed.
        aliases=("PCV", "HCT", "HAEMATOCRIT", "HEMATOCRIT", "PACKED CELL VOLUME"),
    ),
    LabVariation(
        test="mcv",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=1.4,
        source=_EFLM,
        aliases=("MCV", "MEAN CORPUSCULAR VOLUME", "MEAN CELL VOLUME"),
    ),
    LabVariation(
        test="mch",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=1.4,
        source=_EFLM,
        aliases=("MCH", "MEAN CORPUSCULAR HAEMOGLOBIN", "MEAN CORPUSCULAR HEMOGLOBIN"),
    ),
    LabVariation(
        test="mchc",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=1.7,
        source=_EFLM,
        aliases=("MCHC", "MEAN CORPUSCULAR HAEMOGLOBIN CONCENTRATION"),
    ),
    LabVariation(
        test="platelet_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=9.1,
        source=_EFLM,
        aliases=("PLATELET COUNT", "PLATELETS", "PLT"),
    ),
    LabVariation(
        test="rbc_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=3.2,
        source=_EFLM,
        aliases=("RBC COUNT", "T.RBC", "TOTAL RBC COUNT", "RBC", "ERYTHROCYTE COUNT"),
    ),
    LabVariation(
        test="wbc_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=3.0,
        within_subject_cv_pct=11.4,
        source=_EFLM,
        aliases=("WBC COUNT", "TOTAL WBC COUNT", "WBC", "TLC", "LEUCOCYTE COUNT"),
    ),
    LabVariation(
        test="neutrophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=16.0,
        source=_EFLM,
        aliases=("NEUTROPHILS", "POLYMORPHS", "POLYMORPHONUCLEAR CELLS"),
    ),
    LabVariation(
        test="lymphocytes",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=3.0,
        within_subject_cv_pct=10.3,
        source=_EFLM,
        aliases=("LYMPHOCYTES", "LYMPHS"),
    ),
    LabVariation(
        test="monocytes",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=17.8,
        source=_EFLM,
        aliases=("MONOCYTES",),
    ),
    LabVariation(
        test="eosinophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=21.0,
        # EOSINOPHILS VARY WIDELY WITHIN ONE PERSON and published figures
        # differ a great deal. This is the row whose instability the reader
        # first noticed, so it is the second a reviewer should take.
        source=_EFLM + " -- FIGURES VARY WIDELY FOR EOSINOPHILS; provisional",
        aliases=("EOSINOPHILS", "EOS"),
    ),
    LabVariation(
        test="basophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=10.0,
        within_subject_cv_pct=28.0,
        source=_EFLM + " -- provisional; basophil counts are small and noisy",
        aliases=("BASOPHILS", "BASO"),
    ),
    LabVariation(
        test="tsh",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=19.3,
        source=_EFLM,
        aliases=(
            "TSH",
            "TSH (THYROID STIMULATING HORMONE)",
            "TSH (THYROID STIM HORMONE)",
            "THYROID STIMULATING HORMONE",
        ),
    ),
    LabVariation(
        test="alanine_aminotransferase",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=19.4,
        source=_EFLM,
        aliases=("SGPT", "ALT", "SGPT (ALT)", "ALANINE AMINOTRANSFERASE"),
    ),
)


def _build_index() -> Dict[str, LabVariation]:
    index: Dict[str, LabVariation] = {}
    for entry in TABLE:
        for alias in entry.aliases:
            key = fold(alias)
            if not key:
                continue
            # A COLLISION IS A BUG IN THIS FILE, not something to resolve at
            # runtime by preferring one row. Two rows claiming one printed name
            # would make a test's threshold depend on declaration order, so the
            # first wins and `check_table` reports it.
            index.setdefault(key, entry)
    return index


_INDEX: Dict[str, LabVariation] = _build_index()


#: Assay methods, which laboratories print on their own line under the test.
#:
#: ==========================================================================
#: A METHOD IS HOW IT WAS MEASURED, NOT WHAT WAS MEASURED
#: ==========================================================================
#:
#: FOUND BY RE-ANALYSING A REPORT, 2026-09-19. The same PDF extracted twice
#: gave `ESR` one day and `ESR WESTGARD` the next -- the method line folded
#: into the name. Extraction is a model call and is not deterministic.
#:
#: The series still JOINED, because Module 36 matched the two spellings. But
#: the lookup below is exact, so three tests silently stopped finding their
#: rows and went back to asking the model for CVa/CVi:
#:
#:     ESR WESTGARD                              -> no row
#:     SGPT PHOTOMETRIC                          -> no row
#:     C-REACTIVE PROTEIN(CRP) Immunoturbidimetric -> no row
#:
#: **That is precisely the defect this table was built to end** -- a threshold
#: that moves between page loads. The page said so, because the card's
#: provenance line switched to "produced by a language model from the test
#: name alone"; that sentence had never been true before.
#:
#: EVERY WORD HERE IS AN ASSAY METHOD AND NONE CHANGES THE ANALYTE.
#: Deliberately absent: `direct`, `free`, `total`, `calculated`. Direct and
#: calculated LDL are different measurements, and `LDL Cholesterol, Direct` is
#: in the real data -- stripping `direct` would make two different things one,
#: which is the failure the qualifier guard in Module 36 exists to prevent.
#: Checked against all 59 distinct test names stored by this platform: it
#: changes five and leaves the other fifty-four untouched.
_METHOD_WORDS = frozenset(
    {
        "westgard",  # as this laboratory prints it
        "westergren",  # as it is properly spelled
        "photometric",
        "spectrophotometric",
        "colorimetric",
        "immunoturbidimetric",
        "immunoturbidometric",  # both spellings appear in the real data
        "turbidimetric",
        "nephelometric",
        "hplc",
        "elisa",
        "clia",
        "eclia",
        "cmia",
        "chemiluminescence",
        "enzymatic",
        "impedance",
        "cytometry",
    }
)


def _without_method(name: object) -> str:
    """`fold`, minus assay-method words. FOR LOOKUP ONLY.

    NOT FOLDED INTO `fold` ITSELF, and that is deliberate: `fold` must stay
    character-for-character the same rule as `labSeriesService.nameKey` on the
    backend, which its own docstring promises. Changing it here would make the
    two services disagree about which printed names are one test, silently and
    in only one of them.
    """
    words = [w for w in _WORD.findall(str(name or "").lower()) if w not in _METHOD_WORDS]
    return " ".join(sorted(words))


def variation_for(test_name: object) -> Optional[LabVariation]:
    """The row for this printed name, or None to fall through to the model.

    THE EXACT FOLD IS TRIED FIRST, so a name that matches a listed alias can
    never be diverted by the method fallback below.
    """
    row = _INDEX.get(fold(test_name))
    if row is not None:
        return row
    stripped = _without_method(test_name)
    if not stripped:
        # Every word was a method word. That is not a test name, and matching
        # it to anything would be worse than falling through to the model.
        return None
    return _INDEX.get(stripped)


def duplicate_aliases() -> Tuple[str, ...]:
    """Folded aliases claimed by more than one row. Empty is the only OK value.

    Exported so a test can assert the table is well formed rather than a
    reviewer noticing later that one test's threshold came from another's row.
    """
    seen: Dict[str, str] = {}
    clashes = []
    for entry in TABLE:
        for alias in entry.aliases:
            key = fold(alias)
            if key in seen and seen[key] != entry.test:
                clashes.append(key)
            seen.setdefault(key, entry.test)
    return tuple(sorted(set(clashes)))
