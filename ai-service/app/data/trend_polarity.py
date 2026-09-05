"""Module 28 trend polarity and stability bands -- the REVIEWABLE data file.

`app/services/trend_analyzer.py` contains the logic; this file contains the
judgements. It follows `app/data/validation_rules.py` and
`app/data/clinical_rules.py` exactly: plain tables, no control flow beyond a
lookup, every entry citing its basis, and a `_self_check()` that fails at
IMPORT time if this table and `app/data/feature_catalog.py` disagree.

--------------------------------------------------------------------------
WHY THIS FILE EXISTS: DIRECTION IS NOT THE SAME AS "BETTER"
--------------------------------------------------------------------------

A trend module that computes `last - first` knows only that a number went up
or down. Turning that into "improving" or "worsening" is a CLINICAL
judgement and it is different for every feature:

    HbA1c        6.1 -> 6.8   rose   -> WORSENING
    Vitamin D     14 -> 28    rose   -> IMPROVING (it was deficient)
    Creatinine   0.9 -> 1.6   rose   -> WORSENING

There is no rule of arithmetic that separates those. So the polarity is
DECLARED here, per feature, with its basis -- never inferred, never guessed,
and never hard-coded inline in the analyzer.

A feature whose polarity is `UNDECLARED` gets direction and magnitude and
NOTHING ELSE. The analyzer returns `trend: null` with the reason code
`CLINICAL_DIRECTION_UNKNOWN`. That is a deliberate refusal, not a gap in the
table: three features below are undeclared ON PURPOSE and say why.

--------------------------------------------------------------------------
THE TWO DECLARATIONS
--------------------------------------------------------------------------

1. `POLARITY` -- how a change in this feature maps onto better/worse.

   `MONOTONE`          One direction is unfavourable at every value.
                       `direction_of_harm` is "increase" or "decrease".
                       No threshold is needed, which is why these entries are
                       safe WITHOUT sex, age or timing context.

   `TOWARD_REFERENCE`  Both extremes are unfavourable. Improvement is movement
                       TOWARD the declared interval, measured as the distance
                       from the value to that interval. Either bound may be
                       `None`, meaning "no harm threshold is declared on that
                       side".

   `UNDECLARED`        Refusal. Direction only.

2. `STABILITY` -- how much change has to happen before "it changed" is a
   claim worth making. "Stable" is EARNED here, never defaulted: a series that
   fails to reach these thresholds is stable, and a series with fewer than two
   usable points is INSUFFICIENT_DATA, which is a different thing entirely.

--------------------------------------------------------------------------
THE BASIS OF THE STABILITY THRESHOLDS -- READ THIS BEFORE QUOTING THEM
--------------------------------------------------------------------------

Two consecutive laboratory results always differ, even when nothing about the
patient changed, because of analytical imprecision (CVa) and within-subject
biological variation (CVi). The conventional statistic for "is this difference
real?" is the REFERENCE CHANGE VALUE:

    RCV = 2**0.5 * Z * sqrt(CVa**2 + CVi**2)

with Z = 1.96 for a two-sided 95 % probability, i.e. a multiplier of 2.77.
`significant_change_pct` below is that RCV, rounded to a whole percent.

*** THESE CVa / CVi INPUTS ARE LITERATURE-TYPICAL VALUES RECORDED WITH THEIR
*** ARITHMETIC SO A REVIEWER CAN CHECK THEM. THEY HAVE **NOT** BEEN
*** INDEPENDENTLY AUDITED AGAINST THE EFLM BIOLOGICAL VARIATION DATABASE ON
*** THIS PROJECT. Treat them the way `MEMORY.md` treated the Module 5
*** conversion factors before they were verified: usable, written down, and
*** explicitly pending review. Every row states the CVa and CVi it used.

`min_absolute_change` is a second, independent floor in the canonical unit. It
exists because a percentage is meaningless near zero and because a laboratory
does not report to infinite resolution -- a 40 % rise in a vitamin D of 2
ng/mL is one reporting increment, not a trend. A change must clear BOTH the
percentage and the absolute floor to count as a change.

--------------------------------------------------------------------------
WHAT IS NEVER DONE HERE
--------------------------------------------------------------------------

* No polarity is inferred from a feature's name, its reference range, or the
  direction that happens to be more common.
* No feature is given a default polarity. A feature absent from `POLARITY`
  fails `_self_check()` at import; it does not quietly become MONOTONE.
* No clinical classification is restated here. `TOWARD_REFERENCE` bounds are
  cited sufficiency/normality intervals used to answer "is this moving toward
  or away from normal?" -- they are NOT diagnostic cut-offs and Module 28
  makes no diagnostic claim with them. Diagnosis-facing thresholds live in
  `app/data/clinical_rules.py` and are not duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.data.feature_catalog import FEATURES

#: Bump when a polarity or stability entry changes. Echoed in every response so
#: a stored trend can be traced back to the table that produced it.
TREND_POLICY_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Polarity
# --------------------------------------------------------------------------

POLARITY_MONOTONE = "monotone"
POLARITY_TOWARD_REFERENCE = "toward_reference"
POLARITY_UNDECLARED = "undeclared"

POLARITY_KINDS: Tuple[str, ...] = (
    POLARITY_MONOTONE,
    POLARITY_TOWARD_REFERENCE,
    POLARITY_UNDECLARED,
)

HARM_INCREASE = "increase"
HARM_DECREASE = "decrease"


@dataclass(frozen=True)
class TrendPolarity:
    """How a change in one canonical feature maps onto better / worse."""

    feature: str
    kind: str
    basis: str

    #: MONOTONE only. Which direction of change is the unfavourable one.
    direction_of_harm: Optional[str] = None

    #: TOWARD_REFERENCE only. Either bound may be None (= no declared harm
    #: threshold on that side). Stated in the feature's CANONICAL unit.
    optimal_low: Optional[float] = None
    optimal_high: Optional[float] = None

    #: False means "this feature is not a trend at all" -- see `age`.
    trendable: bool = True

    #: The declaration is only valid at or above this age. When any report in
    #: the series carries a younger age, the feature is refused rather than
    #: classified with an adult rule.
    min_age_years: Optional[int] = None

    #: True for features whose value is only comparable between reports when
    #: the sample timing matches (glucose). The analyzer refuses a series that
    #: mixes two DIFFERENT established timings.
    timing_sensitive: bool = False


POLARITY: Dict[str, TrendPolarity] = {
    # =================================================== declared MONOTONE ==
    "hba1c": TrendPolarity(
        "hba1c",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 6 (Glycemic Goals): HbA1c is a monotone summary of average "
            "glycaemia over the preceding ~3 months and lower values indicate "
            "better glycaemic control across the reportable range. The direction "
            "does not depend on sex, age or sample timing, which is why this "
            "entry is safe without context. (Hypoglycaemia risk is a treatment "
            "consideration, not a property of the HbA1c number itself.)"
        ),
    ),
    "creatinine": TrendPolarity(
        "creatinine",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "KDIGO 2012 CKD guideline: serum creatinine is inversely related to "
            "glomerular filtration rate, so a RISE reflects a FALL in kidney "
            "function. The absolute upper reference limit is sex-specific "
            "(see ANEMIA/CREATININE thresholds in app/data/clinical_rules.py), "
            "but the DIRECTION of harm is not -- which is exactly why only the "
            "direction is declared here."
        ),
    ),
    "cholesterol": TrendPolarity(
        "cholesterol",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "NCEP ATP III / AHA-ACC cholesterol guidance: total cholesterol is "
            "positively and continuously associated with atherosclerotic "
            "cardiovascular risk over the measured range. Direction is "
            "sex- and age-independent. NOTE the catalogue definition: "
            "`cholesterol` is TOTAL cholesterol; HDL, whose polarity is the "
            "opposite, is a DISTINCT analyte and is never folded into it "
            "(app/data/feature_catalog.py, DISTINCT_ANALYTE_TOKENS)."
        ),
    ),
    "triglycerides": TrendPolarity(
        "triglycerides",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "NCEP ATP III: fasting triglycerides are classified normal < 150, "
            "borderline-high 150-199, high 200-499, very high >= 500 mg/dL -- a "
            "monotone ordering, so a rise is unfavourable at every level. Only "
            "the ordering is used here; the cut-offs themselves are not "
            "restated."
        ),
    ),
    # ========================================== declared TOWARD_REFERENCE ==
    "vitamin_d": TrendPolarity(
        "vitamin_d",
        POLARITY_TOWARD_REFERENCE,
        optimal_low=30.0,
        optimal_high=100.0,
        basis=(
            "Endocrine Society Clinical Practice Guideline (Holick et al., "
            "2011) for 25-hydroxyvitamin D: deficiency < 20 ng/mL, "
            "insufficiency 21-29 ng/mL, sufficiency >= 30 ng/mL; concern for "
            "toxicity is described above ~100 ng/mL. BOTH bounds matter, which "
            "is the whole reason this feature is not MONOTONE: a rise from a "
            "deficient level is improvement, and a rise past 100 is not."
        ),
    ),
    "vitamin_b12": TrendPolarity(
        "vitamin_b12",
        POLARITY_TOWARD_REFERENCE,
        optimal_low=200.0,
        optimal_high=None,
        basis=(
            "The widely used adult lower reference limit for serum B12 is "
            "~200 pg/mL, below which deficiency is investigated, so movement "
            "up toward 200 is improvement. NO upper bound is declared: a high "
            "B12 is a marker of other pathology rather than a harm of the "
            "vitamin itself, and this module will not make that inference. "
            "Once a series sits above 200 the analyzer reports "
            "CHANGE_WITHIN_REFERENCE_INTERVAL rather than better or worse."
        ),
    ),
    "bmi": TrendPolarity(
        "bmi",
        POLARITY_TOWARD_REFERENCE,
        optimal_low=18.5,
        optimal_high=24.9,
        min_age_years=20,
        basis=(
            "WHO adult BMI classification: underweight < 18.5, normal range "
            "18.5-24.9, overweight >= 25.0 kg/m2. Both tails carry risk, so a "
            "fall in BMI is NOT automatically improvement. The WHO adult "
            "classification is explicitly sex-independent but is NOT valid in "
            "children and adolescents, where BMI is interpreted against "
            "age- and sex-specific percentiles -- hence min_age_years=20. A "
            "series with a younger recorded age is REFUSED, not classified "
            "with the adult rule."
        ),
    ),
    # ================================== declared UNDECLARED, deliberately ==
    "blood_glucose": TrendPolarity(
        "blood_glucose",
        POLARITY_UNDECLARED,
        timing_sensitive=True,
        basis=(
            "REFUSED ON PURPOSE. Two reasons, either of which is sufficient. "
            "(1) The canonical feature carries no sample timing, and a fasting, "
            "random and post-prandial glucose are not comparable quantities -- "
            "Module 8 already refuses to apply fasting cut-offs to a sample "
            "whose timing was not established, and it would be incoherent for "
            "Module 28 to be less careful. (2) Glucose is harmful at BOTH "
            "extremes, so no single direction of harm exists; a fall from 400 "
            "to 120 and a fall from 90 to 40 are opposite clinical events. "
            "Direction and magnitude are still reported; better/worse is not. "
            "EXTENSION POINT: `sample_timing()` in app/data/clinical_rules.py "
            "already infers timing from the printed test name, and the "
            "analyzer uses it to REFUSE a mixed-timing series. Declaring a "
            "per-timing polarity would need a reviewed target interval per "
            "timing and is deliberately not done here."
        ),
    ),
    "hemoglobin": TrendPolarity(
        "hemoglobin",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. Haemoglobin is harmful at both extremes "
            "(anaemia below, polycythaemia above), so it would have to be "
            "TOWARD_REFERENCE -- but the lower bound is sex- and age-specific "
            "(WHO VMNIS 2011: 12.0 g/dL non-pregnant women, 13.0 g/dL men, with "
            "separate paediatric bands) and is further modified by pregnancy, "
            "which this service does not record at all. Declaring one "
            "sex-neutral interval would mis-call one sex systematically. "
            "Direction and magnitude only. EXTENSION POINT: ANEMIA_CUTOFF and "
            "ELEVATED_HB_CUTOFF in app/data/clinical_rules.py are already "
            "ContextualThresholds resolvable from the `gender` and `age` "
            "features that a snapshot carries; wiring them in is the intended "
            "next step and needs clinical review, not just code."
        ),
    ),
    "age": TrendPolarity(
        "age",
        POLARITY_UNDECLARED,
        trendable=False,
        basis=(
            "NOT A TREND. Age rises monotonically for every patient by "
            "construction, so classifying it would produce a confident finding "
            "with no information in it. Refused with NOT_TRENDABLE."
        ),
    ),
    # ============ non-numeric features: no trend arithmetic is possible ====
    "hypertension": TrendPolarity(
        "hypertension",
        POLARITY_UNDECLARED,
        trendable=False,
        basis=(
            "Tri-state boolean (true / false / absent-unknown). There is no "
            "magnitude to trend, and absence means UNKNOWN, never false. "
            "Refused with NOT_NUMERIC."
        ),
    ),
    "heart_disease": TrendPolarity(
        "heart_disease",
        POLARITY_UNDECLARED,
        trendable=False,
        basis=(
            "Tri-state boolean (true / false / absent-unknown). As for "
            "hypertension: no magnitude, and absence is UNKNOWN. Refused with "
            "NOT_NUMERIC."
        ),
    ),
    "smoking_history": TrendPolarity(
        "smoking_history",
        POLARITY_UNDECLARED,
        trendable=False,
        basis=(
            "Categorical. The catalogue categories (never / former / current / "
            "ever / not_current / no_info) are NOT an ordered scale -- "
            "'no_info' has no position on it at all -- so no arithmetic and no "
            "ordering is defensible. Refused with NOT_NUMERIC."
        ),
    ),
    "gender": TrendPolarity(
        "gender",
        POLARITY_UNDECLARED,
        trendable=False,
        basis="Categorical identity attribute. Not a health trend.",
    ),
}


# --------------------------------------------------------------------------
# Stability bands
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StabilityBand:
    """How much change counts as change, for one canonical feature.

    A change must clear BOTH thresholds to be called a change. Below either
    one, the series is STABLE -- which is a positive finding here, earned by
    passing this test, not a value assigned when nothing else matched.
    """

    feature: str
    significant_change_pct: float
    min_absolute_change: float
    basis: str
    #: The inputs to the RCV arithmetic, recorded so a reviewer can recompute.
    analytical_cv_pct: Optional[float] = None
    within_subject_cv_pct: Optional[float] = None


#: RCV multiplier: 2**0.5 * 1.96, the two-sided 95 % reference change value.
RCV_Z = 1.96
RCV_MULTIPLIER = 2.7718585822512662


def reference_change_value(analytical_cv: float, within_subject_cv: float) -> float:
    """`2**0.5 * 1.96 * sqrt(CVa**2 + CVi**2)`, as a percentage.

    Public so the test suite and a reviewer can recompute every row below
    instead of trusting the numbers that were typed in.
    """
    return RCV_MULTIPLIER * ((analytical_cv**2 + within_subject_cv**2) ** 0.5)


_RCV_NOTE = (
    "Reference change value, RCV = 2**0.5 * 1.96 * sqrt(CVa^2 + CVi^2), "
    "rounded to a whole percent. CVa/CVi are literature-typical values and "
    "are PENDING INDEPENDENT VERIFICATION on this project."
)

STABILITY: Dict[str, StabilityBand] = {
    "hba1c": StabilityBand(
        "hba1c",
        significant_change_pct=8.0,
        min_absolute_change=0.2,
        analytical_cv_pct=2.0,
        within_subject_cv_pct=1.9,
        basis=(
            _RCV_NOTE + " CVa 2.0 %, CVi 1.9 % -> RCV 7.6 %, taken as 8 %. "
            "Absolute floor 0.2 % NGSP: HbA1c is reported to 0.1 %, so a "
            "difference of one reporting increment is not a trend."
        ),
    ),
    "blood_glucose": StabilityBand(
        "blood_glucose",
        significant_change_pct=17.0,
        min_absolute_change=5.0,
        analytical_cv_pct=2.5,
        within_subject_cv_pct=5.6,
        basis=(
            _RCV_NOTE + " CVa 2.5 %, CVi 5.6 % -> RCV 17.0 %. Absolute floor "
            "5 mg/dL, the usual reporting increment. NOTE this band is applied "
            "to a feature whose POLARITY is deliberately undeclared, so it can "
            "only ever produce 'stable' or 'changed, direction only'."
        ),
    ),
    "hemoglobin": StabilityBand(
        "hemoglobin",
        significant_change_pct=9.0,
        min_absolute_change=0.3,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=2.8,
        basis=(
            _RCV_NOTE + " CVa 1.5 %, CVi 2.8 % -> RCV 8.8 %, taken as 9 %. "
            "Absolute floor 0.3 g/dL, the usual reporting increment of 0.1 "
            "g/dL times three."
        ),
    ),
    "vitamin_d": StabilityBand(
        "vitamin_d",
        significant_change_pct=36.0,
        min_absolute_change=3.0,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=12.1,
        basis=(
            _RCV_NOTE + " CVa 5.0 %, CVi 12.1 % -> RCV 36.3 %, taken as 36 %. "
            "25-OH vitamin D has large seasonal and assay variability, which is "
            "why this band is much wider than HbA1c's. Absolute floor 3 ng/mL "
            "keeps a percentage from being decisive near the detection limit."
        ),
    ),
    "vitamin_b12": StabilityBand(
        "vitamin_b12",
        significant_change_pct=40.0,
        min_absolute_change=25.0,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=13.4,
        basis=(
            _RCV_NOTE + " CVa 5.0 %, CVi 13.4 % -> RCV 39.6 %, taken as 40 %. "
            "Absolute floor 25 pg/mL."
        ),
    ),
    "creatinine": StabilityBand(
        "creatinine",
        significant_change_pct=14.0,
        min_absolute_change=0.1,
        analytical_cv_pct=2.2,
        within_subject_cv_pct=4.5,
        basis=(
            _RCV_NOTE + " CVa 2.2 %, CVi 4.5 % -> RCV 13.9 %, taken as 14 %. "
            "Absolute floor 0.1 mg/dL, the reporting increment."
        ),
    ),
    "cholesterol": StabilityBand(
        "cholesterol",
        significant_change_pct=17.0,
        min_absolute_change=5.0,
        analytical_cv_pct=2.5,
        within_subject_cv_pct=5.7,
        basis=(
            _RCV_NOTE + " CVa 2.5 %, CVi 5.7 % -> RCV 17.3 %, taken as 17 %. "
            "Absolute floor 5 mg/dL, the reporting increment."
        ),
    ),
    "triglycerides": StabilityBand(
        "triglycerides",
        significant_change_pct=56.0,
        min_absolute_change=15.0,
        analytical_cv_pct=3.5,
        within_subject_cv_pct=19.9,
        basis=(
            _RCV_NOTE + " CVa 3.5 %, CVi 19.9 % -> RCV 56.1 %, taken as 56 %. "
            "Triglycerides have the largest within-subject variation of any "
            "feature here -- a fasting/non-fasting difference alone moves them "
            "substantially -- so a change has to be large to be real. A "
            "narrower band here would generate confident noise."
        ),
    ),
    "bmi": StabilityBand(
        "bmi",
        significant_change_pct=5.0,
        min_absolute_change=0.5,
        analytical_cv_pct=None,
        within_subject_cv_pct=None,
        basis=(
            "NOT AN RCV, AND NOT LITERATURE-DERIVED. BMI is a derived "
            "anthropometric quantity, not an assay, so biological-variation "
            "figures do not apply to it. 5 % / 0.5 kg/m2 is a REVIEWER "
            "JUDGEMENT chosen so that ordinary scale-to-scale and "
            "time-of-day weight differences (roughly 1-2 kg in an adult) do "
            "not register as a trend. It is stated as a judgement precisely so "
            "a clinician can overrule it; it is not dressed up as evidence."
        ),
    ),
}


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------


def polarity_for(feature: str) -> Optional[TrendPolarity]:
    """The polarity declaration for a canonical feature, or None if unknown."""
    return POLARITY.get(feature)


#: The two sides of a reference interval, named so a caller cannot pass a
#: bare boolean and get the sense backwards.
SIDE_BELOW = "below"
SIDE_ABOVE = "above"

SIDES: Tuple[str, ...] = (SIDE_BELOW, SIDE_ABOVE)


def harm_declared_beyond(feature: str, side: str) -> Optional[bool]:
    """Tri-state: is going PAST a reference interval on `side` unfavourable?

    `True`  -- this table declares harm on that side.
    `False` -- this table declares that there is NO harm threshold on that
               side. Not "we have not looked": the declaration is positive.
    `None`  -- UNKNOWN. The feature has no declared clinical direction, or is
               not in this table at all.

    WHY THIS LIVES HERE AND NOT IN THE CALLER. A laboratory report often
    prints only ONE end of a reference interval, and Module 5's contract makes
    `reference_low` and `reference_high` independently nullable, so a
    one-sided interval also arises when extraction loses a bound that WAS
    printed. A consumer then has to answer: a reading that is not past the one
    bound it has -- is it inside the interval, or is its position simply not
    known?

    That question is exactly the judgement this file exists to hold, and it is
    per feature:

        cholesterol   `< 200 mg/dL`, reading 150. MONOTONE, harm on increase
                      only. Nothing below is declared unfavourable, so the
                      reading IS inside. -> harm below: False.
        creatinine    `0.6 - ` with the upper bound lost, reading 6.5.
                      MONOTONE, harm on increase. The missing side is the
                      harmful one, so the position is NOT known.
                      -> harm above: True.
        haemoglobin   ` - 17.0` with the lower bound lost, reading 7.5.
                      UNDECLARED: this table refuses to say where haemoglobin
                      becomes harmful (the lower limit is sex-, age- and
                      pregnancy-specific -- see the entry). -> None, unknown.

    A caller that treated any of those three the same way would be reporting
    severe anaemia as in-range. Getting `False` and `None` confused here is
    the "absence becomes a value" hazard in its most direct form, which is
    why the return is tri-state and why there is no default branch below.

    Only `POLARITY` is read. No threshold, no reference range and no patient
    value reaches this function; it answers a question about the TABLE.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    entry = POLARITY.get(feature)
    if entry is None:
        return None
    if entry.kind == POLARITY_MONOTONE:
        # "One direction is unfavourable at every value" -- so the other
        # direction is declared favourable at every value, and there is no
        # harm threshold on it.
        if entry.direction_of_harm == HARM_INCREASE:
            return side == SIDE_ABOVE
        if entry.direction_of_harm == HARM_DECREASE:
            return side == SIDE_BELOW
        # `_self_check` makes this unreachable; refusing beats guessing.
        return None  # pragma: no cover
    if entry.kind == POLARITY_TOWARD_REFERENCE:
        # A `None` bound is documented above as "no harm threshold is declared
        # on that side" -- a positive declaration, so it maps to False.
        if side == SIDE_BELOW:
            return entry.optimal_low is not None
        return entry.optimal_high is not None
    # UNDECLARED, including the non-trendable rows. Nothing is claimed about
    # either side.
    return None


