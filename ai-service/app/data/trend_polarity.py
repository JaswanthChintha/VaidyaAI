from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.data.feature_catalog import FEATURES

TREND_POLICY_VERSION = "1.0.0"


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

    feature: str
    kind: str
    basis: str

    reader_basis: Optional[str] = None

    direction_of_harm: Optional[str] = None

    optimal_low: Optional[float] = None
    optimal_high: Optional[float] = None

    trendable: bool = True

    min_age_years: Optional[int] = None

    timing_sensitive: bool = False


def _number(value: float) -> str:
    return f"{value:g}"


def _reader_interval(polarity: "TrendPolarity") -> str:
    unit = FEATURES[polarity.feature].canonical_unit if polarity.feature in FEATURES else None
    suffix = f" {unit}" if unit else ""
    low, high = polarity.optimal_low, polarity.optimal_high
    if low is not None and high is not None:
        return f"the range {_number(low)} to {_number(high)}{suffix}"
    if low is not None:
        return f"{_number(low)}{suffix} or above"
    return f"{_number(high)}{suffix} or below"


def reader_reason(polarity: "TrendPolarity") -> str:
    if polarity.reader_basis:
        return polarity.reader_basis
    if polarity.kind == POLARITY_MONOTONE and polarity.direction_of_harm in (
        HARM_INCREASE,
        HARM_DECREASE,
    ):
        worse, better = (
            ("rise", "fall")
            if polarity.direction_of_harm == HARM_INCREASE
            else ("fall", "rise")
        )
        return (
            f"This platform counts a {worse} in this measurement as "
            f"unfavourable and a {better} as favourable, at any level. Only a "
            "change larger than the test's own normal variation is judged at "
            "all, and what a particular result means is a question for a "
            "healthcare professional."
        )
    if polarity.kind == POLARITY_TOWARD_REFERENCE and (
        polarity.optimal_low is not None or polarity.optimal_high is not None
    ):
        both = polarity.optimal_low is not None and polarity.optimal_high is not None
        return (
            "This platform counts a change as favourable when it moves closer "
            f"to {_reader_interval(polarity)}, and unfavourable when it moves "
            "further away. A change that stays within that range"
            + (", or jumps from one side of it to the other," if both else "")
            + " is not judged either way."
        )
    return (
        "This platform does not declare whether a change in this measurement "
        "is an improvement, so the direction and size of the change are "
        "reported without judging them."
    )


