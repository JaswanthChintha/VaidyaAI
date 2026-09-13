"""Canonical feature definitions and the medical test-name synonym table.

This is the CLINICIAN-AUDITABLE data file for Module 5. Everything a reviewer
needs in order to check "does this printed test name really mean this feature?"
lives here, in plain tables, with no control flow.

Two independent things are defined:

1. `FEATURES` -- the canonical feature set of VaidyaAI, its canonical unit, its
   value type, and where the value comes from (lab report vs patient profile).
2. `FEATURE_SYNONYMS` -- every printed test name that maps onto a lab feature.

Also here, because they are clinical judgements rather than code:

* `NON_BLOOD_SPECIMEN_TOKENS` -- a urine/CSF/saliva result is NOT the same
  analyte as the serum one (urine creatinine != serum creatinine), so those
  rows are never mapped.
* `DISTINCT_ANALYTE_TOKENS` -- HDL/LDL/VLDL cholesterol are separate analytes
  and are not folded into `cholesterol` (which means TOTAL cholesterol).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

SOURCE_LAB_REPORT = "lab_report"
SOURCE_PATIENT_PROFILE = "patient_profile"


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    canonical_unit: Optional[str]
    value_type: str  # "number" | "integer" | "boolean" | "category"
    source: str
    description: str
    categories: Tuple[str, ...] = field(default_factory=tuple)


# The 13 features named in the specification, plus `gender`, which Module 2
# stores and Module 11 (heart-disease predictor) consumes.
FEATURES: Dict[str, FeatureDefinition] = {
    # ---- from the laboratory report (Module 4 input) ----
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
    # ---- from the patient profile (Module 2 input) ----
    "bmi": FeatureDefinition(
        "bmi", "kg/m2", "number", SOURCE_PATIENT_PROFILE, "Body mass index"
    ),
    "age": FeatureDefinition(
        "age", "years", "integer", SOURCE_PATIENT_PROFILE, "Age in whole years"
    ),
    # `description` IS A LABEL. It is rendered to readers -- the comparison
    # table, the clinician summary, the progress table -- and it is also fed
    # to the RAG retriever as a search term. The nine laboratory entries above
    # treat it that way ("Serum creatinine", "25-hydroxyvitamin D"); these
    # four did not, and printed an internal note instead:
    #
    #     "Self-described gender as stored by Module 2."
    #     "Smoking history, diabetes-dataset categories."
    #     "Known hypertension. TRI-STATE: true / false / absent(unknown)."
    #
    # A reader comparing two reports was shown a module number, the name of a
    # training dataset, and an implementation contract. The facts those notes
    # carried are real and are kept -- as comments, which is where a note to a
    # maintainer belongs.
    "hypertension": FeatureDefinition(
        "hypertension",
        None,
        # TRI-STATE: true / false / absent meaning unknown. Enforced by the
        # schema and the validator, not by this string.
        "boolean",
        SOURCE_PATIENT_PROFILE,
        "Known high blood pressure",
    ),
    "heart_disease": FeatureDefinition(
        "heart_disease",
        None,
        # TRI-STATE, as above. Absent is never a stated "no".
        "boolean",
        SOURCE_PATIENT_PROFILE,
        "Known heart disease",
    ),
    "smoking_history": FeatureDefinition(
        "smoking_history",
        None,
        "category",
        SOURCE_PATIENT_PROFILE,
        # The six categories below are the diabetes dataset's vocabulary; the
        # `categories` tuple states that far better than a label could.
        "Smoking history",
        categories=("never", "former", "current", "ever", "not_current", "no_info"),
    ),
    "gender": FeatureDefinition(
        "gender",
        None,
        "category",
        SOURCE_PATIENT_PROFILE,
        # "Self-described" is kept deliberately: it is the patient's own
        # answer, not a clinical determination, and that distinction is worth
        # a reader's attention. Only the module number goes.
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


# --------------------------------------------------------------------------
# Synonym table
# --------------------------------------------------------------------------

# `preference` breaks ties when two rows of the same report map to the same
# feature (see the duplicate-resolution policy in the service). Higher wins.
# It encodes SPECIFICITY, not "better": a fasting glucose is the measurement
# the diabetes models are trained on, so it outranks a post-prandial one.
PREFERENCE_DEFAULT = 2


@dataclass(frozen=True)
class Synonym:
    term: str
    preference: int = PREFERENCE_DEFAULT


def _s(*terms: str) -> Tuple[Synonym, ...]:
    return tuple(Synonym(t) for t in terms)


FEATURE_SYNONYMS: Dict[str, Tuple[Synonym, ...]] = {
    # ------------------------------------------------------------- hba1c --
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
    # ----------------------------------------------------- blood_glucose --
    # preference 3 = fasting (what the diabetes models expect)
    # preference 2 = unqualified glucose
    # preference 1 = random
    # preference 0 = post-prandial / post-load
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
    # -------------------------------------------------------- hemoglobin --
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
    # --------------------------------------------------------- vitamin_d --
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
    # ------------------------------------------------------- vitamin_b12 --
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
    # -------------------------------------------------------- creatinine --
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
    # ------------------------------------------------------- cholesterol --
    # TOTAL cholesterol only. HDL/LDL/VLDL are separate analytes -- see
    # DISTINCT_ANALYTE_TOKENS below.
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
    # ----------------------------------------------------- triglycerides --
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
}


# --------------------------------------------------------------------------
# Guards -- clinical judgements about what must NOT be mapped
# --------------------------------------------------------------------------

# A result from these specimens is a different analyte from the blood one.
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

# Lipid sub-fractions are distinct analytes; `cholesterol` means TOTAL.
DISTINCT_ANALYTE_TOKENS: Tuple[str, ...] = (
    "hdl",
    "ldl",
    "vldl",
    "idl",
    "chylomicron",
)

# Whole tokens that are safe to strip from either end of a test name because
# they qualify HOW/WHERE a test was run, not WHAT was measured.
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


# --------------------------------------------------------------------------
# Name normalisation + the lookup index
# --------------------------------------------------------------------------

# British -> American spellings applied to the normalised key. Applied as whole
# substrings, e.g. "haemoglobin" -> "hemoglobin", "glycaemia" -> "glycemia".
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
    """Squeeze a printed test name into a comparison key.

    Case, punctuation, hyphenation, accents and British/American spelling are
    all removed. `"Vitamin D (25-OH)"` -> `"vitamin d 25 oh"`.
    """
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
    """Remove leading/trailing method or specimen-container qualifier tokens."""
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


# Reasons a printed test name was not turned into a canonical feature.
class UnmappedReason:
    NO_SYNONYM = "no_canonical_feature"
    NON_BLOOD_SPECIMEN = "unsupported_specimen"
    DISTINCT_ANALYTE = "distinct_analyte"
    NON_NUMERIC_VALUE = "non_numeric_value"
    EMPTY_TEST_NAME = "empty_test_name"
    DUPLICATE_DISCARDED = "duplicate_discarded"
    UNRECOGNISED_CATEGORY = "unrecognised_category"


def _agreeing_segment_match(segments: List[str]) -> Optional[SynonymMatch]:
    """One feature from several name fragments, or nothing.

    THE SEGMENTS MUST AGREE, and that is the whole safety of every caller.
    Two segments naming different features is a name this module does not
    understand, and picking either one would be a guess.

    Never `exact`: the printed name is not the synonym, a PART of it is, and a
    consumer weighing two candidates for the same feature must be able to
    prefer the one that matched outright.
    """
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
    """Map a printed test name to a canonical feature.

    Returns `(match, None)` on success, or `(None, reason)` where reason is an
    `UnmappedReason`. Never guesses: an unknown name is reported, not mapped.
    """
    if not name or not name.strip():
        return None, UnmappedReason.EMPTY_TEST_NAME

    primary = normalize_test_name(name)
    tokens = set(primary.split())

    if tokens & set(NON_BLOOD_SPECIMEN_TOKENS):
        return None, UnmappedReason.NON_BLOOD_SPECIMEN
    if tokens & set(DISTINCT_ANALYTE_TOKENS):
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

    # A PARENTHETICAL WHOSE GOOD HALF IS THE ONE INSIDE THE BRACKETS.
    #
    # Every candidate above either keeps the parenthetical or THROWS IT AWAY --
    # `strip_parentheticals` discards it and nothing ever tries its contents.
    # That is fine while the outer half is the valid synonym, which is the case
    # the comment below assumed. It fails the other way round, and a real
    # report found it: "GLYSOLATED HAEMOGLOBIN ( HBA1C)" is a laboratory's
    # misspelling of GLYCOSYLATED, so the outer half matches nothing and the
    # inner "( HBA1C)" -- an exact synonym -- was thrown away with it.
    #
    # The cost was not a missing row. `hba1c` came back `state: unavailable`
    # while the same report's unassessed list carried the test at 5.9% flagged
    # HIGH by the laboratory, so the dashboard told a reader with a
    # prediabetic-range result that the test was NOT ON THEIR REPORT. An
    # absence reported as a fact about the document, on a test that was in it.
    #
    # Same agreement rule as the comma branch, and the same reason. Lipid
    # sub-fractions never reach here: `DISTINCT_ANALYTE_TOKENS` is checked
    # against the whole name above and returns first, so "Cholesterol (LDL)"
    # is refused before any segment is tried.
    if _PARENTHETICAL_RE.search(name or ""):
        segments = [strip_parentheticals(name)]
        segments += _PARENTHETICAL_RE.findall(name or "")
        match = _agreeing_segment_match(segments)
        if match is not None:
            return match, None

    # A COMMA-SEPARATED QUALIFIER, which is how many laboratories print the
    # same thing a parenthetical says.
    #
    # `strip_parentheticals` already handles "Glycosylated Hemoglobin (HbA1c)".
    # The comma form was not handled at all, so a real report printing
    # "GLYCOSYLATED HEMOGLOBIN, HbA1c" mapped to NOTHING -- even though both
    # halves are independently valid synonyms of `hba1c`. On a report whose
    # only test was that one, the result was an analysis with zero features
    # and a dashboard on which every row read "Not measured", which a reader
    # reasonably took to mean the platform had lost their results.
    #
    # THE SEGMENTS MUST AGREE, and that is the whole safety of this branch.
    # Two segments naming different features is a name this function does not
    # understand, and picking either one would be a guess. Lipid
    # sub-fractions -- the case where a wrong guess would be clinically
    # serious, mapping an LDL value into TOTAL cholesterol -- never reach
    # here: `DISTINCT_ANALYTE_TOKENS` is checked against the whole name above
    # and returns before any candidate is tried.
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
                    # Never `exact`: the printed name is not the synonym, a
                    # part of it is, and a consumer weighing two candidates
                    # for the same feature must be able to prefer the one
                    # that matched outright.
                    exact=False,
                ),
                None,
            )

    return None, UnmappedReason.NO_SYNONYM


# --------------------------------------------------------------------------
# Patient-profile categorical vocabularies
# --------------------------------------------------------------------------

# Module 2's exact smoking categories (the diabetes-dataset vocabulary).
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


# Values that mean "this boolean is UNKNOWN". They must never collapse to
# False -- absent/unknown and an explicit negative are different findings.
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
    """Return `(value_or_None, recognised)`.

    `(None, True)` means "explicitly unknown" -- which is a legitimate state,
    not an error. `(None, False)` means the token could not be understood.
    """
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


# --------------------------------------------------------------------------
# Type-aware value admission (integration audit D1)
# --------------------------------------------------------------------------
#
# WHY THIS LIVES HERE. `FEATURES` is the single place that declares what kind
# of thing each feature IS. Before this function existed, every consumer that
# wanted to know "is this a usable value for this feature?" answered it with
# `value is not None`, which admits the string "Negative" as a creatinine.
# Downstream, an sklearn ColumnTransformer coerces such a value to NaN and the
# numeric imputer median-fills it from the training cohort -- so a feature
# nobody measured arrives at the model wearing a plausible number.
#
# The catalogue therefore owns the answer, and consumers ask it.

#: `math` is only needed for the finiteness guard.
import math as _math  # noqa: E402


def is_finite_number(value: object) -> bool:
    """True only for a real, finite number (or a string that is exactly one).

    `bool` is EXCLUDED deliberately: `isinstance(True, int)` is True in Python,
    so without this guard a tri-state clinical answer would be admitted as a
    laboratory measurement and silently become 1.0.

    `NaN` and `inf` are excluded because they are not measurements. `NaN` in
    particular is the exact value an imputer replaces, so admitting it as
    "present" would defeat the sufficiency gate in the one case that leaves no
    trace.
    """
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
    """The canonical category for `value` under feature `name`, or None.

    Uses the feature-specific normaliser where one exists (smoking history and
    gender both have alias tables) and falls back to the declared vocabulary.
    """
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
    """Does `value` satisfy the DECLARED type of feature `name`?

    Returns False for an unrecognised feature name only when the value is
    itself empty; an out-of-catalogue name has no declared type, so this
    function has no basis on which to refuse a non-empty value and does not
    pretend to.
    """
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
        # TRI-STATE. Only a real `bool` is an answer; every "unknown" token and
        # every unrecognised token means the patient never said, and the
        # predictors' own `_tri_state()` helpers agree by construction.
        return isinstance(value, bool)
    if definition.value_type == "category":
        return normalize_category_value(name, value) is not None
    return True  # pragma: no cover - no other value_type exists
