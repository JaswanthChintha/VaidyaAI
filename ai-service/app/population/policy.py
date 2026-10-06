"""Module 31 policy: reason codes, copy, and the DELIBERATE exclusions.

This file is the reviewable data layer for population context, in the same
spirit as `app/data/clinical_rules.py` and `app/data/feature_catalog.py`:
tables and strings, no control flow, so a clinician can check what the patient
is going to be told without reading any Python logic.

THE RULE THIS MODULE EXISTS TO OBEY
-----------------------------------
A percentile shown to a patient is a factual claim about a real population. If
there is no real, published distribution for a parameter, this module says so.
It does not estimate, interpolate, borrow a neighbouring age band, rescale
another population, or "reasonably approximate" anything. `EXCLUDED_FEATURES`
below is the list of canonical VaidyaAI features that are deliberately NOT
covered, each with the reason -- because a module that silently omits a feature
is indistinguishable from one that forgot it.
"""

from __future__ import annotations

from typing import Dict, Tuple

MODULE = 31
VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Reason codes -- why a feature has no population context
# --------------------------------------------------------------------------


class PopulationReason:
    """Stable, machine-readable codes. A consumer may branch on these."""

    #: The name is not a canonical VaidyaAI feature at all.
    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    #: Canonical, but not a continuous measurement (boolean / category / age).
    FEATURE_NOT_CONTINUOUS = "FEATURE_NOT_CONTINUOUS"
    #: Canonical and continuous, but no verified published distribution exists.
    NO_VERIFIED_DISTRIBUTION = "NO_VERIFIED_DISTRIBUTION"

    #: No age was supplied, so no age-matched group can be chosen.
    AGE_NOT_PROVIDED = "AGE_NOT_PROVIDED"
    #: An age outside every band the table covers -- never extrapolated.
    AGE_OUTSIDE_TABLE_RANGE = "AGE_OUTSIDE_TABLE_RANGE"
    #: Under the table's minimum age. Called out separately from the above
    #: because scoring a child against an adult table is a clinical error and
    #: deserves its own, unambiguous code.
    AGE_BELOW_ADULT_TABLE = "AGE_BELOW_ADULT_TABLE"

    #: Gender absent, or `other` / `prefer_not_to_say`. The published tables
    #: are male/female only and a person's stated gender is NEVER coerced.
    SEX_COHORT_NOT_AVAILABLE = "SEX_COHORT_NOT_AVAILABLE"

    #: The (sex, age band) cell exists in principle but was not published
    #: because too few people were observed in it.
    COHORT_TOO_SMALL_TO_PUBLISH = "COHORT_TOO_SMALL_TO_PUBLISH"

    #: Value problems.
    VALUE_NOT_NUMERIC = "VALUE_NOT_NUMERIC"
    #: A finite number, but outside the physiologically possible band Module 6
    #: already publishes for this feature. This endpoint accepts raw
    #: measurements rather than a validated snapshot, so a value that Module 6
    #: would have REJECTED as an extraction error can otherwise reach the
    #: lookup and come back with a perfectly well-formed band: an audit got
    #: "below the 1st percentile" out of an HbA1c of -3 %. The statement is
    #: technically true and carries no clinical claim, which is exactly what
    #: makes it bad -- it launders a nonsense input into something that reads
    #: like a finding.
    VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE = "VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE"
    UNIT_NOT_PROVIDED = "UNIT_NOT_PROVIDED"
    UNIT_NOT_RECOGNISED = "UNIT_NOT_RECOGNISED"
    UNIT_NOT_CONVERTIBLE = "UNIT_NOT_CONVERTIBLE"


REASON_CODES: Tuple[str, ...] = tuple(
    v for k, v in vars(PopulationReason).items() if k.isupper()
)


# --------------------------------------------------------------------------
# Canonical features deliberately NOT covered, and why.
#
# Every canonical feature that is not backed by a table in
# `datasets/population/distributions/` MUST appear here. `app/population/
# tables.py` asserts that at import time, so adding a feature to
# feature_catalog.py without deciding what Module 31 does about it fails fast
# instead of silently vanishing from the response.
# --------------------------------------------------------------------------