POLARITY: Dict[str, TrendPolarity] = {
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
        reader_basis=(
            "Whether a change in blood sugar is an improvement is not "
            "reported here, for two reasons. A fasting sample and one taken "
            "after eating are not the same measurement, and this report does "
            "not always say which was taken. And blood sugar can be harmful "
            "when it is too low as well as too high, so a fall is not "
            "automatically good news. The change itself is shown; whether it "
            "is better or worse is a question for a healthcare professional."
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
        reader_basis=(
            "Whether a change in haemoglobin is an improvement is not "
            "reported here. It can be harmful when too low and when too high, "
            "and the usual range differs with sex, age and pregnancy, which "
            "this service does not record. The change itself is shown; "
            "whether it is better or worse is a question for a healthcare "
            "professional."
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
    "hematocrit": TrendPolarity(
        "hematocrit",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE, for the same reason as `hemoglobin`, which "
            "it tracks at roughly 3x. Harmful at both extremes (anaemia "
            "below, polycythaemia/hyperviscosity above), so it would have to "
            "be TOWARD_REFERENCE -- and the interval is sex-specific, "
            "altitude-sensitive and pregnancy-modified, none of which this "
            "service records. Direction and magnitude only."
        ),
        reader_basis=(
            "Whether a change in your PCV is an improvement is not reported "
            "here. It can be too low or too high, and the usual range differs "
            "between men and women. The change itself is shown; whether it "
            "matters is a question for a healthcare professional."
        ),
    ),
    "rbc_count": TrendPolarity(
        "rbc_count",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. Harmful at both extremes and sex-specific, "
            "exactly as `hemoglobin` and `hematocrit`."
        ),
        reader_basis=(
            "Whether a change in your red cell count is an improvement is not "
            "reported here. It can be too low or too high, and the usual "
            "range differs between men and women."
        ),
    ),
    "mcv": TrendPolarity(
        "mcv",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE, and this one is not merely a both-extremes "
            "case: MCV is an INDEX, not a severity measure. A low value "
            "points toward iron deficiency or thalassaemia and a high one "
            "toward B12/folate deficiency, alcohol or myelodysplasia. A move "
            "from 70 toward 90 and a move from 110 toward 90 are opposite "
            "clinical stories that this service cannot tell apart, because it "
            "does not know which one the reader has."
        ),
        reader_basis=(
            "Whether a change in your average red cell size is an improvement "
            "is not reported here. A value can be low or high for very "
            "different reasons, and the number alone does not say which."
        ),
    ),
    "mch": TrendPolarity(
        "mch",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. Derived from haemoglobin and red cell count, "
            "so it inherits both of their refusals, and it is an index rather "
            "than a severity measure."
        ),
        reader_basis=(
            "Whether a change in this red cell measurement is an improvement "
            "is not reported here. It describes the average amount of "
            "haemoglobin in a red cell, and can be low or high for different "
            "reasons."
        ),
    ),
    "mchc": TrendPolarity(
        "mchc",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE, with a reason the others do not have: a "
            "RAISED MCHC is more often a MEASUREMENT ARTEFACT -- lipaemia, "
            "haemolysis, cold agglutinins -- than a physiological change. "
            "Calling a rise 'worse' would be asserting a clinical event where "
            "the likeliest explanation is the sample itself."
        ),
        reader_basis=(
            "Whether a change in this red cell measurement is an improvement "
            "is not reported here. A high value is often caused by the sample "
            "rather than by anything about your health."
        ),
    ),
    "wbc_count": TrendPolarity(
        "wbc_count",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. Harmful at both extremes: a low count raises "
            "infection risk and a high one accompanies infection, "
            "inflammation, steroids and haematological disease. A fall from "
            "30 to 10 and a fall from 5 to 1.5 are opposite events."
        ),
        reader_basis=(
            "Whether a change in your white cell count is an improvement is "
            "not reported here. It can be too low or too high, and a rise can "
            "mean the body is responding to something rather than that "
            "anything is wrong."
        ),
    ),
    "neutrophils": TrendPolarity(
        "neutrophils",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. A PERCENTAGE OF THE WHITE CELL COUNT: it can "
            "rise because neutrophils rose or because lymphocytes fell, which "
            "are different events with different causes. Harmful at both "
            "extremes besides."
        ),
        reader_basis=(
            "Whether a change in this value is an improvement is not reported "
            "here. It is a share of your total white cells, so it can move "
            "because this cell type changed or because another one did."
        ),
    ),
    "lymphocytes": TrendPolarity(
        "lymphocytes",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. A percentage of the white cell count; see "
            "the `neutrophils` row. Harmful at both extremes."
        ),
        reader_basis=(
            "Whether a change in this value is an improvement is not reported "
            "here. It is a share of your total white cells, so it can move "
            "because this cell type changed or because another one did."
        ),
    ),
    "monocytes": TrendPolarity(
        "monocytes",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. A percentage of the white cell count; see "
            "the `neutrophils` row."
        ),
        reader_basis=(
            "Whether a change in this value is an improvement is not reported "
            "here. It is a share of your total white cells, so it can move "
            "because this cell type changed or because another one did."
        ),
    ),
    "eosinophils": TrendPolarity(
        "eosinophils",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. A percentage of the white cell count; see "
            "the `neutrophils` row. Additionally seasonal and strongly "
            "right-skewed (allergy, parasitic exposure), so a change between "
            "two reports frequently reflects the time of year."
        ),
        reader_basis=(
            "Whether a change in this value is an improvement is not reported "
            "here. It is a share of your total white cells, and it commonly "
            "moves with allergies or the time of year."
        ),
    ),
    "basophils": TrendPolarity(
        "basophils",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. A percentage of the white cell count; see "
            "the `neutrophils` row. Reported to one decimal place on a range "
            "of roughly 0-2 %, so the measurement resolution is a large "
            "fraction of the whole scale."
        ),
        reader_basis=(
            "Whether a change in this value is an improvement is not reported "
            "here. It is a small share of your total white cells, and the "
            "numbers involved are so small that ordinary variation looks "
            "large."
        ),
    ),
    "platelet_count": TrendPolarity(
        "platelet_count",
        POLARITY_UNDECLARED,
        basis=(
            "REFUSED ON PURPOSE. Harmful at both extremes: a low count raises "
            "bleeding risk, a high one accompanies thrombocytosis and "
            "reactive states. A fall from 900 to 400 and a fall from 150 to "
            "40 are opposite clinical events."
        ),
        reader_basis=(
            "Whether a change in your platelet count is an improvement is not "
            "reported here. It can be too low or too high, so a fall is not "
            "automatically good news."
        ),
    ),
    "alt": TrendPolarity(
        "alt",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "ACG 2017 abnormal liver chemistries: ALT leaks from injured "
            "hepatocytes, so a RISE reflects more liver-cell injury. A low ALT "
            "carries no clinical harm in this context."
        ),
    ),
    "ast": TrendPolarity(
        "ast",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "ACG 2017: AST rises with hepatocellular (and muscle) injury; a "
            "low AST is not a clinical concern."
        ),
    ),
    "bilirubin_total": TrendPolarity(
        "bilirubin_total",
        POLARITY_MONOTONE,
        direction_of_harm=HARM_INCREASE,
        basis=(
            "Raised total bilirubin reflects reduced clearance (liver, bile "
            "ducts) or increased red-cell breakdown; a low value is not a "
            "clinical concern in adults."
        ),
    ),
}


