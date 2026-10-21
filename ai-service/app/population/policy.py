from __future__ import annotations

from typing import Dict, Tuple

MODULE = 31
VERSION = "1.0.0"


class PopulationReason:

    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    FEATURE_NOT_CONTINUOUS = "FEATURE_NOT_CONTINUOUS"
    NO_VERIFIED_DISTRIBUTION = "NO_VERIFIED_DISTRIBUTION"

    AGE_NOT_PROVIDED = "AGE_NOT_PROVIDED"
    AGE_OUTSIDE_TABLE_RANGE = "AGE_OUTSIDE_TABLE_RANGE"
    AGE_BELOW_ADULT_TABLE = "AGE_BELOW_ADULT_TABLE"

    SEX_COHORT_NOT_AVAILABLE = "SEX_COHORT_NOT_AVAILABLE"

    COHORT_TOO_SMALL_TO_PUBLISH = "COHORT_TOO_SMALL_TO_PUBLISH"

    VALUE_NOT_NUMERIC = "VALUE_NOT_NUMERIC"
    VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE = "VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE"
    UNIT_NOT_PROVIDED = "UNIT_NOT_PROVIDED"
    UNIT_NOT_RECOGNISED = "UNIT_NOT_RECOGNISED"
    UNIT_NOT_CONVERTIBLE = "UNIT_NOT_CONVERTIBLE"


REASON_CODES: Tuple[str, ...] = tuple(
    v for k, v in vars(PopulationReason).items() if k.isupper()
)


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
