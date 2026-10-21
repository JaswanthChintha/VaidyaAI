from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


SOURCE_LAB_REPORT = "lab_report"
SOURCE_PATIENT_PROFILE = "patient_profile"
SOURCE_REPORT_DETAILS = "report_details"
NOT_MEASURED_SOURCES = frozenset({SOURCE_PATIENT_PROFILE, SOURCE_REPORT_DETAILS})


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    canonical_unit: Optional[str]
    value_type: str
    source: str
    description: str
    categories: Tuple[str, ...] = field(default_factory=tuple)


FEATURES: Dict[str, FeatureDefinition] = {
    "hba1c": FeatureDefinition(
        "hba1c", "%", "number", SOURCE_LAB_REPORT, "Glycated haemoglobin, NGSP %"
    ),
    "blood_glucose": FeatureDefinition(
        "blood_glucose", "mg/dl", "number", SOURCE_LAB_REPORT, "Blood glucose"
    ),
    "hemoglobin": FeatureDefinition(
        "hemoglobin", "g/dl", "number", SOURCE_LAB_REPORT, "Haemoglobin concentration"
    ),
    "vitamin_d": FeatureDefinition(
        "vitamin_d", "ng/ml", "number", SOURCE_LAB_REPORT, "25-hydroxyvitamin D"
    ),
    "vitamin_b12": FeatureDefinition(
        "vitamin_b12", "pg/ml", "number", SOURCE_LAB_REPORT, "Vitamin B12 / cobalamin"
    ),
    "creatinine": FeatureDefinition(
        "creatinine", "mg/dl", "number", SOURCE_LAB_REPORT, "Serum creatinine"
    ),
    "cholesterol": FeatureDefinition(
        "cholesterol", "mg/dl", "number", SOURCE_LAB_REPORT, "TOTAL cholesterol"
    ),
    "triglycerides": FeatureDefinition(
        "triglycerides", "mg/dl", "number", SOURCE_LAB_REPORT, "Triglycerides"
    ),
    "hematocrit": FeatureDefinition(
        "hematocrit", "%", "number", SOURCE_LAB_REPORT, "Haematocrit (PCV)"
    ),
    "rbc_count": FeatureDefinition(
        "rbc_count", "10^6/ul", "number", SOURCE_LAB_REPORT, "Red blood cell count"
    ),
    "mcv": FeatureDefinition(
        "mcv", "fl", "number", SOURCE_LAB_REPORT, "Mean corpuscular volume"
    ),
    "mch": FeatureDefinition(
        "mch", "pg", "number", SOURCE_LAB_REPORT, "Mean corpuscular haemoglobin"
    ),
    "mchc": FeatureDefinition(
        "mchc",
        "g/dl",
        "number",
        SOURCE_LAB_REPORT,
        "Mean corpuscular haemoglobin concentration",
    ),
    "wbc_count": FeatureDefinition(
        "wbc_count", "10^3/ul", "number", SOURCE_LAB_REPORT, "White blood cell count"
    ),
    "neutrophils": FeatureDefinition(
        "neutrophils", "%", "number", SOURCE_LAB_REPORT, "Neutrophils"
    ),
    "lymphocytes": FeatureDefinition(
        "lymphocytes", "%", "number", SOURCE_LAB_REPORT, "Lymphocytes"
    ),
    "monocytes": FeatureDefinition(
        "monocytes", "%", "number", SOURCE_LAB_REPORT, "Monocytes"
    ),
    "eosinophils": FeatureDefinition(
        "eosinophils", "%", "number", SOURCE_LAB_REPORT, "Eosinophils"
    ),
    "basophils": FeatureDefinition(
        "basophils", "%", "number", SOURCE_LAB_REPORT, "Basophils"
    ),
    "platelet_count": FeatureDefinition(
        "platelet_count", "10^3/ul", "number", SOURCE_LAB_REPORT, "Platelet count"
    ),
    "alt": FeatureDefinition(
        "alt", "u/l", "number", SOURCE_LAB_REPORT, "ALT (SGPT)"
    ),
    "ast": FeatureDefinition(
        "ast", "u/l", "number", SOURCE_LAB_REPORT, "AST (SGOT)"
    ),
    "bilirubin_total": FeatureDefinition(
        "bilirubin_total", "mg/dl", "number", SOURCE_LAB_REPORT, "Total bilirubin"
    ),
    "bmi": FeatureDefinition(
        "bmi", "kg/m2", "number", SOURCE_PATIENT_PROFILE, "Body mass index"
    ),
    "age": FeatureDefinition(
        "age", "years", "integer", SOURCE_PATIENT_PROFILE, "Age in whole years"
    ),
    "hypertension": FeatureDefinition(
        "hypertension",
        None,
        "boolean",
        SOURCE_PATIENT_PROFILE,
        "Known high blood pressure",
    ),
    "heart_disease": FeatureDefinition(
        "heart_disease",
        None,
        "boolean",
        SOURCE_PATIENT_PROFILE,
        "Known heart disease",
    ),
    "smoking_history": FeatureDefinition(
        "smoking_history",
        None,
        "category",
        SOURCE_PATIENT_PROFILE,
        "Smoking history",
        categories=("never", "former", "current", "ever", "not_current", "no_info"),
    ),
    "gender": FeatureDefinition(
        "gender",
        None,
        "category",
        SOURCE_PATIENT_PROFILE,
        "Self-described gender",
        categories=("male", "female", "other", "prefer_not_to_say"),
    ),
}