EXCLUDED_FEATURES: Dict[str, Dict[str, str]] = {
    "blood_glucose": {
        "reason_code": PopulationReason.NO_VERIFIED_DISTRIBUTION,
        "message": (
            "No population comparison is offered for blood glucose. A glucose "
            "result means something different depending on whether the sample "
            "was taken fasting, and neither this service nor the uploaded "
            "report reliably records fasting status. Comparing a random "
            "glucose against a fasting population, or the reverse, would "
            "produce a percentile that looks precise and is wrong."
        ),
    },
    "triglycerides": {
        "reason_code": PopulationReason.NO_VERIFIED_DISTRIBUTION,
        "message": (
            "No population comparison is offered for triglycerides. "
            "Triglycerides are the lipid most strongly affected by recent "
            "eating -- a value can differ substantially between a fasting and "
            "a non-fasting sample -- and fasting status is not recorded by "
            "this service, so no matched population group can be chosen "
            "honestly."
        ),
    },
    # THE LIVER PANEL (2026-10-04). NHANES 2017-2018 (BIOPRO_J, already in
    # this repository's git history) holds ALT, AST and total bilirubin, so a
    # verified table is possible -- but none has been built or checked yet,
    # and an unverified percentile is worse than none.
    "alt": {
        "reason_code": PopulationReason.NO_VERIFIED_DISTRIBUTION,
        "message": (
            "No population comparison is offered for ALT yet. A comparison "
            "group for it has not been built and checked."
        ),
    },
    "ast": {
        "reason_code": PopulationReason.NO_VERIFIED_DISTRIBUTION,
        "message": (
            "No population comparison is offered for AST yet. A comparison "
            "group for it has not been built and checked."
        ),
    },
    "bilirubin_total": {
        "reason_code": PopulationReason.NO_VERIFIED_DISTRIBUTION,
        "message": (
            "No population comparison is offered for total bilirubin yet. A "
            "comparison group for it has not been built and checked."
        ),
    },
    "hypertension": {
        "reason_code": PopulationReason.FEATURE_NOT_CONTINUOUS,
        "message": (
            "Hypertension is recorded as yes / no / not answered, not as a "
            "measured number, so there is no distribution to place a value in."
        ),
    },
    "heart_disease": {
        "reason_code": PopulationReason.FEATURE_NOT_CONTINUOUS,
        "message": (
            "Known heart disease is recorded as yes / no / not answered, not "
            "as a measured number, so there is no distribution to place a "
            "value in."
        ),
    },
    "smoking_history": {
        "reason_code": PopulationReason.FEATURE_NOT_CONTINUOUS,
        "message": (
            "Smoking history is a category, not a measured number, so there "
            "is no distribution to place a value in."
        ),
    },
    "gender": {
        "reason_code": PopulationReason.FEATURE_NOT_CONTINUOUS,
        "message": (
            "Gender is one of the things the population group is matched ON. "
            "It is not itself a measurement that can be given a percentile."
        ),
    },
    "age": {
        "reason_code": PopulationReason.FEATURE_NOT_CONTINUOUS,
        "message": (
            "Age is one of the things the population group is matched ON. It "
            "is not itself a measurement that can be given a percentile."
        ),
    },
}


# --------------------------------------------------------------------------
# Copy. Deliberately flat, non-clinical language.
#
# Module 31 makes NO clinical claim, so none of this text may contain a risk
# word, a recommendation, a normal/abnormal judgement, or a comparison against
# a reference range. Module 8 owns "is this value in range"; Module 31 owns
# only "how common is this value". Those are different questions and the copy
# must keep them apart.
# --------------------------------------------------------------------------

WHAT_THIS_MEANS = (
    "A percentile says how common a value is in a group of people of similar "
    "age and sex. It is a description of that group, nothing more."
)

WHAT_THIS_DOES_NOT_MEAN = (
    "A percentile is NOT a reference range, NOT a test result interpretation, "
    "and NOT a diagnosis. A value can sit at a high or low percentile and "
    "still be entirely normal, and a value inside the usual range for most "
    "people is not automatically healthy for any one person. Whether a result "
    "matters is a question for the reference range on the report and for a "
    "qualified clinician -- not for this comparison."
)

