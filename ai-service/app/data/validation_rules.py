from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.data.feature_catalog import FEATURES


class RejectionCode:

    NON_CANONICAL_UNIT = "NON_CANONICAL_UNIT"

    UNIT_MISMATCH = "UNIT_MISMATCH"

    NOT_A_NUMBER = "NOT_A_NUMBER"

    NON_FINITE_VALUE = "NON_FINITE_VALUE"

    NOT_AN_INTEGER = "NOT_AN_INTEGER"

    NOT_A_BOOLEAN = "NOT_A_BOOLEAN"

    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"

    IMPLAUSIBLE_VALUE_LOW = "IMPLAUSIBLE_VALUE_LOW"

    IMPLAUSIBLE_VALUE_HIGH = "IMPLAUSIBLE_VALUE_HIGH"

    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"


class FlagCode:

    UNIT_ASSUMED = "UNIT_ASSUMED"

    CENSORED_VALUE = "CENSORED_VALUE"

    DERIVED_VALUE = "DERIVED_VALUE"

    LOW_EXTRACTION_CONFIDENCE = "LOW_EXTRACTION_CONFIDENCE"

    PARTIAL_DOCUMENT = "PARTIAL_DOCUMENT"

    CLINICALLY_EXTREME_LOW = "CLINICALLY_EXTREME_LOW"
    CLINICALLY_EXTREME_HIGH = "CLINICALLY_EXTREME_HIGH"


QUESTIONABLE_FLAGS: Tuple[str, ...] = (
    FlagCode.UNIT_ASSUMED,
    FlagCode.CENSORED_VALUE,
    FlagCode.DERIVED_VALUE,
    FlagCode.LOW_EXTRACTION_CONFIDENCE,
    FlagCode.PARTIAL_DOCUMENT,
)

LOW_CONFIDENCE_THRESHOLD: float = 0.6


