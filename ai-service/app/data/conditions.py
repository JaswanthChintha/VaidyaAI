"""The CANONICAL CONDITION VOCABULARY.

`app/schemas/decisions.py` says of `ClinicalDecision.condition`:

    "Module 16 groups by this value, so producers MUST use a consistent
     spelling -- see app/data/conditions.py for the canonical list."

This is that list. It exists because fusion is a *string grouping*. If Module 8
emits ``"Diabetes"`` and Module 10 emits ``"diabetes"`` or ``"Diabetes Mellitus"``
the Fusion Engine sees two unrelated conditions, shows the user two cards, and
silently never fuses a rule decision with a model decision -- the single feature
Module 16 exists to provide. Nothing would raise; the product would just be
quietly worse.

So: NO producer may invent a condition string. Import a constant from here.

--------------------------------------------------------------------------
THE THREE SHARED CONDITIONS
--------------------------------------------------------------------------

`DIABETES`, `HEART_DISEASE` and `KIDNEY_DISEASE` are the conditions Modules
10, 11 and 12 will also produce (spec Module 9's predictor list). They are
declared here FIRST, before the ML layer exists, precisely so the ML layer has
something to match rather than something to guess at.

--------------------------------------------------------------------------
NAMING RULES
--------------------------------------------------------------------------

* Title Case, spelled exactly as written here.
* AMERICAN spelling ("Anemia", "Hemoglobin"), matching
  `app/data/feature_catalog.py`, which normalises British spellings to
  American ones. One convention, applied everywhere.
* A condition name is a TOPIC, not a diagnosis. "Diabetes" names what was
  assessed; whether anything was found lives in `DecisionStatus`. This is why
  there is no separate "Prediabetes" entry: a prediabetic HbA1c is the
  `Diabetes` topic with status `BORDERLINE`, which keeps it fusable with a
  Module 10 diabetes prediction instead of splitting it into a private
  condition no predictor will ever emit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

# --------------------------------------------------------------------------
# The shared conditions -- Module 8 AND Modules 10-12 emit these exact strings
# --------------------------------------------------------------------------

DIABETES = "Diabetes"
HEART_DISEASE = "Heart Disease"
KIDNEY_DISEASE = "Kidney Disease"

#: The conditions that both the rule engine and a condition-specific predictor
#: produce, and which Module 16 therefore actually fuses.
FUSION_CONDITIONS: Tuple[str, ...] = (DIABETES, HEART_DISEASE, KIDNEY_DISEASE)

# --------------------------------------------------------------------------
# Laboratory-finding conditions -- Module 8 only, for now
# --------------------------------------------------------------------------

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
    """One entry in the canonical vocabulary.

    `always_assessed` marks a condition that must ALWAYS produce exactly one
    decision, even when the inputs are missing -- in which case the decision is
    `INSUFFICIENT_DATA`. Silence would be indistinguishable from "assessed and
    nothing found", which is the exact failure `decisions.py` calls "the most
    dangerous failure mode this type can have".
    """

    name: str
    description: str
    always_assessed: bool = False
    also_produced_by: Tuple[str, ...] = ()
    #: When the source document was PARTIALLY UNREADABLE and this condition's
    #: feature is absent, absence may mean UNREAD rather than not-present, so an
    #: INSUFFICIENT_DATA decision is emitted rather than silence.
    #:
    #: Set False for the SECONDARY reading of a feature (e.g. "Elevated
    #: Vitamin D" is the other end of the same analyte as "Vitamin D
    #: Deficiency"). Reporting both would put two "could not assess" cards in
    #: front of the reader for one missing test, which is noise, not safety.
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
        # Secondary reading of `blood_glucose`; `Diabetes` already reports when
        # that test could not be read.
        report_when_unread=False,
    ),
    ANEMIA: ConditionDefinition(ANEMIA, "Low haemoglobin concentration."),
    ELEVATED_HEMOGLOBIN: ConditionDefinition(
        ELEVATED_HEMOGLOBIN,
        "Raised haemoglobin concentration.",
        # Secondary reading of `hemoglobin`; `Anemia` reports the unread case.
        report_when_unread=False,
    ),
    VITAMIN_D_DEFICIENCY: ConditionDefinition(
        VITAMIN_D_DEFICIENCY, "Low 25-hydroxyvitamin D."
    ),
    ELEVATED_VITAMIN_D: ConditionDefinition(
        ELEVATED_VITAMIN_D,
        "Raised 25-hydroxyvitamin D.",
        # Secondary reading of `vitamin_d`.
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
    # 2026-10-04. Rule-based only for now (no predictor), named to match
    # "Kidney Disease": the rules report raised liver tests worth discussing,
    # they do not diagnose a disease.
    LIVER_DISEASE: ConditionDefinition(
        LIVER_DISEASE,
        "Liver tests (ALT, AST, total bilirubin) against their upper limits.",
    ),
    OBESITY: ConditionDefinition(OBESITY, "Body mass index in the WHO obesity range."),
    UNDERWEIGHT: ConditionDefinition(
        UNDERWEIGHT, "Body mass index in the WHO thinness range."
    ),
}

#: Stable ordering for output. Fusion conditions first, then lab findings.
CONDITION_ORDER: Tuple[str, ...] = tuple(CONDITIONS)

ALWAYS_ASSESSED_CONDITIONS: Tuple[str, ...] = tuple(
    name for name, d in CONDITIONS.items() if d.always_assessed
)


def is_canonical_condition(name: str) -> bool:
    return name in CONDITIONS


def condition_rank(name: str) -> int:
    """Position in `CONDITION_ORDER`; unknown names sort last."""
    try:
        return CONDITION_ORDER.index(name)
    except ValueError:
        return len(CONDITION_ORDER)


def _self_check() -> None:
    """Fail at import if the vocabulary is internally inconsistent."""
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
    """Machine-readable dump, for review and for Modules 10-12 to check against."""
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
