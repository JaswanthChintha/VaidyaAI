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

#: The date the figures below were read off the EFLM database.
_READ_ON = "2026-09-19"


def _eflm(analyte: str, page: int, median: float, low: float, high: float) -> str:
    """The citation for one row's CVi: the page, the figure, and its interval.

    ==========================================================================
    THE CITATION NAMES THE NUMBER, AND A TEST HOLDS THEM TOGETHER
    ==========================================================================

    The rows used to carry one shared `_EFLM` string -- a database name and a
    paper, with no page, no figure and no date. That is a bibliography, not a
    citation: a reviewer still had to go and find the analyte, and nothing
    stopped the stored figure drifting away from whatever the source said.

    Each row now names ITS OWN meta-analysis page and repeats the median it
    took from it, and `test_every_row_cites_the_figure_it_stores` parses that
    median back out and compares it to `within_subject_cv_pct`. Change one
    without the other and the suite fails.

    ==========================================================================
    THIS IS STILL NOT VERIFICATION
    ==========================================================================

    These figures were read off those pages BY A MODEL on the date above, and
    the module docstring's rule is unchanged: `verified=True` may only be set
    by a human who has opened the page and compared it. What has changed is
    that opening the page is now one click from the row instead of a search.

    CVa IS NOT COVERED BY ANY OF THIS. The EFLM database publishes CVI and not
    analytical CV, because analytical variation is a property of the ANALYSER
    -- which is what this module's docstring already said. Every `CVa` in this
    table remains an unsourced placeholder.
    """
    return (
        f"EFLM Biological Variation Database, meta-analysis for {analyte}: "
        f"CVi median {median} % (CI {low}-{high} %). "
        f"biologicalvariation.eu/meta_by_analyte/{page}, read {_READ_ON} and "
        f"NOT YET CONFIRMED against that page by a human. "
        f"CVa IS NOT FROM THIS SOURCE -- EFLM publishes no analytical CV."
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
        # WAS 42.2, inside the published interval but above the median.
        within_subject_cv_pct=34.7,
        source=_eflm("C-reactive protein (CRP)", 1635, 34.7, 29.4, 74.4),
        aliases=("CRP", "C-REACTIVE PROTEIN", "C-REACTIVE PROTEIN(CRP)", "CRP (C-REACTIVE PROTEIN)"),
    ),
    LabVariation(
        test="esr",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=10.0,
        within_subject_cv_pct=20.2,
        # ==================================================================
        # THE SOURCE THIS ROW NAMED DOES NOT CONTAIN IT
        # ==================================================================
        #
        # Every other row here cites its own EFLM meta-analysis page. ESR has
        # none: searching that database for `ESR` and for `sedimentation`
        # returns NOTHING (checked 2026-09-19 through its own search API).
        # The row previously pointed a reviewer at EFLM anyway, which is a
        # citation to a page that does not exist -- worse than no citation,
        # because it reads as checkable.
        #
        # AND ESR MAY NOT HAVE A SINGLE CV AT ALL. The long-term study that
        # does exist (Scand J Clin Lab Invest 1996;56:191-8) reports
        # SEX-SPECIFIC WITHIN-SUBJECT VARIANCES rather than one coefficient,
        # and the analytical CV is CONCENTRATION-DEPENDENT -- about 13 % near
        # 4 mm/h against about 4 % near 16 mm/h. A single fixed percentage
        # threshold for ESR is therefore questionable in PRINCIPLE, not only
        # unverified.
        #
        # THE ROW STAYS ANYWAY, and deliberately. Deleting it sends ESR back
        # to the model for its figures, which is the unreproducible behaviour
        # 6aw replaced -- the reader saw a threshold move between page loads.
        # A stable questionable number that says it is questionable beats a
        # different questionable number every time the page is opened.
        source=(
            "NO SOURCE. The EFLM Biological Variation Database has NO ENTRY "
            "for ESR -- searched 2026-09-19 for both `ESR` and "
            "`sedimentation`, no result. The figures here are "
            "literature-typical and cite nothing. Published work reports "
            "sex-specific variances (Scand J Clin Lab Invest 1996;56:191-8), "
            "not one CV, and the analytical CV varies with the value itself, "
            "so a single percentage threshold for ESR is questionable in "
            "principle. THIS IS THE ROW TO SETTLE FIRST."
        ),
        aliases=("ESR", "ERYTHROCYTE SEDIMENTATION RATE"),
    ),
    LabVariation(
        test="haemoglobin_a_note",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.5,
        # Unchanged: 2.8 is the published median exactly.
        within_subject_cv_pct=2.8,
        source=_eflm("Haematocrit (Hct)", 1524, 2.8, 2.2, 3.1),
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
        # WAS 1.4, which is OUTSIDE the published interval 0.7-1.1. This is
        # also the one row whose change of figure moves a verdict on the
        # reader's own page: MCV 85.1 -> 88.6 is 4.1 %, under the old 4.8 %
        # threshold and over the new 3.5 % one.
        within_subject_cv_pct=0.8,
        source=_eflm("Mean corpuscular volume (MCV)", 1527, 0.8, 0.7, 1.1),
        aliases=("MCV", "MEAN CORPUSCULAR VOLUME", "MEAN CELL VOLUME"),
    ),
    LabVariation(
        test="mch",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        # WAS 1.4, inside the wide published interval but above the median.
        within_subject_cv_pct=0.8,
        source=_eflm("Mean corpuscular haemoglobin (MCH)", 1525, 0.8, 0.3, 1.7),
        aliases=("MCH", "MEAN CORPUSCULAR HAEMOGLOBIN", "MEAN CORPUSCULAR HEMOGLOBIN"),
    ),
    LabVariation(
        test="mchc",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        # WAS 1.7, OUTSIDE the published interval 0.8-1.0.
        within_subject_cv_pct=1.0,
        source=_eflm(
            "Mean corpuscular haemoglobin concentration (MCHC)", 1526, 1.0, 0.8, 1.0
        ),
        aliases=("MCHC", "MEAN CORPUSCULAR HAEMOGLOBIN CONCENTRATION"),
    ),
    LabVariation(
        test="platelet_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=4.0,
        # WAS 9.1, inside the published interval but above the median.
        within_subject_cv_pct=7.3,
        source=_eflm("Thrombocytes", 1538, 7.3, 6.6, 10.2),
        aliases=("PLATELET COUNT", "PLATELETS", "PLT"),
    ),
    LabVariation(
        test="rbc_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.5,
        # WAS 3.2, inside the interval, above the median.
        within_subject_cv_pct=2.6,
        source=_eflm("Erythrocytes", 1523, 2.6, 1.4, 4.0),
        aliases=("RBC COUNT", "T.RBC", "TOTAL RBC COUNT", "RBC", "ERYTHROCYTE COUNT"),
    ),
    LabVariation(
        test="wbc_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=3.0,
        # WAS 11.4, barely above the median and well inside the interval.
        within_subject_cv_pct=11.1,
        source=_eflm("Leukocytes", 1532, 11.1, 8.1, 12.8),
        aliases=("WBC COUNT", "TOTAL WBC COUNT", "WBC", "TLC", "LEUCOCYTE COUNT"),
    ),
    LabVariation(
        test="neutrophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=4.0,
        # WAS 16.0, inside a very wide interval, above the median.
        within_subject_cv_pct=12.5,
        source=_eflm("Neutrophils", 1533, 12.5, 6.3, 26.9),
        aliases=("NEUTROPHILS", "POLYMORPHS", "POLYMORPHONUCLEAR CELLS"),
    ),
    LabVariation(
        test="lymphocytes",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        # WAS 10.3 -- THE ONLY ROW THAT WAS BELOW its published median, and
        # so the only one whose threshold WIDENS here rather than narrowing.
        within_subject_cv_pct=10.5,
        analytical_cv_pct=3.0,
        source=_eflm("Lymphocytes", 1534, 10.5, 9.8, 14.7),
        aliases=("LYMPHOCYTES", "LYMPHS"),
    ),
    LabVariation(
        test="monocytes",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        # WAS 17.8, inside the interval, above the median.
        within_subject_cv_pct=14.0,
        source=_eflm("Monocytes", 1535, 14.0, 11.1, 19.3),
        aliases=("MONOCYTES",),
    ),
    LabVariation(
        test="eosinophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        # WAS 21.0. THIS ROW EXPLAINS THE FLICKER THE READER FIRST REPORTED:
        # the old figure gave a 59.8 % threshold against a 60.0 % change on
        # their own reports -- a margin of two tenths of a percentage point,
        # which is why EOSINOPHILS 5 -> 2 read `stable` on one request and
        # was refused on the next. The published median moves the threshold
        # to 44.1 % and the verdict off the knife edge.
        within_subject_cv_pct=15.1,
        source=_eflm("Eosinophils", 1536, 15.1, 10.1, 26.9),
        aliases=("EOSINOPHILS", "EOS"),
    ),
    LabVariation(
        test="basophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=10.0,
        # WAS 28.0 -- MORE THAN DOUBLE the published median, the largest
        # discrepancy in the table, though still inside a very wide interval.
        within_subject_cv_pct=12.6,
        source=_eflm("Basophils", 1537, 12.6, 11.4, 32.0),
        aliases=("BASOPHILS", "BASO"),
    ),
    LabVariation(
        test="tsh",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        # WAS 19.3, inside the interval, above the median.
        within_subject_cv_pct=17.8,
        source=_eflm("Thyroid stimulating hormone (TSH)", 1065, 17.8, 12.0, 29.3),
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
        # WAS 19.4, OUTSIDE the published interval 9.3-17.3. 6aw called SGPT
        # "the row to verify first" because `SGPT 101.9 -> 13 improving` rests
        # on the U/L == IU/L declaration; its variation figure was out of range
        # too. The verdict survives either way -- an 87 % fall clears both
        # thresholds -- but the figure behind it was not supported.
        within_subject_cv_pct=12.6,
        source=_eflm("Alanine transaminase (ALT)", 1495, 12.6, 9.3, 17.3),
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