CANONICAL_FEATURES: Tuple[str, ...] = tuple(FEATURES)
LAB_FEATURES: Tuple[str, ...] = tuple(
    n for n, d in FEATURES.items() if d.source == SOURCE_LAB_REPORT
)
PROFILE_FEATURES: Tuple[str, ...] = tuple(
    n for n, d in FEATURES.items() if d.source == SOURCE_PATIENT_PROFILE
)


PREFERENCE_DEFAULT = 2


@dataclass(frozen=True)
class Synonym:
    term: str
    preference: int = PREFERENCE_DEFAULT


def _s(*terms: str) -> Tuple[Synonym, ...]:
    return tuple(Synonym(t) for t in terms)


FEATURE_SYNONYMS: Dict[str, Tuple[Synonym, ...]] = {
    "hba1c": _s(
        "HbA1c",
        "Hb A1c",
        "HbA1C%",
        "A1c",
        "HgbA1c",
        "Hgb A1c",
        "Haemoglobin A1c",
        "Hemoglobin A1c",
        "Glycated Haemoglobin",
        "Glycated Hemoglobin",
        "Glycosylated Haemoglobin",
        "Glycosylated Hemoglobin",
        "Glycated Hb",
        "Glycosylated Hb",
        "Glycohemoglobin",
        "Glycohaemoglobin",
        "HbA1c (Glycated Haemoglobin)",
        "Glycated Haemoglobin (HbA1c)",
        "HbA1c NGSP",
        "Average Blood Glucose HbA1c",
    ),
    "blood_glucose": (
        Synonym("Glucose", 2),
        Synonym("Blood Glucose", 2),
        Synonym("Blood Sugar", 2),
        Synonym("Serum Glucose", 2),
        Synonym("Plasma Glucose", 2),
        Synonym("Sugar", 2),
        Synonym("Glucose Blood", 2),
        Synonym("Fasting Blood Glucose", 3),
        Synonym("Fasting Blood Sugar", 3),
        Synonym("Fasting Plasma Glucose", 3),
        Synonym("Fasting Glucose", 3),
        Synonym("Glucose Fasting", 3),
        Synonym("FBS", 3),
        Synonym("FPG", 3),
        Synonym("Blood Sugar Fasting", 3),
        Synonym("Random Blood Sugar", 1),
        Synonym("Random Blood Glucose", 1),
        Synonym("Random Glucose", 1),
        Synonym("RBS", 1),
        Synonym("Blood Sugar Random", 1),
        Synonym("Postprandial Blood Sugar", 0),
        Synonym("Post Prandial Blood Sugar", 0),
        Synonym("Post Prandial Glucose", 0),
        Synonym("Postprandial Glucose", 0),
        Synonym("PPBS", 0),
        Synonym("PP Blood Sugar", 0),
        Synonym("Glucose PP", 0),
        Synonym("2 Hour Postprandial Glucose", 0),
        Synonym("Blood Sugar Post Prandial", 0),
    ),
    "hemoglobin": _s(
        "Hemoglobin",
        "Haemoglobin",
        "Hb",
        "Hgb",
        "HGB",
        "Total Hemoglobin",
        "Total Haemoglobin",
        "Hemoglobin (Hb)",
        "Haemoglobin (Hb)",
        "Blood Hemoglobin",
    ),
    "vitamin_d": _s(
        "Vitamin D",
        "Vitamin D3",
        "Vitamin D (25-OH)",
        "25-OH Vitamin D",
        "25 OH Vitamin D3",
        "25-Hydroxy Vitamin D",
        "25-Hydroxyvitamin D",
        "25-OHD",
        "Vitamin D Total",
        "Total 25-Hydroxyvitamin D",
        "Vit D",
        "Vit D3",
        "Vitamin D 25 Hydroxy",
        "25 Hydroxycholecalciferol",
        "Calcidiol",
    ),
    "vitamin_b12": _s(
        "Vitamin B12",
        "Vitamin B-12",
        "Vit B12",
        "B12",
        "Vitamin B 12",
        "Cobalamin",
        "Cyanocobalamin",
        "Vitamin B12 (Cobalamin)",
        "Serum Vitamin B12",
    ),
    "creatinine": _s(
        "Creatinine",
        "Serum Creatinine",
        "Creatinine Serum",
        "S. Creatinine",
        "Creat",
        "Blood Creatinine",
        "Creatinine (Jaffe)",
        "Plasma Creatinine",
    ),
    "cholesterol": _s(
        "Cholesterol",
        "Total Cholesterol",
        "Cholesterol Total",
        "Serum Cholesterol",
        "Total Cholesterol Serum",
        "T. Cholesterol",
        "Chol",
        "TC",
        "Cholesterol (Total)",
    ),
    "triglycerides": _s(
        "Triglycerides",
        "Triglyceride",
        "Serum Triglycerides",
        "Triglycerides Serum",
        "TG",
        "TGL",
        "Trig",
        "Triglycerides (TG)",
    ),
    "hematocrit": _s(
        "PCV",
        "P.C.V",
        "Packed Cell Volume",
        "Haematocrit",
        "Hematocrit",
        "HCT",
        "Hct",
        "PCV (Packed Cell Volume)",
        "Haematocrit (PCV)",
    ),
    "rbc_count": _s(
        "RBC Count",
        "RBC COUNT",
        "T.RBC",
        "Total RBC",
        "Total RBC Count",
        "Red Blood Cell Count",
        "Red Cell Count",
        "RBC",
        "Erythrocyte Count",
    ),
    "mcv": _s(
        "MCV",
        "M.C.V",
        "Mean Corpuscular Volume",
        "Mean Cell Volume",
    ),
    "mch": _s(
        "MCH",
        "M.C.H",
        "Mean Corpuscular Haemoglobin",
        "Mean Corpuscular Hemoglobin",
        "Mean Cell Haemoglobin",
        "Mean Cell Hemoglobin",
    ),
    "mchc": _s(
        "MCHC",
        "M.C.H.C",
        "Mean Corpuscular Haemoglobin Concentration",
        "Mean Corpuscular Hemoglobin Concentration",
        "Mean Cell Haemoglobin Concentration",
        "Mean Cell Hemoglobin Concentration",
    ),
    "wbc_count": _s(
        "WBC Count",
        "WBC COUNT",
        "Total WBC Count",
        "TOTAL WBC COUNT",
        "Total Leucocyte Count",
        "Total Leukocyte Count",
        "TLC",
        "White Blood Cell Count",
        "White Cell Count",
        "WBC",
        "Leucocyte Count",
        "Leukocyte Count",
    ),
    "neutrophils": _s(
        "Neutrophils",
        "NEUTROPHILS",
        "Neutrophil",
        "Polymorphs",
        "Polymorphonuclear Cells",
        "Segmented Neutrophils",
        "Neutrophils %",
        "Neutrophil Percentage",
    ),
    "lymphocytes": _s(
        "Lymphocytes",
        "LYMPHOCYTES",
        "Lymphocyte",
        "Lymphs",
        "Lymphocytes %",
        "Lymphocyte Percentage",
    ),
    "monocytes": _s(
        "Monocytes",
        "MONOCYTES",
        "Monocyte",
        "Monocytes %",
        "Monocyte Percentage",
    ),
    "eosinophils": _s(
        "Eosinophils",
        "EOSINOPHILS",
        "Eosinophil",
        "Eosinophils %",
        "Eosinophil Percentage",
    ),
    "basophils": _s(
        "Basophils",
        "BASOPHILS",
        "Basophil",
        "Basophils %",
        "Basophil Percentage",
    ),
    "platelet_count": _s(
        "Platelet Count",
        "PLATELET COUNT",
        "Platelets",
        "Platelet",
        "Thrombocyte Count",
        "Plt",
        "PLT",
        "Platelet Count (PLT)",
    ),
    "alt": _s(
        "ALT",
        "SGPT",
        "S.G.P.T",
        "SGPT (ALT)",
        "ALT (SGPT)",
        "SGPT/ALT",
        "ALT/SGPT",
        "ALAT",
        "Alanine Aminotransferase",
        "Alanine Transaminase",
        "Alanine Aminotransferase (ALT)",
        "Alanine Aminotransferase (SGPT)",
        "Alanine Aminotransferase (ALT/SGPT)",
        "Serum Glutamic Pyruvic Transaminase",
        "SGPT (Alanine Aminotransferase)",
    ),
    "ast": _s(
        "AST",
        "SGOT",
        "S.G.O.T",
        "SGOT (AST)",
        "AST (SGOT)",
        "SGOT/AST",
        "AST/SGOT",
        "ASAT",
        "Aspartate Aminotransferase",
        "Aspartate Transaminase",
        "Aspartate Aminotransferase (AST)",
        "Aspartate Aminotransferase (SGOT)",
        "Aspartate Aminotransferase (AST/SGOT)",
        "Serum Glutamic Oxaloacetic Transaminase",
        "SGOT (Aspartate Aminotransferase)",
    ),
    "bilirubin_total": _s(
        "Total Bilirubin",
        "Bilirubin Total",
        "Bilirubin (Total)",
        "Total Bilirubin (TBIL)",
        "T. Bilirubin",
        "T.Bilirubin",
        "TBIL",
        "T Bil",
        "Bilirubin",
        "Serum Bilirubin",
        "Bilirubin Total Serum",
    ),
}