def stability_for(feature: str) -> Optional[StabilityBand]:
    """The stability band for a canonical feature, or None if it has none.

    None means the feature is not numerically trendable at all; it does NOT
    mean "no threshold, so everything counts as a change". The analyzer
    refuses a feature with no band rather than treating any change as real.
    """
    return STABILITY.get(feature)


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Fail at import if this table and the feature catalog disagree.

    A canonical feature with no polarity row is the dangerous case: the
    analyzer would have to pick a default, and every default here is a silent
    clinical claim. So the table must be TOTAL over the catalog.
    """
    missing = [name for name in FEATURES if name not in POLARITY]
    if missing:
        raise ValueError(
            f"features with no declared trend polarity: {missing}. Add a row to "
            "app/data/trend_polarity.py -- including an explicit UNDECLARED "
            "row with its reason. A polarity is never defaulted."
        )
    extra = [name for name in POLARITY if name not in FEATURES]
    if extra:
        raise ValueError(f"trend polarity for unknown features: {extra}")

    for name, entry in POLARITY.items():
        definition = FEATURES[name]
        if entry.feature != name:
            raise ValueError(f"polarity key {name!r} != entry.feature {entry.feature!r}")
        if entry.kind not in POLARITY_KINDS:
            raise ValueError(f"{name}: unknown polarity kind {entry.kind!r}")
        if not entry.basis.strip():
            raise ValueError(f"{name}: every polarity entry must state its basis")
        # NOT scanned by the recommendation safety scanner, deliberately. These
        # `basis` strings are REVIEWER-facing: they cite guidelines and discuss
        # why a declaration is or is not safe, so they legitimately contain
        # words ("treatment", "deficiency") the patient-facing scanner bans.
        # They are served only by the policy endpoint, which returns no patient
        # data. The PATIENT-FACING strings this module can emit are the reason
        # templates in app/services/trend_analyzer.py, and THOSE are scanned at
        # import time.

        numeric = definition.value_type in ("number", "integer")

        if entry.kind == POLARITY_MONOTONE:
            if entry.direction_of_harm not in (HARM_INCREASE, HARM_DECREASE):
                raise ValueError(
                    f"{name}: MONOTONE needs direction_of_harm "
                    f"{HARM_INCREASE!r} or {HARM_DECREASE!r}"
                )
            if entry.optimal_low is not None or entry.optimal_high is not None:
                raise ValueError(f"{name}: MONOTONE must not declare an interval")
            if not numeric:
                raise ValueError(f"{name}: MONOTONE declared on a non-numeric feature")
            if not entry.trendable:
                raise ValueError(f"{name}: MONOTONE declared on a non-trendable feature")
        elif entry.kind == POLARITY_TOWARD_REFERENCE:
            if entry.direction_of_harm is not None:
                raise ValueError(
                    f"{name}: TOWARD_REFERENCE must not declare direction_of_harm"
                )
            if entry.optimal_low is None and entry.optimal_high is None:
                raise ValueError(
                    f"{name}: TOWARD_REFERENCE needs at least one bound"
                )
            if (
                entry.optimal_low is not None
                and entry.optimal_high is not None
                and entry.optimal_low >= entry.optimal_high
            ):
                raise ValueError(f"{name}: optimal_low >= optimal_high")
            if not numeric:
                raise ValueError(
                    f"{name}: TOWARD_REFERENCE declared on a non-numeric feature"
                )
            if not entry.trendable:
                raise ValueError(
                    f"{name}: TOWARD_REFERENCE declared on a non-trendable feature"
                )
        else:  # UNDECLARED
            if entry.direction_of_harm is not None or entry.optimal_low is not None:
                raise ValueError(
                    f"{name}: UNDECLARED must not carry a polarity parameter"
                )

        # A non-numeric feature can never be trendable, whatever the row says.
        if not numeric and entry.trendable:
            raise ValueError(
                f"{name}: value_type {definition.value_type!r} cannot be trendable"
            )

    # Every feature the analyzer is willing to trend must have a stability
    # band, or "stable" would have no meaning for it.
    for name, entry in POLARITY.items():
        if entry.trendable and name not in STABILITY:
            raise ValueError(
                f"{name}: trendable but has no stability band. 'Stable' must be "
                "earned against a declared threshold."
            )
    for name, band in STABILITY.items():
        if name not in FEATURES:
            raise ValueError(f"stability band for unknown feature: {name}")
        if band.feature != name:
            raise ValueError(f"stability key {name!r} != band.feature {band.feature!r}")
        if band.significant_change_pct <= 0 or band.min_absolute_change < 0:
            raise ValueError(f"{name}: stability thresholds must be positive")
        if not band.basis.strip():
            raise ValueError(f"{name}: every stability band must state its basis")
        # Where the row claims to be an RCV, recompute it. A typo in the
        # percentage is otherwise invisible.
        if band.analytical_cv_pct is not None and band.within_subject_cv_pct is not None:
            computed = reference_change_value(
                band.analytical_cv_pct, band.within_subject_cv_pct
            )
            if abs(computed - band.significant_change_pct) > 0.6:
                raise ValueError(
                    f"{name}: significant_change_pct "
                    f"{band.significant_change_pct} does not match the RCV "
                    f"{computed:.2f} computed from the stated CVa/CVi"
                )

    # ---- `harm_declared_beyond` is total, and answers only where the table
    # ---- actually declares something.
    #
    # The consumer of this accessor (Module 29's abnormality axis) treats
    # `False` as "a reading on this side of a one-sided interval is inside it"
    # and `None` as "not determinable". So a row that declares NO clinical
    # direction must never yield a definite `False`, or an undeclared feature
    # would silently acquire a normality claim. That is asserted here rather
    # than trusted to the branch structure.
    for name, entry in POLARITY.items():
        answers = tuple(harm_declared_beyond(name, side) for side in SIDES)
        if entry.kind == POLARITY_UNDECLARED:
            if answers != (None, None):
                raise ValueError(
                    f"{name}: an UNDECLARED polarity must give no answer on "
                    f"either side, got {answers}"
                )
            continue
        if any(answer is None for answer in answers):
            raise ValueError(
                f"{name}: a declared polarity must answer on both sides, "
                f"got {answers}"
            )
        if entry.kind == POLARITY_MONOTONE and answers.count(True) != 1:
            raise ValueError(
                f"{name}: MONOTONE declares harm in exactly one direction, "
                f"got {answers}"
            )


_self_check()


def policy_document() -> Dict[str, object]:
    """Machine-readable dump of both tables, for review and for the API.

    Shape and thresholds only -- no patient data of any kind.
    """
    return {
        "version": TREND_POLICY_VERSION,
        "polarity_kinds": {
            POLARITY_MONOTONE: "One direction is unfavourable at every value.",
            POLARITY_TOWARD_REFERENCE: "Both extremes are unfavourable; "
            "improvement is movement toward the declared interval.",
            POLARITY_UNDECLARED: "No clinical direction is declared. The "
            "analyzer reports direction and magnitude and returns trend: null "
            "with CLINICAL_DIRECTION_UNKNOWN. This is a refusal, not a gap.",
        },
        "stability_rule": (
            "A change must clear BOTH significant_change_pct and "
            "min_absolute_change to count as a change. Below either, the "
            "series is STABLE. Fewer than two usable points is "
            "INSUFFICIENT_DATA, which is not stable."
        ),
        "reference_change_value_formula": (
            "RCV = 2**0.5 * 1.96 * sqrt(CVa^2 + CVi^2), two-sided 95 %"
        ),
        "verification_status": (
            "The CVa/CVi inputs are literature-typical values recorded with "
            "their arithmetic. They have NOT been independently audited on "
            "this project. The bmi band is an explicitly stated reviewer "
            "judgement and is not literature-derived."
        ),
        "features": {
            name: {
                "kind": entry.kind,
                "direction_of_harm": entry.direction_of_harm,
                "optimal_low": entry.optimal_low,
                "optimal_high": entry.optimal_high,
                "canonical_unit": FEATURES[name].canonical_unit,
                "value_type": FEATURES[name].value_type,
                "trendable": entry.trendable,
                "min_age_years": entry.min_age_years,
                "timing_sensitive": entry.timing_sensitive,
                "basis": entry.basis,
                "stability": (
                    {
                        "significant_change_pct": STABILITY[name].significant_change_pct,
                        "min_absolute_change": STABILITY[name].min_absolute_change,
                        "analytical_cv_pct": STABILITY[name].analytical_cv_pct,
                        "within_subject_cv_pct": STABILITY[name].within_subject_cv_pct,
                        "basis": STABILITY[name].basis,
                    }
                    if name in STABILITY
                    else None
                ),
            }
            for name, entry in POLARITY.items()
        },
    }


__all__ = [
    "HARM_DECREASE",
    "HARM_INCREASE",
    "POLARITY",
    "POLARITY_KINDS",
    "POLARITY_MONOTONE",
    "POLARITY_TOWARD_REFERENCE",
    "POLARITY_UNDECLARED",
    "RCV_MULTIPLIER",
    "RCV_Z",
    "SIDES",
    "SIDE_ABOVE",
    "SIDE_BELOW",
    "STABILITY",
    "TREND_POLICY_VERSION",
    "StabilityBand",
    "TrendPolarity",
    "harm_declared_beyond",
    "polarity_for",
    "policy_document",
    "reference_change_value",
    "stability_for",
]