@dataclass(frozen=True)
class StabilityBand:

    feature: str
    significant_change_pct: float
    min_absolute_change: float
    basis: str
    analytical_cv_pct: Optional[float] = None
    within_subject_cv_pct: Optional[float] = None


RCV_Z = 1.96
RCV_MULTIPLIER = 2.7718585822512662


def reference_change_value(analytical_cv: float, within_subject_cv: float) -> float:
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
    "hematocrit": StabilityBand(
        "hematocrit",
        significant_change_pct=9.0,
        min_absolute_change=1.0,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=2.8,
        basis=(
            "⚠ A PROXY, AND SAID SO. Haematocrit has NO ROW in "
            "app/data/lab_variation.py and therefore no cited CVi of its own. "
            "The haemoglobin band is reused because haematocrit tracks "
            "haemoglobin at approximately 3x and their published CVI are "
            "close -- but that is a REASONED SUBSTITUTION, not a measurement, "
            "and it is the first thing to replace if a haematocrit row is "
            "ever added. CVa 1.5 %, CVi 2.8 % -> RCV 8.8 %, taken as 9 %. "
            "Absolute floor 1.0 percentage point."
        ),
    ),
    "rbc_count": StabilityBand(
        "rbc_count",
        significant_change_pct=8.0,
        min_absolute_change=0.1,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=2.6,
        basis=(
            _RCV_NOTE + " CVa 1.5 %, CVi 2.6 % (EFLM median, via "
            "app/data/lab_variation.py) -> RCV 8.3 %, taken as 8 %. Absolute "
            "floor 0.1 x10^6/uL, the usual reporting increment."
        ),
    ),
    "mcv": StabilityBand(
        "mcv",
        significant_change_pct=3.5,
        min_absolute_change=1.0,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=0.8,
        basis=(
            _RCV_NOTE + " CVa 1.0 %, CVi 0.8 % (EFLM median) -> RCV 3.5 %. "
            "⚠ THIS IS THE TIGHTEST BAND IN THE FILE and it has already moved "
            "a verdict: §6bb records `MCV 85.1 -> 88.6 fl`, a 4.1 % change, "
            "reading `stable` under the old 4.8 % threshold and `rose` under "
            "this one. The 1.0 fL absolute floor exists so that a single "
            "reporting increment cannot alone clear a band this narrow."
        ),
    ),
    "mch": StabilityBand(
        "mch",
        significant_change_pct=3.5,
        min_absolute_change=0.5,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=0.8,
        basis=(
            _RCV_NOTE + " CVa 1.0 %, CVi 0.8 % (EFLM median) -> RCV 3.5 %. "
            "Absolute floor 0.5 pg."
        ),
    ),
    "mchc": StabilityBand(
        "mchc",
        significant_change_pct=4.0,
        min_absolute_change=0.5,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=1.0,
        basis=(
            _RCV_NOTE + " CVa 1.0 %, CVi 1.0 % (EFLM median) -> RCV 3.9 %, "
            "taken as 4 %. Absolute floor 0.5 g/dL. NOTE that a change "
            "clearing this band is as likely to be a sample artefact as a "
            "physiological event -- see the polarity row."
        ),
    ),
    "wbc_count": StabilityBand(
        "wbc_count",
        significant_change_pct=32.0,
        min_absolute_change=0.5,
        analytical_cv_pct=3.0,
        within_subject_cv_pct=11.1,
        basis=(
            _RCV_NOTE + " CVa 3.0 %, CVi 11.1 % (EFLM median) -> RCV 31.9 %, "
            "taken as 32 %. A WIDE band, and correctly so: the white cell "
            "count genuinely swings with infection, stress and time of day, "
            "so a small change carries little information."
        ),
    ),
    "neutrophils": StabilityBand(
        "neutrophils",
        significant_change_pct=36.0,
        min_absolute_change=1.0,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=12.5,
        basis=(
            _RCV_NOTE + " CVa 4.0 %, CVi 12.5 % (EFLM median) -> RCV 36.4 %, "
            "taken as 36 %. Absolute floor 1 percentage point, the reporting "
            "increment on the reports this service reads."
        ),
    ),
    "lymphocytes": StabilityBand(
        "lymphocytes",
        significant_change_pct=30.0,
        min_absolute_change=1.0,
        analytical_cv_pct=3.0,
        within_subject_cv_pct=10.5,
        basis=(
            _RCV_NOTE + " CVa 3.0 %, CVi 10.5 % (EFLM median) -> RCV 30.2 %, "
            "taken as 30 %."
        ),
    ),
    "monocytes": StabilityBand(
        "monocytes",
        significant_change_pct=41.0,
        min_absolute_change=1.0,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=14.0,
        basis=(
            _RCV_NOTE + " CVa 5.0 %, CVi 14.0 % (EFLM median) -> RCV 41.2 %, "
            "taken as 41 %."
        ),
    ),
    "eosinophils": StabilityBand(
        "eosinophils",
        significant_change_pct=44.0,
        min_absolute_change=1.0,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=15.1,
        basis=(
            _RCV_NOTE + " CVa 5.0 %, CVi 15.1 % (EFLM median) -> RCV 44.1 %, "
            "taken as 44 %. ⚠ §6bb RECORDS WHY THIS NUMBER MATTERS: the "
            "PREVIOUS figure gave a 59.8 % threshold against a 60.0 % change "
            "on the owner's own two reports -- a margin of two tenths of a "
            "point -- so `EOSINOPHILS 5 -> 2` read `stable` on one request "
            "and was refused on the next. The published median takes it off "
            "that knife edge."
        ),
    ),
    "basophils": StabilityBand(
        "basophils",
        significant_change_pct=45.0,
        min_absolute_change=0.3,
        analytical_cv_pct=10.0,
        within_subject_cv_pct=12.6,
        basis=(
            _RCV_NOTE + " CVa 10.0 %, CVi 12.6 % (EFLM median) -> RCV 44.6 %, "
            "taken as 45 %. ⚠ THE ABSOLUTE FLOOR IS DOING MOST OF THE WORK "
            "HERE: basophils run at roughly 0-2 % and are reported to one "
            "decimal place, so a 45 % relative change can be two reporting "
            "increments. 0.3 percentage points is a reviewer judgement chosen "
            "so that 0.5 -> 0.7 is not announced as a trend."
        ),
    ),
    "platelet_count": StabilityBand(
        "platelet_count",
        significant_change_pct=23.0,
        min_absolute_change=10.0,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=7.3,
        basis=(
            _RCV_NOTE + " CVa 4.0 %, CVi 7.3 % (EFLM median) -> RCV 23.1 %, "
            "taken as 23 %. Absolute floor 10 x10^3/uL."
        ),
    ),
    "alt": StabilityBand(
        "alt",
        significant_change_pct=29.0,
        min_absolute_change=3.0,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=9.6,
        basis=(
            _RCV_NOTE + " CVa 4.0 %, CVi 9.6 % (EFLM biological variation "
            "database, adult) -> RCV 28.8 %, taken as 29 %. Absolute floor "
            "3 U/L."
        ),
    ),
    "ast": StabilityBand(
        "ast",
        significant_change_pct=29.0,
        min_absolute_change=3.0,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=9.5,
        basis=(
            _RCV_NOTE + " CVa 4.0 %, CVi 9.5 % (EFLM biological variation "
            "database, adult) -> RCV 28.6 %, taken as 29 %. Absolute floor "
            "3 U/L."
        ),
    ),
    "bilirubin_total": StabilityBand(
        "bilirubin_total",
        significant_change_pct=62.0,
        min_absolute_change=0.1,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=21.8,
        basis=(
            _RCV_NOTE + " CVa 5.0 %, CVi 21.8 % (EFLM biological variation "
            "database) -> RCV 62.0 %, taken as 62 %. Bilirubin varies a lot "
            "from day to day in the same person. Absolute floor 0.1 mg/dL."
        ),
    ),
}