#: The patient-facing sentence for every reason code that is NOT specific to
#: one feature. The per-feature refusals live in `EXCLUDED_FEATURES` above and
#: carry their own wording; these cover the refusals that depend on the
#: REQUEST rather than on which parameter was asked about.
#:
#: `tables.py` checks at import time that this dict covers every code in
#: `REASON_CODES` that is not already answered by an `EXCLUDED_FEATURES` entry,
#: so a new reason code cannot ship without wording a patient can read.
REASON_MESSAGES: Dict[str, str] = {
    PopulationReason.UNKNOWN_FEATURE: (
        "No population comparison is offered, because this is not one of the "
        "parameters this service recognises."
    ),
    PopulationReason.FEATURE_NOT_CONTINUOUS: (
        "No population comparison is offered, because this is not a measured "
        "number and so has no distribution to place a value in."
    ),
    PopulationReason.NO_VERIFIED_DISTRIBUTION: (
        "No population comparison is offered for this parameter, because "
        "there is no verified published distribution behind it. Nothing is "
        "estimated in its place."
    ),
    PopulationReason.AGE_NOT_PROVIDED: (
        "No population comparison is offered, because no age was supplied. "
        "The comparison groups are defined by age and sex, and no group can "
        "be chosen without both."
    ),
    PopulationReason.AGE_OUTSIDE_TABLE_RANGE: (
        "No population comparison is offered, because the age given falls "
        "outside every group the survey published for this parameter. The "
        "nearest group is not substituted."
    ),
    PopulationReason.AGE_BELOW_ADULT_TABLE: (
        "No population comparison is offered, because the survey groups "
        "behind this parameter cover adults only. A child's or adolescent's "
        "result is never compared against an adult group."
    ),
    PopulationReason.SEX_COHORT_NOT_AVAILABLE: (
        "No population comparison is offered, because the published survey "
        "groups are recorded as male and female only and no group matches "
        "what was supplied. Nothing is assumed on your behalf."
    ),
    PopulationReason.COHORT_TOO_SMALL_TO_PUBLISH: (
        "No population comparison is offered, because too few people of this "
        "age and sex were measured in the survey for a percentile to mean "
        "anything. A noisy number is not published."
    ),
    PopulationReason.VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE: (
        "No population comparison is offered for this reading. The value lies "
        "outside the range this service considers physiologically possible "
        "for the parameter, so it is read as a transcription or extraction "
        "problem rather than as a measurement. Placing it in a population "
        "would give a precise-looking answer to a question the number cannot "
        "support."
    ),
    PopulationReason.VALUE_NOT_NUMERIC: (
        "No population comparison is offered, because no usable number was "
        "supplied for this parameter."
    ),
    PopulationReason.UNIT_NOT_PROVIDED: (
        "No population comparison is offered, because no unit was supplied "
        "with this result. The same number means different things in "
        "different units, so a unit is never assumed."
    ),
    PopulationReason.UNIT_NOT_RECOGNISED: (
        "No population comparison is offered, because the unit supplied with "
        "this result was not recognised. A unit that cannot be read is never "
        "guessed at."
    ),
    PopulationReason.UNIT_NOT_CONVERTIBLE: (
        "No population comparison is offered, because there is no verified "
        "conversion from the unit supplied into the unit the survey published "
        "for this parameter."
    ),
}


#: SAY "AT OR BELOW", NOT "LOWER". The two are not the same number here, and
#: the difference is large enough to mislead.
#:
#: The published cut-points are `min{x : P(X <= x) >= p}` and the band is found
#: with `bisect_right`, so a band is a statement about the share AT OR BELOW a
#: value. Laboratory results cluster hard at one decimal place, so the share
#: STRICTLY below is much smaller. Measured against the raw NHANES microdata
#: for men aged 20-29, HbA1c:
#:
#:     5.2 % (the modal value)  reported 50th-75th   strictly below 40.9 %
#:     5.8 %                    reported 97.5th-99th strictly below 95.0 %
#:     4.6 %                    reported 5th-10th    strictly below  2.4 %
#:
#: An audit found this wording telling a 25-year-old man with an entirely
#: ordinary 5.2 that he was between the 50th and 75th percentile of people with
#: a LOWER result, when only 41% are lower. The banding arithmetic was correct
#: throughout; this sentence was written for a point percentile and never
#: revised for the band design. The band is defensible under "at or below", so
#: that is what it now says.
PER_FEATURE_MEANS = (
    "Of people of this age and sex in the survey, this is the share whose "
    "{label} was at or below yours. People whose result equals yours are "
    "counted in that share."
)