FEATURE_DISTINCT_TOKENS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "bilirubin_total": (
        "bilirubin",
        ("direct", "indirect", "conjugated", "unconjugated", "dbil", "ibil", "neonatal"),
    ),
}


NON_BLOOD_SPECIMEN_TOKENS: Tuple[str, ...] = (
    "urine",
    "urinary",
    "csf",
    "saliva",
    "salivary",
    "stool",
    "faecal",
    "fecal",
    "sputum",
    "synovial",
    "pleural",
    "ascitic",
    "amniotic",
    "dialysate",
    "semen",
    "sweat",
)

DISTINCT_ANALYTE_TOKENS: Tuple[str, ...] = (
    "hdl",
    "ldl",
    "vldl",
    "idl",
    "chylomicron",
)

STRIPPABLE_QUALIFIERS: Tuple[str, ...] = (
    "serum",
    "plasma",
    "s",
    "p",
    "level",
    "levels",
    "test",
    "assay",
    "estimation",
    "measurement",
    "quantitative",
    "direct",
    "photometric",
    "clia",
    "eclia",
    "hplc",
    "elisa",
    "method",
)


SPELLING_NORMALISATIONS: Tuple[Tuple[str, str], ...] = (
    ("haemo", "hemo"),
    ("haemato", "hemato"),
    ("glycaem", "glycem"),
    ("anaem", "anem"),
    ("oestro", "estro"),
    ("sulph", "sulf"),
)

