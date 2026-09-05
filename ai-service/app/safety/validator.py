"""Module 24 -- the validator itself.

    text  ->  validate_text()  ->  SafetyVerdict(verdict, violations,
                                                 approved_text, modifications)

Framework-independent: no FastAPI, no HTTP, no network, no I/O. Module 23 will
call `validate_text` in-process on every generation, so the whole layer has to
be importable and callable without a server.

==========================================================================
THE THREE PROPERTIES THIS FILE HAS TO HOLD
==========================================================================

1. FAIL CLOSED. Every path that cannot complete an analysis returns REJECT.
   The whole body of `validate_text` is wrapped in `try/except BaseException`
   whose handler builds a rejection; there is no `return APPROVE` reachable
   from an error. A validator that answers "no violations found" because it
   crashed is worse than no validator, because the caller cannot tell the two
   apart.

2. NEVER LOG THE CONTENT. The text under validation is PHI-adjacent -- it may
   restate laboratory values, and Module 23 will feed it the patient's own
   numbers. Only codes, counts and the verdict are logged, through
   `safe_meta`. The offending spans travel in the RETURN VALUE, where the
   caller who already has the text can audit them.

3. NEVER REWRITE CLINICAL MEANING. The only two things a modification may do
   are append fixed catalogue text, and delete a whole sentence that carried an
   instruction. No paraphrase, no substitution, no softening. See
   `MODIFICATION_POLICY` in policy.py, which the endpoint publishes.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.safety.policy import (
    CODE_SEVERITY,
    CLINICAL_SUBJECT,
    HEDGE_MARKERS,
    IMPERATIVE_ACTION_VERBS,
    INTERPRETIVE_VERBS,
    PERMITTED_DIRECTIVE_VERBS,
    PROFESSIONAL_REFERENCE,
    RULES,
    SAFETY_LAYER_VERSION,
    SafetyRule,
    Severity,
    ViolationCode,
)

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------

APPROVE = "approve"
APPROVE_WITH_MODIFICATION = "approve_with_modification"
REJECT = "reject"

VERDICTS: Tuple[str, ...] = (APPROVE, APPROVE_WITH_MODIFICATION, REJECT)

#: Anything longer than this is refused rather than analysed. A patient-facing
#: explanation is a few paragraphs; a megabyte of text is a malfunction, and
#: running a dozen regexes over it is how a validator becomes a denial of
#: service.
MAX_TEXT_LENGTH = 20_000

#: What replaces a redacted sentence. Fixed, reviewed, and itself safe: it
#: names a qualified healthcare professional and issues no instruction beyond
#: the permitted `discuss`.
REDACTION_NOTICE = (
    "[A sentence was removed here by the VaidyaAI safety layer because it "
    "gave guidance this system is not permitted to give. Please discuss this "
    "topic with a qualified healthcare professional.]"
)

#: Appended when the mandated referral framing is missing. Taken VERBATIM from
#: the reviewed recommendation catalogue rather than written here, so the one
#: sentence this layer is allowed to add is a sentence a clinician signed off.
def _framing_text() -> str:
    from app.data.recommendation_catalog import NOT_A_DIAGNOSIS, recommendation

    return recommendation(NOT_A_DIAGNOSIS).text


# --------------------------------------------------------------------------
# The returned objects
# --------------------------------------------------------------------------


class SafetyViolation(BaseModel):
    """One finding: what rule, where, and why.

    `excerpt` is the offending span, so a rejection is actionable -- Module 23
    can retry with the span quoted back into the prompt, and a reviewer can see
    what tripped. It is NEVER logged.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ViolationCode
    rule_id: str
    severity: Severity
    reason: str
    span_start: int
    span_end: int
    excerpt: str
    #: The sentence the span sits in, so a caller can act on whole statements.
    sentence_index: int


class SafetyModification(BaseModel):
    """One change applied to produce `approved_text`. Auditable by design."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    code: ViolationCode
    reason: str
    span_start: int
    span_end: int
    removed_excerpt: Optional[str] = None


class SafetyVerdict(BaseModel):
    """The machine-readable answer Module 23 acts on.

    `approved_text` is the ONLY string a caller may show a patient, and it is
    `None` for a rejection. A caller that shows `analysed_text` instead has
    bypassed the layer; there is deliberately no other field that could be
    mistaken for approved output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: str
    version: str = SAFETY_LAYER_VERSION
    approved_text: Optional[str] = None
    #: The normalised text the spans index into. Present so an offset is
    #: interpretable; NOT for display.
    analysed_text: Optional[str] = None
    violations: Tuple[SafetyViolation, ...] = ()
    modifications: Tuple[SafetyModification, ...] = ()
    #: True exactly when the caller must show the fallback instead.
    fallback_required: bool = False

    @property
    def approved(self) -> bool:
        return self.verdict in (APPROVE, APPROVE_WITH_MODIFICATION)

    @property
    def codes(self) -> Tuple[str, ...]:
        return tuple(v.code.value for v in self.violations)

    def code_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for violation in self.violations:
            counts[violation.code.value] = counts.get(violation.code.value, 0) + 1
        return counts


