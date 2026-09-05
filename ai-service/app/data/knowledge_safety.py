"""The Module 22 corpus safety scanner.

WHY THIS FILE EXISTS AT ALL (please read before "de-duplicating" it)
--------------------------------------------------------------------------
`app/data/recommendation_catalog.py` already carries a safety scanner, and this
one is deliberately a SEPARATE implementation of the same idea rather than an
import of it. Two reasons, one temporary and one permanent:

* TEMPORARY: at the time Modules 21/22 were written, another module was
  concurrently hardening the recommendation catalogue's scanner. Importing a
  file being edited underneath you couples two modules' import-time failure
  behaviour to one in-flight edit.
* PERMANENT: the two scanners guard DIFFERENT text. The recommendation
  catalogue guards ~30 short, fixed sentences that the platform emits verbatim.
  This scanner guards multi-paragraph patient-education prose that is fed to an
  LLM as grounding. Prose has failure modes a one-line recommendation does not
  -- narrative certainty, second-person instruction, "what to do about it"
  sections -- and it needs patterns the recommendation scanner has no reason to
  carry.

**THIS DUPLICATION IS REPORTED, NOT HIDDEN.** If the two are later reconciled,
the merge must keep the strictly-wider union of the patterns, and the corpus
must be re-scanned; it must not keep whichever list is shorter. See
`ai-service/README.md`, Modules 21-22 section.

WHAT IT ENFORCES
--------------------------------------------------------------------------
The corpus is what an LLM is grounded on (spec section 12, section 14). Unsafe
content HERE becomes unsafe output THERE, after every downstream guard has
already been passed, because a grounded model is *supposed* to repeat its
sources. So the corpus is held to the Module 24 output standard at import time:

    no diagnostic assertion     no medication name or class
    no dosage                   no treatment instruction
    no certainty claim          no "you don't need a clinician"

A violation raises at IMPORT, so the service refuses to start. It is never a
warning and never a filtered-out document: a corpus that silently drops a
document retrieves less than the reviewer thinks it does, which is the failure
mode that makes an audit meaningless.

DESIGN NOTE -- WIDE PATTERNS, NARROW EXCUSES
--------------------------------------------------------------------------
Every pattern below is written to over-match and then to excuse only the exact
safe phrasing the platform is required to use (e.g. `\\bdiagnos\\w*` is banned
outright, with a fixed-width lookbehind carving out "not a diagnosis"). This is
the right way round. A new way of asserting a diagnosis is caught by default,
whereas a new entry in an enumeration of banned words is not.
"""

from __future__ import annotations

import re
from typing import List, Tuple