_PARENTHETICAL_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_test_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _NON_ALNUM_RE.sub(" ", text).strip()
    for british, american in SPELLING_NORMALISATIONS:
        text = text.replace(british, american)
    return " ".join(text.split())


def strip_parentheticals(name: str) -> str:
    return _PARENTHETICAL_RE.sub(" ", name or "")


def strip_qualifiers(normalised: str) -> str:
    tokens = normalised.split()
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        if tokens[0] in STRIPPABLE_QUALIFIERS:
            tokens = tokens[1:]
            changed = True
        if len(tokens) > 1 and tokens[-1] in STRIPPABLE_QUALIFIERS:
            tokens = tokens[:-1]
            changed = True
    return " ".join(tokens)


@dataclass(frozen=True)
class SynonymMatch:
    feature: str
    preference: int
    matched_term: str
    matched_key: str
    exact: bool


def _build_index() -> Dict[str, SynonymMatch]:
    index: Dict[str, SynonymMatch] = {}
    for feature, synonyms in FEATURE_SYNONYMS.items():
        for syn in synonyms:
            key = normalize_test_name(syn.term)
            if not key:
                raise ValueError(f"Synonym {syn.term!r} normalises to an empty key")
            existing = index.get(key)
            if existing is not None and existing.feature != feature:
                raise ValueError(
                    f"Synonym key {key!r} is claimed by both "
                    f"{existing.feature!r} and {feature!r}"
                )
            index[key] = SynonymMatch(
                feature=feature,
                preference=syn.preference,
                matched_term=syn.term,
                matched_key=key,
                exact=True,
            )
    return index