class SafetyContext(BaseModel):
    """What policy applies to this particular generation.

    `grounding_sources` are the retrieved knowledge chunks Module 21/22 handed
    the LLM; `permitted_numbers` are the patient's own validated values, which
    an explanation is obviously allowed to restate. Together they define which
    numbers may appear in the output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Retrieved knowledge the generation was supposed to be grounded in.
    grounding_sources: Tuple[str, ...] = ()
    #: Numbers the explanation may legitimately state (the patient's values,
    #: reference-range bounds, and so on).
    permitted_numbers: Tuple[float, ...] = ()
    #: Refuse the generation outright if no grounding was supplied.
    require_grounding: bool = False
    #: Require the mandated "consult a qualified healthcare professional"
    #: framing. Off only for fragment-level checks (a single sentence, a band
    #: label) where the framing lives in the surrounding document.
    require_referral: bool = True
    #: Enforce the numeric-grounding control. Automatically active whenever
    #: grounding material is supplied.
    check_numeric_grounding: bool = True
    #: Free-text label for what is being validated. Never logged, never shown.
    purpose: str = "llm_explanation"


class UnsafeGeneratedContentError(ValueError):
    """Raised by `assert_safe_for_patient` when a verdict is a rejection."""

    def __init__(self, verdict: SafetyVerdict) -> None:
        super().__init__(
            "generated content was refused by the Module 24 safety layer: "
            f"{sorted(set(verdict.codes))}"
        )
        self.verdict = verdict


# --------------------------------------------------------------------------
# Normalisation -- run BEFORE any pattern, so homoglyph/zero-width evasion of
# a word boundary is at least made harder. Spans index into the result.
# --------------------------------------------------------------------------

#: Invisible format characters, mapped to a SPACE -- NOT deleted.
#:
#: These used to be deleted (`dict.fromkeys([...], None)`), which made the
#: layer WORSE than doing nothing: deleting the zero-width space in
#: "you<ZWSP>have" yields "youhave", which matches no rule at all. A banned
#: phrase escaped by having an INVISIBLE character inserted into it, and the
#: deletion is what created the escape.
#:
#: Mapping to a space is length-preserving (one character in, one out), so
#: every span offset stays valid and redaction is unaffected. It also composes
#: correctly with `_GAP` in the rule patterns, which already tolerates a run of
#: non-word characters between words.
#:
#: NOT closed by this: homoglyphs (Cyrillic "у" for Latin "y") and combining
#: marks, which need confusable folding. Deliberately out of scope -- the
#: endpoint is service-key gated and the realistic producer is Gemini, which
#: does not emit Cyrillic lookalikes. Published in SAFETY_POLICY["limitations"]
#: rather than implied away, the same posture this layer takes about `digoxin`.
_ZERO_WIDTH = {
    cp: " " for cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E)
}

#: C0/C1 control characters other than tab, newline and carriage return.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


#: Line separators mapped to a plain space, one character in, one character
#: out.
#:
#: An earlier version of this comment claimed the mapping meant "every span
#: offset computed against the normalised text still indexes correctly into the
#: caller's original string". THAT WAS FALSE and an audit caught it: the NFKC
#: pass in `_normalise` runs first and is NOT length-preserving
#: (`len(_normalise("ﬁx")) == 3` for a 2-character input, because the "fi"
#: ligature expands). Spans index into `analysed`, not into the caller's text.
#:
#: Nothing is broken by that -- redaction operates on `analysed` throughout, so
#: the system is self-consistent -- but the invariant as stated was untrue, and
#: someone would eventually have relied on it. The 1:1 mapping here is still
#: worth keeping: it means THIS step adds no drift of its own.
_LINE_BREAKS = {
    0x000A: " ",  # newline
    0x000D: " ",  # carriage return
    0x0085: " ",  # NEL
    0x2028: " ",  # line separator
    0x2029: " ",  # paragraph separator
}


def _normalise(text: str) -> str:
    """Fold away typography so detection depends on WORDS, not line wrapping.

    THIS IS A CORRECTNESS FIX, NOT COSMETIC, and it matters in BOTH directions.
    Many rules contain literal spaces ("you have", "not a diagnosis"), and a
    literal space does not match a newline. Before this, whether a phrase
    happened to straddle a line break decided whether the scanner saw it:

      * EVASION. "you<newline>have diabetes" matched NOTHING -- the verdict fell
        from `reject` (UNSUPPORTED_DIAGNOSIS) to `approve_with_modification`.
        A banned assertion escaped purely by falling across a line end.
      * FALSE POSITIVE. "this is not a<newline>diagnosis" WAS flagged, because
        the `(?<!not a )` carve-out is a fixed-width literal-space lookbehind.
        The exact phrasing the platform is REQUIRED to use was rejected because
        of where the text happened to wrap.

    This is not a theoretical edge case here. Module 23 emits wrapped LLM prose,
    so a soft wrap landing mid-phrase is the NORMAL case. The same defect was
    found independently in the Module 22 corpus scanner.

    THE THREE SCANNERS ARE NOT RECONCILED, and an earlier version of this
    comment wrongly claimed they were ("fixed in all three so the sibling
    scanners cannot drift apart again"). They had drifted, and the drift is
    exactly why this one was the weakest: the two siblings collapse ALL
    whitespace runs (`" ".join(text.split())`), while this validator mapped
    five line-separator code points 1:1 -- which closed a bare newline and
    nothing else. CRLF became two spaces, tab was never mapped, and a
    pre-existing double space had never been addressed.

    What actually closes that class here is `_GAP` in `app/safety/policy.py`:
    the rules tolerate a run of non-word characters between words, so the fix
    lives in the patterns rather than in the normalisation. Reconciling the
    three scanners into one rule table is still worth doing and has not been
    done.

    Line breaks are mapped 1:1 to spaces rather than collapsed, so offsets are
    preserved exactly and the caller's own text -- paragraphs intact -- remains
    what gets returned.
    """
    folded = unicodedata.normalize("NFKC", text.translate(_ZERO_WIDTH))
    return folded.translate(_LINE_BREAKS)


#: Sentence boundaries. Line breaks are already spaces by the time this runs
#: (see `_normalise`), so a soft wrap no longer splits one sentence into two and
#: cannot hide a phrase from a rule by straddling the join.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[Tuple[int, int, str]]:
    """`(start, end, text)` for each sentence. Offsets index into `text`."""
    out: List[Tuple[int, int, str]] = []
    cursor = 0
    for match in _SENTENCE_SPLIT.finditer(text):
        chunk = text[cursor : match.start()]
        if chunk.strip():
            out.append((cursor, match.start(), chunk))
        cursor = match.end()
    tail = text[cursor:]
    if tail.strip():
        out.append((cursor, len(text), tail))
    return out


def _sentence_index_for(span_start: int, sentences: Sequence[Tuple[int, int, str]]) -> int:
    for index, (start, end, _) in enumerate(sentences):
        if start <= span_start < end:
            return index
    return -1


# --------------------------------------------------------------------------
# Positive controls
# --------------------------------------------------------------------------

_HEDGE = re.compile(
    r"\b(" + "|".join(re.escape(h) for h in HEDGE_MARKERS) + r")\b", re.IGNORECASE
)
_INTERPRETIVE = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in INTERPRETIVE_VERBS) + r")\b",
    re.IGNORECASE,
)
_DIRECTIVE_MODAL = re.compile(
    r"\byou\s+(?:should|must|need\s+to|ought\s+to|have\s+to|are\s+advised\s+to"
    r"|are\s+recommended\s+to|had\s+better)\s+(?:not\s+)?([a-z][a-z-]*)",
    re.IGNORECASE,
)
#: The epistemic construction Module 6's own boilerplate uses -- "treat it with
#: reduced confidence" -- must never read as an imperative to act on a body.
#: Same closed list as the treatment rule's lookahead, kept here because the
#: imperative check works on the clause head rather than on the whole text.
_EPISTEMIC_TREAT = re.compile(
    r"^treat(?:s|ed|ing)?\s+(?:it|this|that|these|them|such\s+values?|these\s+values?|those\s+values?|the\s+values?"
    r"|the\s+value|the\s+figure)\s+with\s+(?:reduced\s+confidence"
    r"|less\s+confidence|lower\s+confidence|caution|care|scepticism"
    r"|skepticism|suspicion)\b",
    re.IGNORECASE,
)
_CLAUSE_HEAD = re.compile(r"(?:^|[.!?;:\n]\s*)([A-Za-z][A-Za-z-]*)")
#: Digit-form numbers.
#:
#: The lookbehind stops a match mid-identifier ("HbA1c" must not yield "1"),
#: but `(?<![\w.])` also rejected a LEADING DECIMAL POINT, so ".5 points" was
#: invisible to the grounding check entirely. `(?<!\d)\.?` below allows a
#: bare ".5" while still refusing "6.8" to match a second time at ".8".
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?|(?<![\w.])\.\d+")

#: Numbers written as WORDS.
#:
#: The grounding control is the one place a hallucination can be checked
#: exactly, and it was defeated by the model simply spelling the number out:
#:
#:     "Your HbA1c is nine point nine percent."   -> approved
#:
#: That is not an exotic evasion. Spec Module 23 asks for plain language, so a
#: spelled-out number is a NORMAL thing for this model to produce -- the
#: control was blind in precisely the register it was written for.
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_WORD = re.compile(
    r"\b(?:"
    + "|".join(sorted(list(_UNITS) + list(_TENS) + ["hundred", "point", "and"], key=len, reverse=True))
    + r")(?:[\s-]+(?:"
    + "|".join(sorted(list(_UNITS) + list(_TENS) + ["hundred", "point", "and"], key=len, reverse=True))
    + r"))*\b",
    re.IGNORECASE,
)


#: A unit immediately after a spelled number is what makes it a reading rather
#: than a word. "nine percent" is a measurement; "one of the two main types" is
#: English.
#: DELIBERATELY CONSERVATIVE. Only units that are unambiguously measurements.
#:
#: An earlier version included "unit", "point", "time", "year" and similar.
#: Those are ordinary English words, and the corpus says things like "one unit
#: either side of the reference range" -- which was read as the measurement
#: "1 unit" and reported as a fabricated value, so Module 24 REJECTED the
#: platform's own reviewed text and the patient lost the explanation entirely.
#:
#: Being conservative here costs very little: a digit-form number is caught
#: regardless of what follows it, and a spelled-out decimal ("nine point nine")
#: or compound ("one hundred and twenty six") is caught by shape alone. This
#: list only has to catch the remaining case of a single spelled digit next to
#: a real unit, and a false positive there is far more damaging than a miss --
#: it silently withholds a correct explanation.
_MEASUREMENT_UNIT = re.compile(
    r"\s*(percent|per\s*cent|%|mg|mcg|µg|ug|kg|ng|pg|mmol|umol|µmol"
    r"|mg/dl|mmol/l|g/dl|ng/ml|pg/ml|mmhg|kg/m2)\b",
    re.IGNORECASE,
)


def _spelled_number(phrase: str) -> Optional[float]:
    """Parse "nine point nine" / "one hundred and twenty six" to a float.

    Returns None for a phrase that is not actually a number ("and", "point"
    alone), so an ordinary sentence containing the word "one" does not become a
    grounding violation.
    """
    words = [w for w in re.split(r"[\s-]+", phrase.lower()) if w and w != "and"]
    if not words or all(w in {"point", "hundred"} for w in words):
        return None

    if "point" in words:
        head, _, tail = phrase.lower().partition("point")
        whole = _spelled_number(head) if head.strip() else 0.0
        digits = [
            _UNITS[w] for w in re.split(r"[\s-]+", tail.strip()) if w in _UNITS
        ]
        if whole is None or not digits:
            return None
        return float(f"{int(whole)}.{''.join(str(d) for d in digits)}")

    total, current = 0, 0
    seen = False
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
            seen = True
        elif word in _TENS:
            current += _TENS[word]
            seen = True
        elif word == "hundred":
            if not seen:
                return None
            current *= 100
        else:
            return None
    return float(total + current) if seen else None

#: "what X means", "whether this indicates" -- naming an interpretation is not
#: making one.
_INTERROGATIVE = re.compile(r"\b(what|whether|how|why|question of)\b", re.IGNORECASE)

#: A negator anywhere earlier in the clause turns a replacement claim into a
#: DISCLAIMER: "nothing in it replaces an assessment", "rather than a
#: substitute for it". The platform is REQUIRED to write sentences of exactly
#: that shape, so the rule that bans claiming to replace a clinician must not
#: fire on the sentence disclaiming it.
_NEGATOR = re.compile(
    r"\b(not|never|no|nothing|none|cannot|rather\s+than|instead\s+of\s+a\s+"
    r"substitute)\b",
    re.IGNORECASE,
)


#: Invisible format characters REMOVED rather than spaced. Used only by
#: `_compacted_pass`.
_FORMAT_STRIPPED = dict.fromkeys(
    (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E), None
)


def _compacted_pass(
    original: str, analysed: str, already: Sequence[SafetyViolation]
) -> List[SafetyViolation]:
    """Second detection pass with invisible characters REMOVED, not spaced.

    An invisible character inside a word and one between two words need
    OPPOSITE treatments, and no single normalisation gives both:

        "met<ZWSP>formin"      -> must become "metformin"  (remove)
        "you<ZWSP>have"        -> must become "you have"   (space)

    Removing breaks the second (it yields "youhave", matching nothing, which is
    how an invisible character used to smuggle a banned phrase through).
    Spacing breaks the first (it yields "met formin", so an obfuscated drug
    name escapes). So the text is scanned BOTH ways and the results unioned.

    Only PROHIBITED findings are taken from this pass, and they are reported
    against the whole text rather than a span, because offsets computed on the
    compacted string do not index into the caller's text. That is safe: a
    prohibited violation always rejects outright and is never redacted, so no
    span is ever used. Redactable and required codes are deliberately ignored
    here -- they would drive a redaction with a wrong span.
    """
    # Derive from the ORIGINAL, not from `analysed`: `_normalise` has already
    # turned every format character into a space, so stripping `analysed`
    # would find nothing to strip and this pass would silently do nothing.
    compacted = (
        unicodedata.normalize("NFKC", original)
        .translate(_FORMAT_STRIPPED)
        .translate(_LINE_BREAKS)
    )
    if compacted == analysed:
        return []

    seen = {(v.code, v.rule_id) for v in already}
    extra: List[SafetyViolation] = []
    whole = [(0, len(original), original)]
    for violation in _scan_rules(compacted, whole, RULES):
        if CODE_SEVERITY[violation.code] is not Severity.PROHIBITED:
            continue
        if (violation.code, violation.rule_id) in seen:
            continue
        seen.add((violation.code, violation.rule_id))
        extra.append(
            SafetyViolation(
                code=violation.code,
                rule_id=violation.rule_id,
                severity=violation.severity,
                reason=violation.reason,
                span_start=0,
                span_end=len(original),
                excerpt=violation.excerpt,
                sentence_index=0,
            )
        )
    return extra


def _drop_disclaimed_diagnoses(
    text: str,
    sentences: Sequence[Tuple[int, int, str]],
    violations: List[SafetyViolation],
) -> List[SafetyViolation]:
    """Excuse `diagnos*` hits that sit inside a disclaiming clause.

    This replaces eight fixed-width negative lookbehinds that used to live in
    the pattern itself. They excused the eight phrasings their author happened
    to enumerate and REJECTED every other correct English disclaimer:

        "This is never a diagnosis."          -> rejected
        "This is not any kind of diagnosis."  -> rejected
        "No diagnosis is offered here."       -> rejected
        "This is not  a diagnosis."           -> rejected (two spaces)

    `UNSUPPORTED_DIAGNOSIS` is PROHIBITED, so each of those refused the WHOLE
    generation and handed the patient the fallback -- punishing the model for
    disclaiming correctly. Worse, the retry feedback quotes the offending span
    back to the model, which teaches it to drop the disclaimer altogether.

    Scoped exactly like `_drop_disclaimed_replacements`, because a negation
    guard is the classic place to hide a hole in a safety rule:

    * only hits whose matched text IS the word `diagnos*` are eligible. The
      rule's other branch ("you have <condition>") is NEVER excused -- "you do
      not have diabetes" is still a clinical assertion this system may not make;
    * only the text BEFORE the match is considered;
    * the window is clamped to the violation's own sentence, so a negator in a
      previous sentence cannot excuse a claim in this one.
    """
    kept: List[SafetyViolation] = []
    for violation in violations:
        if (
            violation.code is ViolationCode.UNSUPPORTED_DIAGNOSIS
            and violation.excerpt.lower().startswith("diagnos")
        ):
            floor = 0
            if 0 <= violation.sentence_index < len(sentences):
                floor = sentences[violation.sentence_index][0]
            window_start = max(floor, violation.span_start - 60)
            if _NEGATOR.search(text[window_start : violation.span_start]):
                continue
        kept.append(violation)
    return kept


def _drop_disclaimed_replacements(
    text: str,
    sentences: Sequence[Tuple[int, int, str]],
    violations: List[SafetyViolation],
) -> List[SafetyViolation]:
    """Remove REPLACES_* hits that sit inside a negated (disclaiming) clause.

    Scoped three ways, because a negation guard is the classic place to put a
    hole in a safety rule:

    * only this one code is affected;
    * only the text before the match is considered;
    * THE WINDOW IS CLAMPED TO THE VIOLATION'S OWN SENTENCE. A negator in a
      PREVIOUS sentence must never excuse a claim in this one -- without the
      clamp, "You do not need to see a doctor. There is no need to consult
      anyone." would have the first sentence excusing the second.

    The assertions themselves are untouched: "you do not need to see a doctor"
    carries its negator INSIDE the matched span, so there is nothing before it
    to excuse it.
    """
    kept: List[SafetyViolation] = []
    for violation in violations:
        if violation.code is ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION:
            floor = 0
            if 0 <= violation.sentence_index < len(sentences):
                floor = sentences[violation.sentence_index][0]
            window_start = max(floor, violation.span_start - 60)
            if _NEGATOR.search(text[window_start : violation.span_start]):
                continue
        kept.append(violation)
    return kept


def _check_hedging(
    sentences: Sequence[Tuple[int, int, str]]
) -> List[SafetyViolation]:
    """REQUIRED_HEDGING -- an interpretation must be hedged.

    This is a positive control, not a blocklist: it does not look for a list of
    bad interpretations, it requires that ANY interpretation carry the register
    the spec mandates. "Your HbA1c is 6.8%" is a restatement and passes
    untouched; "this means you are diabetic" is an interpretation with no
    hedge and is refused whatever condition it names.

    THREE conditions must hold before the rule fires, and the third is what
    keeps it from becoming noise: the sentence has to be ABOUT SOMEONE'S
    CLINICAL STATE. A definitional gloss is not an interpretation --
    "confidence=None, which means no probability is produced" is this
    service's own rule metadata, and Module 25's terminology explainer exists
    precisely to say "HbA1c means glycated haemoglobin". Neither is a claim
    about a patient, and neither needs a hedge. See
    `policy._clinical_subject_terms`.
    """
    out: List[SafetyViolation] = []
    for index, (start, _end, sentence) in enumerate(sentences):
        match = _INTERPRETIVE.search(sentence)
        if match is None:
            continue
        if _HEDGE.search(sentence):
            continue
        if not CLINICAL_SUBJECT.search(sentence):
            continue
        # "What a result means for an individual is a question for a qualified
        # healthcare professional" NAMES an interpretation without making one.
        # An interrogative or nominal clause is not an assertion, and a rule
        # that fires on the sentence deferring to a clinician is a rule nobody
        # will keep switched on.
        if _INTERROGATIVE.search(sentence[max(0, match.start() - 40) : match.start()]):
            continue
        out.append(
            SafetyViolation(
                code=ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM,
                rule_id="positive.required_hedging",
                severity=CODE_SEVERITY[ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM],
                reason=(
                    "States an interpretation without a hedge. A patient-facing "
                    "explanation must say what a finding MAY mean, not what it "
                    "does mean."
                ),
                span_start=start + match.start(),
                span_end=start + match.end(),
                excerpt=match.group(0),
                sentence_index=index,
            )
        )
    return out


def _check_directives(
    sentences: Sequence[Tuple[int, int, str]]
) -> List[SafetyViolation]:
    """DIRECTIVE_VERB_ALLOWLIST -- what the reader is told to do.

    Two detectors, and they are different in kind:

    * `you should <verb>` is an ALLOWLIST check. The verb must be one of the
      permitted ones (discuss, ask, consult, ...). Everything else is refused
      without the layer knowing what it was.
    * a clause-initial imperative is a BLOCKLIST check against
      `IMPERATIVE_ACTION_VERBS`, because an imperative cannot be recognised
      without a part-of-speech tagger. This half is honestly incomplete.

    "Take half a tablet at night" trips both, and independently trips the
    dosage rules, which is why it is rejected rather than redacted.
    """
    out: List[SafetyViolation] = []
    for index, (start, _end, sentence) in enumerate(sentences):
        for match in _DIRECTIVE_MODAL.finditer(sentence):
            verb = match.group(1).lower()
            if verb in PERMITTED_DIRECTIVE_VERBS:
                continue
            out.append(
                SafetyViolation(
                    code=ViolationCode.UNPERMITTED_DIRECTIVE,
                    rule_id="positive.directive_verb_allowlist",
                    severity=CODE_SEVERITY[ViolationCode.UNPERMITTED_DIRECTIVE],
                    reason=(
                        f"Tells the reader to {verb!r}. Only "
                        f"{', '.join(PERMITTED_DIRECTIVE_VERBS[:6])} and a few "
                        "other conversational verbs are permitted; every other "
                        "instruction belongs to a clinician."
                    ),
                    span_start=start + match.start(),
                    span_end=start + match.end(),
                    excerpt=match.group(0),
                    sentence_index=index,
                )
            )
        for match in _CLAUSE_HEAD.finditer(sentence):
            word = match.group(1)
            if word.lower() not in IMPERATIVE_ACTION_VERBS:
                continue
            if _EPISTEMIC_TREAT.match(sentence[match.start(1) :]):
                continue
            out.append(
                SafetyViolation(
                    code=ViolationCode.UNPERMITTED_DIRECTIVE,
                    rule_id="positive.directive_verb_allowlist",
                    severity=CODE_SEVERITY[ViolationCode.UNPERMITTED_DIRECTIVE],
                    reason=(
                        f"Opens a clause with the instruction {word.lower()!r}. "
                        "A patient-facing explanation does not instruct."
                    ),
                    span_start=start + match.start(1),
                    span_end=start + match.end(1),
                    excerpt=word,
                    sentence_index=index,
                )
            )
    return out


def _permitted_number_strings(context: SafetyContext) -> Tuple[set, bool]:
    """The numbers this generation is allowed to state, and whether to check."""
    allowed = set()
    for source in context.grounding_sources:
        if not isinstance(source, str):
            continue
        for match in _NUMBER.finditer(source):
            allowed.add(float(match.group(0)))
    for number in context.permitted_numbers:
        allowed.add(float(number))
    active = bool(context.grounding_sources) or bool(context.permitted_numbers)
    return allowed, active


def _check_numeric_grounding(
    text: str,
    sentences: Sequence[Tuple[int, int, str]],
    context: SafetyContext,
) -> List[SafetyViolation]:
    """NUMERIC_GROUNDING -- no number the model invented.

    Spec section 23 requires LLM explanations to "be grounded in retrieved
    medical information". Numbers are the part of that requirement which can
    actually be checked exactly, and they are the part where a hallucination
    does the most damage (a fabricated threshold reads as a clinical fact).

    Only active when the caller supplies grounding material. Module 23 is
    expected to always supply it; a caller that supplies none gets no numeric
    control and `SAFETY_POLICY['limitations']` says so.
    """
    if not context.check_numeric_grounding:
        return []
    allowed, active = _permitted_number_strings(context)
    if not active:
        return []
    out: List[SafetyViolation] = []

    # Digit form and word form are checked with the same allowlist, so
    # "6.8" and "six point eight" are treated identically. Without the second
    # pass the control was defeated by the model writing the number out, which
    # plain-language guidance actively encourages it to do.
    candidates: List[Tuple[int, int, str, float]] = []
    for match in _NUMBER.finditer(text):
        candidates.append((match.start(), match.end(), match.group(0), float(match.group(0))))
    for match in _NUMBER_WORD.finditer(text):
        phrase = match.group(0)
        # A spelled number only counts as a MEASUREMENT CLAIM in a numeric
        # context. Without this, ordinary prose became ungrounded numbers:
        # the curated corpus says things like "one of the two main types",
        # and "one" and "two" were each reported as a fabricated value --
        # which made Module 24 reject the platform's own reviewed text.
        #
        # A phrase qualifies when it is a decimal ("nine point nine"), a
        # compound ("one hundred and twenty six"), or is immediately followed
        # by a unit. A bare "one" in a sentence is a word, not a reading.
        words = [w.lower() for w in re.split(r"[\s-]+", phrase.strip()) if w]
        # "and" and "point" are CONNECTORS, not values. Counting them as words
        # made "one and why it is..." look like a two-word number and flagged
        # the curated corpus's own prose as a fabricated value.
        value_words = [w for w in words if w in _UNITS or w in _TENS or w == "hundred"]
        has_decimal = "point" in words and len(value_words) >= 2
        followed_by_unit = bool(
            _MEASUREMENT_UNIT.match(text[match.end() : match.end() + 24])
        )
        if len(value_words) < 2 and not has_decimal and not followed_by_unit:
            continue
        value = _spelled_number(phrase)
        if value is not None:
            candidates.append((match.start(), match.end(), phrase, value))

    for span_start, span_end, excerpt, value in candidates:
        if value in allowed:
            continue
        out.append(
            SafetyViolation(
                code=ViolationCode.UNGROUNDED_NUMERIC_CLAIM,
                rule_id="positive.numeric_grounding",
                severity=CODE_SEVERITY[ViolationCode.UNGROUNDED_NUMERIC_CLAIM],
                reason=(
                    "States a number that appears neither in the retrieved "
                    "knowledge nor among the patient's validated values. An "
                    "unsourced number in a medical explanation reads as a "
                    "clinical fact."
                ),
                span_start=span_start,
                span_end=span_end,
                excerpt=excerpt,
                sentence_index=_sentence_index_for(span_start, sentences),
            )
        )
    return out


def _check_referral(text: str) -> List[SafetyViolation]:
    """REQUIRED_PROFESSIONAL_REFERRAL -- the framing the spec mandates."""
    if PROFESSIONAL_REFERENCE.search(text):
        return []
    return [
        SafetyViolation(
            code=ViolationCode.MISSING_PROFESSIONAL_REFERRAL,
            rule_id="positive.required_professional_referral",
            severity=CODE_SEVERITY[ViolationCode.MISSING_PROFESSIONAL_REFERRAL],
            reason=(
                "Does not name a qualified healthcare professional. Spec "
                "section 14 requires patient-facing output to point at "
                "professional care rather than stand in for it."
            ),
            span_start=len(text),
            span_end=len(text),
            excerpt="",
            sentence_index=-1,
        )
    ]


# --------------------------------------------------------------------------
# Prohibition scan
# --------------------------------------------------------------------------


def _scan_rules(
    text: str, sentences: Sequence[Tuple[int, int, str]], rules: Iterable[SafetyRule]
) -> List[SafetyViolation]:
    out: List[SafetyViolation] = []
    for rule in rules:
        assert rule.pattern is not None  # guaranteed by policy._self_check
        for match in rule.pattern.finditer(text):
            out.append(
                SafetyViolation(
                    code=rule.code,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    reason=rule.reason,
                    span_start=match.start(),
                    span_end=match.end(),
                    excerpt=match.group(0),
                    sentence_index=_sentence_index_for(match.start(), sentences),
                )
            )
    return out


# --------------------------------------------------------------------------
# Structural / fail-closed gate
# --------------------------------------------------------------------------


def _structural_violation(code: ViolationCode, reason: str) -> SafetyViolation:
    return SafetyViolation(
        code=code,
        rule_id=f"structural.{code.value.lower()}",
        severity=Severity.STRUCTURAL,
        reason=reason,
        span_start=0,
        span_end=0,
        excerpt="",
        sentence_index=-1,
    )


def _reject(violations: Sequence[SafetyViolation], analysed: Optional[str]) -> SafetyVerdict:
    return SafetyVerdict(
        verdict=REJECT,
        approved_text=None,
        analysed_text=analysed,
        violations=tuple(violations),
        modifications=(),
        fallback_required=True,
    )


def _structural_gate(text: object) -> Optional[SafetyVerdict]:
    """Everything that makes the text un-analysable. All of it rejects.

    This is the fail-closed core. Note what is NOT here: there is no branch
    that returns an approval. The only way out of this function is `None`
    (meaning "analysis may proceed") or a rejection.
    """
    if not isinstance(text, str):
        return _reject(
            [
                _structural_violation(
                    ViolationCode.UNANALYSABLE_INPUT,
                    f"Expected text, received {type(text).__name__}. The "
                    "validator refuses what it cannot read.",
                )
            ],
            None,
        )
    try:
        text.encode("utf-8")
    except (UnicodeEncodeError, UnicodeError):
        return _reject(
            [
                _structural_violation(
                    ViolationCode.UNANALYSABLE_INPUT,
                    "The text is not encodable as UTF-8 (lone surrogates or "
                    "broken encoding). It cannot be reliably scanned, so it is "
                    "refused.",
                )
            ],
            None,
        )
    if len(text) > MAX_TEXT_LENGTH:
        return _reject(
            [
                _structural_violation(
                    ViolationCode.INPUT_TOO_LARGE,
                    f"Longer than {MAX_TEXT_LENGTH} characters. A patient-facing "
                    "explanation is not this long; the input is refused rather "
                    "than partially analysed.",
                )
            ],
            None,
        )
    if _CONTROL.search(text):
        return _reject(
            [
                _structural_violation(
                    ViolationCode.UNANALYSABLE_INPUT,
                    "Contains control characters. Text that can hide content "
                    "from a scanner is refused rather than scanned.",
                )
            ],
            None,
        )
    if not text.strip():
        return _reject(
            [
                _structural_violation(
                    ViolationCode.EMPTY_OUTPUT,
                    "Empty or whitespace-only. An empty generation is a "
                    "failure, not an approval.",
                )
            ],
            None,
        )
    return None


# --------------------------------------------------------------------------
# Modification -- the ONLY two things this layer may change
# --------------------------------------------------------------------------

#: Fraction of sentences above which redaction is refused: a mostly-redacted
#: explanation is not an explanation, and stitching one together would present
#: fragments as a coherent answer.
MAX_REDACTED_FRACTION = 0.5
MIN_SURVIVING_CHARACTERS = 40


def _redact(
    text: str,
    sentences: Sequence[Tuple[int, int, str]],
    violations: Sequence[SafetyViolation],
) -> Tuple[Optional[str], List[SafetyModification]]:
    """Remove whole sentences carrying a REDACTABLE violation.

    Whole sentences only. There is no code path here that edits inside a
    sentence, so the layer cannot turn "your creatinine is raised" into
    "your creatinine is normal" by any sequence of steps.
    """
    targets = sorted(
        {
            v.sentence_index
            for v in violations
            if v.severity is Severity.REDACTABLE and v.sentence_index >= 0
        }
    )
    if not targets:
        return None, []
    if not sentences or len(targets) / len(sentences) > MAX_REDACTED_FRACTION:
        return None, []

    modifications: List[SafetyModification] = []
    pieces: List[str] = []
    cursor = 0
    surviving = 0
    reason_by_index = {
        v.sentence_index: (v.code, v.reason)
        for v in violations
        if v.severity is Severity.REDACTABLE
    }
    for index, (start, end, sentence) in enumerate(sentences):
        if index not in targets:
            surviving += len(sentence.strip())
            continue
        pieces.append(text[cursor:start])
        pieces.append(REDACTION_NOTICE)
        cursor = end
        code, reason = reason_by_index[index]
        modifications.append(
            SafetyModification(
                action="redact_sentence",
                code=code,
                reason=reason,
                span_start=start,
                span_end=end,
                removed_excerpt=sentence,
            )
        )
    pieces.append(text[cursor:])
    if surviving < MIN_SURVIVING_CHARACTERS:
        return None, []
    return "".join(pieces), modifications


# --------------------------------------------------------------------------
# The entry point
# --------------------------------------------------------------------------


def validate_text(
    text: object, context: Optional[SafetyContext] = None
) -> SafetyVerdict:
    """Validate one piece of patient-facing text. Never raises.

    Returns a `SafetyVerdict`. `approved_text` is the only string that may be
    shown to a patient, and it is `None` unless the verdict approves.

    Fail-closed: every failure -- an unexpected type, a broken encoding, an
    internal exception -- comes back as REJECT with a structural code. The
    caller can always distinguish "clean" from "could not tell".
    """
    ctx = context if context is not None else SafetyContext()
    try:
        structural = _structural_gate(text)
        if structural is not None:
            _log(structural)
            return structural

        assert isinstance(text, str)
        analysed = _normalise(text)
        sentences = _sentences(analysed)

        violations: List[SafetyViolation] = []
        violations.extend(
            _drop_disclaimed_diagnoses(
                analysed,
                sentences,
                _drop_disclaimed_replacements(
                    analysed, sentences, _scan_rules(analysed, sentences, RULES)
                ),
            )
        )
        violations.extend(_compacted_pass(text, analysed, violations))
        violations.extend(_check_hedging(sentences))
        violations.extend(_check_directives(sentences))

        if ctx.require_grounding and not (
            ctx.grounding_sources or ctx.permitted_numbers
        ):
            violations.append(
                _structural_violation(
                    ViolationCode.GROUNDING_REQUIRED_BUT_ABSENT,
                    "Grounding was required for this generation and none was "
                    "supplied. An ungrounded explanation is refused before its "
                    "content is considered.",
                )
            )
        violations.extend(_check_numeric_grounding(analysed, sentences, ctx))

        prohibited = [v for v in violations if v.severity is Severity.PROHIBITED]
        structural_hits = [v for v in violations if v.severity is Severity.STRUCTURAL]
        if prohibited or structural_hits:
            verdict = _reject(violations, analysed)
            _log(verdict)
            return verdict

        redactable = [v for v in violations if v.severity is Severity.REDACTABLE]
        working = analysed
        modifications: List[SafetyModification] = []
        if redactable:
            redacted, applied = _redact(analysed, sentences, violations)
            if redacted is None:
                verdict = _reject(
                    list(violations)
                    + [
                        _structural_violation(
                            ViolationCode.REDACTION_NOT_POSSIBLE,
                            "The offending sentences could not be removed "
                            "without gutting the explanation, so the whole "
                            "generation is refused.",
                        )
                    ],
                    analysed,
                )
                _log(verdict)
                return verdict
            working = redacted
            modifications.extend(applied)
            # Re-validate what redaction produced. A modification that leaves a
            # violation behind must not be able to launder text into approval.
            recheck_sentences = _sentences(working)
            recheck = _drop_disclaimed_replacements(
                working,
                recheck_sentences,
                _scan_rules(working, recheck_sentences, RULES),
            )
            recheck += _check_hedging(recheck_sentences)
            recheck += _check_directives(recheck_sentences)
            if any(v.severity is not Severity.REQUIRED for v in recheck):
                verdict = _reject(tuple(violations) + tuple(recheck), analysed)
                _log(verdict)
                return verdict

        if ctx.require_referral:
            missing = _check_referral(working)
            if missing:
                violations.extend(missing)
                framing = _framing_text()
                separator = "" if working.endswith(("\n", " ")) else " "
                modifications.append(
                    SafetyModification(
                        action="append_safety_framing",
                        code=ViolationCode.MISSING_PROFESSIONAL_REFERRAL,
                        reason=missing[0].reason,
                        span_start=len(working),
                        span_end=len(working) + len(separator) + len(framing),
                        removed_excerpt=None,
                    )
                )
                working = working + separator + framing

        verdict = SafetyVerdict(
            verdict=APPROVE_WITH_MODIFICATION if modifications else APPROVE,
            approved_text=working,
            analysed_text=analysed,
            violations=tuple(violations),
            modifications=tuple(modifications),
            fallback_required=False,
        )
        _log(verdict)
        return verdict
    except BaseException as exc:  # noqa: BLE001 -- fail closed, deliberately
        # The exception MESSAGE may embed the text being validated, so only the
        # type is recorded, and only in the reason (never in a log line).
        verdict = _reject(
            [
                _structural_violation(
                    ViolationCode.VALIDATOR_ERROR,
                    "The safety validator failed while analysing this text "
                    f"({type(exc).__name__}). Unanalysable content is refused, "
                    "never approved by default.",
                )
            ],
            None,
        )
        _log(verdict)
        return verdict


def assert_safe_for_patient(
    text: object, context: Optional[SafetyContext] = None
) -> str:
    """Return the approved text, or raise. For callers that want an exception.

    `validate_text` is the interface Module 23 should use, because a verdict
    can be retried and an exception cannot. This exists for the places that
    want the catalogue's import-time discipline: a hard failure rather than a
    branch nobody took.
    """
    verdict = validate_text(text, context)
    if not verdict.approved or verdict.approved_text is None:
        raise UnsafeGeneratedContentError(verdict)
    return verdict.approved_text


# --------------------------------------------------------------------------
# Logging -- codes and counts ONLY
# --------------------------------------------------------------------------


def _log(verdict: SafetyVerdict) -> None:
    """Record that a validation happened. NEVER the content.

    Not the text, not the excerpt, not the reason (a reason can quote a verb
    lifted from the text). Codes, counts and the verdict, which is everything a
    reviewer needs to see that the layer is firing and nothing they need the
    patient's words for.
    """
    counts = verdict.code_counts()
    logger.info(
        "safety_validation %s",
        safe_meta(
            verdict=verdict.verdict,
            violation_count=len(verdict.violations),
            modification_count=len(verdict.modifications),
            codes=",".join(sorted(counts)),
            module=24,
        ),
    )


__all__ = [
    "APPROVE",
    "APPROVE_WITH_MODIFICATION",
    "MAX_REDACTED_FRACTION",
    "MAX_TEXT_LENGTH",
    "MIN_SURVIVING_CHARACTERS",
    "REDACTION_NOTICE",
    "REJECT",
    "VERDICTS",
    "SafetyContext",
    "SafetyModification",
    "SafetyVerdict",
    "SafetyViolation",
    "UnsafeGeneratedContentError",
    "assert_safe_for_patient",
    "validate_text",
]
