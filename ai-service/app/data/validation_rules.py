"""Module 6 validation rules -- the CLINICIAN-AUDITABLE data file.

Everything a reviewer needs in order to answer "is this bound right?" lives
here, in plain tables, with no control flow. `app/services/validator.py`
contains the logic; this file contains the medicine.

--------------------------------------------------------------------------
THE CENTRAL DISTINCTION: implausible vs. abnormal
--------------------------------------------------------------------------

Module 5 answers "what feature is this, and in what canonical unit?".
Module 6 answers "is this value BELIEVABLE?".

It does NOT answer "is this value healthy?" -- that is Module 8 (clinical
rules) and Modules 10-12 (ML). Rejecting a value for being abnormal would
destroy the product: abnormal findings are the entire reason it exists.

So every numeric feature carries TWO bands, and they mean different things:

  1. POSSIBLE band  (`possible_low` .. `possible_high`)
     The range of values a living human being can actually have, taken
     generously -- the extremes of the published case-report literature, not
     the extremes of everyday practice. A value OUTSIDE this band is not a
     sick patient; it is almost certainly an OCR misread, a misplaced decimal
     point, or a unit that was silently wrong. Such a value is REJECTED.
     The bands are deliberately WIDE. A wrong rejection deletes a real
     finding, which is the more dangerous error, so where the literature was
     ambiguous the band was widened, not narrowed.

  2. EXTREME band   (`extreme_low` .. `extreme_high`)
     Inside the possible band, but far enough from normal that the value is a
     genuine clinical emergency or near-emergency. Values beyond these
     thresholds are VALID AND FULLY USABLE -- they are merely tagged
     `clinically_extreme` so that Module 8 and the report can prioritise them.
     `None` on either side means "no extreme threshold is meaningful for this
     feature".

The worked example from the specification:

    blood_glucose = 400 mg/dL   -> inside possible (5 .. 3000), beyond
                                   extreme_high (400) -> VALID, flagged
                                   `clinically_extreme`. It is a real, and
                                   serious, diabetic reading.
    blood_glucose = 40000 mg/dL -> outside possible -> REJECTED as
                                   `IMPLAUSIBLE_VALUE_HIGH`. No human has ever
                                   had this; an OCR run of digits did.

Bounds are stated in the CANONICAL unit of `app/data/feature_catalog.py`.
Every bound cites its basis in a comment. Where a bound is a judgement call
rather than a documented physiological limit, the comment says so.

--------------------------------------------------------------------------
WHAT IS NEVER DONE HERE
--------------------------------------------------------------------------

* No value is ever repaired, rescaled, clamped or guessed. A value is either
  passed through untouched, flagged untouched, or rejected untouched. If a
  glucose looks like a mmol/L number printed as mg/dL, we do NOT convert it --
  we reject it and say why. Silently "fixing" a value is how a wrong number
  acquires false authority.
* No default is ever substituted for a missing value. Absent stays absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.data.feature_catalog import FEATURES

# --------------------------------------------------------------------------
# Reason codes -- stable, machine-readable, consumed by Modules 8, 17 and 20
# --------------------------------------------------------------------------


class RejectionCode:
    """Why a feature was excluded from the usable set.

    A rejected feature is NEVER deleted: it is returned with its original
    value and full provenance so Module 20 can explain the exclusion.
    """

    #: The printed unit was not recognised, so Module 5 did NOT convert the
    #: value (`canonical_unit: false`). Its magnitude is therefore meaningless
    #: and no range check can be applied to it. This is the explicit
    #: unit-consistency rejection.
    NON_CANONICAL_UNIT = "NON_CANONICAL_UNIT"

    #: The unit is marked canonical but does not match the catalog's canonical
    #: unit for the feature. Should be unreachable via Module 5; kept because
    #: a silent unit mismatch is the single most dangerous failure available.
    UNIT_MISMATCH = "UNIT_MISMATCH"

    #: A numeric feature arrived carrying something that is not a number
    #: (string, bool, null).
    NOT_A_NUMBER = "NOT_A_NUMBER"

    #: NaN or +/-Infinity.
    NON_FINITE_VALUE = "NON_FINITE_VALUE"

    #: An integer feature (`age`) arrived with a fractional value.
    NOT_AN_INTEGER = "NOT_AN_INTEGER"

    #: A tri-state boolean arrived as something other than true/false.
    #: NOTE: this is for a PRESENT but malformed value. An ABSENT tri-state is
    #: not an error at all -- it means UNKNOWN and stays unknown.
    NOT_A_BOOLEAN = "NOT_A_BOOLEAN"

    #: A categorical feature arrived with a token outside its vocabulary.
    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"

    #: Below the physiologically possible band -- a suspected extraction error.
    IMPLAUSIBLE_VALUE_LOW = "IMPLAUSIBLE_VALUE_LOW"

    #: Above the physiologically possible band -- a suspected extraction error.
    IMPLAUSIBLE_VALUE_HIGH = "IMPLAUSIBLE_VALUE_HIGH"

    #: The feature key is not in the canonical catalog.
    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"


class FlagCode:
    """Why a feature is usable but should be treated with less confidence,
    or is usable and clinically urgent.

    A flag NEVER removes a feature from the usable set.
    """

    #: No unit was printed; Module 5 assumed the canonical one. A value that
    #: is plausible in the assumed unit may be absurd in the real one, so the
    #: range check that just passed is weaker than it looks.
    UNIT_ASSUMED = "UNIT_ASSUMED"

    #: A '<x' / '>x' result held at its stated detection limit. The true value
    #: is on one side of the reported number, not equal to it.
    CENSORED_VALUE = "CENSORED_VALUE"

    #: Not read from the report; computed by an earlier stage (e.g. Module 5's
    #: BMI fallback from height and weight).
    DERIVED_VALUE = "DERIVED_VALUE"

    #: Module 4 reported low confidence in the row this value came from.
    LOW_EXTRACTION_CONFIDENCE = "LOW_EXTRACTION_CONFIDENCE"

    #: The value is attributed to a page Module 4 reported as UNREADABLE --
    #: self-contradictory, so the attribution or the value is unreliable.
    #: NOTE this is deliberately per-page, not per-document: an unreadable page
    #: elsewhere does not make a cleanly-read row less trustworthy. That is a
    #: document-level warning, and its real consequence is that an ABSENT
    #: feature may be UNREAD rather than absent.
    PARTIAL_DOCUMENT = "PARTIAL_DOCUMENT"

    #: Inside the possible band but beyond the extreme threshold. VALID AND
    #: USABLE -- this is a prioritisation signal, not a data-quality doubt.
    CLINICALLY_EXTREME_LOW = "CLINICALLY_EXTREME_LOW"
    CLINICALLY_EXTREME_HIGH = "CLINICALLY_EXTREME_HIGH"


#: Flags that make a feature `questionable` (usable, but its trustworthiness is
#: degraded). The two CLINICALLY_EXTREME codes are deliberately NOT here: an
#: extreme value is a fully trusted value that happens to be alarming.
QUESTIONABLE_FLAGS: Tuple[str, ...] = (
    FlagCode.UNIT_ASSUMED,
    FlagCode.CENSORED_VALUE,
    FlagCode.DERIVED_VALUE,
    FlagCode.LOW_EXTRACTION_CONFIDENCE,
    FlagCode.PARTIAL_DOCUMENT,
)

#: Module 4 row confidence at or below this raises LOW_EXTRACTION_CONFIDENCE.
#: Mirrors `Settings.low_confidence_threshold` (0.6) but is kept here as a
#: plain constant so `validate_features()` stays framework-independent.
LOW_CONFIDENCE_THRESHOLD: float = 0.6


# --------------------------------------------------------------------------
# The rule table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationRule:
    """Validation rules for one canonical feature.

    `possible_low` / `possible_high` -- the physiologically possible band.
        Outside it the value is treated as an extraction error and REJECTED.
    `extreme_low` / `extreme_high` -- the critical-but-real thresholds.
        Beyond them the value is VALID and additionally tagged
        `clinically_extreme`. `None` = no meaningful threshold on that side.
    `basis` -- the clinical justification, shown to reviewers and carried into
        the rejection message so a clinician can challenge it.
    """

    feature: str
    value_type: str  # "number" | "integer" | "boolean" | "category"
    unit: Optional[str]
    possible_low: Optional[float] = None
    possible_high: Optional[float] = None
    extreme_low: Optional[float] = None
    extreme_high: Optional[float] = None
    basis: str = ""

    @property
    def is_numeric(self) -> bool:
        return self.value_type in ("number", "integer")


RULES: Dict[str, ValidationRule] = {
    # ------------------------------------------------------------- hba1c --
    "hba1c": ValidationRule(
        "hba1c",
        "number",
        "%",
        # POSSIBLE 2.0 - 25.0 %NGSP.
        #   Low bound: HbA1c is a fraction of total haemoglobin and is never
        #   zero in a living person; values below ~3 % are seen only in
        #   haemolysis/haemoglobinopathy artefact. 2.0 leaves room for those.
        #   High bound: the highest values reported in the literature for
        #   untreated diabetes sit around 18-20 %; assay linearity typically
        #   tops out near 20 %. 25 gives generous headroom.
        #   A printed IFCC value (mmol/mol, e.g. 48-120) that was NOT converted
        #   lands above 25 and is correctly rejected rather than read as a
        #   percentage.
        possible_low=2.0,
        possible_high=25.0,
        # EXTREME: >= 10 % is very poor long-term control (ADA target < 7 %,
        #   > 10 % is the usual "urgent review" threshold). A low HbA1c is not
        #   itself an emergency, so there is no extreme_low.
        extreme_high=10.0,
        basis="NGSP %. Assay linearity and reported clinical extremes; "
        "ADA glycaemic-control thresholds for the extreme band.",
    ),
    # ----------------------------------------------------- blood_glucose --
    "blood_glucose": ValidationRule(
        "blood_glucose",
        "number",
        "mg/dl",
        # POSSIBLE 5 - 3000 mg/dL.
        #   Low bound: survival has been documented at plasma glucose in the
        #   single digits (severe insulin overdose); below 5 mg/dL is not
        #   compatible with a measurable living sample.
        #   High bound: the highest survived blood glucose on record is
        #   ~2656 mg/dL (Guinness-recorded case, 2008); hyperosmolar states
        #   commonly reach 1000-1500. 3000 sits just above the record.
        #   40000 mg/dL -- the spec's worked example -- is far outside and is
        #   rejected as an extraction error.
        possible_low=5.0,
        possible_high=3000.0,
        # EXTREME: <= 54 mg/dL is ADA "level 2" clinically significant
        #   hypoglycaemia. >= 400 mg/dL is a very common laboratory critical
        #   high and the spec's named valid-but-extreme case.
        extreme_low=54.0,
        extreme_high=400.0,
        basis="mg/dL. ADA level-2 hypoglycaemia (54) and the conventional "
        "laboratory critical high (400); possible band from documented "
        "survival extremes.",
    ),
    # -------------------------------------------------------- hemoglobin --
    "hemoglobin": ValidationRule(
        "hemoglobin",
        "number",
        "g/dl",
        # POSSIBLE 1.0 - 30.0 g/dL.
        #   Low bound: survival with Hb between 1.5 and 2 g/dL is documented
        #   (Jehovah's Witness case series). 1.0 is below any reported survivor
        #   and so is a safe floor.
        #   High bound: extreme polycythaemia vera / high-altitude chronic
        #   mountain sickness reach 24-26 g/dL. 30 gives headroom.
        #   A g/L value (e.g. 142) printed without a unit would exceed 30 and
        #   be rejected rather than read as 142 g/dL.
        possible_low=1.0,
        possible_high=30.0,
        # EXTREME: <= 7 g/dL is the usual transfusion trigger in stable adults;
        #   >= 20 g/dL warrants urgent haematology review.
        extreme_low=7.0,
        extreme_high=20.0,
        basis="g/dL. Restrictive-transfusion threshold (7) and polycythaemia "
        "review threshold (20); possible band from documented survival and "
        "polycythaemia extremes.",
    ),
    # --------------------------------------------------------- vitamin_d --
    "vitamin_d": ValidationRule(
        "vitamin_d",
        "number",
        "ng/ml",
        # POSSIBLE 0.0 - 400.0 ng/mL.
        #   Low bound: 25-OH vitamin D can be genuinely undetectable, and many
        #   assays report "< 3" or 0. Zero is a real result, not an error.
        #   High bound: intoxication case reports run to 150-400 ng/mL after
        #   massive supplementation. 400 covers them.
        #   An nmol/L result (typically 25-250) that was NOT converted falls
        #   INSIDE this band -- which is exactly why an unrecognised unit is a
        #   rejection in its own right and never leans on the range check.
        possible_low=0.0,
        possible_high=400.0,
        # EXTREME: <= 10 ng/mL is severe deficiency (rickets/osteomalacia
        #   risk); >= 100 ng/mL is the usual "potential toxicity" threshold.
        extreme_low=10.0,
        extreme_high=100.0,
        basis="ng/mL. Endocrine Society severe-deficiency (<10) and potential-"
        "toxicity (>100) thresholds; possible band from intoxication reports.",
    ),
    # ------------------------------------------------------- vitamin_b12 --
    "vitamin_b12": ValidationRule(
        "vitamin_b12",
        "number",
        "pg/ml",
        # POSSIBLE 0.0 - 50000.0 pg/mL.
        #   Low bound: severe pernicious anaemia can read below the assay
        #   floor; 0 is reported.
        #   High bound: values in the tens of thousands are documented after
        #   parenteral B12, and in liver disease and myeloproliferative
        #   disorders. 50000 is deliberately generous -- a wrongly rejected
        #   B12 is worse than a wrongly accepted high one.
        possible_low=0.0,
        possible_high=50000.0,
        # EXTREME: <= 150 pg/mL is frank deficiency. No high threshold: a high
        #   B12 is a workup trigger, not an emergency value, and setting one
        #   would flag every post-injection patient.
        extreme_low=150.0,
        basis="pg/mL. Conventional deficiency cut-off (150); possible band "
        "deliberately wide to cover post-injection and hepatic elevations.",
    ),
    # -------------------------------------------------------- creatinine --
    "creatinine": ValidationRule(
        "creatinine",
        "number",
        "mg/dl",
        # POSSIBLE 0.05 - 40.0 mg/dL.
        #   Low bound: very low creatinine occurs with severe muscle wasting,
        #   advanced liver disease and pregnancy; 0.05 is below any plausible
        #   living value but is not zero, because an exactly-zero serum
        #   creatinine is not a real measurement.
        #   High bound: untreated end-stage renal failure and rhabdomyolysis
        #   reach 20-30 mg/dL; isolated reports exceed 30. 40 gives headroom.
        #   A umol/L result (60-1200) that was NOT converted exceeds 40 and is
        #   rejected rather than read as mg/dL.
        possible_low=0.05,
        possible_high=40.0,
        # EXTREME: >= 5.0 mg/dL indicates severe renal impairment needing
        #   urgent attention. No extreme_low: a low creatinine is not urgent.
        extreme_high=5.0,
        basis="mg/dL. Severe-renal-impairment threshold (5.0); possible band "
        "from untreated ESRD and rhabdomyolysis extremes.",
    ),
    # ------------------------------------------------------- cholesterol --
    "cholesterol": ValidationRule(
        "cholesterol",
        "number",
        "mg/dl",
        # POSSIBLE 20.0 - 2000.0 mg/dL. (TOTAL cholesterol.)
        #   Low bound: abetalipoproteinaemia and severe liver failure produce
        #   total cholesterol in the 20-50 range.
        #   High bound: homozygous familial hypercholesterolaemia and severe
        #   secondary hyperlipidaemia reach 700-1000+; lipaemic samples higher
        #   still. 2000 is generous by design.
        #   NOTE (corrected by integration audit 2026-08-29): an earlier version
        #   of this comment claimed an unconverted mmol/L value (3-8) falls
        #   INSIDE this band. It does NOT -- possible_low is 20.0, so 3-8 is
        #   rejected as IMPLAUSIBLE_VALUE_LOW. Cholesterol is therefore a BAD
        #   example of the point. The point itself still stands, and the real
        #   examples are VITAMIN D (25-250 nmol/L sits inside 0-400 ng/mL) and
        #   BLOOD GLUCOSE (5.5-30 mmol/L sits inside 5-3000 mg/dL): for those,
        #   a range check CANNOT catch the unit error, which is exactly why
        #   `canonical_unit: false` is an unconditional rejection rather than
        #   something the range check is expected to mop up.
        possible_low=20.0,
        possible_high=2000.0,
        # EXTREME: >= 400 mg/dL suggests a severe primary lipid disorder
        #   needing specialist referral. No extreme_low -- a low total
        #   cholesterol is a workup finding, not an emergency.
        extreme_high=400.0,
        basis="mg/dL, TOTAL cholesterol. Severe-hypercholesterolaemia referral "
        "threshold (400); possible band from homozygous FH and "
        "abetalipoproteinaemia extremes.",
    ),
    # ----------------------------------------------------- triglycerides --
    "triglycerides": ValidationRule(
        "triglycerides",
        "number",
        "mg/dl",
        # POSSIBLE 5.0 - 20000.0 mg/dL.
        #   Low bound: values below 10 occur in abetalipoproteinaemia and
        #   severe malnutrition; 5 is a safe floor.
        #   High bound: severe hypertriglyceridaemia case reports exceed
        #   15000 mg/dL. 20000 covers the published extremes.
        possible_low=5.0,
        possible_high=20000.0,
        # EXTREME: >= 1000 mg/dL is the acute-pancreatitis risk threshold and
        #   is genuinely urgent. No extreme_low.
        extreme_high=1000.0,
        basis="mg/dL. Pancreatitis-risk threshold (1000); possible band from "
        "published severe-hypertriglyceridaemia case reports.",
    ),
    # --------------------------------------------------------------- bmi --
    "bmi": ValidationRule(
        "bmi",
        "number",
        "kg/m2",
        # POSSIBLE 8.0 - 200.0 kg/m2.
        #   Low bound: the lowest BMIs recorded in survivors of severe anorexia
        #   nervosa and famine are around 9-10. 8 sits just below.
        #   High bound: the heaviest recorded human corresponds to a BMI near
        #   186. 200 sits just above.
        possible_low=8.0,
        possible_high=200.0,
        # EXTREME: <= 15 is a judgement-call priority threshold set just BELOW
        # WHO severe thinness (which is BMI < 16.0), not equal to it; >= 40 is
        # WHO obesity class III. (Citation corrected: Module 8's audit of this
        # table caught the original comment misstating the WHO severe-thinness
        # cut-off as 15. The BOUND is deliberate and unchanged -- only the
        # justification was wrong.)
        extreme_low=15.0,
        extreme_high=40.0,
        basis="kg/m2. Priority threshold <=15 (just below WHO severe thinness, which is <16.0) and WHO obesity class III (>=40); "
        "possible band from recorded human extremes.",
    ),
    # --------------------------------------------------------------- age --
    "age": ValidationRule(
        "age",
        "integer",
        "years",
        # POSSIBLE 0 - 125 years.
        #   The oldest verified human lifespan is 122 years. 125 sits above it.
        #   0 is valid: a neonate has age 0 in whole years.
        possible_low=0.0,
        possible_high=125.0,
        # NO extreme band. Age is demographic, not a laboratory measurement;
        # flagging every very old patient as "clinically extreme" would be
        # noise, and Module 8's rules apply their own age thresholds.
        basis="Whole years. Oldest verified human lifespan (122). No extreme "
        "band: age is demographic context, not a critical result.",
    ),
    # ------------------------------------------------------ hypertension --
    "hypertension": ValidationRule(
        "hypertension",
        "boolean",
        None,
        basis="TRI-STATE. Only true/false are valid PRESENT values. ABSENT "
        "means UNKNOWN and is not an error and never becomes false.",
    ),
    # ----------------------------------------------------- heart_disease --
    "heart_disease": ValidationRule(
        "heart_disease",
        "boolean",
        None,
        basis="TRI-STATE. Only true/false are valid PRESENT values. ABSENT "
        "means UNKNOWN and is not an error and never becomes false.",
    ),
    # --------------------------------------------------- smoking_history --
    "smoking_history": ValidationRule(
        "smoking_history",
        "category",
        None,
        basis="Validated against Module 2's diabetes-dataset vocabulary "
        "(never/former/current/ever/not_current/no_info). Note 'no_info' is a "
        "legitimate stored category, distinct from the feature being absent.",
    ),
    # ------------------------------------------------------------ gender --
    "gender": ValidationRule(
        "gender",
        "category",
        None,
        basis="Validated against Module 2's stored vocabulary "
        "(male/female/other/prefer_not_to_say). The stored answer is never "
        "coerced into a binary; narrowing for a binary model is the ML "
        "layer's problem, not validation's.",
    ),
    # ==================== the complete blood count ==========================
    #
    # THE POSSIBLE BANDS ARE WIDER THAN ANY REFERENCE INTERVAL, DELIBERATELY.
    # `possible_*` asks "could a living person's report really say this?", not
    # "is this healthy" -- that is Module 8's question. A band drawn at the
    # reference interval would REJECT the abnormal results this platform
    # exists to explain, and a rejected value is not shown at all.
    #
    # The observed NHANES 2017-2018 range is quoted in each note as a floor
    # for plausibility, never as the bound itself: NHANES is a household
    # survey of ambulatory adults and systematically under-samples exactly
    # the extremes a hospital report shows.
    # -------------------------------------------------------- hematocrit --
    "hematocrit": ValidationRule(
        "hematocrit",
        "number",
        "%",
        # POSSIBLE 5 - 75 %.
        #   Low: haematocrit tracks haemoglobin at roughly 3x, so the 2 g/dL
        #   survivable haemoglobin floor corresponds to about 6 %.
        #   High: polycythaemia vera and severe dehydration reach the 60s;
        #   75 leaves headroom without admitting a percentage over 100.
        #   NHANES observed 23.0 - 58.8.
        possible_low=5.0,
        possible_high=75.0,
        extreme_low=20.0,
        extreme_high=60.0,
        basis="Tracks haemoglobin at approximately 3x. Extremes set at the "
        "transfusion-consideration and hyperviscosity thresholds. Printed as "
        "PCV on most Indian reports.",
    ),
    # --------------------------------------------------------- rbc_count --
    "rbc_count": ValidationRule(
        "rbc_count",
        "number",
        "10^6/ul",
        # POSSIBLE 0.5 - 12.0 x10^6/uL. NHANES observed 2.32 - 7.84.
        possible_low=0.5,
        possible_high=12.0,
        extreme_low=2.0,
        extreme_high=8.0,
        basis="Severe anaemia and polycythaemia bound the possible band. A "
        "count printed in 10^12/L is NUMERICALLY IDENTICAL to 10^6/uL, so a "
        "unit mix-up between those two is invisible here and harmless.",
    ),
    # --------------------------------------------------------------- mcv --
    "mcv": ValidationRule(
        "mcv",
        "number",
        "fl",
        # POSSIBLE 40 - 150 fL. NHANES observed 35.4 - 114.6.
        #   Severe thalassaemia reaches the 50s; B12 deficiency and
        #   myelodysplasia reach the 120s-130s.
        possible_low=40.0,
        possible_high=150.0,
        extreme_low=65.0,
        extreme_high=115.0,
        basis="Microcytosis and macrocytosis bound the band. An INDEX rather "
        "than a severity measure: neither end is 'better'.",
    ),
    # --------------------------------------------------------------- mch --
    "mch": ValidationRule(
        "mch",
        "number",
        "pg",
        # POSSIBLE 10 - 60 pg. NHANES observed 12.4 - 39.2.
        possible_low=10.0,
        possible_high=60.0,
        extreme_low=20.0,
        extreme_high=40.0,
        basis="Derived from haemoglobin and red cell count, so its band "
        "follows theirs.",
    ),
    # -------------------------------------------------------------- mchc --
    "mchc": ValidationRule(
        "mchc",
        "number",
        "g/dl",
        # POSSIBLE 20 - 50 g/dL. NHANES observed 25.2 - 38.3.
        #   MCHC is the TIGHTEST of the red cell indices: haemoglobin cannot
        #   be packed into a red cell beyond about 37 g/dL, so a value above
        #   that is usually an artefact rather than a physiological state.
        possible_low=20.0,
        possible_high=50.0,
        extreme_low=28.0,
        extreme_high=37.0,
        basis="Solubility of haemoglobin bounds the upper end. A raised MCHC "
        "is more often lipaemia, haemolysis or cold agglutinins than a real "
        "finding. `%` and `g/dL` are the same scale for MCHC -- see "
        "backend/src/services/unitEquivalence.js and the conditions it names.",
    ),
    # --------------------------------------------------------- wbc_count --
    "wbc_count": ValidationRule(
        "wbc_count",
        "number",
        "10^3/ul",
        # POSSIBLE 0.1 - 500 x10^3/uL. NHANES observed 1.9 - 400.0 -- the 400
        #   is real and is why the upper bound is not drawn at 100.
        possible_low=0.1,
        possible_high=500.0,
        extreme_low=2.0,
        extreme_high=30.0,
        basis="Agranulocytosis bounds the low end; leukaemic counts in the "
        "hundreds bound the high end, and NHANES itself contains a 400. "
        "10^3/uL and 10^9/L are numerically identical.",
    ),
    # ------------------------------------------------------- neutrophils --
    # THE FIVE DIFFERENTIALS ARE PERCENTAGES, SO 0-100 IS THE HARD BAND.
    # A value above 100 is an extraction error, not a rare result, and the
    # absolute-count form of the same analyte would land there constantly --
    # which is the point of rejecting it.
    "neutrophils": ValidationRule(
        "neutrophils",
        "number",
        "%",
        possible_low=0.0,
        possible_high=100.0,
        extreme_low=10.0,
        extreme_high=90.0,
        basis="A percentage of the white cell count, so bounded by 0 and 100 "
        "by definition. NHANES observed 8.4 - 92.8.",
    ),
    # ------------------------------------------------------- lymphocytes --
    "lymphocytes": ValidationRule(
        "lymphocytes",
        "number",
        "%",
        possible_low=0.0,
        possible_high=100.0,
        extreme_low=5.0,
        extreme_high=90.0,
        basis="A percentage of the white cell count. NHANES observed "
        "4.4 - 89.7.",
    ),
    # --------------------------------------------------------- monocytes --
    "monocytes": ValidationRule(
        "monocytes",
        "number",
        "%",
        possible_low=0.0,
        possible_high=100.0,
        extreme_high=30.0,
        basis="A percentage of the white cell count. NHANES observed "
        "0.7 - 57.2. No low extreme: a monocyte percentage near zero is "
        "common and is not itself a critical finding.",
    ),
    # ------------------------------------------------------- eosinophils --
    "eosinophils": ValidationRule(
        "eosinophils",
        "number",
        "%",
        possible_low=0.0,
        possible_high=100.0,
        extreme_high=20.0,
        basis="A percentage of the white cell count. NHANES observed "
        "0.0 - 29.1, and zero is an ordinary result, so there is no low "
        "extreme.",
    ),
    # --------------------------------------------------------- basophils --
    "basophils": ValidationRule(
        "basophils",
        "number",
        "%",
        possible_low=0.0,
        possible_high=100.0,
        extreme_high=5.0,
        basis="A percentage of the white cell count. NHANES observed "
        "0.1 - 4.8. Zero is an ordinary result, so there is no low extreme.",
    ),
    # ---------------------------------------------------- platelet_count --
    "platelet_count": ValidationRule(
        "platelet_count",
        "number",
        "10^3/ul",
        # POSSIBLE 1 - 3000 x10^3/uL. NHANES observed 8 - 818.
        possible_low=1.0,
        possible_high=3000.0,
        extreme_low=50.0,
        extreme_high=1000.0,
        basis="Extremes set at the usual bleeding-risk threshold and at the "
        "threshold for extreme thrombocytosis. 10^3/uL and 10^9/L are "
        "numerically identical, so a report printing either maps correctly.",
    ),
}


def rule_for(feature: str) -> Optional[ValidationRule]:
    """The rule for a canonical feature, or None if the name is unknown."""
    return RULES.get(feature)


def _self_check() -> None:
    """Fail at import time if the rule table and the catalog disagree.

    A feature present in the catalog but missing here would silently escape
    validation entirely -- exactly the failure this module exists to prevent.
    """
    missing = [name for name in FEATURES if name not in RULES]
    if missing:
        raise ValueError(f"features with no validation rule: {missing}")
    extra = [name for name in RULES if name not in FEATURES]
    if extra:
        raise ValueError(f"validation rules for unknown features: {extra}")
    for name, rule in RULES.items():
        definition = FEATURES[name]
        if rule.value_type != definition.value_type:
            raise ValueError(
                f"{name}: rule value_type {rule.value_type!r} != catalog "
                f"{definition.value_type!r}"
            )
        if rule.unit != definition.canonical_unit:
            raise ValueError(
                f"{name}: rule unit {rule.unit!r} != catalog canonical unit "
                f"{definition.canonical_unit!r}"
            )
        if rule.is_numeric:
            if rule.possible_low is None or rule.possible_high is None:
                raise ValueError(f"{name}: numeric feature needs a possible band")
            if rule.possible_low >= rule.possible_high:
                raise ValueError(f"{name}: possible_low >= possible_high")
            # The extreme band must sit INSIDE the possible band, otherwise a
            # value could be "clinically extreme" and "impossible" at once.
            if rule.extreme_low is not None and not (
                rule.possible_low <= rule.extreme_low <= rule.possible_high
            ):
                raise ValueError(f"{name}: extreme_low outside the possible band")
            if rule.extreme_high is not None and not (
                rule.possible_low <= rule.extreme_high <= rule.possible_high
            ):
                raise ValueError(f"{name}: extreme_high outside the possible band")
            if (
                rule.extreme_low is not None
                and rule.extreme_high is not None
                and rule.extreme_low > rule.extreme_high
            ):
                raise ValueError(f"{name}: extreme_low > extreme_high")
        else:
            if rule.possible_low is not None or rule.possible_high is not None:
                raise ValueError(f"{name}: non-numeric feature must not have a band")


_self_check()


def rules_document() -> Dict[str, object]:
    """Machine-readable dump of the rule table, for review and for Module 20."""
    return {
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "questionable_flags": list(QUESTIONABLE_FLAGS),
        "rejection_codes": sorted(
            v for k, v in vars(RejectionCode).items() if not k.startswith("_")
        ),
        "flag_codes": sorted(
            v for k, v in vars(FlagCode).items() if not k.startswith("_")
        ),
        "band_semantics": {
            "possible": "Outside this band the value is treated as an "
            "extraction error and REJECTED. It is not a clinical judgement.",
            "extreme": "Inside the possible band but beyond this threshold: "
            "the value is VALID and usable, and additionally tagged "
            "clinically_extreme for downstream prioritisation.",
        },
        "features": {
            name: {
                "value_type": rule.value_type,
                "unit": rule.unit,
                "possible_low": rule.possible_low,
                "possible_high": rule.possible_high,
                "extreme_low": rule.extreme_low,
                "extreme_high": rule.extreme_high,
                "categories": list(FEATURES[name].categories),
                "basis": rule.basis,
            }
            for name, rule in RULES.items()
        },
    }


__all__ = [
    "FlagCode",
    "LOW_CONFIDENCE_THRESHOLD",
    "QUESTIONABLE_FLAGS",
    "RULES",
    "RejectionCode",
    "ValidationRule",
    "rule_for",
    "rules_document",
]