#: (name, compiled pattern). The NAME is reported on failure so a rejection
#: says which rule tripped rather than only that something did.
FORBIDDEN_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        # ------------------------------------------------ medication names --
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
        # Pharmacological STEMS, so a drug nobody thought to enumerate is still
        # caught. The leading `\w{3,}` stops the stems matching short innocent
        # words ("also" would otherwise trip `-olol`... it would not, but
        # "control" and "protocols" are the kind of near-miss this guards).
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
        # ------------------------------------------------------ see NOTE ----
        # `prescrib\w*` lives in `treatment_instruction` below and fires on
        # "prescribed preparations" -- which is the platform's own APPROVED way
        # of referring to medication in general without naming any. Banning the
        # safe circumlocution pushes an author toward naming a drug instead,
        # which is strictly worse, so that exact noun phrase is excused there.
        # ------------------------------------------------------- dosage ----
        # A DOSE is a quantity of a substance to put in a body ("500 mg").
        # A laboratory THRESHOLD is a concentration ("126 mg/dL"). The negative
        # lookahead for a following "/" is the whole distinction, so reference
        # bands may be quoted while doses stay banned.
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
        # A spelled-out unit with a NUMBER in front of it is a dose.
        (
            "dose_quantity_word",
            r"\b\d+(\.\d+)?\s*(milligrams?|micrograms?|international units?)\b",
        ),
        # A spelled-out unit with no number is only a dose if it is not naming a
        # CONCENTRATION. "milligrams per decilitre" is the written-out form of
        # mg/dL, which the numeric `dose_quantity` pattern already excuses via
        # its `(?!\s*/)` lookahead; without the same carve-out here, the corpus
        # could quote "126 mg/dL" but not explain what mg/dL means, which is
        # precisely what the terminology documents exist to do.
        (
            "dose_unit_word",
            r"\b(milligrams?|micrograms?|international units?)\b"
            r"(?!\s+per\s+(decilitre|deciliter|litre|liter|millilitre|milliliter"
            r"|mole|kilogram|square))",
        ),
        # ------------------------------------------ treatment instruction --
        # `treat` has one common non-clinical sense the platform genuinely uses
        # ("treat it with reduced confidence"), so exactly that epistemic
        # construction is excused and nothing wider. "treat it with iron",
        # "treated with", "treatment", "treating" all still match.
        (
            "treatment_instruction",
            # `prescribed preparation(s)` is excused -- and ONLY that exact noun
            # phrase. "prescribes", "prescription", "prescribed metformin",
            # "prescribed for you" all still fire, because the excuse requires
            # the literal word `preparation` immediately after.
            r"\b((?!prescribed\s+preparations?\b)prescrib\w*"
            # `treat` has an epistemic sense the platform genuinely uses. Two
            # constructions are excused: "treat it with reduced confidence"
            # (how much to BELIEVE a number) and "treated as context" (what
            # ROLE a value plays). Neither is about putting anything in a body.
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
        # ------------------------------------------ unsupported diagnosis --
        (
            "diagnostic_assertion",
            r"\b(you have|you are suffering|you suffer from|patient has"
            r"|this means you|indicates that you have|shows that you have)\b"
            r"|(?<!not a )(?<!not an )(?<!\bnot )(?<!never )(?<!\bnot a )"
            r"\bdiagnos\w*"
            r"|\byou are (diabetic|anaemic|anemic|obese)\b",
        ),
        # ----------------------------------------------- certainty claims --
        (
            "certainty_claim",
            r"\b(definitely|certainly|undoubtedly|guaranteed?|proves?|proven"
            r"|confirms?|confirmed|conclusive(ly)?|always means|never means"
            r"|no doubt|will develop|will get|will cause|is certain|invariably)\b"
            r"|\b100\s*%",
        ),
        # ------------------------------------------- replacing a clinician --
        (
            "replaces_clinician",
            r"\b(no need to (see|consult|visit)|instead of (seeing|consulting)"
            r"|without (seeing|consulting) a doctor|rather than (seeing|consulting)"
            r"|do not need (a|to see a) (doctor|clinician|physician))\b",
        ),
        # ---------------------------------- prose-only: urgency and alarm ----
        # These have no analogue in the recommendation catalogue, which emits no
        # prose. In multi-paragraph education, alarm language is itself unsafe:
        # it drives behaviour without evidence, and an LLM grounded on it will
        # reproduce the tone as well as the facts.
        (
            "alarmist_prose",
            r"\b(life[- ]threatening|deadly|fatal|dangerously|emergency room"
            r"|you are at risk of dying|irreversible damage)\b",
        ),
        # A grounding corpus must never speak as though it has seen the reader.
        (
            "personalised_claim",
            r"\b(your (result|value|level|report) (shows|means|indicates|proves)"
            r"|based on your results?, you)\b",
        ),
    )
)


class UnsafeKnowledgeError(ValueError):
    """Raised at import time when corpus text violates the safety rules."""


