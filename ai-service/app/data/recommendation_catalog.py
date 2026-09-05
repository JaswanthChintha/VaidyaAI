"""The RECOMMENDATION CATALOGUE -- the structural safety mechanism.

`app/schemas/decisions.py` states the design rule this file implements:

    "Recommendation text is drawn from a fixed, reviewable catalogue
     (app/data/recommendation_catalog.py) rather than composed ad hoc, so an
     unsafe recommendation cannot be introduced by a caller passing a string."

and spec Module 26 requires "pre-approved educational guidance rather than
unrestricted AI-generated medical treatment advice".

--------------------------------------------------------------------------
WHY THIS IS STRUCTURAL AND NOT A CONVENTION
--------------------------------------------------------------------------

Three mechanisms, each independent of the other two:

1. NO CODE PATH CAN COMPOSE TEXT. `recommendation(code)` is the ONLY way a
   `Recommendation` object is built anywhere in Module 8, and it takes a CODE.
   An unknown code raises `UnknownRecommendationError`. There is no
   `Recommendation(text=...)` call in the rule engine at all, so there is no
   string for a bug, a caller, or a future LLM to inject through.

2. THE TEXT IS SCANNED AT IMPORT TIME. `_self_check()` runs the safety scanner
   over every entry below and raises `UnsafeRecommendationError` on a match.
   That is an ImportError at service start: adding unsafe wording does not
   produce a bad report, it produces a service that refuses to run. A reviewer
   cannot "forget" to run the check.

3. THE SCANNER IS ITSELF TESTED against planted violations, so it cannot
   silently rot into a regex that matches nothing.

--------------------------------------------------------------------------
WHAT IS BANNED (spec section 14 / Module 24)
--------------------------------------------------------------------------

    unsupported diagnosis .... "you have diabetes", "diagnosis of anaemia"
    medication ............... any drug name, any drug class
    dosage ................... any quantity + unit, "dose", "dosage"
    treatment instruction .... "treat", "therapy", "prescribe", "regimen"
    claims of certainty ...... "definitely", "confirms", "proves", "100%"
    replacing a clinician .... covered positively -- almost every entry names
                               a qualified healthcare professional as the
                               place the question belongs

The preferred register, per the module brief, is:

    "this finding may warrant discussion with a qualified healthcare
     professional"

Nothing here tells anyone to do anything to their body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.schemas.decisions import Recommendation

# --------------------------------------------------------------------------
# Categories (the vocabulary `Recommendation.category` documents)
# --------------------------------------------------------------------------

CATEGORY_CONSULTATION = "consultation"
CATEGORY_MONITORING = "monitoring"
CATEGORY_LIFESTYLE = "lifestyle"
CATEGORY_RETEST = "retest"
CATEGORY_INFORMATION = "information"
CATEGORY_DATA_QUALITY = "data_quality"

CATEGORIES: Tuple[str, ...] = (
    CATEGORY_CONSULTATION,
    CATEGORY_MONITORING,
    CATEGORY_LIFESTYLE,
    CATEGORY_RETEST,
    CATEGORY_INFORMATION,
    CATEGORY_DATA_QUALITY,
)


# --------------------------------------------------------------------------
# Codes
# --------------------------------------------------------------------------

NOT_A_DIAGNOSIS = "NOT_A_DIAGNOSIS"
DISCUSS_WITH_CLINICIAN = "DISCUSS_WITH_CLINICIAN"
SEEK_PROMPT_MEDICAL_ADVICE = "SEEK_PROMPT_MEDICAL_ADVICE"
CONFIRM_WITH_REPEAT_TESTING = "CONFIRM_WITH_REPEAT_TESTING"
MONITOR_OVER_TIME = "MONITOR_OVER_TIME"
DISCUSS_SAMPLE_TIMING = "DISCUSS_SAMPLE_TIMING"
GENERAL_BALANCED_DIET = "GENERAL_BALANCED_DIET"
GENERAL_PHYSICAL_ACTIVITY = "GENERAL_PHYSICAL_ACTIVITY"
GENERAL_LIMIT_ADDED_SUGAR = "GENERAL_LIMIT_ADDED_SUGAR"
GENERAL_DIETARY_FAT_QUALITY = "GENERAL_DIETARY_FAT_QUALITY"
GENERAL_HYDRATION = "GENERAL_HYDRATION"
GENERAL_IRON_RICH_FOODS = "GENERAL_IRON_RICH_FOODS"
GENERAL_VITAMIN_D_SOURCES = "GENERAL_VITAMIN_D_SOURCES"
GENERAL_VITAMIN_B12_SOURCES = "GENERAL_VITAMIN_B12_SOURCES"
GENERAL_SMOKING_CESSATION_SUPPORT = "GENERAL_SMOKING_CESSATION_SUPPORT"
GENERAL_WEIGHT_DISCUSSION = "GENERAL_WEIGHT_DISCUSSION"
NOTHING_FLAGGED_EDUCATIONAL = "NOTHING_FLAGGED_EDUCATIONAL"
INFORMATION_INCOMPLETE = "INFORMATION_INCOMPLETE"
UNREADABLE_DOCUMENT_RECHECK = "UNREADABLE_DOCUMENT_RECHECK"
INPUT_QUALITY_CAVEAT = "INPUT_QUALITY_CAVEAT"


@dataclass(frozen=True)
class CatalogEntry:
    """One approved recommendation.

    `basis` records WHY the entry exists and who may safely be shown it. It is
    reviewer-facing and never rendered to a user.
    """

    code: str
    text: str
    category: str
    basis: str


def _entry(code: str, text: str, category: str, basis: str) -> Tuple[str, CatalogEntry]:
    return code, CatalogEntry(code=code, text=text, category=category, basis=basis)


RECOMMENDATIONS: Dict[str, CatalogEntry] = dict(
    [
        # ---------------------------------------------------------- safety --
        _entry(
            NOT_A_DIAGNOSIS,
            "This is an automated educational analysis, not a diagnosis, and it "
            "does not replace assessment by a qualified healthcare professional.",
            CATEGORY_INFORMATION,
            "Spec section 14 / Module 24: the platform must never present itself "
            "as a substitute for professional medical care. Attached to EVERY "
            "decision the rule engine emits.",
        ),
        # ---------------------------------------------------- consultation --
        _entry(
            DISCUSS_WITH_CLINICIAN,
            "This finding may warrant discussion with a qualified healthcare "
            "professional.",
            CATEGORY_CONSULTATION,
            "The default action for any flagged finding. Deliberately says "
            "'may warrant discussion', not 'you should be treated'.",
        ),
        _entry(
            SEEK_PROMPT_MEDICAL_ADVICE,
            "Results in this range are usually reviewed promptly by a qualified "
            "healthcare professional.",
            CATEGORY_CONSULTATION,
            "Reserved for HIGH-risk bands only. States what usually happens in "
            "practice rather than instructing the reader to do anything.",
        ),
        # ---------------------------------------------- retest / monitoring --
        _entry(
            CONFIRM_WITH_REPEAT_TESTING,
            "A single laboratory result rarely settles a question on its own; a "
            "qualified healthcare professional can advise whether repeat testing "
            "is appropriate.",
            CATEGORY_RETEST,
            "Every guideline behind this rule table (ADA, WHO, NCEP) requires "
            "confirmation on a second sample before anything is concluded. "
            "Saying so is the single most honest thing this catalogue does.",
        ),
        _entry(
            MONITOR_OVER_TIME,
            "Tracking this parameter across future reports can help a qualified "
            "healthcare professional see whether it is changing.",
            CATEGORY_MONITORING,
            "Supports spec Modules 28-30 (trend analysis) without promising the "
            "reader any particular outcome.",
        ),
        _entry(
            DISCUSS_SAMPLE_TIMING,
            "Whether a blood sample was taken after fasting changes how a glucose "
            "result is read; a qualified healthcare professional can confirm the "
            "collection conditions.",
            CATEGORY_RETEST,
            "Attached whenever the glucose rule could not establish that the "
            "sample was fasting. Names the engine's own uncertainty instead of "
            "hiding it.",
        ),
        _entry(
            INPUT_QUALITY_CAVEAT,
            "At least one value behind this finding was marked as less reliable "
            "when the report was read, so a qualified healthcare professional "
            "should check it against the original document.",
            CATEGORY_DATA_QUALITY,
            "Attached when any input feature was `questionable` in Module 6 "
            "(assumed unit, censored value, low extraction confidence, partially "
            "unreadable document).",
        ),
        _entry(
            UNREADABLE_DOCUMENT_RECHECK,
            "Part of the uploaded document could not be read, so this topic could "
            "not be assessed from it. Uploading a clearer copy may help.",
            CATEGORY_DATA_QUALITY,
            "Attached when Module 4 reported unreadable pages and the feature "
            "this topic needs is absent -- absence may then mean UNREAD rather "
            "than not present.",
        ),
        # ------------------------------------------------------- lifestyle --
        _entry(
            GENERAL_BALANCED_DIET,
            "General educational guidance for most adults includes a varied diet "
            "with vegetables, fruit and whole grains.",
            CATEGORY_LIFESTYLE,
            "Spec Module 26 names 'healthy eating practices'. Population-level "
            "wording; nothing personalised, nothing quantified.",
        ),
        _entry(
            GENERAL_PHYSICAL_ACTIVITY,
            "General educational guidance for most adults includes regular "
            "physical activity within limits agreed with a qualified healthcare "
            "professional.",
            CATEGORY_LIFESTYLE,
            "Spec Module 26 names 'general physical activity'. The clause about "
            "agreed limits is deliberate: exercise is not safe for everyone.",
        ),
        _entry(
            GENERAL_LIMIT_ADDED_SUGAR,
            "General educational guidance for most adults includes limiting "
            "drinks and foods with a lot of added sugar.",
            CATEGORY_LIFESTYLE,
            "Attached to glycaemic findings only.",
        ),
        _entry(
            GENERAL_DIETARY_FAT_QUALITY,
            "General educational guidance for most adults includes limiting "
            "saturated fat in favour of unsaturated sources.",
            CATEGORY_LIFESTYLE,
            "Attached to lipid findings only.",
        ),
        _entry(
            GENERAL_HYDRATION,
            "General educational guidance for most adults includes drinking "
            "enough fluid across the day.",
            CATEGORY_LIFESTYLE,
            "Spec Module 26 names 'hydration reminders where appropriate'. "
            "Attached only to renal findings, which is the 'where appropriate'.",
        ),
        _entry(
            GENERAL_IRON_RICH_FOODS,
            "Dietary sources of iron are a general educational topic a qualified "
            "healthcare professional can cover when haemoglobin is low.",
            CATEGORY_LIFESTYLE,
            "Named as a TOPIC, not an instruction. Not all low haemoglobin is "
            "iron related, and iron is harmful in some conditions, so this entry "
            "must never become 'take iron'.",
        ),
        _entry(
            GENERAL_VITAMIN_D_SOURCES,
            "Sunlight exposure and dietary sources are the general educational "
            "topics associated with vitamin D status.",
            CATEGORY_LIFESTYLE,
            "Named as topics. Supplementation is deliberately NOT mentioned: "
            "that is a clinical decision with a dose attached.",
        ),
        _entry(
            GENERAL_VITAMIN_B12_SOURCES,
            "Dietary sources of vitamin B12 are a general educational topic a "
            "qualified healthcare professional can cover.",
            CATEGORY_LIFESTYLE,
            "Same reasoning as the vitamin D entry.",
        ),
        _entry(
            GENERAL_SMOKING_CESSATION_SUPPORT,
            "Support for stopping smoking is available from qualified healthcare "
            "professionals and public health services.",
            CATEGORY_LIFESTYLE,
            "Attached only when smoking history is a counted cardiovascular risk "
            "factor. States that support exists; issues no instruction.",
        ),
        _entry(
            GENERAL_WEIGHT_DISCUSSION,
            "Body weight is one of several factors a qualified healthcare "
            "professional can discuss in context.",
            CATEGORY_LIFESTYLE,
            "Deliberately neutral. Weight findings are a common place for an "
            "automated tool to do harm.",
        ),
        # ----------------------------------------------------- information --
        _entry(
            NOTHING_FLAGGED_EDUCATIONAL,
            "This value sits inside the band configured in this tool. That is not "
            "the same as a professional interpretation of the whole report.",
            CATEGORY_INFORMATION,
            "Attached to NOT_INDICATED decisions. It must not read as "
            "reassurance: a normal single analyte says nothing about the rest.",
        ),
        _entry(
            INFORMATION_INCOMPLETE,
            "There was not enough information in this report to look at this "
            "topic. A qualified healthcare professional can advise what is worth "
            "checking.",
            CATEGORY_INFORMATION,
            "Attached to INSUFFICIENT_DATA decisions, which carry risk=None. "
            "Absence of information must never read as absence of a problem.",
        ),
    ]
)


# --------------------------------------------------------------------------
# The safety scanner
# --------------------------------------------------------------------------

#: (name, compiled pattern). Names are reported so a failure says WHAT tripped.
#: Word boundaries are used throughout so that a banned word inside an innocent
#: longer word (e.g. "confirmatory" vs "confirms") does not produce a false
#: positive that would tempt someone to weaken the scanner.
_FORBIDDEN_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        # ---- medication names and drug classes ----
        (
            "medication_name",
            r"\b(metformin|insulin|glimepiride|gliclazide|sitagliptin|empagliflozin"
            r"|atorvastatin|simvastatin|rosuvastatin|statins?|fibrate|ezetimibe"
            r"|aspirin|clopidogrel|warfarin|heparin|ibuprofen|paracetamol"
            r"|acetaminophen|levothyroxine|amlodipine|lisinopril|ramipril|losartan"
            r"|atenolol|metoprolol|furosemide|prednisone|prednisolone|antibiotics?"
            r"|ferrous|cholecalciferol|ergocalciferol|cyanocobalamin"
            r"|hydroxocobalamin|erythropoietin)\b",
        ),
        # HARDENED (integration audit D7). The list above is an enumeration, so
        # every drug NOT on it passed -- and no enumeration of drug names is
        # ever finished. Generic pharmacological stems catch whole classes at
        # once: any `-statin`, `-pril`, `-sartan`, `-olol`, `-prazole`,
        # `-gliptin`, `-flozin`, `-cillin`, `-mycin`, `-mab`, `-nib` and so on
        # is a drug regardless of whether anyone thought to list it. The
        # leading `\w{3,}` keeps the stems from matching short innocent words.
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
            r"\b(supplements?|supplementation|supplementing)\b",
        ),
        # ---- dosage ----
        # A DOSE is a quantity of a substance to put in a body: "500 mg".
        # A laboratory THRESHOLD is a concentration: "126 mg/dL". The negative
        # lookahead for a following "/" is what separates the two, so that a
        # rule band may legitimately say "126 mg/dL" while "500 mg" is still
        # banned everywhere. Drug names are banned by their own pattern, so a
        # real dosage cannot slip through by omitting the slash.
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
        ("dose_unit_word", r"\b(milligrams?|micrograms?|international units?)\b",),
        # ---- treatment instructions ----
        # `treat` is the only verb here with a common NON-clinical sense, and
        # the system's own Module 6 boilerplate uses it: "Feature 'bmi' is
        # usable but flagged (DERIVED_VALUE); treat it with reduced
        # confidence." That is an instruction about how much to BELIEVE a
        # number, not about what to put in a body, and the scanner firing on it
        # trained readers to ignore the scanner (integration audit D5).
        #
        # The exclusion is a negative lookahead over exactly that construction
        # -- an epistemic verb phrase, `treat <this/it/them> with <caution or a
        # synonym>`, and the confidence word must END the clause -- and nothing
        # wider. "treat it with metformin", "treat this with antibiotics",
        # "treat them with insulin", "treat them with care and a statin",
        # "treatment", "treated with", "treating" all still match, because the
        # complement after `with` must be one of a closed list of confidence
        # words AND nothing may follow it. A real treatment instruction cannot
        # satisfy both.
        (
            "treatment_instruction",
            r"\b(prescrib\w*"
            r"|(?!treat(?:s|ed|ing)?\s+(?:it|this|that|these|them|such\s+values?"
            r"|the\s+value|the\s+figure)\s+with\s+(?:reduced\s+confidence"
            r"|less\s+confidence|lower\s+confidence|caution|care|scepticism"
            r"|skepticism|suspicion)\s*(?:[.,;:)]|$))treat(?:s|ed|ing|ment|ments)?"
            r"|therapy|therapies|medication|medications|medicine|medicines|drugs?"
            r"|cure|cures|curing|regimen|surgery|injection|injections|infusion)\b",
        ),
        (
            "self_administration",
            r"\b(you (should|must|need to) (take|start|stop|increase|decrease))\b"
            r"|\b(start taking|stop taking|take (this|these|it|them))\b",
        ),
        # ---- unsupported diagnosis ----
        # HARDENED (integration audit D7). The enumerated forms
        # `diagnos(is of|ed with|tic of)` missed the most natural assertion of
        # all -- "the diagnosis is diabetes" -- and every other inflection
        # besides. Any `diagnos*` word now trips the pattern, with fixed-width
        # negative lookbehinds carving out ONLY the disclaiming construction the
        # platform is required to use ("this is not a diagnosis", "it does not
        # diagnose"). Widening the match and then excusing the one safe phrasing
        # is the right way round: a new way of asserting a diagnosis is caught
        # by default, whereas a new item in an enumeration is not.
        (
            "diagnostic_assertion",
            r"\b(you have|you are suffering|you suffer from|patient has)\b"
            r"|(?<!not a )(?<!not an )(?<!\bnot )(?<!never )(?<!\bnot a )"
            r"\bdiagnos\w*"
            r"|\byou are (diabetic|anaemic|anemic)\b",
        ),
        # ---- claims of certainty ----
        (
            "certainty_claim",
            r"\b(definitely|certainly|undoubtedly|guaranteed?|proves?|proven"
            r"|confirms|confirmed|conclusive(ly)?|always means|no doubt"
            r"|will develop|will get|is certain)\b|\b100\s*%",
        ),
        # ---- replacing professional care ----
        (
            "replaces_clinician",
            r"\b(no need to (see|consult|visit)|instead of (seeing|consulting)"
            r"|without (seeing|consulting) a doctor)\b",
        ),
    )
)


class UnsafeRecommendationError(ValueError):
    """Raised at import time when catalogue text violates the safety rules."""


class UnknownRecommendationError(KeyError):
    """Raised when a code is not in the catalogue. Never falls back to text."""


def scan_text(text: str) -> List[str]:
    """Names of every safety pattern `text` matches. Empty list means clean.

    Public because Module 8's rule table scans its own user-facing band labels
    with it, and because the test suite plants known violations to prove this
    function has not rotted into something that matches nothing.
    """
    # Whitespace is folded to single spaces FIRST. This is a correctness fix,
    # not cosmetic, and it matters in both directions: several patterns contain
    # literal spaces ("you have", "not a diagnosis"), and a literal space does
    # not match a newline. Without folding, "you\nhave diabetes" matched
    # NOTHING (a banned phrase escaping because it straddled a line end), while
    # "not a\ndiagnosis" DID match, because the `(?<!not a )` carve-out is a
    # fixed-width literal-space lookbehind -- so the one phrasing the platform
    # is required to use was rejected purely by where the text wrapped.
    #
    # Entries here are short and single-line, so this was latent rather than
    # live. It was found in the Module 22 corpus scanner and confirmed live in
    # the Module 24 validator, where wrapped LLM prose makes it the normal case.
    # Fixed in all three so the sibling scanners cannot drift apart again.
    #
    # `scan_text` reports pattern NAMES, never offsets, so collapsing runs here
    # is safe -- nothing downstream indexes into the scanned string.
    folded = " ".join((text or "").split())
    return [name for name, pattern in _FORBIDDEN_PATTERNS if pattern.search(folded)]


def assert_safe(text: str, where: str) -> None:
    matches = scan_text(text)
    if matches:
        raise UnsafeRecommendationError(
            f"{where}: text matches forbidden pattern(s) {matches}: {text!r}"
        )


# --------------------------------------------------------------------------
# The ONLY way to build a Recommendation
# --------------------------------------------------------------------------


def recommendation(code: str) -> Recommendation:
    """Build a `Recommendation` from an approved catalogue code.

    There is deliberately no parameter for the text. A caller cannot supply
    wording, so no code path -- present or future, including an LLM-driven one
    -- can emit a recommendation that has not been reviewed in this file.
    """
    entry = RECOMMENDATIONS.get(code)
    if entry is None:
        raise UnknownRecommendationError(
            f"{code!r} is not in the recommendation catalogue. Recommendations "
            "must be added to app/data/recommendation_catalog.py and reviewed; "
            "they are never composed at runtime."
        )
    return Recommendation(code=entry.code, text=entry.text, category=entry.category)


def recommendations(codes: Tuple[str, ...]) -> List[Recommendation]:
    """Resolve several codes, preserving order and removing duplicates."""
    seen: Dict[str, None] = {}
    for code in codes:
        seen.setdefault(code, None)
    return [recommendation(code) for code in seen]


def is_known_code(code: str) -> bool:
    return code in RECOMMENDATIONS


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    for code, entry in RECOMMENDATIONS.items():
        if code != entry.code:
            raise ValueError(f"catalogue key {code!r} != entry code {entry.code!r}")
        if not entry.text.strip():
            raise ValueError(f"{code}: empty recommendation text")
        if entry.category not in CATEGORIES:
            raise ValueError(f"{code}: unknown category {entry.category!r}")
        if not entry.basis.strip():
            raise ValueError(f"{code}: every entry must record why it exists")
        assert_safe(entry.text, f"recommendation {code}")
    # The scanner itself must not be vacuous. If none of the patterns matches a
    # sentence built out of the very things they exist to ban, the scanner has
    # been broken and the whole safety property with it.
    canary = "Take metformin 500 mg twice a day; this confirms you have diabetes."
    if len(scan_text(canary)) < 4:
        raise ValueError(
            "the recommendation safety scanner no longer detects an obviously "
            "unsafe sentence -- it has been broken"
        )


_self_check()


def catalog_document() -> Dict[str, object]:
    """Machine-readable dump of the catalogue, for clinical review."""
    return {
        "categories": list(CATEGORIES),
        "forbidden_patterns": [name for name, _ in _FORBIDDEN_PATTERNS],
        "recommendations": {
            code: {
                "text": entry.text,
                "category": entry.category,
                "basis": entry.basis,
            }
            for code, entry in RECOMMENDATIONS.items()
        },
    }


__all__ = [
    "CATEGORIES",
    "CONFIRM_WITH_REPEAT_TESTING",
    "DISCUSS_SAMPLE_TIMING",
    "DISCUSS_WITH_CLINICIAN",
    "GENERAL_BALANCED_DIET",
    "GENERAL_DIETARY_FAT_QUALITY",
    "GENERAL_HYDRATION",
    "GENERAL_IRON_RICH_FOODS",
    "GENERAL_LIMIT_ADDED_SUGAR",
    "GENERAL_PHYSICAL_ACTIVITY",
    "GENERAL_SMOKING_CESSATION_SUPPORT",
    "GENERAL_VITAMIN_B12_SOURCES",
    "GENERAL_VITAMIN_D_SOURCES",
    "GENERAL_WEIGHT_DISCUSSION",
    "INFORMATION_INCOMPLETE",
    "INPUT_QUALITY_CAVEAT",
    "MONITOR_OVER_TIME",
    "NOTHING_FLAGGED_EDUCATIONAL",
    "NOT_A_DIAGNOSIS",
    "RECOMMENDATIONS",
    "SEEK_PROMPT_MEDICAL_ADVICE",
    "UNREADABLE_DOCUMENT_RECHECK",
    "CatalogEntry",
    "UnknownRecommendationError",
    "UnsafeRecommendationError",
    "assert_safe",
    "catalog_document",
    "is_known_code",
    "recommendation",
    "recommendations",
    "scan_text",
]
