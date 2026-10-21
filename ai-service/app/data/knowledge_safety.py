from __future__ import annotations

import re
from typing import List, Tuple

FORBIDDEN_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        (
            "medication_name",
            r"\b(metformin|insulin|glimepiride|gliclazide|sitagliptin|empagliflozin"
            r"|atorvastatin|simvastatin|rosuvastatin|statins?|fibrates?|ezetimibe"
            r"|aspirin|clopidogrel|warfarin|heparin|ibuprofen|paracetamol"
            r"|acetaminophen|levothyroxine|amlodipine|lisinopril|ramipril|losartan"
            r"|atenolol|metoprolol|furosemide|prednisone|prednisolone|antibiotics?"
            r"|ferrous|cholecalciferol|ergocalciferol|cyanocobalamin"
            r"|hydroxocobalamin|erythropoietin|niacin|allopurinol)\b",
        ),
        (
            "medication_class_stem",
            r"\b\w{3,}("
            r"statins?|prils?|sartans?|olols?|dipines?|zosins?|parins?"
            r"|prazoles?|azoles?|tidines?|gliptins?|glitazones?|flozins?"
            r"|glinides?|cillins?|mycins?|micins?|floxacins?|cyclines?"
            r"|sulfamethoxazole|mabs?|nibs?|virs?|triptans?|setrons?|caines?"
            r"|barbitals?|zepams?|zolams?|codones?|morphones?"
            r")\b",
        ),
        (
            "supplementation_advice",
            r"\b(supplements?|supplementation|supplementing|multivitamins?)\b",
        ),
        (
            "dose_quantity",
            r"\b\d+(\.\d+)?\s*(mg|mcg|ug|µg|g|kg|ml|l|iu|units?|tablets?|capsules?)"
            r"\b(?!\s*/)",
        ),
        ("dose_word", r"\b(dose|doses|dosage|dosing|posology)\b"),
        (
            "dose_frequency",
            r"\b(once|twice|three times|four times)\s+(a|per)\s+(day|week)\b"
            r"|\b(daily dose|bd|tds|qds|od|prn)\b",
        ),
        (
            "dose_quantity_word",
            r"\b\d+(\.\d+)?\s*(milligrams?|micrograms?|international units?)\b",
        ),
        (
            "dose_unit_word",
            r"\b(milligrams?|micrograms?|international units?)\b"
            r"(?!\s+per\s+(decilitre|deciliter|litre|liter|millilitre|milliliter"
            r"|mole|kilogram|square))",
        ),
        (
            "treatment_instruction",
            r"\b((?!prescribed\s+preparations?\b)prescrib\w*"
            r"|(?!treat(?:s|ed|ing)?\s+(?:it|this|that|these|them|such\s+values?"
            r"|the\s+value|the\s+figure|the\s+number)\s+with\s+(?:reduced\s+confidence"
            r"|less\s+confidence|lower\s+confidence|caution|care|scepticism"
            r"|skepticism|suspicion)\s*(?:[.,;:)]|$))"
            r"(?!treat(?:s|ed|ing)?\s+as\s+(?:context|data|information|evidence"
            r"|a\s+prompt|an\s+input)\b)treat(?:s|ed|ing|ment|ments)?"
            r"|therapy|therapies|therapeutic|medication|medications|medicine"
            r"|medicines|drugs?|cure|cures|curing|regimens?|surgery|surgical"
            r"|injections?|infusions?|transfusions?)\b",
        ),
        (
            "self_administration",
            r"\b(you (should|must|need to|ought to) (take|start|stop|increase"
            r"|decrease|avoid|eat|use))\b"
            r"|\b(start taking|stop taking|take (this|these|it|them))\b",
        ),
        (
            "diagnostic_assertion",
            r"\b(you have|you are suffering|you suffer from|patient has"
            r"|this means you|indicates that you have|shows that you have)\b"
            r"|(?<!not a )(?<!not an )(?<!\bnot )(?<!never )(?<!\bnot a )"
            r"\bdiagnos\w*"
            r"|\byou are (diabetic|anaemic|anemic|obese)\b",
        ),
        (
            "certainty_claim",
            r"\b(definitely|certainly|undoubtedly|guaranteed?|proves?|proven"
            r"|confirms?|confirmed|conclusive(ly)?|always means|never means"
            r"|no doubt|will develop|will get|will cause|is certain|invariably)\b"
            r"|\b100\s*%",
        ),
        (
            "replaces_clinician",
            r"\b(no need to (see|consult|visit)|instead of (seeing|consulting)"
            r"|without (seeing|consulting) a doctor|rather than (seeing|consulting)"
            r"|do not need (a|to see a) (doctor|clinician|physician))\b",
        ),
        (
            "alarmist_prose",
            r"\b(life[- ]threatening|deadly|fatal|dangerously|emergency room"
            r"|you are at risk of dying|irreversible damage)\b",
        ),
        (
            "personalised_claim",
            r"\b(your (result|value|level|report) (shows|means|indicates|proves)"
            r"|based on your results?, you)\b",
        ),
    )
)


class UnsafeKnowledgeError(ValueError):
    pass


_WHITESPACE_RUN = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text or "").strip()


def scan_text(text: str) -> List[str]:
    flat = normalise(text)
    return [name for name, pattern in FORBIDDEN_PATTERNS if pattern.search(flat)]


def assert_safe(text: str, where: str, exempt: Tuple[str, ...] = ()) -> None:
    matches = [m for m in scan_text(text) if m not in exempt]
    if matches:
        raise UnsafeKnowledgeError(
            f"{where}: knowledge-base text violates the medical safety rules "
            f"({', '.join(matches)}). This corpus grounds an LLM, so unsafe "
            f"text here becomes unsafe output downstream. Rewrite the document "
            f"as patient education; do not weaken the scanner."
        )


EXEMPTIBLE_PATTERNS: Tuple[str, ...] = ("medication_name",)

_ADMIN_VERB = (
    r"(?:take|takes|taking|taken|inject\w*|administer\w*|start\w*|stop\w*"
    r"|increase\w*|decrease\w*|adjust\w*|switch\w*|use|uses|using)"
)
_SUBSTANCE = r"(?:insulin|metformin|glimepiride|gliclazide)"
ADMINISTRATION_CONTEXT: "re.Pattern[str]" = re.compile(
    rf"\b{_ADMIN_VERB}\b(?:\W+\w+){{0,4}}?\W+{_SUBSTANCE}\b"
    rf"|\b{_SUBSTANCE}\b(?:\W+\w+){{0,4}}?\W+{_ADMIN_VERB}\b",
    re.IGNORECASE,
)


def scan_administration(text: str) -> bool:
    return bool(ADMINISTRATION_CONTEXT.search(normalise(text)))


CANARY_SENTENCE = (
    "Take metformin 500 mg twice a day; this confirms you have diabetes and "
    "you do not need a doctor."
)
CANARY_MIN_MATCHES = 6


__all__ = [
    "ADMINISTRATION_CONTEXT",
    "CANARY_MIN_MATCHES",
    "CANARY_SENTENCE",
    "EXEMPTIBLE_PATTERNS",
    "FORBIDDEN_PATTERNS",
    "UnsafeKnowledgeError",
    "assert_safe",
    "normalise",
    "scan_administration",
    "scan_text",
]
