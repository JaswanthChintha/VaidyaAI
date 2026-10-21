from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


DIABETES = "Diabetes"
HEART_DISEASE = "Heart Disease"
KIDNEY_DISEASE = "Kidney Disease"

FUSION_CONDITIONS: Tuple[str, ...] = (DIABETES, HEART_DISEASE, KIDNEY_DISEASE)


HYPOGLYCEMIA = "Hypoglycemia"
ANEMIA = "Anemia"
ELEVATED_HEMOGLOBIN = "Elevated Hemoglobin"
VITAMIN_D_DEFICIENCY = "Vitamin D Deficiency"
ELEVATED_VITAMIN_D = "Elevated Vitamin D"
VITAMIN_B12_DEFICIENCY = "Vitamin B12 Deficiency"
HIGH_CHOLESTEROL = "High Cholesterol"
HIGH_TRIGLYCERIDES = "High Triglycerides"
LIVER_DISEASE = "Liver Disease"
OBESITY = "Obesity"
UNDERWEIGHT = "Underweight"


@dataclass(frozen=True)
class ConditionDefinition:

    name: str
    description: str
    always_assessed: bool = False
    also_produced_by: Tuple[str, ...] = ()
    report_when_unread: bool = True


CONDITIONS: Dict[str, ConditionDefinition] = {
    DIABETES: ConditionDefinition(
        DIABETES,
        "Glycaemic status assessed from HbA1c and blood glucose.",
        always_assessed=True,
        also_produced_by=("Module 10 Diabetes Predictor",),
    ),
    HEART_DISEASE: ConditionDefinition(
        HEART_DISEASE,
        "Cardiovascular risk-factor context.",
        always_assessed=True,
        also_produced_by=("Module 11 Heart Disease Predictor",),
    ),
    KIDNEY_DISEASE: ConditionDefinition(
        KIDNEY_DISEASE,
        "Renal status assessed from serum creatinine.",
        always_assessed=True,
        also_produced_by=("Module 12 Kidney Disease Predictor",),
    ),
    HYPOGLYCEMIA: ConditionDefinition(
        HYPOGLYCEMIA,
        "Low blood glucose.",
        report_when_unread=False,
    ),
    ANEMIA: ConditionDefinition(ANEMIA, "Low haemoglobin concentration."),
    ELEVATED_HEMOGLOBIN: ConditionDefinition(
        ELEVATED_HEMOGLOBIN,
        "Raised haemoglobin concentration.",
        report_when_unread=False,
    ),
    VITAMIN_D_DEFICIENCY: ConditionDefinition(
        VITAMIN_D_DEFICIENCY, "Low 25-hydroxyvitamin D."
    ),
    ELEVATED_VITAMIN_D: ConditionDefinition(
        ELEVATED_VITAMIN_D,
        "Raised 25-hydroxyvitamin D.",
        report_when_unread=False,
    ),
    VITAMIN_B12_DEFICIENCY: ConditionDefinition(
        VITAMIN_B12_DEFICIENCY, "Low serum vitamin B12."
    ),
    HIGH_CHOLESTEROL: ConditionDefinition(
        HIGH_CHOLESTEROL, "Raised total cholesterol."
    ),
    HIGH_TRIGLYCERIDES: ConditionDefinition(
        HIGH_TRIGLYCERIDES, "Raised triglycerides."
    ),
    LIVER_DISEASE: ConditionDefinition(
        LIVER_DISEASE,
        "Liver tests (ALT, AST, total bilirubin) against their upper limits.",
    ),
    OBESITY: ConditionDefinition(OBESITY, "Body mass index in the WHO obesity range."),
    UNDERWEIGHT: ConditionDefinition(
        UNDERWEIGHT, "Body mass index in the WHO thinness range."
    ),
}

CONDITION_ORDER: Tuple[str, ...] = tuple(CONDITIONS)

ALWAYS_ASSESSED_CONDITIONS: Tuple[str, ...] = tuple(
    name for name, d in CONDITIONS.items() if d.always_assessed
)


def is_canonical_condition(name: str) -> bool:
    return name in CONDITIONS


def condition_rank(name: str) -> int:
    try:
        return CONDITION_ORDER.index(name)
    except ValueError:
        return len(CONDITION_ORDER)


def _self_check() -> None:
    for key, definition in CONDITIONS.items():
        if key != definition.name:
            raise ValueError(f"condition key {key!r} != definition name {definition.name!r}")
        if not key.strip():
            raise ValueError("blank condition name")
        if key != key.strip():
            raise ValueError(f"condition {key!r} has surrounding whitespace")
    lowered = [k.lower() for k in CONDITIONS]
    if len(set(lowered)) != len(lowered):
        raise ValueError("two conditions differ only by case -- fusion would split them")
    for name in FUSION_CONDITIONS:
        if name not in CONDITIONS:
            raise ValueError(f"fusion condition {name!r} missing from CONDITIONS")
        if not CONDITIONS[name].always_assessed:
            raise ValueError(
                f"{name!r} is fused with an ML predictor and must be always_assessed, "
                "otherwise 'not assessed' is indistinguishable from 'nothing found'"
            )


_self_check()


def conditions_document() -> Dict[str, object]:
    return {
        "fusion_conditions": list(FUSION_CONDITIONS),
        "order": list(CONDITION_ORDER),
        "conditions": {
            name: {
                "description": d.description,
                "always_assessed": d.always_assessed,
                "report_when_unread": d.report_when_unread,
                "also_produced_by": list(d.also_produced_by),
            }
            for name, d in CONDITIONS.items()
        },
    }


__all__ = [
    "ALWAYS_ASSESSED_CONDITIONS",
    "ANEMIA",
    "CONDITIONS",
    "CONDITION_ORDER",
    "DIABETES",
    "ELEVATED_HEMOGLOBIN",
    "ELEVATED_VITAMIN_D",
    "FUSION_CONDITIONS",
    "HEART_DISEASE",
    "HIGH_CHOLESTEROL",
    "HIGH_TRIGLYCERIDES",
    "HYPOGLYCEMIA",
    "KIDNEY_DISEASE",
    "OBESITY",
    "UNDERWEIGHT",
    "VITAMIN_B12_DEFICIENCY",
    "VITAMIN_D_DEFICIENCY",
    "ConditionDefinition",
    "condition_rank",
    "conditions_document",
    "is_canonical_condition",
]