@dataclass(frozen=True)
class ValidationRule:

    feature: str
    value_type: str
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
    "hba1c": ValidationRule(
        "hba1c",
        "number",
        "%",
        possible_low=2.0,
        possible_high=25.0,
        extreme_high=10.0,
        basis="NGSP %. Assay linearity and reported clinical extremes; "
        "ADA glycaemic-control thresholds for the extreme band.",
    ),
    "blood_glucose": ValidationRule(
        "blood_glucose",
        "number",
        "mg/dl",
        possible_low=5.0,
        possible_high=3000.0,
        extreme_low=54.0,
        extreme_high=400.0,
        basis="mg/dL. ADA level-2 hypoglycaemia (54) and the conventional "
        "laboratory critical high (400); possible band from documented "
        "survival extremes.",
    ),
    "hemoglobin": ValidationRule(
        "hemoglobin",
        "number",
        "g/dl",
        possible_low=1.0,
        possible_high=30.0,
        extreme_low=7.0,
        extreme_high=20.0,
        basis="g/dL. Restrictive-transfusion threshold (7) and polycythaemia "
        "review threshold (20); possible band from documented survival and "
        "polycythaemia extremes.",
    ),
    "vitamin_d": ValidationRule(
        "vitamin_d",
        "number",
        "ng/ml",
        possible_low=0.0,
        possible_high=400.0,
        extreme_low=10.0,
        extreme_high=100.0,
        basis="ng/mL. Endocrine Society severe-deficiency (<10) and potential-"
        "toxicity (>100) thresholds; possible band from intoxication reports.",
    ),
    "vitamin_b12": ValidationRule(
        "vitamin_b12",
        "number",
        "pg/ml",
        possible_low=0.0,
        possible_high=50000.0,
        extreme_low=150.0,
        basis="pg/mL. Conventional deficiency cut-off (150); possible band "
        "deliberately wide to cover post-injection and hepatic elevations.",
    ),
    "creatinine": ValidationRule(
        "creatinine",
        "number",
        "mg/dl",
        possible_low=0.05,
        possible_high=40.0,
        extreme_high=5.0,
        basis="mg/dL. Severe-renal-impairment threshold (5.0); possible band "
        "from untreated ESRD and rhabdomyolysis extremes.",
    ),
    "cholesterol": ValidationRule(
        "cholesterol",
        "number",
        "mg/dl",
        possible_low=20.0,
        possible_high=2000.0,
        extreme_high=400.0,
        basis="mg/dL, TOTAL cholesterol. Severe-hypercholesterolaemia referral "
        "threshold (400); possible band from homozygous FH and "
        "abetalipoproteinaemia extremes.",
    ),
    "triglycerides": ValidationRule(
        "triglycerides",
        "number",
        "mg/dl",
        possible_low=5.0,
        possible_high=20000.0,
        extreme_high=1000.0,
        basis="mg/dL. Pancreatitis-risk threshold (1000); possible band from "
        "published severe-hypertriglyceridaemia case reports.",
    ),
    "bmi": ValidationRule(
        "bmi",
        "number",
        "kg/m2",
        possible_low=8.0,
        possible_high=200.0,
        extreme_low=15.0,
        extreme_high=40.0,
        basis="kg/m2. Priority threshold <=15 (just below WHO severe thinness, which is <16.0) and WHO obesity class III (>=40); "
        "possible band from recorded human extremes.",
    ),
    "age": ValidationRule(
        "age",
        "integer",
        "years",
        possible_low=0.0,
        possible_high=125.0,
        basis="Whole years. Oldest verified human lifespan (122). No extreme "
        "band: age is demographic context, not a critical result.",
    ),
    "hypertension": ValidationRule(
        "hypertension",
        "boolean",
        None,
        basis="TRI-STATE. Only true/false are valid PRESENT values. ABSENT "
        "means UNKNOWN and is not an error and never becomes false.",
    ),
    "heart_disease": ValidationRule(
        "heart_disease",
        "boolean",
        None,
        basis="TRI-STATE. Only true/false are valid PRESENT values. ABSENT "
        "means UNKNOWN and is not an error and never becomes false.",
    ),
    "smoking_history": ValidationRule(
        "smoking_history",
        "category",
        None,
        basis="Validated against Module 2's diabetes-dataset vocabulary "
        "(never/former/current/ever/not_current/no_info). Note 'no_info' is a "
        "legitimate stored category, distinct from the feature being absent.",
    ),
    "gender": ValidationRule(
        "gender",
        "category",
        None,
        basis="Validated against Module 2's stored vocabulary "
        "(male/female/other/prefer_not_to_say). The stored answer is never "
        "coerced into a binary; narrowing for a binary model is the ML "
        "layer's problem, not validation's.",
    ),
    "hematocrit": ValidationRule(
        "hematocrit",
        "number",
        "%",
        possible_low=5.0,
        possible_high=75.0,
        extreme_low=20.0,
        extreme_high=60.0,
        basis="Tracks haemoglobin at approximately 3x. Extremes set at the "
        "transfusion-consideration and hyperviscosity thresholds. Printed as "
        "PCV on most Indian reports.",
    ),
    "rbc_count": ValidationRule(
        "rbc_count",
        "number",
        "10^6/ul",
        possible_low=0.5,
        possible_high=12.0,
        extreme_low=2.0,
        extreme_high=8.0,
        basis="Severe anaemia and polycythaemia bound the possible band. A "
        "count printed in 10^12/L is NUMERICALLY IDENTICAL to 10^6/uL, so a "
        "unit mix-up between those two is invisible here and harmless.",
    ),
    "mcv": ValidationRule(
        "mcv",
        "number",
        "fl",
        possible_low=40.0,
        possible_high=150.0,
        extreme_low=65.0,
        extreme_high=115.0,
        basis="Microcytosis and macrocytosis bound the band. An INDEX rather "
        "than a severity measure: neither end is 'better'.",
    ),
    "mch": ValidationRule(
        "mch",
        "number",
        "pg",
        possible_low=10.0,
        possible_high=60.0,
        extreme_low=20.0,
        extreme_high=40.0,
        basis="Derived from haemoglobin and red cell count, so its band "
        "follows theirs.",
    ),
    "mchc": ValidationRule(
        "mchc",
        "number",
        "g/dl",
        possible_low=20.0,
        possible_high=50.0,
        extreme_low=28.0,
        extreme_high=37.0,
        basis="Solubility of haemoglobin bounds the upper end. A raised MCHC "
        "is more often lipaemia, haemolysis or cold agglutinins than a real "
        "finding. `%` and `g/dL` are the same scale for MCHC -- see "
        "backend/src/services/unitEquivalence.js and the conditions it names.",
    ),
    "wbc_count": ValidationRule(
        "wbc_count",
        "number",
        "10^3/ul",
        possible_low=0.1,
        possible_high=500.0,
        extreme_low=2.0,
        extreme_high=30.0,
        basis="Agranulocytosis bounds the low end; leukaemic counts in the "
        "hundreds bound the high end, and NHANES itself contains a 400. "
        "10^3/uL and 10^9/L are numerically identical.",
    ),
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
    "platelet_count": ValidationRule(
        "platelet_count",
        "number",
        "10^3/ul",
        possible_low=1.0,
        possible_high=3000.0,
        extreme_low=50.0,
        extreme_high=1000.0,
        basis="Extremes set at the usual bleeding-risk threshold and at the "
        "threshold for extreme thrombocytosis. 10^3/uL and 10^9/L are "
        "numerically identical, so a report printing either maps correctly.",
    ),
    "alt": ValidationRule(
        "alt",
        "number",
        "u/l",
        possible_low=1.0,
        possible_high=30000.0,
        extreme_high=1000.0,
        basis="U/L (= IU/L). ACG 2017 abnormal liver chemistries: > 1000 U/L "
        "implies acute hepatocellular injury; possible band from acute liver "
        "failure case reports.",
    ),
    "ast": ValidationRule(
        "ast",
        "number",
        "u/l",
        possible_low=1.0,
        possible_high=40000.0,
        extreme_high=1000.0,
        basis="U/L (= IU/L). Same urgency threshold as ALT (ACG 2017); "
        "possible band widened for muscle injury.",
    ),
    "bilirubin_total": ValidationRule(
        "bilirubin_total",
        "number",
        "mg/dl",
        possible_low=0.05,
        possible_high=60.0,
        extreme_high=15.0,
        basis="mg/dL (umol/L / 17.1). Severe adult hyperbilirubinaemia "
        "threshold (15 mg/dL); possible band from cholestasis and haemolysis "
        "extremes.",
    ),
}


def rule_for(feature: str) -> Optional[ValidationRule]:
    return RULES.get(feature)


def _self_check() -> None:
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