#: Collapses every run of whitespace -- including newlines -- to one space.
_WHITESPACE_RUN = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Collapse whitespace runs to single spaces before scanning.

    THIS IS A CORRECTNESS FIX, NOT COSMETIC, and it matters in BOTH directions.

    Several patterns contain literal spaces ("you have", "not a diagnosis").
    The corpus is wrapped prose, so whether a phrase happens to straddle a line
    break is an accident of formatting -- and without normalisation that
    accident decides whether the scanner sees it:

      * EVASION.  "you\\nhave diabetes" did not match `diagnostic_assertion`.
        A banned phrase escaped simply by falling across a line end. Any author
        reflowing a paragraph could silently disarm a pattern.
      * FALSE POSITIVE.  "this is not a\\ndiagnosis" DID match, because the
        `(?<!not a )` carve-out is a fixed-width literal-space lookbehind. The
        one phrasing the platform is REQUIRED to use was rejected purely
        because of where the line wrapped.

    Normalising first makes the scanner depend on the words rather than on the
    typography. Offsets are not preserved, which is why `scan_text` reports
    pattern NAMES rather than positions.

    NOTE FOR RECONCILIATION: `app/data/recommendation_catalog.py` scans raw
    text and has the same latent defect. It is not live there -- its entries
    are short single-line strings -- but any merge of the two scanners must
    keep this normalisation. See this module's docstring.
    """
    return _WHITESPACE_RUN.sub(" ", text or "").strip()


def scan_text(text: str) -> List[str]:
    """Names of every forbidden pattern present in `text`. Empty means clean."""
    flat = normalise(text)
    return [name for name, pattern in FORBIDDEN_PATTERNS if pattern.search(flat)]


def assert_safe(text: str, where: str, exempt: Tuple[str, ...] = ()) -> None:
    """Raise `UnsafeKnowledgeError` if `text` trips any non-exempt pattern.

    `where` identifies the offending document and field so a startup failure is
    actionable without grepping the corpus by hand. `exempt` names patterns a
    reviewer has deliberately granted this document -- see `EXEMPTIBLE_PATTERNS`
    and the extra checks `knowledge_base._check_document` layers on top.
    """
    matches = [m for m in scan_text(text) if m not in exempt]
    if matches:
        raise UnsafeKnowledgeError(
            f"{where}: knowledge-base text violates the medical safety rules "
            f"({', '.join(matches)}). This corpus grounds an LLM, so unsafe "
            f"text here becomes unsafe output downstream. Rewrite the document "
            f"as patient education; do not weaken the scanner."
        )


#: Patterns a single document may be granted a REVIEWED exemption from. Exactly
#: one is listed, and the list is deliberately hard to extend.
#:
#: `medication_name` is here because a handful of substances are BOTH a
#: medication and something the body makes -- insulin above all. A corpus that
#: cannot use the word "insulin" cannot explain what diabetes is, and Module 25
#: exists precisely to explain such words. Refusing the noun does not make the
#: corpus safer; it makes it useless and pushes an author toward vaguer, less
#: accurate prose.
#:
#: The exemption is granted per document, must carry a written justification,
#: and does NOT relax any other pattern. `ADMINISTRATION_CONTEXT` below is
#: applied on top, so an exempted document still cannot tell anyone to take the
#: substance -- which is the actual hazard the pattern was guarding against.
EXEMPTIBLE_PATTERNS: Tuple[str, ...] = ("medication_name",)

#: Applied to any document holding a `medication_name` exemption. This is the
#: real guard: the noun is allowed, the INSTRUCTION never is. Matches a banned
#: substance name within a short span of administration language, in either
#: order, so "insulin should be taken" and "taking insulin" both trip it while
#: "insulin is the hormone that lets glucose into cells" does not.
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
    """True if `text` puts a medication noun next to administration language."""
    return bool(ADMINISTRATION_CONTEXT.search(normalise(text)))


#: A sentence built entirely out of the things the scanner exists to ban. If
#: fewer than this many patterns fire, the scanner has been broken and the
#: whole safety property with it. Asserted by `knowledge_base._self_check()`.
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