PER_FEATURE_DOES_NOT_MEAN = (
    "This does not say whether your {label} is normal, high, or low. It only "
    "says how common it is."
)

DISCLAIMER = (
    "Population context is educational information, not a medical assessment. "
    "It compares one number with a survey of people of similar age and sex. "
    "It cannot take account of your medical history, medicines, ethnicity, "
    "pregnancy, altitude, or why the test was ordered. Discuss your results "
    "with a qualified healthcare professional."
)

GENERAL_LIMITATIONS: Tuple[str, ...] = (
    "The reference population is the United States civilian non-"
    "institutionalised population surveyed by NHANES. It is not matched to "
    "any other country, ethnicity, or health status.",
    "The surveyed groups include people who have the relevant condition and "
    "people taking medicines that change the result. They describe a "
    "population as it is, not a population of healthy people.",
    "Pregnant participants were excluded from every group, so a pregnant "
    "patient is being compared against people who were not pregnant.",
    "Only adults aged 20 and over are covered. No comparison is offered for "
    "children or adolescents.",
    "A percentile BAND is reported rather than a single percentile number, "
    "because the underlying survey estimates carry sampling uncertainty that "
    "this module does not quantify.",
)

POLICY: Dict[str, object] = {
    "module": MODULE,
    "version": VERSION,
    "purpose": (
        "Report how a patient's value compares with an age- and sex-matched "
        "population group, as context beyond the reference range."
    ),
    "makes_clinical_claims": False,
    "calls_an_llm": False,
    "matching": {
        "matched_on": ["age_band", "sex"],
        "unmatched_cohort_offered": False,
        "unmatched_cohort_rationale": (
            "An all-adults distribution is never substituted for a missing "
            "age or sex. Haemoglobin and creatinine differ so much by sex, "
            "and HbA1c and BMI so much by age, that an unmatched percentile "
            "would be a different and misleading claim wearing the same "
            "words. Absence is reported as absence."
        ),
        "gender_handling": (
            "Module 2 stores male / female / other / prefer_not_to_say. The "
            "published tables are male/female only. `other`, "
            "`prefer_not_to_say` and an absent gender all yield "
            "SEX_COHORT_NOT_AVAILABLE. A stated gender is never coerced into "
            "a binary category to force a lookup."
        ),
        "age_handling": (
            "An age outside the bands a table publishes yields "
            "AGE_OUTSIDE_TABLE_RANGE, and an age below the table's minimum "
            "yields AGE_BELOW_ADULT_TABLE. Neither is extrapolated. A "
            "paediatric value is never scored against an adult table."
        ),
        "unit_handling": (
            "The patient's unit is normalised and converted through the "
            "audited table in app/data/unit_conversions.py. If the unit is "
            "absent, unrecognised for that feature, or has no verified "
            "conversion into the table's unit, the feature is unavailable. A "
            "unit is never assumed."
        ),
    },
    "percentile_reporting": {
        "style": "band_between_published_grid_points",
        "interpolated": False,
        "note": (
            "The patient's value is bracketed between two adjacent published "
            "percentile cut-points. No percentile number is interpolated, so "
            "no number is reported that was not measured."
        ),
    },
    "reason_codes": list(REASON_CODES),
    "what_this_means": WHAT_THIS_MEANS,
    "what_this_does_not_mean": WHAT_THIS_DOES_NOT_MEAN,
    "limitations": list(GENERAL_LIMITATIONS),
    "disclaimer": DISCLAIMER,
}


__all__ = [
    "DISCLAIMER",
    "EXCLUDED_FEATURES",
    "GENERAL_LIMITATIONS",
    "MODULE",
    "PER_FEATURE_DOES_NOT_MEAN",
    "PER_FEATURE_MEANS",
    "POLICY",
    "PopulationReason",
    "REASON_CODES",
    "REASON_MESSAGES",
    "VERSION",
    "WHAT_THIS_DOES_NOT_MEAN",
    "WHAT_THIS_MEANS",
]
