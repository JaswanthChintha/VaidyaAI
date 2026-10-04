"""Module 8 clinical rules -- the CLINICIAN-AUDITABLE data file.

`app/services/rule_engine.py` contains the logic; this file contains the
medicine. It follows `app/data/validation_rules.py` exactly: plain tables, no
control flow beyond threshold lookup, every threshold citing its clinical
basis, and a `_self_check()` that fails at IMPORT time if the table and the
feature catalog disagree.

--------------------------------------------------------------------------
WHAT MODULE 8 IS, AND WHAT IT IS NOT
--------------------------------------------------------------------------

Module 6 answered "is this value BELIEVABLE?". Module 8 answers "is this value
NOTABLE, against a published threshold?" -- deterministically, transparently,
and traceably. There is no model here, no probability, and no learning. Every
decision this engine emits can be reproduced by a human reading this file.

That is also why every decision it emits carries ``confidence=None``: per
`app/schemas/decisions.py`, `None` means "this component produces no
probability", which is exactly true of a threshold comparison. It is NOT 0.0.

--------------------------------------------------------------------------
HOW A RULE WORKS
--------------------------------------------------------------------------

A `ThresholdRule` names ONE canonical feature and an ORDERED tuple of `Band`s.
The first band whose comparator holds decides the outcome; the final band has
`comparator=None` and always matches, so a rule that fires produces exactly one
decision. Ordering matters and is deliberate: the most severe band is first.

Comparator semantics are exact and are tested ON the threshold as well as
either side of it:

    ">=" fires AT the threshold          "<" does NOT fire at the threshold
    ">"  does NOT fire at the threshold  "<=" fires AT the threshold

--------------------------------------------------------------------------
MISSING DATA
--------------------------------------------------------------------------

A rule whose feature is absent from Module 6's `valid` map DOES NOT FIRE. It
does not fall through to its final band; there is nothing to compare. Absence
never produces a NOT_INDICATED decision, because "we did not measure it" and
"we measured it and it was fine" are different statements and conflating them
is the failure mode this whole project keeps re-encountering.

The tri-state booleans (`hypertension`, `heart_disease`) are only ever read as
POSITIVE risk factors: a factor counts when the value is exactly `True`.
`False` and ABSENT both simply fail to add a factor, and are never distinguished
in a way that lets absence masquerade as a stated negative.

--------------------------------------------------------------------------
SEX- AND AGE-SPECIFIC THRESHOLDS
--------------------------------------------------------------------------

Haemoglobin, creatinine and cardiovascular age thresholds are genuinely
sex-specific, so they are implemented as `ContextualThreshold`s rather than
being flattened into one number and quietly mis-called for half the population.

Where sex is NOT established (absent, `other`, `prefer_not_to_say`) the rule
uses the threshold that AVOIDS OVER-CALLING, and adds an explicit BORDERLINE
band covering the zone between the male and female cut-offs, with a note saying
why. Neither silently over-calling nor silently under-calling is acceptable;
saying "this depends on a value I do not have" is.

Adult reference intervals are not valid for children. Rules carrying
`min_age_years` therefore emit INSUFFICIENT_DATA -- never a numeric verdict --
when the recorded age is below it.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from app.data import conditions as C
from app.data.egfr import EGFR_FEATURE, EGFR_MIN_AGE_YEARS, EGFR_UNIT
from app.data.feature_catalog import FEATURES, normalize_test_name
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_SAMPLE_TIMING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_BALANCED_DIET,
    GENERAL_DIETARY_FAT_QUALITY,
    GENERAL_HYDRATION,
    GENERAL_IRON_RICH_FOODS,
    GENERAL_LIMIT_ADDED_SUGAR,
    GENERAL_PHYSICAL_ACTIVITY,
    GENERAL_SMOKING_CESSATION_SUPPORT,
    GENERAL_VITAMIN_B12_SOURCES,
    GENERAL_VITAMIN_D_SOURCES,
    GENERAL_WEIGHT_DISCUSSION,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    SEEK_PROMPT_MEDICAL_ADVICE,
    assert_safe,
    is_known_code,
)
from app.schemas.decisions import DecisionStatus, RiskLevel

#: Bumped whenever any threshold, band or rule in this file changes. Recorded
#: in every decision's `metadata` so a past report can be reproduced.
RULE_TABLE_VERSION = "1.1.0"

#: The human-readable producer name written into every `ClinicalDecision`.
RULE_ENGINE_SOURCE = "Clinical Rule Engine"


# --------------------------------------------------------------------------
# Comparators
# --------------------------------------------------------------------------

COMPARATORS: Dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
}


# --------------------------------------------------------------------------
# Sample timing -- which glucose thresholds are even applicable
# --------------------------------------------------------------------------

TIMING_FASTING = "fasting"
TIMING_POST_PRANDIAL = "post_prandial"
TIMING_RANDOM = "random"
TIMING_UNSPECIFIED = "unspecified"

# Module 5 maps fasting, random and post-prandial glucose onto the SAME
# canonical feature (`blood_glucose`), keeping the printed name in
# `provenance.original_test_name` / `matched_synonym`. The ADA fasting
# thresholds (126 / 100 mg/dL) are only valid for a FASTING sample, so the
# engine recovers the timing from those strings rather than assuming.
#
# These token sets mirror the qualifiers already present in
# `FEATURE_SYNONYMS["blood_glucose"]`, normalised with `normalize_test_name`.
FASTING_TOKENS: Tuple[str, ...] = ("fasting", "fbs", "fpg")
POST_PRANDIAL_TOKENS: Tuple[str, ...] = ("postprandial", "prandial", "ppbs", "pp")
RANDOM_TOKENS: Tuple[str, ...] = ("random", "rbs")


def sample_timing(*texts: Optional[str]) -> str:
    """Infer glucose sample timing from the printed test name.

    Returns `unspecified` when nothing in the text establishes the timing.
    UNSPECIFIED IS NOT FASTING: it is the reason a separate, deliberately more
    conservative rule exists.
    """
    for text in texts:
        if not text:
            continue
        tokens = set(normalize_test_name(text).split())
        if tokens & set(FASTING_TOKENS):
            return TIMING_FASTING
        if tokens & set(POST_PRANDIAL_TOKENS):
            return TIMING_POST_PRANDIAL
        if tokens & set(RANDOM_TOKENS):
            return TIMING_RANDOM
    return TIMING_UNSPECIFIED


# --------------------------------------------------------------------------
# Thresholds that depend on sex or age
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextualThreshold:
    """A threshold whose value depends on recorded sex and age.

    `unknown` is used when sex was not established. It is ALWAYS the value that
    avoids over-calling, and `unknown_note` is carried into the decision's
    evidence so the reader is told the threshold was chosen conservatively.

    `paediatric` is an ordered tuple of `(max_age_inclusive, value)` applied
    before sex, because the paediatric cut-offs below are not sex-specific.
    """

    male: float
    female: float
    unknown: float
    unknown_note: str
    paediatric: Tuple[Tuple[int, float], ...] = ()
    basis: str = ""


def resolve_threshold(
    threshold: Any, sex: Optional[str], age: Optional[float]
) -> Tuple[Optional[float], Optional[str]]:
    """`(value, note)` for a plain float or a `ContextualThreshold`."""
    if threshold is None:
        return None, None
    if not isinstance(threshold, ContextualThreshold):
        return float(threshold), None
    if age is not None:
        for max_age, value in threshold.paediatric:
            if age <= max_age:
                return (
                    float(value),
                    f"paediatric threshold for age {int(age)} years applied",
                )
    if sex == "male":
        return float(threshold.male), None
    if sex == "female":
        return float(threshold.female), None
    return float(threshold.unknown), threshold.unknown_note


# --------------------------------------------------------------------------
# Bands and rules
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Band:
    """One outcome of a rule.

    `label` is USER-FACING (it reaches `EvidenceItem.note`), so it is scanned by
    the recommendation catalogue's safety scanner at import time. `basis` is
    reviewer-facing and cites the guideline.
    """

    comparator: Optional[str]
    threshold: Optional[Any]
    status: DecisionStatus
    risk: Optional[RiskLevel]
    label: str
    recommendations: Tuple[str, ...]
    basis: str
    #: Restricts the band to the case where sex was / was not established.
    only_when_sex_unknown: bool = False


@dataclass(frozen=True)
class ThresholdRule:
    """A single-feature, banded rule."""

    id: str
    version: str
    condition: str
    feature: str
    bands: Tuple[Band, ...]
    basis: str
    #: Adult reference intervals are invalid below this age -> INSUFFICIENT_DATA.
    min_age_years: Optional[int] = None
    #: Fire only when the sample timing is one of these. Empty = any timing.
    only_timing: Tuple[str, ...] = ()
    #: Extra features read to resolve thresholds. Recorded in evidence.
    context_features: Tuple[str, ...] = ()
    #: Recommendations added to every decision this rule produces.
    always_recommend: Tuple[str, ...] = ()
    #: When set, the bands compare a value CALCULATED from `feature` (and the
    #: context features), not `feature` itself. One of `DERIVED_VALUES`.
    #: `feature` stays the measured input, so a report without it still means
    #: "no input, no decision".
    derived: Optional[str] = None


#: Values a rule may calculate rather than read, with the unit they are
#: compared in and the context features the calculation needs.
DERIVED_VALUES: Dict[str, Dict[str, Any]] = {
    EGFR_FEATURE: {
        "input": "creatinine",
        "unit": EGFR_UNIT,
        "requires": ("age", "gender"),
        "min_age_years": EGFR_MIN_AGE_YEARS,
    },
}


# --------------------------------------------------------------------------
# The contextual thresholds
# --------------------------------------------------------------------------

# WHO, "Haemoglobin concentrations for the diagnosis of anaemia and assessment
# of severity" (VMNIS, WHO/NMH/NHD/MNM/11.1, 2011), Table 1, sea level, g/dL:
#     children 6-59 months        11.0
#     children 5-11 years         11.5
#     children 12-14 years        12.0
#     non-pregnant women 15+      12.0
#     men 15+                     13.0
# Whole-year age buckets are used because Module 2 stores age in whole years,
# so the 6-59 month band becomes ages 0-4. Infants under 6 months are NOT
# covered by the WHO table at all; this is recorded as a known gap rather than
# extrapolated.
ANEMIA_CUTOFF = ContextualThreshold(
    male=13.0,
    female=12.0,
    unknown=12.0,
    unknown_note=(
        "sex was not recorded, so the lower (WHO non-pregnant female) cut-off "
        "of 12.0 g/dL was used to avoid over-calling"
    ),
    paediatric=((4, 11.0), (11, 11.5), (14, 12.0)),
    basis="WHO VMNIS 2011 Table 1 anaemia cut-offs at sea level.",
)

# WHO VMNIS 2011 Table 1 severity boundaries (g/dL):
#     moderate anaemia below   11.0 (adults and children 5+), 10.0 (under 5)
#     severe anaemia below      8.0 (adults and children 5+),  7.0 (under 5)
ANEMIA_MODERATE_BELOW = ContextualThreshold(
    male=11.0,
    female=11.0,
    unknown=11.0,
    unknown_note="",
    paediatric=((4, 10.0),),
    basis="WHO VMNIS 2011 Table 1 moderate-anaemia boundary.",
)
ANEMIA_SEVERE_BELOW = ContextualThreshold(
    male=8.0,
    female=8.0,
    unknown=8.0,
    unknown_note="",
    paediatric=((4, 7.0),),
    basis="WHO VMNIS 2011 Table 1 severe-anaemia boundary.",
)

# WHO 2016 revision of the classification of myeloid neoplasms, polycythaemia
# vera major criterion 1: haemoglobin > 16.5 g/dL in men, > 16.0 g/dL in women.
# Used here only as the "raised haemoglobin, worth a look" boundary -- this
# engine does not and cannot classify a myeloproliferative disorder.
ELEVATED_HB_CUTOFF = ContextualThreshold(
    male=16.5,
    female=16.0,
    unknown=16.5,
    unknown_note=(
        "sex was not recorded, so the higher (male) cut-off of 16.5 g/dL was "
        "used to avoid over-calling"
    ),
    basis="WHO 2016 polycythaemia vera haemoglobin criterion.",
)

# Adult serum creatinine upper reference limits, mg/dL. Typical isotope-dilution
# mass-spectrometry-traceable enzymatic assay reference intervals (e.g. Mayo
# Clinic Laboratories): men 0.74-1.35, women 0.59-1.04. Reference intervals are
# assay-specific, which is why the report's OWN printed reference range is
# carried into the evidence alongside this configured threshold.
CREATININE_UPPER = ContextualThreshold(
    male=1.35,
    female=1.04,
    unknown=1.35,
    unknown_note=(
        "sex was not recorded, so the higher (male) upper reference limit of "
        "1.35 mg/dL was used to avoid over-calling"
    ),
    basis="Adult sex-specific serum creatinine upper reference limits.",
)

# NCEP ATP III major cardiovascular risk factor: age >= 45 in men, >= 55 in
# women.
CVD_AGE_THRESHOLD = ContextualThreshold(
    male=45.0,
    female=55.0,
    unknown=55.0,
    unknown_note=(
        "sex was not recorded, so the higher (female) age threshold of 55 years "
        "was used to avoid over-counting risk factors"
    ),
    basis="NCEP ATP III major risk factor: age >= 45 (men) / >= 55 (women).",
)


# --------------------------------------------------------------------------
# Shared band fragments
# --------------------------------------------------------------------------

_NOT_FLAGGED = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)
_FLAGGED = (DISCUSS_WITH_CLINICIAN, CONFIRM_WITH_REPEAT_TESTING)
_FLAGGED_HIGH = (
    SEEK_PROMPT_MEDICAL_ADVICE,
    DISCUSS_WITH_CLINICIAN,
    CONFIRM_WITH_REPEAT_TESTING,
)


def _normal_band(label: str, basis: str) -> Band:
    return Band(
        comparator=None,
        threshold=None,
        status=DecisionStatus.NOT_INDICATED,
        risk=RiskLevel.LOW,
        label=label,
        recommendations=_NOT_FLAGGED,
        basis=basis,
    )


# --------------------------------------------------------------------------
# THE RULE TABLE
# --------------------------------------------------------------------------

THRESHOLD_RULES: Tuple[ThresholdRule, ...] = (
    # ==================================================== DIABETES: HbA1c ==
    ThresholdRule(
        id="RULE_DIABETES_HBA1C",
        version="1.0.0",
        condition=C.DIABETES,
        feature="hba1c",
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2 (Diagnosis and Classification): HbA1c >= 6.5 % is a "
            "diabetes-range result and 5.7-6.4 % is the prediabetes range, both "
            "NGSP-aligned. The ADA requires a confirmatory second test before "
            "anything is concluded, which is why CONFIRM_WITH_REPEAT_TESTING is "
            "attached to every flagged band."
        ),
        always_recommend=(GENERAL_BALANCED_DIET, GENERAL_PHYSICAL_ACTIVITY),
        bands=(
            Band(
                comparator=">=",
                threshold=6.5,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above the ADA diabetes-range HbA1c threshold of 6.5 %",
                recommendations=_FLAGGED_HIGH + (GENERAL_LIMIT_ADDED_SUGAR,),
                basis="ADA: HbA1c >= 6.5 % (NGSP).",
            ),
            Band(
                comparator=">=",
                threshold=5.7,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.MEDIUM,
                label="inside the ADA prediabetes HbA1c range of 5.7-6.4 %",
                recommendations=_FLAGGED + (GENERAL_LIMIT_ADDED_SUGAR,),
                basis="ADA: HbA1c 5.7-6.4 % (NGSP).",
            ),
            _normal_band(
                "below the ADA prediabetes HbA1c threshold of 5.7 %",
                "ADA: HbA1c < 5.7 % (NGSP).",
            ),
        ),
    ),
    # ====================================== DIABETES: FASTING glucose only ==
    ThresholdRule(
        id="RULE_DIABETES_GLUCOSE_FASTING",
        version="1.0.0",
        condition=C.DIABETES,
        feature="blood_glucose",
        only_timing=(TIMING_FASTING,),
        basis=(
            "ADA Standards of Care, section 2: fasting plasma glucose >= 126 "
            "mg/dL is a diabetes-range result; 100-125 mg/dL is impaired fasting "
            "glucose. THESE CUT-OFFS ARE ONLY VALID FOR A FASTING SAMPLE, so "
            "this rule fires only when the printed test name established that "
            "the sample was fasting."
        ),
        always_recommend=(GENERAL_BALANCED_DIET, GENERAL_PHYSICAL_ACTIVITY),
        bands=(
            Band(
                comparator=">=",
                threshold=126.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label=(
                    "at or above the ADA diabetes-range fasting plasma glucose "
                    "threshold of 126 mg/dL"
                ),
                recommendations=_FLAGGED_HIGH + (GENERAL_LIMIT_ADDED_SUGAR,),
                basis="ADA: fasting plasma glucose >= 126 mg/dL.",
            ),
            Band(
                comparator=">=",
                threshold=100.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.MEDIUM,
                label=(
                    "inside the ADA impaired-fasting-glucose range of 100-125 mg/dL"
                ),
                recommendations=_FLAGGED + (GENERAL_LIMIT_ADDED_SUGAR,),
                basis="ADA: fasting plasma glucose 100-125 mg/dL.",
            ),
            _normal_band(
                "below the ADA impaired-fasting-glucose threshold of 100 mg/dL",
                "ADA: fasting plasma glucose < 100 mg/dL.",
            ),
        ),
    ),
    # ============================ DIABETES: glucose of unestablished timing ==
    ThresholdRule(
        id="RULE_DIABETES_GLUCOSE_UNSPECIFIED",
        version="1.0.0",
        condition=C.DIABETES,
        feature="blood_glucose",
        only_timing=(TIMING_UNSPECIFIED, TIMING_RANDOM, TIMING_POST_PRANDIAL),
        basis=(
            "Applied when the sample was NOT established as fasting. The fasting "
            "cut-offs would over-call a post-meal sample, so the conservative "
            "post-load thresholds are used instead: ADA random plasma glucose "
            ">= 200 mg/dL is a diabetes-range result, and >= 140 mg/dL is the "
            "2-hour post-load impaired-glucose-tolerance boundary. Using the "
            "post-load boundary for a sample of unknown timing is a deliberate "
            "judgement in favour of not over-calling; the resulting uncertainty "
            "is stated to the reader via DISCUSS_SAMPLE_TIMING."
        ),
        always_recommend=(
            DISCUSS_SAMPLE_TIMING,
            GENERAL_BALANCED_DIET,
            GENERAL_PHYSICAL_ACTIVITY,
        ),
        bands=(
            Band(
                comparator=">=",
                threshold=200.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                # THE TIMING IS PART OF THE CLASSIFICATION, NOT A FOOTNOTE.
                #
                # This rule's `only_timing` accepts unspecified, random and
                # post-prandial ONLY, so every band below is used exclusively
                # on a sample that was NOT established as fasting. Saying so in
                # the label is therefore always true, and it puts the
                # qualification wherever the classification goes -- the patient
                # page, the clinician page and the written narrative alike.
                #
                # WHY IT HAD TO GO HERE. The `basis` above says the uncertainty
                # "is stated to the reader via DISCUSS_SAMPLE_TIMING", and on
                # the PATIENT page that is true -- the recommendation renders.
                # The CLINICIAN page carries no recommendations at all, so it
                # showed "at or above the 2-hour post-load boundary" against a
                # RANDOM sample with nothing saying the timing was never
                # established. A clinician reading that would reasonably take
                # it for a post-load draw. Found 2026-09-18.
                label=(
                    "at or above the ADA diabetes-range random plasma glucose "
                    "threshold of 200 mg/dL, on a sample not established as "
                    "fasting"
                ),
                recommendations=_FLAGGED_HIGH + (GENERAL_LIMIT_ADDED_SUGAR,),
                basis="ADA: random plasma glucose >= 200 mg/dL.",
            ),
            Band(
                comparator=">=",
                threshold=140.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.MEDIUM,
                # THE ONE THAT MATTERS MOST. "at or above the 2-hour post-load
                # boundary" beside a RANDOM glucose reads as a post-load draw
                # unless the label says otherwise. See the band above.
                label=(
                    "at or above the 2-hour post-load impaired-glucose-tolerance "
                    "boundary of 140 mg/dL, applied because the sample was not "
                    "established as fasting"
                ),
                recommendations=_FLAGGED + (GENERAL_LIMIT_ADDED_SUGAR,),
                basis="ADA: 2-hour post-load plasma glucose 140-199 mg/dL.",
            ),
            _normal_band(
                "below the 2-hour post-load boundary of 140 mg/dL, applied "
                "because the sample was not established as fasting",
                "ADA: 2-hour post-load plasma glucose < 140 mg/dL.",
            ),
        ),
    ),
    # ====================================================== HYPOGLYCAEMIA ==
    ThresholdRule(
        id="RULE_HYPOGLYCEMIA_GLUCOSE",
        version="1.0.0",
        condition=C.HYPOGLYCEMIA,
        feature="blood_glucose",
        basis=(
            "ADA/EASD hypoglycaemia classification: level 1 (glucose alert) is "
            "< 70 mg/dL, level 2 (clinically significant) is < 54 mg/dL. These "
            "apply whatever the sample timing, so no timing gate is used."
        ),
        bands=(
            Band(
                comparator="<",
                threshold=54.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label=(
                    "below the ADA level-2 (clinically significant) hypoglycaemia "
                    "threshold of 54 mg/dL"
                ),
                recommendations=_FLAGGED_HIGH,
                basis="ADA/EASD level 2 hypoglycaemia: < 54 mg/dL.",
            ),
            Band(
                comparator="<",
                threshold=70.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.MEDIUM,
                label="below the ADA level-1 glucose alert value of 70 mg/dL",
                recommendations=_FLAGGED,
                basis="ADA/EASD level 1 hypoglycaemia: < 70 mg/dL.",
            ),
            _normal_band(
                "at or above the ADA level-1 glucose alert value of 70 mg/dL",
                "ADA/EASD: >= 70 mg/dL is not a hypoglycaemia alert value.",
            ),
        ),
    ),
    # ============================================================ ANAEMIA ==
    ThresholdRule(
        id="RULE_ANEMIA_HEMOGLOBIN",
        version="1.0.0",
        condition=C.ANEMIA,
        feature="hemoglobin",
        context_features=("gender", "age"),
        basis=(
            "WHO VMNIS 2011 anaemia cut-offs, which ARE sex- and age-specific "
            "and are implemented as such rather than flattened to one number. "
            "Pregnancy has its own WHO cut-off (11.0 g/dL); VaidyaAI does not "
            "record pregnancy, so the non-pregnant female cut-off is used and "
            "this limitation is documented rather than hidden. When age is "
            "absent the adult cut-offs are applied, which could under-call a "
            "child -- stated in the evidence note."
        ),
        always_recommend=(GENERAL_IRON_RICH_FOODS,),
        bands=(
            Band(
                comparator="<",
                threshold=ANEMIA_SEVERE_BELOW,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="inside the WHO severe-anaemia band",
                recommendations=_FLAGGED_HIGH,
                basis="WHO VMNIS 2011: severe anaemia.",
            ),
            Band(
                comparator="<",
                threshold=ANEMIA_MODERATE_BELOW,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="inside the WHO moderate-anaemia band",
                recommendations=_FLAGGED,
                basis="WHO VMNIS 2011: moderate anaemia.",
            ),
            Band(
                comparator="<",
                threshold=ANEMIA_CUTOFF,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.LOW,
                label="inside the WHO mild-anaemia band",
                recommendations=_FLAGGED,
                basis="WHO VMNIS 2011: mild anaemia.",
            ),
            Band(
                comparator="<",
                threshold=13.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label=(
                    "between the WHO female (12.0 g/dL) and male (13.0 g/dL) "
                    "anaemia cut-offs, and sex was not recorded"
                ),
                recommendations=_FLAGGED,
                basis=(
                    "WHO VMNIS 2011. Sex decides which cut-off applies; with sex "
                    "unrecorded this zone is reported as borderline rather than "
                    "resolved by guessing."
                ),
                only_when_sex_unknown=True,
            ),
            _normal_band(
                "at or above the applicable WHO anaemia cut-off",
                "WHO VMNIS 2011: at or above the cut-off for the recorded sex "
                "and age.",
            ),
        ),
    ),
    # ================================================ ELEVATED HAEMOGLOBIN ==
    ThresholdRule(
        id="RULE_ELEVATED_HEMOGLOBIN",
        version="1.0.0",
        condition=C.ELEVATED_HEMOGLOBIN,
        feature="hemoglobin",
        min_age_years=18,
        context_features=("gender", "age"),
        basis=(
            "WHO 2016 polycythaemia vera haemoglobin criterion (> 16.5 g/dL men, "
            "> 16.0 g/dL women) used as a 'raised haemoglobin' boundary only. "
            "20 g/dL matches the extreme_high already configured in Module 6's "
            "validation table. Paediatric haemoglobin references differ, so this "
            "rule is adult-only."
        ),
        bands=(
            Band(
                comparator=">=",
                threshold=20.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above 20.0 g/dL",
                recommendations=_FLAGGED_HIGH,
                basis="Markedly raised haemoglobin; matches Module 6's "
                "clinically-extreme high threshold of 20 g/dL.",
            ),
            Band(
                comparator=">=",
                threshold=ELEVATED_HB_CUTOFF,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="at or above the sex-specific raised-haemoglobin boundary",
                recommendations=_FLAGGED,
                basis="WHO 2016 polycythaemia vera haemoglobin criterion.",
            ),
            Band(
                comparator=">=",
                threshold=16.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label=(
                    "between the female (16.0 g/dL) and male (16.5 g/dL) "
                    "raised-haemoglobin boundaries, and sex was not recorded"
                ),
                recommendations=_FLAGGED,
                basis="WHO 2016 criterion; sex unrecorded, so reported as "
                "borderline rather than resolved by guessing.",
                only_when_sex_unknown=True,
            ),
            _normal_band(
                "below the applicable raised-haemoglobin boundary",
                "WHO 2016 criterion not met.",
            ),
        ),
    ),
    # ============================================== VITAMIN D DEFICIENCY ==
    ThresholdRule(
        id="RULE_VITAMIN_D_DEFICIENCY",
        version="1.0.0",
        condition=C.VITAMIN_D_DEFICIENCY,
        feature="vitamin_d",
        basis=(
            "Endocrine Society Clinical Practice Guideline, 'Evaluation, "
            "Treatment, and Prevention of Vitamin D Deficiency' (Holick et al., "
            "J Clin Endocrinol Metab 2011): 25(OH)D deficiency < 20 ng/mL, "
            "insufficiency 21-29 ng/mL, sufficiency >= 30 ng/mL. Severe "
            "deficiency < 10 ng/mL matches Module 6's extreme_low. Note the "
            "Institute of Medicine uses 20 ng/mL as sufficient for bone health; "
            "the Endocrine Society bands were chosen because Module 6 already "
            "cites them, so the two modules cannot drift apart."
        ),
        always_recommend=(GENERAL_VITAMIN_D_SOURCES,),
        bands=(
            Band(
                comparator="<",
                threshold=10.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="below the severe vitamin D deficiency threshold of 10 ng/mL",
                recommendations=_FLAGGED_HIGH,
                basis="Endocrine Society 2011: severe deficiency < 10 ng/mL.",
            ),
            Band(
                comparator="<",
                threshold=20.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="below the vitamin D deficiency threshold of 20 ng/mL",
                recommendations=_FLAGGED,
                basis="Endocrine Society 2011: deficiency < 20 ng/mL.",
            ),
            Band(
                comparator="<",
                threshold=30.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label="inside the vitamin D insufficiency band of 20-29 ng/mL",
                recommendations=_FLAGGED,
                basis="Endocrine Society 2011: insufficiency 21-29 ng/mL.",
            ),
            _normal_band(
                "at or above the vitamin D sufficiency threshold of 30 ng/mL",
                "Endocrine Society 2011: sufficiency >= 30 ng/mL.",
            ),
        ),
    ),
    # ================================================= ELEVATED VITAMIN D ==
    ThresholdRule(
        id="RULE_ELEVATED_VITAMIN_D",
        version="1.0.0",
        condition=C.ELEVATED_VITAMIN_D,
        feature="vitamin_d",
        basis=(
            "Endocrine Society 2011: 25(OH)D above 100 ng/mL is the conventional "
            "potential-toxicity boundary, and matches Module 6's extreme_high. "
            "A value below it produces no decision for this condition, because "
            "'not high' is already covered by the deficiency rule's own bands "
            "and a second reassuring card would be noise."
        ),
        bands=(
            Band(
                comparator=">=",
                threshold=100.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="at or above the potential-toxicity boundary of 100 ng/mL",
                recommendations=_FLAGGED,
                basis="Endocrine Society 2011: potential toxicity > 100 ng/mL.",
            ),
            _normal_band(
                "below the potential-toxicity boundary of 100 ng/mL",
                "Endocrine Society 2011.",
            ),
        ),
    ),
    # ============================================ VITAMIN B12 DEFICIENCY ==
    ThresholdRule(
        id="RULE_VITAMIN_B12_DEFICIENCY",
        version="1.0.0",
        condition=C.VITAMIN_B12_DEFICIENCY,
        feature="vitamin_b12",
        basis=(
            "Widely used serum B12 bands (BCSH 'Guidelines for the diagnosis and "
            "treatment of cobalamin and folate disorders', 2014, and common "
            "laboratory practice): below ~200 pg/mL is deficient, 200-300 pg/mL "
            "is indeterminate, above 300 pg/mL is unlikely to be deficient. "
            "150 pg/mL matches Module 6's extreme_low. Serum B12 is an imperfect "
            "marker -- methylmalonic acid and holotranscobalamin are the "
            "confirmatory tests -- which is why every flagged band carries "
            "CONFIRM_WITH_REPEAT_TESTING."
        ),
        always_recommend=(GENERAL_VITAMIN_B12_SOURCES,),
        bands=(
            Band(
                comparator="<",
                threshold=150.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="below 150 pg/mL",
                recommendations=_FLAGGED_HIGH,
                basis="Frank B12 deficiency band; matches Module 6's extreme_low.",
            ),
            Band(
                comparator="<",
                threshold=200.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="below the serum B12 deficiency boundary of 200 pg/mL",
                recommendations=_FLAGGED,
                basis="BCSH 2014 / common laboratory practice: < 200 pg/mL.",
            ),
            Band(
                comparator="<",
                threshold=300.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label="inside the indeterminate serum B12 band of 200-299 pg/mL",
                recommendations=_FLAGGED,
                basis="BCSH 2014 / common laboratory practice: 200-300 pg/mL.",
            ),
            _normal_band(
                "at or above 300 pg/mL",
                "BCSH 2014 / common laboratory practice: > 300 pg/mL.",
            ),
        ),
    ),
    # ====================================================== KIDNEY: creat ==
    ThresholdRule(
        id="RULE_KIDNEY_CREATININE",
        version="1.0.0",
        condition=C.KIDNEY_DISEASE,
        feature="creatinine",
        min_age_years=18,
        context_features=("gender", "age"),
        basis=(
            "IMPORTANT SCOPE NOTE: KDIGO 2012/2024 defines and stages chronic "
            "kidney disease by eGFR and albuminuria, NOT by raw creatinine. "
            "eGFR is calculated separately by RULE_KIDNEY_EGFR (CKD-EPI 2021); "
            "staging requires a second sample at least 90 days apart plus a "
            "urine albumin-to-creatinine ratio -- neither of which this "
            "threshold engine has. So this rule reports a RAISED CREATININE against sex-specific "
            "adult reference limits and says it may warrant discussion. It does "
            "not stage, and must not be read as staging. 5.0 mg/dL matches "
            "Module 6's extreme_high. Adult references only, so under-18 yields "
            "INSUFFICIENT_DATA rather than a wrong verdict."
        ),
        always_recommend=(GENERAL_HYDRATION,),
        bands=(
            Band(
                comparator=">=",
                threshold=5.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above 5.0 mg/dL",
                recommendations=_FLAGGED_HIGH,
                basis="Severe renal impairment boundary; matches Module 6's "
                "clinically-extreme high threshold.",
            ),
            Band(
                comparator=">=",
                threshold=2.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above 2.0 mg/dL",
                recommendations=_FLAGGED_HIGH,
                basis="Substantially above every adult reference interval, in "
                "either sex, by a wide margin.",
            ),
            Band(
                comparator=">",
                threshold=CREATININE_UPPER,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="above the sex-specific adult upper reference limit",
                recommendations=_FLAGGED,
                basis="Adult sex-specific serum creatinine reference intervals. "
                "'>' not '>=' because a value exactly AT the upper reference "
                "limit is still inside the reference interval.",
            ),
            Band(
                comparator=">",
                threshold=1.04,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label=(
                    "above the female (1.04 mg/dL) but not the male (1.35 mg/dL) "
                    "adult upper reference limit, and sex was not recorded"
                ),
                recommendations=_FLAGGED,
                basis="Sex decides which reference interval applies; with sex "
                "unrecorded this zone is reported as borderline.",
                only_when_sex_unknown=True,
            ),
            _normal_band(
                "at or below the applicable adult upper reference limit",
                "Inside the adult reference interval for the recorded sex.",
            ),
        ),
    ),
    # ======================================================= KIDNEY: eGFR ==
    #
    # THE VALUE KDIGO ACTUALLY USES (owner, 2026-10-04). Calculated from the
    # creatinine above with the CKD-EPI 2021 equation (`app/data/egfr.py`),
    # only for an adult whose sex is recorded as male or female -- otherwise
    # this rule does not fire and the creatinine rule speaks alone. A low eGFR
    # can flag the topic even when creatinine sits inside its reference
    # interval (owner's decision): a 75-year-old woman with creatinine 1.0
    # mg/dL (inside 0.59-1.04) has an eGFR of 59, and that is the reading a
    # clinician would make.
    #
    # Compared on the WHOLE NUMBER the reader is shown, so "59.6" is reported
    # as 60 and not flagged as below 60.
    ThresholdRule(
        id="RULE_KIDNEY_EGFR",
        version="1.0.0",
        condition=C.KIDNEY_DISEASE,
        feature="creatinine",
        derived=EGFR_FEATURE,
        min_age_years=EGFR_MIN_AGE_YEARS,
        context_features=("gender", "age"),
        basis=(
            "KDIGO 2012/2024 GFR categories (mL/min/1.73 m2): G1 >= 90, G2 "
            "60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 < 15. eGFR from the "
            "CKD-EPI 2021 creatinine equation (Inker et al., NEJM 2021). A "
            "single estimate does not stage chronic kidney disease: staging "
            "needs the finding to persist for at least three months and a "
            "urine albumin-to-creatinine ratio, neither of which this engine "
            "has. G2 without markers of kidney damage does not meet the CKD "
            "definition, so 60 and above is not flagged."
        ),
        always_recommend=(GENERAL_HYDRATION,),
        bands=(
            Band(
                comparator="<",
                threshold=15.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="estimated filtration below 15 mL/min/1.73 m²",
                recommendations=_FLAGGED_HIGH,
                basis="KDIGO GFR category G5 (< 15).",
            ),
            Band(
                comparator="<",
                threshold=30.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="estimated filtration below 30 mL/min/1.73 m²",
                recommendations=_FLAGGED_HIGH,
                basis="KDIGO GFR category G4 (15-29).",
            ),
            Band(
                comparator="<",
                threshold=45.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="estimated filtration below 45 mL/min/1.73 m²",
                recommendations=_FLAGGED,
                basis="KDIGO GFR category G3b (30-44).",
            ),
            Band(
                comparator="<",
                threshold=60.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="estimated filtration below 60 mL/min/1.73 m²",
                recommendations=_FLAGGED,
                basis="KDIGO GFR category G3a (45-59): below the eGFR at "
                "which guidelines describe kidney function as decreased.",
            ),
            _normal_band(
                "estimated filtration at or above 60 mL/min/1.73 m²",
                "KDIGO GFR categories G1-G2 (60 and above).",
            ),
        ),
    ),
    # ==================================================== HIGH CHOLESTEROL ==
    ThresholdRule(
        id="RULE_HIGH_CHOLESTEROL",
        version="1.0.0",
        condition=C.HIGH_CHOLESTEROL,
        feature="cholesterol",
        min_age_years=18,
        basis=(
            "NCEP ATP III total cholesterol classification: desirable < 200 "
            "mg/dL, borderline high 200-239, high >= 240. The 400 mg/dL band "
            "matches Module 6's extreme_high and is the level at which a severe "
            "primary lipid disorder is usually considered. Total cholesterol "
            "alone is a weak marker -- LDL, HDL and non-HDL matter more -- and "
            "VaidyaAI's feature set has only the total, which is stated here so "
            "no reviewer assumes otherwise. Adult classification only."
        ),
        always_recommend=(GENERAL_DIETARY_FAT_QUALITY, GENERAL_PHYSICAL_ACTIVITY),
        bands=(
            Band(
                comparator=">=",
                threshold=400.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above 400 mg/dL",
                recommendations=_FLAGGED_HIGH,
                basis="Matches Module 6's clinically-extreme high threshold.",
            ),
            Band(
                comparator=">=",
                threshold=240.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="at or above the ATP III high total cholesterol threshold "
                "of 240 mg/dL",
                recommendations=_FLAGGED,
                basis="NCEP ATP III: total cholesterol >= 240 mg/dL is high.",
            ),
            Band(
                comparator=">=",
                threshold=200.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label="inside the ATP III borderline-high band of 200-239 mg/dL",
                recommendations=_FLAGGED,
                basis="NCEP ATP III: total cholesterol 200-239 mg/dL.",
            ),
            _normal_band(
                "below the ATP III desirable total cholesterol threshold of "
                "200 mg/dL",
                "NCEP ATP III: total cholesterol < 200 mg/dL is desirable.",
            ),
        ),
    ),
    # ================================================== HIGH TRIGLYCERIDES ==
    ThresholdRule(
        id="RULE_HIGH_TRIGLYCERIDES",
        version="1.0.0",
        condition=C.HIGH_TRIGLYCERIDES,
        feature="triglycerides",
        min_age_years=18,
        basis=(
            "NCEP ATP III triglyceride classification: normal < 150 mg/dL, "
            "borderline high 150-199, high 200-499, very high >= 500. The 1000 "
            "mg/dL band is the acute-pancreatitis risk level (AHA scientific "
            "statement on hypertriglyceridaemia) and matches Module 6's "
            "extreme_high. Triglycerides are strongly affected by how recently "
            "the person ate, which is why repeat testing is always attached. "
            "Adult classification only."
        ),
        always_recommend=(GENERAL_DIETARY_FAT_QUALITY, GENERAL_LIMIT_ADDED_SUGAR),
        bands=(
            Band(
                comparator=">=",
                threshold=1000.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above 1000 mg/dL",
                recommendations=_FLAGGED_HIGH,
                basis="AHA: acute pancreatitis risk level; matches Module 6's "
                "clinically-extreme high threshold.",
            ),
            Band(
                comparator=">=",
                threshold=500.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above the ATP III very-high triglyceride threshold "
                "of 500 mg/dL",
                recommendations=_FLAGGED_HIGH,
                basis="NCEP ATP III: triglycerides >= 500 mg/dL is very high.",
            ),
            Band(
                comparator=">=",
                threshold=200.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="at or above the ATP III high triglyceride threshold of "
                "200 mg/dL",
                recommendations=_FLAGGED,
                basis="NCEP ATP III: triglycerides 200-499 mg/dL is high.",
            ),
            Band(
                comparator=">=",
                threshold=150.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label="inside the ATP III borderline-high band of 150-199 mg/dL",
                recommendations=_FLAGGED,
                basis="NCEP ATP III: triglycerides 150-199 mg/dL.",
            ),
            _normal_band(
                "below the ATP III normal triglyceride threshold of 150 mg/dL",
                "NCEP ATP III: triglycerides < 150 mg/dL is normal.",
            ),
        ),
    ),
    # ============================================================ OBESITY ==
    ThresholdRule(
        id="RULE_OBESITY_BMI",
        version="1.0.0",
        condition=C.OBESITY,
        feature="bmi",
        min_age_years=18,
        basis=(
            "WHO BMI classification for adults: overweight 25.0-29.9, obese "
            "class I 30.0-34.9, class II 35.0-39.9, class III >= 40.0. BMI in "
            "children and adolescents is assessed against age- and sex-specific "
            "percentiles, NOT these fixed cut-offs, so this rule is adult-only. "
            "The WHO cut-offs are also known to perform differently across "
            "populations (lower action points are used for South Asian "
            "populations); the WHO values are used unchanged and this is "
            "recorded as a known limitation rather than silently adjusted."
        ),
        always_recommend=(
            GENERAL_WEIGHT_DISCUSSION,
            GENERAL_PHYSICAL_ACTIVITY,
            GENERAL_BALANCED_DIET,
        ),
        bands=(
            Band(
                comparator=">=",
                threshold=40.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="at or above the WHO obesity class III threshold of 40.0",
                recommendations=_FLAGGED,
                basis="WHO: BMI >= 40.0 kg/m2 is obesity class III.",
            ),
            Band(
                comparator=">=",
                threshold=30.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="at or above the WHO obesity threshold of 30.0",
                recommendations=_FLAGGED,
                basis="WHO: BMI >= 30.0 kg/m2 is obesity.",
            ),
            Band(
                comparator=">=",
                threshold=25.0,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label="inside the WHO overweight band of 25.0-29.9",
                recommendations=_FLAGGED,
                basis="WHO: BMI 25.0-29.9 kg/m2 is overweight.",
            ),
            _normal_band(
                "below the WHO overweight threshold of 25.0",
                "WHO: BMI < 25.0 kg/m2.",
            ),
        ),
    ),
    # ========================================================= UNDERWEIGHT ==
    ThresholdRule(
        id="RULE_UNDERWEIGHT_BMI",
        version="1.0.0",
        condition=C.UNDERWEIGHT,
        feature="bmi",
        min_age_years=18,
        basis=(
            "WHO BMI classification for adults: severe thinness < 16.0, moderate "
            "thinness 16.0-16.9, mild thinness 17.0-18.4, normal >= 18.5. Note "
            "Module 6's validation table uses 15.0 as its clinically-extreme low "
            "for BMI, which is a data-plausibility band and not the same thing "
            "as the WHO severe-thinness class; both are correct for their own "
            "purpose. Adult-only, for the same reason as the obesity rule."
        ),
        always_recommend=(GENERAL_WEIGHT_DISCUSSION, GENERAL_BALANCED_DIET),
        bands=(
            Band(
                comparator="<",
                threshold=16.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.HIGH,
                label="below the WHO severe thinness threshold of 16.0",
                recommendations=_FLAGGED_HIGH,
                basis="WHO: BMI < 16.0 kg/m2 is severe thinness.",
            ),
            Band(
                comparator="<",
                threshold=17.0,
                status=DecisionStatus.INDICATED,
                risk=RiskLevel.MEDIUM,
                label="inside the WHO moderate thinness band of 16.0-16.9",
                recommendations=_FLAGGED,
                basis="WHO: BMI 16.0-16.9 kg/m2 is moderate thinness.",
            ),
            Band(
                comparator="<",
                threshold=18.5,
                status=DecisionStatus.BORDERLINE,
                risk=RiskLevel.LOW,
                label="inside the WHO mild thinness band of 17.0-18.4",
                recommendations=_FLAGGED,
                basis="WHO: BMI 17.0-18.4 kg/m2 is mild thinness.",
            ),
            _normal_band(
                "at or above the WHO normal-range threshold of 18.5",
                "WHO: BMI >= 18.5 kg/m2.",
            ),
        ),
    ),
)


# --------------------------------------------------------------------------
# The composite cardiovascular risk-factor rule
# --------------------------------------------------------------------------

FACTOR_NUMERIC = "numeric"
FACTOR_CATEGORY = "category"
FACTOR_BOOLEAN_TRUE = "boolean_true"


@dataclass(frozen=True)
class RiskFactorDefinition:
    """One countable cardiovascular risk factor.

    A factor is counted ONLY when its feature is present in the usable set AND
    the condition below holds. A missing feature contributes nothing and is
    reported as "not established" -- never as "absent risk factor".
    """

    id: str
    label: str
    kind: str
    feature: str
    threshold: Optional[Any] = None
    comparator: Optional[str] = None
    categories: Tuple[str, ...] = ()
    recommendations: Tuple[str, ...] = ()
    basis: str = ""


@dataclass(frozen=True)
class CountBand:
    """An outcome keyed on how many risk factors were counted."""

    minimum_count: int
    status: DecisionStatus
    risk: Optional[RiskLevel]
    label: str
    recommendations: Tuple[str, ...]
    basis: str
    #: When set, the band applies only if this factor id was counted.
    requires_factor: Optional[str] = None


@dataclass(frozen=True)
class CompositeRule:
    id: str
    version: str
    condition: str
    factors: Tuple[RiskFactorDefinition, ...]
    bands: Tuple[CountBand, ...]
    #: Fewer evaluable inputs than this -> INSUFFICIENT_DATA, never a verdict.
    min_evaluable_inputs: int
    min_age_years: Optional[int]
    basis: str
    always_recommend: Tuple[str, ...] = ()


HEART_DISEASE_RULE = CompositeRule(
    id="RULE_HEART_DISEASE_RISK_FACTORS",
    version="1.0.0",
    condition=C.HEART_DISEASE,
    min_evaluable_inputs=3,
    min_age_years=18,
    basis=(
        "A TALLY OF MAJOR MODIFIABLE CARDIOVASCULAR RISK FACTORS as listed by "
        "NCEP ATP III and the ACC/AHA primary-prevention guideline. It is "
        "EXPLICITLY NOT a validated risk score: Framingham and the ACC/AHA "
        "Pooled Cohort Equations both need systolic blood pressure and HDL "
        "cholesterol, neither of which VaidyaAI collects, so producing a "
        "percentage here would be inventing precision that does not exist. A "
        "count is honest about what it is.\n\n"
        "Every factor is counted only when POSITIVELY established. Absent and "
        "false both add nothing, so an unknown tri-state can never be read as a "
        "stated negative -- but that also means a tally built from few inputs "
        "understates risk, which is why fewer than three evaluable inputs "
        "produces INSUFFICIENT_DATA instead of a reassuring low count.\n\n"
        "Adult risk factors only, hence the age floor."
    ),
    always_recommend=(GENERAL_PHYSICAL_ACTIVITY, GENERAL_BALANCED_DIET),
    factors=(
        RiskFactorDefinition(
            id="known_heart_disease",
            label="heart disease recorded in the patient profile",
            kind=FACTOR_BOOLEAN_TRUE,
            feature="heart_disease",
            basis="A stated history, taken from Module 2's tri-state field. "
            "Counted only when the value is exactly true; absent means UNKNOWN "
            "and false means explicitly denied, and neither is counted.",
        ),
        RiskFactorDefinition(
            id="hypertension",
            label="hypertension recorded in the patient profile",
            kind=FACTOR_BOOLEAN_TRUE,
            feature="hypertension",
            basis="NCEP ATP III major risk factor. Same tri-state handling as "
            "above: absent is never read as 'no hypertension'.",
        ),
        RiskFactorDefinition(
            id="smoking",
            label="current or lifetime smoking recorded in the patient profile",
            kind=FACTOR_CATEGORY,
            feature="smoking_history",
            categories=("current", "ever"),
            recommendations=(GENERAL_SMOKING_CESSATION_SUPPORT,),
            basis="NCEP ATP III major risk factor (cigarette smoking). Only "
            "'current' and 'ever' are counted. 'former' is not counted because "
            "excess risk falls substantially after cessation; 'not_current' and "
            "'no_info' are not counted because they do not establish anything.",
        ),
        RiskFactorDefinition(
            id="high_total_cholesterol",
            label="total cholesterol at or above 240 mg/dL",
            kind=FACTOR_NUMERIC,
            feature="cholesterol",
            comparator=">=",
            threshold=240.0,
            recommendations=(GENERAL_DIETARY_FAT_QUALITY,),
            basis="NCEP ATP III: total cholesterol >= 240 mg/dL is high. ATP "
            "III's actual major risk factor is low HDL, which is not collected; "
            "high total cholesterol is used as the available proxy and this "
            "substitution is deliberate and recorded.",
        ),
        RiskFactorDefinition(
            id="diabetes_range_hba1c",
            label="HbA1c at or above the diabetes-range threshold of 6.5 %",
            kind=FACTOR_NUMERIC,
            feature="hba1c",
            comparator=">=",
            threshold=6.5,
            recommendations=(GENERAL_LIMIT_ADDED_SUGAR,),
            basis="ATP III treats diabetes as a coronary risk equivalent. HbA1c "
            "is used rather than glucose because it does not depend on when the "
            "person last ate.",
        ),
        RiskFactorDefinition(
            id="obesity",
            label="body mass index at or above 30.0",
            kind=FACTOR_NUMERIC,
            feature="bmi",
            comparator=">=",
            threshold=30.0,
            recommendations=(GENERAL_WEIGHT_DISCUSSION,),
            basis="ACC/AHA primary prevention guideline: obesity is a "
            "risk-enhancing factor. WHO BMI >= 30.0 kg/m2.",
        ),
        RiskFactorDefinition(
            id="age",
            label="age at or above the sex-specific cardiovascular age threshold",
            kind=FACTOR_NUMERIC,
            feature="age",
            comparator=">=",
            threshold=CVD_AGE_THRESHOLD,
            basis="NCEP ATP III major risk factor: age >= 45 (men) / >= 55 "
            "(women).",
        ),
    ),
    bands=(
        CountBand(
            minimum_count=0,
            requires_factor="known_heart_disease",
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            label="heart disease is recorded in the patient profile",
            recommendations=_FLAGGED,
            basis="A recorded history is stated fact, not a threshold result, "
            "and is surfaced regardless of how many other factors are present.",
        ),
        CountBand(
            minimum_count=3,
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            label="three or more major cardiovascular risk factors were counted",
            recommendations=_FLAGGED,
            basis="ATP III risk-factor counting; three or more places a person "
            "in the higher-risk group in every scheme that counts factors.",
        ),
        CountBand(
            minimum_count=2,
            status=DecisionStatus.BORDERLINE,
            risk=RiskLevel.MEDIUM,
            label="two major cardiovascular risk factors were counted",
            recommendations=_FLAGGED,
            basis="ATP III risk-factor counting: two factors is the intermediate "
            "group.",
        ),
        CountBand(
            minimum_count=0,
            status=DecisionStatus.NOT_INDICATED,
            risk=RiskLevel.LOW,
            label="fewer than two major cardiovascular risk factors were counted",
            recommendations=_NOT_FLAGGED,
            basis="ATP III risk-factor counting: 0-1 factors. This counts only "
            "what was established; it is not a statement that no other risk "
            "factor exists.",
        ),
    ),
)

COMPOSITE_RULES: Tuple[CompositeRule, ...] = (HEART_DISEASE_RULE,)


# --------------------------------------------------------------------------
# Derived indexes
# --------------------------------------------------------------------------


def _condition_inputs() -> Dict[str, Tuple[str, ...]]:
    """Which features each condition is assessed from.

    DERIVED from the rule table rather than written out again, so it cannot
    drift when a rule is added or its feature changed.
    """
    index: Dict[str, list] = {}
    for rule in THRESHOLD_RULES:
        index.setdefault(rule.condition, [])
        if rule.feature not in index[rule.condition]:
            index[rule.condition].append(rule.feature)
    for composite in COMPOSITE_RULES:
        index.setdefault(composite.condition, [])
        for factor in composite.factors:
            if factor.feature not in index[composite.condition]:
                index[composite.condition].append(factor.feature)
    return {condition: tuple(features) for condition, features in index.items()}


CONDITION_INPUTS: Dict[str, Tuple[str, ...]] = _condition_inputs()

ALL_RULE_IDS: Tuple[str, ...] = tuple(
    [rule.id for rule in THRESHOLD_RULES] + [rule.id for rule in COMPOSITE_RULES]
)


def rule_by_id(rule_id: str) -> Optional[Any]:
    for rule in THRESHOLD_RULES:
        if rule.id == rule_id:
            return rule
    for composite in COMPOSITE_RULES:
        if composite.id == rule_id:
            return composite
    return None


# --------------------------------------------------------------------------
# Import-time self-check -- mirrors app/data/validation_rules.py
# --------------------------------------------------------------------------


def _check_band(rule_id: str, band: Any) -> None:
    if band.comparator is not None and band.comparator not in COMPARATORS:
        raise ValueError(f"{rule_id}: unknown comparator {band.comparator!r}")
    if (band.comparator is None) != (band.threshold is None):
        raise ValueError(
            f"{rule_id}: a band needs a comparator and a threshold together, or "
            "neither (the always-matching fallback)"
        )
    if band.status is DecisionStatus.INSUFFICIENT_DATA:
        raise ValueError(
            f"{rule_id}: a band that compared a value cannot be INSUFFICIENT_DATA"
        )
    if band.risk is None:
        raise ValueError(f"{rule_id}: every comparing band must carry a risk level")
    if not band.label.strip():
        raise ValueError(f"{rule_id}: band has no label")
    if not band.basis.strip():
        raise ValueError(f"{rule_id}: band {band.label!r} cites no clinical basis")
    for code in band.recommendations:
        if not is_known_code(code):
            raise ValueError(f"{rule_id}: unknown recommendation code {code!r}")
    # Band labels reach the user through EvidenceItem.note, so they are held to
    # the same safety standard as the recommendation catalogue itself.
    assert_safe(band.label, f"{rule_id} band label")


def _self_check() -> None:
    seen_ids = set()
    for rule in THRESHOLD_RULES:
        if rule.id in seen_ids:
            raise ValueError(f"duplicate rule id {rule.id!r}")
        seen_ids.add(rule.id)
        if rule.feature not in FEATURES:
            raise ValueError(
                f"{rule.id}: {rule.feature!r} is not a canonical feature -- a rule "
                "on a feature that does not exist can never fire"
            )
        if not FEATURES[rule.feature].value_type in ("number", "integer"):
            raise ValueError(
                f"{rule.id}: {rule.feature!r} is not numeric, so a threshold rule "
                "cannot apply to it"
            )
        if not C.is_canonical_condition(rule.condition):
            raise ValueError(
                f"{rule.id}: {rule.condition!r} is not in app/data/conditions.py -- "
                "a non-canonical condition silently prevents Module 16 fusion"
            )
        if not rule.basis.strip():
            raise ValueError(f"{rule.id}: rule cites no clinical basis")
        if not rule.bands:
            raise ValueError(f"{rule.id}: rule has no bands")
        if rule.bands[-1].comparator is not None:
            raise ValueError(
                f"{rule.id}: the last band must be the always-matching fallback, "
                "otherwise a rule can fire and produce nothing"
            )
        if any(band.comparator is None for band in rule.bands[:-1]):
            raise ValueError(
                f"{rule.id}: only the LAST band may be the always-matching one"
            )
        for band in rule.bands:
            _check_band(rule.id, band)
        for name in rule.context_features:
            if name not in FEATURES:
                raise ValueError(f"{rule.id}: unknown context feature {name!r}")
        if rule.derived is not None:
            spec = DERIVED_VALUES.get(rule.derived)
            if spec is None:
                raise ValueError(f"{rule.id}: unknown derived value {rule.derived!r}")
            if rule.derived in FEATURES:
                raise ValueError(
                    f"{rule.id}: derived value {rule.derived!r} collides with a "
                    "catalogue feature -- a calculated value must never be "
                    "mistaken for one read off the report"
                )
            if rule.feature != spec["input"]:
                raise ValueError(
                    f"{rule.id}: {rule.derived!r} is calculated from "
                    f"{spec['input']!r}, not {rule.feature!r}"
                )
            missing = [n for n in spec["requires"] if n not in rule.context_features]
            if missing:
                raise ValueError(
                    f"{rule.id}: {rule.derived!r} needs context features {missing}"
                )
            if rule.min_age_years != spec["min_age_years"]:
                raise ValueError(
                    f"{rule.id}: {rule.derived!r} is validated from age "
                    f"{spec['min_age_years']}, and the rule must say so"
                )
            if any(band.only_when_sex_unknown for band in rule.bands):
                raise ValueError(
                    f"{rule.id}: a derived value that needs sex cannot have a "
                    "sex-unknown band"
                )
            if any(
                isinstance(band.threshold, ContextualThreshold) for band in rule.bands
            ):
                raise ValueError(
                    f"{rule.id}: derived-value bands use plain thresholds"
                )
        for code in rule.always_recommend:
            if not is_known_code(code):
                raise ValueError(f"{rule.id}: unknown recommendation code {code!r}")
        for timing in rule.only_timing:
            if timing not in (
                TIMING_FASTING,
                TIMING_POST_PRANDIAL,
                TIMING_RANDOM,
                TIMING_UNSPECIFIED,
            ):
                raise ValueError(f"{rule.id}: unknown sample timing {timing!r}")

    for composite in COMPOSITE_RULES:
        if composite.id in seen_ids:
            raise ValueError(f"duplicate rule id {composite.id!r}")
        seen_ids.add(composite.id)
        if not C.is_canonical_condition(composite.condition):
            raise ValueError(f"{composite.id}: {composite.condition!r} is not canonical")
        if not composite.factors:
            raise ValueError(f"{composite.id}: no risk factors defined")
        factor_ids = set()
        for factor in composite.factors:
            if factor.id in factor_ids:
                raise ValueError(f"{composite.id}: duplicate factor id {factor.id!r}")
            factor_ids.add(factor.id)
            if factor.feature not in FEATURES:
                raise ValueError(f"{composite.id}: unknown feature {factor.feature!r}")
            if factor.kind == FACTOR_NUMERIC:
                if factor.comparator not in COMPARATORS or factor.threshold is None:
                    raise ValueError(
                        f"{composite.id}/{factor.id}: a numeric factor needs a "
                        "comparator and a threshold"
                    )
            elif factor.kind == FACTOR_CATEGORY:
                if not factor.categories:
                    raise ValueError(
                        f"{composite.id}/{factor.id}: a category factor needs "
                        "categories"
                    )
                allowed = FEATURES[factor.feature].categories
                unknown = [c for c in factor.categories if c not in allowed]
                if unknown:
                    raise ValueError(
                        f"{composite.id}/{factor.id}: categories {unknown} are not "
                        f"in the catalog vocabulary for {factor.feature!r}"
                    )
            elif factor.kind == FACTOR_BOOLEAN_TRUE:
                if FEATURES[factor.feature].value_type != "boolean":
                    raise ValueError(
                        f"{composite.id}/{factor.id}: {factor.feature!r} is not a "
                        "boolean feature"
                    )
            else:
                raise ValueError(f"{composite.id}/{factor.id}: unknown kind")
            if not factor.basis.strip():
                raise ValueError(f"{composite.id}/{factor.id}: cites no basis")
            assert_safe(factor.label, f"{composite.id}/{factor.id} label")
            for code in factor.recommendations:
                if not is_known_code(code):
                    raise ValueError(f"{composite.id}/{factor.id}: unknown code {code!r}")
        if composite.min_evaluable_inputs > len(composite.factors):
            raise ValueError(
                f"{composite.id}: min_evaluable_inputs exceeds the number of "
                "factors, so the rule could never produce a verdict"
            )
        for band in composite.bands:
            if band.risk is None:
                raise ValueError(f"{composite.id}: count band without a risk level")
            if not band.basis.strip():
                raise ValueError(f"{composite.id}: count band cites no basis")
            assert_safe(band.label, f"{composite.id} band label")
            for code in band.recommendations:
                if not is_known_code(code):
                    raise ValueError(f"{composite.id}: unknown code {code!r}")
            if band.requires_factor and band.requires_factor not in factor_ids:
                raise ValueError(
                    f"{composite.id}: band requires unknown factor "
                    f"{band.requires_factor!r}"
                )
        if composite.bands[-1].minimum_count != 0 or composite.bands[-1].requires_factor:
            raise ValueError(
                f"{composite.id}: the last count band must be the unconditional "
                "fallback"
            )
        for code in composite.always_recommend:
            if not is_known_code(code):
                raise ValueError(f"{composite.id}: unknown code {code!r}")

    # Every condition that promises always to be assessed must actually have a
    # rule capable of assessing it.
    for condition in C.ALWAYS_ASSESSED_CONDITIONS:
        if condition not in CONDITION_INPUTS:
            raise ValueError(
                f"{condition!r} is declared always_assessed but no rule assesses it"
            )


_self_check()


# --------------------------------------------------------------------------
# Review dump
# --------------------------------------------------------------------------


def _threshold_document(threshold: Any) -> Any:
    if isinstance(threshold, ContextualThreshold):
        return {
            "male": threshold.male,
            "female": threshold.female,
            "unknown": threshold.unknown,
            "unknown_note": threshold.unknown_note,
            "paediatric": [list(p) for p in threshold.paediatric],
            "basis": threshold.basis,
        }
    return threshold


def rules_document() -> Dict[str, Any]:
    """Machine-readable dump of the rule table, for clinical review."""
    return {
        "rule_table_version": RULE_TABLE_VERSION,
        "source": RULE_ENGINE_SOURCE,
        "policy": (
            "Deterministic threshold comparison only. No model, no probability, "
            "no learning. A rule whose feature is absent does not fire, and "
            "absence is never reported as a normal result."
        ),
        "threshold_rules": [
            {
                "id": rule.id,
                "version": rule.version,
                "condition": rule.condition,
                "feature": rule.feature,
                "derived": rule.derived,
                "unit": (
                    DERIVED_VALUES[rule.derived]["unit"]
                    if rule.derived
                    else FEATURES[rule.feature].canonical_unit
                ),
                "min_age_years": rule.min_age_years,
                "only_timing": list(rule.only_timing),
                "context_features": list(rule.context_features),
                "always_recommend": list(rule.always_recommend),
                "basis": rule.basis,
                "bands": [
                    {
                        "comparator": band.comparator,
                        "threshold": _threshold_document(band.threshold),
                        "status": band.status.value,
                        "risk": band.risk.value if band.risk else None,
                        "label": band.label,
                        "recommendations": list(band.recommendations),
                        "only_when_sex_unknown": band.only_when_sex_unknown,
                        "basis": band.basis,
                    }
                    for band in rule.bands
                ],
            }
            for rule in THRESHOLD_RULES
        ],
        "composite_rules": [
            {
                "id": rule.id,
                "version": rule.version,
                "condition": rule.condition,
                "min_evaluable_inputs": rule.min_evaluable_inputs,
                "min_age_years": rule.min_age_years,
                "basis": rule.basis,
                "always_recommend": list(rule.always_recommend),
                "factors": [
                    {
                        "id": factor.id,
                        "label": factor.label,
                        "kind": factor.kind,
                        "feature": factor.feature,
                        "comparator": factor.comparator,
                        "threshold": _threshold_document(factor.threshold),
                        "categories": list(factor.categories),
                        "recommendations": list(factor.recommendations),
                        "basis": factor.basis,
                    }
                    for factor in rule.factors
                ],
                "bands": [
                    {
                        "minimum_count": band.minimum_count,
                        "requires_factor": band.requires_factor,
                        "status": band.status.value,
                        "risk": band.risk.value if band.risk else None,
                        "label": band.label,
                        "recommendations": list(band.recommendations),
                        "basis": band.basis,
                    }
                    for band in rule.bands
                ],
            }
            for rule in COMPOSITE_RULES
        ],
        "condition_inputs": {k: list(v) for k, v in CONDITION_INPUTS.items()},
    }


__all__ = [
    "ALL_RULE_IDS",
    "COMPARATORS",
    "COMPOSITE_RULES",
    "CONDITION_INPUTS",
    "DERIVED_VALUES",
    "FACTOR_BOOLEAN_TRUE",
    "FACTOR_CATEGORY",
    "FACTOR_NUMERIC",
    "HEART_DISEASE_RULE",
    "RULE_ENGINE_SOURCE",
    "RULE_TABLE_VERSION",
    "THRESHOLD_RULES",
    "TIMING_FASTING",
    "TIMING_POST_PRANDIAL",
    "TIMING_RANDOM",
    "TIMING_UNSPECIFIED",
    "Band",
    "CompositeRule",
    "ContextualThreshold",
    "CountBand",
    "RiskFactorDefinition",
    "ThresholdRule",
    "resolve_threshold",
    "rule_by_id",
    "rules_document",
    "sample_timing",
]