SYNONYM_INDEX: Dict[str, SynonymMatch] = _build_index()


class UnmappedReason:
    NO_SYNONYM = "no_canonical_feature"
    NON_BLOOD_SPECIMEN = "unsupported_specimen"
    DISTINCT_ANALYTE = "distinct_analyte"
    NON_NUMERIC_VALUE = "non_numeric_value"
    EMPTY_TEST_NAME = "empty_test_name"
    DUPLICATE_DISCARDED = "duplicate_discarded"
    UNRECOGNISED_CATEGORY = "unrecognised_category"


def _agreeing_segment_match(segments: List[str]) -> Optional[SynonymMatch]:
    found: Dict[str, SynonymMatch] = {}
    for segment in segments:
        normalised = normalize_test_name(segment)
        for key in (normalised, strip_qualifiers(normalised)):
            hit = SYNONYM_INDEX.get(key) if key else None
            if hit is not None:
                found.setdefault(hit.feature, hit)
                break
    if len(found) != 1:
        return None
    hit = next(iter(found.values()))
    return SynonymMatch(
        feature=hit.feature,
        preference=hit.preference,
        matched_term=hit.matched_term,
        matched_key=hit.matched_key,
        exact=False,
    )


def lookup_test_name(name: str) -> Tuple[Optional[SynonymMatch], Optional[str]]:
    if not name or not name.strip():
        return None, UnmappedReason.EMPTY_TEST_NAME

    primary = normalize_test_name(name)
    tokens = set(primary.split())

    if tokens & set(NON_BLOOD_SPECIMEN_TOKENS):
        return None, UnmappedReason.NON_BLOOD_SPECIMEN
    if tokens & set(DISTINCT_ANALYTE_TOKENS):
        return None, UnmappedReason.DISTINCT_ANALYTE
    for word, distinct in FEATURE_DISTINCT_TOKENS.values():
        if word in tokens and tokens & set(distinct):
            return None, UnmappedReason.DISTINCT_ANALYTE

    without_parens = normalize_test_name(strip_parentheticals(name))

    candidates: List[Tuple[str, bool]] = [
        (primary, True),
        (without_parens, False),
        (strip_qualifiers(primary), False),
        (strip_qualifiers(without_parens), False),
    ]

    seen: set = set()
    for key, exact in candidates:
        if not key or key in seen:
            continue
        seen.add(key)
        hit = SYNONYM_INDEX.get(key)
        if hit is not None:
            return (
                SynonymMatch(
                    feature=hit.feature,
                    preference=hit.preference,
                    matched_term=hit.matched_term,
                    matched_key=key,
                    exact=exact and key == hit.matched_key,
                ),
                None,
            )

    if _PARENTHETICAL_RE.search(name or ""):
        segments = [strip_parentheticals(name)]
        segments += _PARENTHETICAL_RE.findall(name or "")
        match = _agreeing_segment_match(segments)
        if match is not None:
            return match, None

    if "," in (name or ""):
        found: Dict[str, SynonymMatch] = {}
        for segment in name.split(","):
            for key in (
                normalize_test_name(segment),
                strip_qualifiers(normalize_test_name(segment)),
            ):
                hit = SYNONYM_INDEX.get(key) if key else None
                if hit is not None:
                    found.setdefault(hit.feature, hit)
                    break
        if len(found) == 1:
            hit = next(iter(found.values()))
            return (
                SynonymMatch(
                    feature=hit.feature,
                    preference=hit.preference,
                    matched_term=hit.matched_term,
                    matched_key=hit.matched_key,
                    exact=False,
                ),
                None,
            )

    return None, UnmappedReason.NO_SYNONYM


