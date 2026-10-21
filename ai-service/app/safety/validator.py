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


APPROVE = "approve"
APPROVE_WITH_MODIFICATION = "approve_with_modification"
REJECT = "reject"

VERDICTS: Tuple[str, ...] = (APPROVE, APPROVE_WITH_MODIFICATION, REJECT)

MAX_TEXT_LENGTH = 20_000

REDACTION_NOTICE = (
    "[A sentence was removed here by the VaidyaAI safety layer because it "
    "gave guidance this system is not permitted to give. Please discuss this "
    "topic with a qualified healthcare professional.]"
)

def _framing_text() -> str:
    from app.data.recommendation_catalog import NOT_A_DIAGNOSIS, recommendation

    return recommendation(NOT_A_DIAGNOSIS).text


class SafetyViolation(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ViolationCode
    rule_id: str
    severity: Severity
    reason: str
    span_start: int
    span_end: int
    excerpt: str
    sentence_index: int


class SafetyModification(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    code: ViolationCode
    reason: str
    span_start: int
    span_end: int
    removed_excerpt: Optional[str] = None


class SafetyVerdict(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: str
    version: str = SAFETY_LAYER_VERSION
    approved_text: Optional[str] = None
    analysed_text: Optional[str] = None
    violations: Tuple[SafetyViolation, ...] = ()
    modifications: Tuple[SafetyModification, ...] = ()
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

    model_config = ConfigDict(frozen=True, extra="forbid")

    grounding_sources: Tuple[str, ...] = ()
    permitted_numbers: Tuple[float, ...] = ()
    require_grounding: bool = False
    require_referral: bool = True
    check_numeric_grounding: bool = True
    purpose: str = "llm_explanation"


class UnsafeGeneratedContentError(ValueError):

    def __init__(self, verdict: SafetyVerdict) -> None:
        super().__init__(
            "generated content was refused by the Module 24 safety layer: "
            f"{sorted(set(verdict.codes))}"
        )
        self.verdict = verdict


_ZERO_WIDTH = {
    cp: " " for cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E)
}

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


_LINE_BREAKS = {
    0x000A: " ",
    0x000D: " ",
    0x0085: " ",
    0x2028: " ",
    0x2029: " ",
}


def _normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text.translate(_ZERO_WIDTH))
    return folded.translate(_LINE_BREAKS)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[Tuple[int, int, str]]:
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
_EPISTEMIC_TREAT = re.compile(
    r"^treat(?:s|ed|ing)?\s+(?:it|this|that|these|them|such\s+values?|these\s+values?|those\s+values?|the\s+values?"
    r"|the\s+value|the\s+figure)\s+with\s+(?:reduced\s+confidence"
    r"|less\s+confidence|lower\s+confidence|caution|care|scepticism"
    r"|skepticism|suspicion)\b",
    re.IGNORECASE,
)
_CLAUSE_HEAD = re.compile(r"(?:^|[.!?;:\n]\s*)([A-Za-z][A-Za-z-]*)")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?|(?<![\w.])\.\d+")

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


_MEASUREMENT_UNIT = re.compile(
    r"\s*(percent|per\s*cent|%|mg|mcg|µg|ug|kg|ng|pg|mmol|umol|µmol"
    r"|mg/dl|mmol/l|g/dl|ng/ml|pg/ml|mmhg|kg/m2)\b",
    re.IGNORECASE,
)


def _spelled_number(phrase: str) -> Optional[float]:
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

_INTERROGATIVE = re.compile(r"\b(what|whether|how|why|question of)\b", re.IGNORECASE)

_NEGATOR = re.compile(
    r"\b(not|never|no|nothing|none|cannot|rather\s+than|instead\s+of\s+a\s+"
    r"substitute)\b",
    re.IGNORECASE,
)


_FORMAT_STRIPPED = dict.fromkeys(
    (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E), None
)


def _compacted_pass(
    original: str, analysed: str, already: Sequence[SafetyViolation]
) -> List[SafetyViolation]:
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
    out: List[SafetyViolation] = []
    for index, (start, _end, sentence) in enumerate(sentences):
        match = _INTERPRETIVE.search(sentence)
        if match is None:
            continue
        if _HEDGE.search(sentence):
            continue
        if not CLINICAL_SUBJECT.search(sentence):
            continue
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
    if not context.check_numeric_grounding:
        return []
    allowed, active = _permitted_number_strings(context)
    if not active:
        return []
    out: List[SafetyViolation] = []

    candidates: List[Tuple[int, int, str, float]] = []
    for match in _NUMBER.finditer(text):
        candidates.append((match.start(), match.end(), match.group(0), float(match.group(0))))
    for match in _NUMBER_WORD.finditer(text):
        phrase = match.group(0)
        words = [w.lower() for w in re.split(r"[\s-]+", phrase.strip()) if w]
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


def _scan_rules(
    text: str, sentences: Sequence[Tuple[int, int, str]], rules: Iterable[SafetyRule]
) -> List[SafetyViolation]:
    out: List[SafetyViolation] = []
    for rule in rules:
        assert rule.pattern is not None
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


MAX_REDACTED_FRACTION = 0.5
MIN_SURVIVING_CHARACTERS = 40


def _redact(
    text: str,
    sentences: Sequence[Tuple[int, int, str]],
    violations: Sequence[SafetyViolation],
) -> Tuple[Optional[str], List[SafetyModification]]:
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


def validate_text(
    text: object, context: Optional[SafetyContext] = None
) -> SafetyVerdict:
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
    except BaseException as exc:
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
    verdict = validate_text(text, context)
    if not verdict.approved or verdict.approved_text is None:
        raise UnsafeGeneratedContentError(verdict)
    return verdict.approved_text


def _log(verdict: SafetyVerdict) -> None:
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