def polarity_for(feature: str) -> Optional[TrendPolarity]:
    return POLARITY.get(feature)


SIDE_BELOW = "below"
SIDE_ABOVE = "above"

SIDES: Tuple[str, ...] = (SIDE_BELOW, SIDE_ABOVE)


def harm_declared_beyond(feature: str, side: str) -> Optional[bool]:
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    entry = POLARITY.get(feature)
    if entry is None:
        return None
    if entry.kind == POLARITY_MONOTONE:
        if entry.direction_of_harm == HARM_INCREASE:
            return side == SIDE_ABOVE
        if entry.direction_of_harm == HARM_DECREASE:
            return side == SIDE_BELOW
        return None
    if entry.kind == POLARITY_TOWARD_REFERENCE:
        if side == SIDE_BELOW:
            return entry.optimal_low is not None
        return entry.optimal_high is not None
    return None


def stability_for(feature: str) -> Optional[StabilityBand]:
    return STABILITY.get(feature)


def _self_check() -> None:
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
        else:
            if entry.direction_of_harm is not None or entry.optimal_low is not None:
                raise ValueError(
                    f"{name}: UNDECLARED must not carry a polarity parameter"
                )

        if not numeric and entry.trendable:
            raise ValueError(
                f"{name}: value_type {definition.value_type!r} cannot be trendable"
            )

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