SMOKING_CATEGORIES: Tuple[str, ...] = FEATURES["smoking_history"].categories

SMOKING_ALIASES: Dict[str, str] = {
    "never": "never",
    "never smoked": "never",
    "non smoker": "never",
    "nonsmoker": "never",
    "no": "never",
    "former": "former",
    "ex smoker": "former",
    "exsmoker": "former",
    "quit": "former",
    "past": "former",
    "current": "current",
    "smoker": "current",
    "yes": "current",
    "active": "current",
    "ever": "ever",
    "not current": "not_current",
    "notcurrent": "not_current",
    "no info": "no_info",
    "noinfo": "no_info",
    "unknown": "no_info",
    "not known": "no_info",
    "unspecified": "no_info",
    "no information": "no_info",
}

GENDER_CATEGORIES: Tuple[str, ...] = FEATURES["gender"].categories

GENDER_ALIASES: Dict[str, str] = {
    "male": "male",
    "m": "male",
    "female": "female",
    "f": "female",
    "other": "other",
    "o": "other",
    "prefer not to say": "prefer_not_to_say",
    "prefernottosay": "prefer_not_to_say",
    "undisclosed": "prefer_not_to_say",
}


def _category_key(value: str) -> str:
    return " ".join(_NON_ALNUM_RE.sub(" ", str(value).lower()).split())


def normalize_smoking_history(value: str) -> Optional[str]:
    key = _category_key(value)
    if not key:
        return None
    if key.replace(" ", "_") in SMOKING_CATEGORIES:
        return key.replace(" ", "_")
    return SMOKING_ALIASES.get(key)


def normalize_gender(value: str) -> Optional[str]:
    key = _category_key(value)
    if not key:
        return None
    if key.replace(" ", "_") in GENDER_CATEGORIES:
        return key.replace(" ", "_")
    return GENDER_ALIASES.get(key)


BOOLEAN_UNKNOWN_TOKENS: Tuple[str, ...] = (
    "",
    "unknown",
    "no info",
    "noinfo",
    "not known",
    "unspecified",
    "n a",
    "na",
    "null",
    "none",
)
BOOLEAN_TRUE_TOKENS: Tuple[str, ...] = ("true", "yes", "y", "1", "present", "positive")
BOOLEAN_FALSE_TOKENS: Tuple[str, ...] = ("false", "no", "n", "0", "absent", "negative")


def normalize_tristate_boolean(value: object) -> Tuple[Optional[bool], bool]:
    if value is None:
        return None, True
    if isinstance(value, bool):
        return value, True
    if isinstance(value, int) and value in (0, 1):
        return bool(value), True
    if isinstance(value, str):
        key = _category_key(value)
        if key in BOOLEAN_UNKNOWN_TOKENS:
            return None, True
        if key in BOOLEAN_TRUE_TOKENS:
            return True, True
        if key in BOOLEAN_FALSE_TOKENS:
            return False, True
    return None, False


import math as _math


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return _math.isfinite(float(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            return _math.isfinite(float(text))
        except (TypeError, ValueError):
            return False
    return False


def normalize_category_value(name: str, value: object) -> Optional[str]:
    definition = FEATURES.get(name)
    if definition is None or definition.value_type != "category":
        return None
    if isinstance(value, bool) or value is None:
        return None
    if name == "smoking_history":
        return normalize_smoking_history(str(value))
    if name == "gender":
        return normalize_gender(str(value))
    key = _category_key(str(value)).replace(" ", "_")
    return key if key in definition.categories else None


def is_valid_value(name: str, value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False

    definition = FEATURES.get(name)
    if definition is None:
        return True

    if definition.value_type in ("number", "integer"):
        return is_finite_number(value)
    if definition.value_type == "boolean":
        return isinstance(value, bool)
    if definition.value_type == "category":
        return normalize_category_value(name, value) is not None
    return True
