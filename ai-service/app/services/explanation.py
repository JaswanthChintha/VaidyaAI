"""Module 23 -- LLM-based patient-friendly explanation.

    Structured findings + retrieved knowledge
        -> LLM
        -> Safety Validation (Module 24)
        -> Approved response

and NEVER

    LLM output -> shown to patient

This is the first component in VaidyaAI that puts UNREVIEWED PROSE in front of
a patient. Everything before it emits structured objects, or text a human wrote
into `app/data/`. The file is written accordingly.

==========================================================================
THE ONE PROPERTY THIS FILE MUST HAVE
==========================================================================

`PatientExplanation.explanation` is assigned in exactly one place in this
module: from `GuardedGenerationResult.approved_text`, inside
`_result_from_guarded`. There is no other constructor, no other assignment,
and the model's raw output is never stored on the object at all -- not in a
debug field, not in a "candidate" field, not in the sources. A rejected
generation is discarded inside `guarded_generation` and this module never sees
it.

`tests/test_explanation.py` checks this three ways: by asserting that a
planted unsafe sentence never appears anywhere in the serialised response, by
asserting the safety layer is called on every path that calls the model, and by
reading this source file for a second assignment.

==========================================================================
WHY GENERATION IS REFUSED BEFORE IT STARTS, IN TWO CASES
==========================================================================

1. NO RETRIEVAL, NO GENERATION. If Module 21 returns nothing above its
   similarity floor, the model is not called. A model asked to explain a
   finding with no supporting knowledge will still answer -- from its
   pre-training, which is exactly the ungrounded medical claim the whole
   architecture exists to prevent. `SafetyContext(require_grounding=True)` is
   set as well, so even a coding error here fails closed.

2. NO MODEL, NO GENERATION. With no `GEMINI_API_KEY` the model is not called
   and the caller is told the explanation is unavailable. This is what makes
   the whole test suite runnable offline, and it is also the production
   behaviour on a credential outage: the structured report still renders.

In both cases the patient gets `safe_fallback()` -- the structured,
catalogue-sourced findings -- with `generated_explanation_available: false`.
Never an empty screen, never a silent substitution.

==========================================================================
RETRIES
==========================================================================

`guarded_generation(attempts=2)`. The second attempt is only ever made when
the first was REFUSED BY THE SAFETY LAYER, and it is made with a DIFFERENT
prompt: the violated codes, reasons and offending spans are quoted back (see
`explanation_prompt._feedback_block`). A transport failure is NOT retried
here, because `GeminiTextClient` already retried it with backoff; retrying
again would only multiply the outage.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.errors import ServiceError
from app.core.logging import get_logger, safe_meta
from app.data.feature_catalog import FEATURES
from app.prompts.explanation_prompt import (
    PROHIBITIONS,
    PROMPT_VERSION,
    KnowledgeExtract,
    build_explanation_prompt,
    build_terminology_prompt,
)
from app.rag.index import DEFAULT_TOP_K
from app.rag.retriever import retrieve
from app.safety import (
    GuardedGenerationResult,
    SafeFallback,
    SafetyContext,
    guarded_generation,
    safe_fallback,
)
from app.safety.policy import SAFETY_LAYER_VERSION

logger = get_logger(__name__)

EXPLANATION_VERSION = "1.0.0"

#: How many grounding chunks are put in front of the model. More is not better:
#: every extra chunk widens the set of numbers the model may legitimately write
#: and dilutes the ones that actually concern the finding.
GROUNDING_TOP_K = 4

#: Caller-supplied interpretation labels are STRUCTURED OUTPUT from Modules
#: 8/16, not user text. Bounded anyway -- a long "label" is a malfunction or an
#: injection attempt, and neither should reach the prompt intact.
MAX_INTERPRETATION_CHARS = 240


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------

OUTCOME_GENERATED = "generated"
OUTCOME_WITHHELD_BY_SAFETY = "withheld_by_safety"
OUTCOME_NOT_GROUNDED = "not_grounded"
OUTCOME_MODEL_UNAVAILABLE = "model_unavailable"
OUTCOME_UNKNOWN_SUBJECT = "unknown_subject"

OUTCOMES: Tuple[str, ...] = (
    OUTCOME_GENERATED,
    OUTCOME_WITHHELD_BY_SAFETY,
    OUTCOME_NOT_GROUNDED,
    OUTCOME_MODEL_UNAVAILABLE,
    OUTCOME_UNKNOWN_SUBJECT,
)

#: Fixed, reviewed wording for the two refusals that are NOT safety
#: rejections. `FALLBACK_NOTICE` covers the safety case and is not restated.
NOT_GROUNDED_NOTICE = (
    "No reviewed medical knowledge in this platform covers this finding "
    "closely enough to explain it, so no explanation was written. The "
    "structured findings above are unaffected, and a qualified healthcare "
    "professional can go through them with you."
)

MODEL_UNAVAILABLE_NOTICE = (
    "The plain-language explanation service was not available, so no "
    "explanation was written. The structured findings above were produced by "
    "the analysis itself and are unaffected. A qualified healthcare "
    "professional can go through them with you."
)

EXPLANATION_POLICY = (
    "Every patient-facing sentence this module can produce is generated by an "
    "LLM and then validated by Module 24 before it is returned. There is no "
    "path that returns model output directly: `explanation` is populated only "
    "from `guarded_generation().approved_text`, which is None unless the "
    "safety layer approved it. The model is not called at all unless Module "
    "21 retrieved grounding knowledge, and it is given only that knowledge, "
    "the patient's own validated values, and the findings the analysis "
    "already reached -- never raw report text and never anything the patient "
    "typed. When nothing is approved, the response carries the structured "
    "catalogue fallback and says plainly that an explanation could not be "
    "produced."
)


# --------------------------------------------------------------------------
# Returned shapes
# --------------------------------------------------------------------------


class ExplanationSource(BaseModel):
    """One cited grounding chunk. Module 20's chain, applied to retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    doc_id: str
    title: str
    topic: str
    basis: str = Field(description="Guideline or reference the content reflects.")
    last_reviewed: str
    score: float
    features: Tuple[str, ...] = ()
    conditions: Tuple[str, ...] = ()


class SafetyOutcome(BaseModel):
    """What the safety layer did. Codes and counts only -- never the text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validated: bool = Field(
        description=(
            "True when text was actually put through Module 24. False only "
            "when no text was ever generated (no grounding, or no model)."
        )
    )
    verdict: Optional[str] = None
    version: str = SAFETY_LAYER_VERSION
    violation_codes: Tuple[str, ...] = ()
    modification_count: int = 0
    attempts: int = 0


class PatientExplanation(BaseModel):
    """One explanation, or the reason there is not one.

    `explanation` is the ONLY string here a caller may show a patient, and it
    is populated exclusively from `guarded_generation().approved_text`. When it
    is None the caller renders `fallback` and `notice`; `outcome` says which
    case this is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 23
    version: str = EXPLANATION_VERSION
    prompt_version: str = PROMPT_VERSION
    subject: str
    feature: Optional[str] = None
    conditions: Tuple[str, ...] = ()
    outcome: str
    explanation: Optional[str] = None
    #: Present on EVERY non-generated outcome. Never None when explanation is.
    fallback: Optional[SafeFallback] = None
    #: Plain wording for the reader saying an explanation could not be made.
    notice: Optional[str] = None
    grounding_available: bool = False
    sources: Tuple[ExplanationSource, ...] = ()
    permitted_numbers: Tuple[float, ...] = ()
    findings: Tuple[str, ...] = ()
    safety: SafetyOutcome


class ReportExplanationSet(BaseModel):
    """Explanations attached to one clinical report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 23
    version: str = EXPLANATION_VERSION
    explanations: Tuple[PatientExplanation, ...] = ()
    generated_count: int = 0
    withheld_count: int = 0
    #: Features present in the report that were not explained, and why.
    skipped: Tuple[Dict[str, str], ...] = ()


# --------------------------------------------------------------------------
# Grounding
# --------------------------------------------------------------------------


def _to_source(scored: Any) -> ExplanationSource:
    chunk = scored.chunk
    return ExplanationSource(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        title=chunk.title,
        topic=chunk.topic,
        basis=chunk.basis,
        last_reviewed=chunk.last_reviewed,
        score=round(float(scored.score), 6),
        features=tuple(chunk.features),
        conditions=tuple(chunk.conditions),
    )


#: Public name for the same conversion. `app/services/terminology.py` builds
#: its own `ScoredChunk`s from exact document selection and cites them through
#: this, so both modules produce byte-identical citation shapes.
to_explanation_source = _to_source


def _to_extract(scored: Any) -> KnowledgeExtract:
    chunk = scored.chunk
    return KnowledgeExtract(
        doc_id=chunk.doc_id,
        title=chunk.title,
        topic=chunk.topic,
        basis=chunk.basis,
        text=chunk.text,
    )


def _ground(
    *, features: Sequence[str], conditions: Sequence[str], top_k: int
) -> List[Any]:
    """Retrieve grounding for a CANONICAL finding.

    Note what is NOT passed: free text. Module 23 always retrieves from the
    catalogue vocabulary, which is why it is insulated from the TF-IDF
    coverage problem that `app/services/terminology.py` has to handle
    explicitly -- a canonical feature is in the corpus by construction.
    """
    try:
        return list(retrieve(features=features, conditions=conditions, top_k=top_k))
    except Exception:  # noqa: BLE001 -- a retrieval failure is "no grounding"
        logger.warning(
            "explanation_retrieval_failed %s", safe_meta(module=23, outcome="no_grounding")
        )
        return []


# --------------------------------------------------------------------------
# Findings rendering -- structured in, flat lines out
# --------------------------------------------------------------------------


def _clean_label(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    collapsed = " ".join(str(text).split())
    if not collapsed:
        return None
    return collapsed[:MAX_INTERPRETATION_CHARS]


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _finding_lines(
    *,
    feature: str,
    value: Any,
    unit: Optional[str],
    interpretation: Optional[str],
    conditions: Sequence[str],
    reference_low: Optional[float],
    reference_high: Optional[float],
    status: Optional[str],
) -> Tuple[str, ...]:
    definition = FEATURES.get(feature)
    lines: List[str] = []
    if definition is not None:
        lines.append(f"Parameter: {feature} -- {definition.description}")
    else:  # pragma: no cover -- guarded by the caller
        lines.append(f"Parameter: {feature}")
    if value is not None:
        rendered = _format_value(value)
        lines.append(
            f"The reader's validated value: {rendered}"
            + (f" {unit}" if unit else "")
        )
    else:
        lines.append("The reader's value: not available for this parameter.")
    if reference_low is not None or reference_high is not None:
        low = "not stated" if reference_low is None else _format_value(reference_low)
        high = "not stated" if reference_high is None else _format_value(reference_high)
        # "printed on the report" would be false for a converted parameter:
        # the bounds are the report's own interval carried into the value's
        # unit by Module 5 (`feature_engineer._reference_bounds`), so they are
        # comparable with the value above but are not always the printed
        # digits. Say what is true of every case.
        lines.append(
            f"The reference interval for this parameter, in the same unit as "
            f"the value above: {low} to {high}"
        )
    label = _clean_label(interpretation)
    if label:
        lines.append(f"The interpretation the analysis reached: {label}")
    if status:
        lines.append(f"How reliable the analysis judged this value: {status}")
    if conditions:
        lines.append(
            "Conditions this parameter contributed to: " + ", ".join(conditions)
        )
    lines.append(
        "This finding was produced by deterministic rules and models before "
        "you were called. Do not re-derive it, revise it, or extend it."
    )
    return tuple(lines)


def _permitted(
    value: Any,
    reference_low: Optional[float],
    reference_high: Optional[float],
    extra: Sequence[float],
) -> Tuple[float, ...]:
    """The numbers the explanation may state.

    ONLY the patient's own validated value, that report's reference bounds in
    the value's own unit, and whatever the caller explicitly vouched for.
    Numbers found in the retrieved knowledge are permitted automatically by
    Module 24 because the chunks are handed to it as `grounding_sources`; they
    are deliberately not duplicated here.

    THE BOUNDS AND THE VALUE ARE IN ONE UNIT SYSTEM, which is what makes this
    set correct. Module 5 converts the reference interval alongside the value
    (`feature_engineer._reference_bounds`), so whitelisting the bounds
    whitelists numbers that are genuinely this patient's range as stated to
    the model. Before that fix the bounds arrived in the report's printed unit
    while the value was canonical, and this control -- designed to stop a
    fabricated number -- was licensing prose that quoted a range 60x off. The
    control was never wrong; its input was.
    """
    out: List[float] = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        out.append(float(value))
    for bound in (reference_low, reference_high):
        if isinstance(bound, (int, float)) and not isinstance(bound, bool):
            out.append(float(bound))
    for number in extra or ():
        if isinstance(number, (int, float)) and not isinstance(number, bool):
            out.append(float(number))
    # Stable order, no duplicates.
    seen: Dict[float, None] = {}
    for number in out:
        seen.setdefault(float(number), None)
    return tuple(seen)


# --------------------------------------------------------------------------
# The guarded call
# --------------------------------------------------------------------------


class _Generator:
    """Calls the model, records why an attempt failed, refuses futile retries.

    Kept as a class rather than a closure so the failure reason survives the
    call and `explain_*` can distinguish "the safety layer refused it" from
    "the model never answered" -- `guarded_generation` deliberately swallows
    generator exceptions, which is right for safety and useless for
    diagnostics.
    """

    def __init__(self, llm: Any, build_prompt: Any) -> None:
        self._llm = llm
        self._build_prompt = build_prompt
        self.transport_error: Optional[BaseException] = None
        self.calls = 0

    def __call__(self, feedback: Any = None) -> Optional[str]:
        if self.transport_error is not None:
            # The client already retried transient failures with backoff. A
            # second round here would multiply an outage, and there is nothing
            # different to ask.
            return None
        triples = _feedback_triples(feedback)
        if feedback is not None and not triples:
            # A retry with nothing to say back is the same prompt again.
            return None
        self.calls += 1
        prompt = self._build_prompt(triples)
        try:
            return self._llm.generate_text(prompt)
        except ServiceError as exc:
            self.transport_error = exc
            logger.warning(
                "explanation_model_failed %s",
                safe_meta(module=23, error_code=getattr(exc, "code", None)),
            )
            return None
        except Exception as exc:  # noqa: BLE001 -- never an approval
            self.transport_error = exc
            logger.warning(
                "explanation_model_failed %s",
                safe_meta(module=23, error_type=type(exc).__name__),
            )
            return None


def _feedback_triples(feedback: Any) -> Tuple[Tuple[str, str, str], ...]:
    violations = getattr(feedback, "violations", None) or ()
    out: List[Tuple[str, str, str]] = []
    for violation in violations:
        code = getattr(getattr(violation, "code", None), "value", None) or str(
            getattr(violation, "code", "")
        )
        out.append(
            (code, str(getattr(violation, "reason", "")), str(getattr(violation, "excerpt", "")))
        )
    return tuple(out)


def _result_from_guarded(
    *,
    guarded: GuardedGenerationResult,
    generator: _Generator,
    subject: str,
    feature: Optional[str],
    conditions: Sequence[str],
    sources: Sequence[ExplanationSource],
    permitted_numbers: Sequence[float],
    findings: Sequence[str],
) -> PatientExplanation:
    """THE ONLY PLACE `explanation` IS EVER ASSIGNED.

    `guarded.approved_text` is None unless Module 24 approved the text, so
    there is no branch here that could return model output the safety layer
    did not clear.
    """
    verdict = guarded.verdict
    safety = SafetyOutcome(
        validated=generator.calls > 0,
        verdict=verdict.verdict,
        violation_codes=tuple(sorted(set(verdict.codes))),
        modification_count=len(verdict.modifications),
        attempts=guarded.attempts,
    )
    if guarded.approved_text is not None:
        return PatientExplanation(
            subject=subject,
            feature=feature,
            conditions=tuple(conditions),
            outcome=OUTCOME_GENERATED,
            explanation=guarded.approved_text,
            fallback=None,
            notice=None,
            grounding_available=True,
            sources=tuple(sources),
            permitted_numbers=tuple(permitted_numbers),
            findings=tuple(findings),
            safety=safety,
        )

    if generator.transport_error is not None:
        outcome = OUTCOME_MODEL_UNAVAILABLE
        notice = MODEL_UNAVAILABLE_NOTICE
    else:
        outcome = OUTCOME_WITHHELD_BY_SAFETY
        notice = None  # `fallback.notice` is the reviewed wording for this case
    return PatientExplanation(
        subject=subject,
        feature=feature,
        conditions=tuple(conditions),
        outcome=outcome,
        explanation=None,
        fallback=guarded.fallback or safe_fallback(verdict),
        notice=notice,
        grounding_available=True,
        sources=tuple(sources),
        permitted_numbers=tuple(permitted_numbers),
        findings=tuple(findings),
        safety=safety,
    )


def _refused(
    *,
    subject: str,
    feature: Optional[str],
    conditions: Sequence[str],
    outcome: str,
    notice: str,
    sources: Sequence[ExplanationSource] = (),
    grounding_available: bool = False,
) -> PatientExplanation:
    """A refusal decided BEFORE any generation. No model call was made."""
    return PatientExplanation(
        subject=subject,
        feature=feature,
        conditions=tuple(conditions),
        outcome=outcome,
        explanation=None,
        fallback=safe_fallback(None),
        notice=notice,
        grounding_available=grounding_available,
        sources=tuple(sources),
        safety=SafetyOutcome(validated=False, verdict=None, attempts=0),
    )


def _resolve_llm(llm: Any, settings: Optional[Settings]) -> Optional[Any]:
    """The text client, or None when generation is not possible at all.

    An injected `llm` is always used -- that is how the offline suite runs.
    Otherwise a client is built only if a key is configured; constructing one
    without a key would turn a configuration state into an exception on every
    request.
    """
    if llm is not None:
        return llm
    resolved = settings or get_settings()
    if not resolved.has_api_key:
        return None
    from app.services.gemini_text import build_text_client

    return build_text_client(resolved)


# --------------------------------------------------------------------------
# Module 23's public entry points -- framework-independent
# --------------------------------------------------------------------------


def explain_feature(
    feature: str,
    *,
    value: Any = None,
    unit: Optional[str] = None,
    interpretation: Optional[str] = None,
    conditions: Sequence[str] = (),
    reference_low: Optional[float] = None,
    reference_high: Optional[float] = None,
    status: Optional[str] = None,
    additional_permitted_numbers: Sequence[float] = (),
    llm: Any = None,
    settings: Optional[Settings] = None,
    top_k: int = GROUNDING_TOP_K,
) -> PatientExplanation:
    """Explain ONE canonical parameter to the patient whose value it is.

    The spec's own example: `HbA1c = 6.8%` becomes prose covering what HbA1c
    represents, why it matters, how the value relates to the interpretation the
    analysis reached, and what to raise with a professional.

    `feature` MUST be canonical. An unknown name is refused rather than
    retrieved on -- see `app/services/terminology.py` for why guessing from
    free text is the specific thing this platform will not do.

    `additional_permitted_numbers` is for rule-table thresholds the caller
    already holds. Everything passed here becomes a number the model is
    allowed to state, so a caller must only pass values it can vouch for.
    """
    subject = f"the {feature} result"
    if feature not in FEATURES:
        return _refused(
            subject=subject,
            feature=None,
            conditions=conditions,
            outcome=OUTCOME_UNKNOWN_SUBJECT,
            notice=NOT_GROUNDED_NOTICE,
        )

    scored = _ground(features=[feature], conditions=list(conditions), top_k=top_k)
    if not scored:
        return _refused(
            subject=subject,
            feature=feature,
            conditions=conditions,
            outcome=OUTCOME_NOT_GROUNDED,
            notice=NOT_GROUNDED_NOTICE,
        )

    sources = [_to_source(s) for s in scored]
    extracts = [_to_extract(s) for s in scored]
    grounding_texts = tuple(s.chunk.text for s in scored)
    findings = _finding_lines(
        feature=feature,
        value=value,
        unit=unit,
        interpretation=interpretation,
        conditions=list(conditions),
        reference_low=reference_low,
        reference_high=reference_high,
        status=status,
    )
    permitted = _permitted(
        value, reference_low, reference_high, additional_permitted_numbers
    )

    client = _resolve_llm(llm, settings)
    if client is None:
        return _refused(
            subject=subject,
            feature=feature,
            conditions=conditions,
            outcome=OUTCOME_MODEL_UNAVAILABLE,
            notice=MODEL_UNAVAILABLE_NOTICE,
            sources=sources,
            grounding_available=True,
        )

    generator = _Generator(
        client,
        lambda triples: build_explanation_prompt(
            subject=subject,
            findings=findings,
            extracts=extracts,
            permitted_numbers=permitted,
            feedback=triples,
        ),
    )
    guarded = guarded_generation(
        generator,
        context=SafetyContext(
            grounding_sources=grounding_texts,
            permitted_numbers=permitted,
            require_grounding=True,
            require_referral=True,
            check_numeric_grounding=True,
            purpose="module_23_patient_explanation",
        ),
        attempts=2,
    )
    result = _result_from_guarded(
        guarded=guarded,
        generator=generator,
        subject=subject,
        feature=feature,
        conditions=conditions,
        sources=sources,
        permitted_numbers=permitted,
        findings=findings,
    )
    logger.info(
        "explanation_completed %s",
        safe_meta(
            module=23,
            feature=feature,
            outcome=result.outcome,
            attempts=result.safety.attempts,
            sources=len(sources),
        ),
    )
    return result


def explain_terminology_entry(
    *,
    term: str,
    canonical_feature: Optional[str],
    scored_chunks: Sequence[Any],
    llm: Any = None,
    settings: Optional[Settings] = None,
) -> PatientExplanation:
    """Module 25's generated path, gated identically to Module 23's.

    Lives here rather than in `terminology.py` so that there is ONE guarded
    generation implementation in the service and one place where an
    `explanation` field is assigned. `terminology.py` decides WHETHER the term
    may be explained at all; this decides nothing and only generates.
    """
    subject = f"the medical term {term}"
    if not scored_chunks:
        return _refused(
            subject=subject,
            feature=canonical_feature,
            conditions=(),
            outcome=OUTCOME_NOT_GROUNDED,
            notice=NOT_GROUNDED_NOTICE,
        )
    sources = [_to_source(s) for s in scored_chunks]
    extracts = [_to_extract(s) for s in scored_chunks]
    grounding_texts = tuple(s.chunk.text for s in scored_chunks)

    client = _resolve_llm(llm, settings)
    if client is None:
        return _refused(
            subject=subject,
            feature=canonical_feature,
            conditions=(),
            outcome=OUTCOME_MODEL_UNAVAILABLE,
            notice=MODEL_UNAVAILABLE_NOTICE,
            sources=sources,
            grounding_available=True,
        )

    generator = _Generator(
        client,
        lambda triples: build_terminology_prompt(
            term=term,
            canonical_feature=canonical_feature,
            extracts=extracts,
            permitted_numbers=(),
            feedback=triples,
        ),
    )
    guarded = guarded_generation(
        generator,
        context=SafetyContext(
            grounding_sources=grounding_texts,
            # No patient value is involved in a terminology answer, so the only
            # numbers the model may write are ones the corpus already prints.
            permitted_numbers=(),
            require_grounding=True,
            require_referral=True,
            check_numeric_grounding=True,
            purpose="module_25_terminology",
        ),
        attempts=2,
    )
    return _result_from_guarded(
        guarded=guarded,
        generator=generator,
        subject=subject,
        feature=canonical_feature,
        conditions=(),
        sources=sources,
        permitted_numbers=(),
        findings=(),
    )


# --------------------------------------------------------------------------
# Report-level convenience
# --------------------------------------------------------------------------

#: Each explanation is one model call, so this stays a bound rather than
#: "however many rows arrived" -- one request must not be able to become
#: dozens of round trips.
#:
#: RAISED FROM 6 TO 10 (2026-09-11) so an ordinary report is explained in full.
#: At 6, a report carrying eight laboratory values left two of them with no
#: explanation and the reader was not told which -- and the two that lost were
#: whichever came last in the row order, not the least important. The platform
#: maps eight laboratory features today (`FEATURES` also holds age, sex, BMI
#: and the three history answers, which are context rather than results and no
#: longer consume the budget), so 10 covers every printed value with headroom
#: for two more before anyone has to think about this again.
DEFAULT_MAX_EXPLANATIONS = 10

#: How many per-feature generations may be in flight at once.
#:
#: MEASURED, not guessed. Sequentially, six usable values at ~25s each ran past
#: the backend's 120s stage timeout and the patient got nothing. At 4 the wall
#: time fell to ~40s but the free-tier key returned MODEL_RATE_LIMITED for
#: several features -- a timeout traded for a 429, which is not a win.
#:
#: 2 is the setting that produced explanations for every feature without
#: tripping the limiter. Raise it only against a key whose quota you have
#: actually checked; `AI_EXPLANATION_CONCURRENCY` exists so that does not
#: require a code change.
#:
#: Note the failure is GRACEFUL either way: a rate-limited generation yields no
#: text, Module 24 rejects the empty string as UNANALYSABLE_INPUT (fail-closed,
#: working as designed), and that feature falls back to catalogue guidance while
#: the others still explain. Concurrency tuning changes how MANY explanations a
#: patient gets, never whether an unvalidated one can reach them.
_EXPLANATION_CONCURRENCY = max(
    1, int(os.environ.get("AI_EXPLANATION_CONCURRENCY", "2"))
)


def _report_field(report: Any, name: str) -> Any:
    if isinstance(report, Mapping):
        return report.get(name)
    return getattr(report, name, None)


#: The value of `laboratory_values[].source` that means "the laboratory
#: printed this". Anything else is context the assessment used, not a result
#: the reader is holding.
SOURCE_LAB_REPORT = "lab_report"


def explain_report(
    report: Any,
    *,
    llm: Any = None,
    settings: Optional[Settings] = None,
    max_explanations: int = DEFAULT_MAX_EXPLANATIONS,
    features: Optional[Sequence[str]] = None,
) -> ReportExplanationSet:
    """Attach patient-friendly explanations to a Module 17 clinical report.

    Accepts a `ClinicalReport` or the same thing as a dict, so the Node backend
    and Modules 27/32 can call it either way.

    Only USABLE laboratory values are explained. A rejected value is one the
    validator refused to trust, and writing a friendly paragraph about a number
    the system does not believe would be the worst kind of fluency.
    """
    values = _report_field(report, "laboratory_values") or []
    conditions = _report_field(report, "conditions") or []

    by_feature: Dict[str, List[str]] = {}
    for condition in conditions:
        name = _report_field(condition, "condition")
        for feature_name in _report_field(condition, "evidence_features") or []:
            by_feature.setdefault(str(feature_name), []).append(str(name))

    explanations: List[Optional[PatientExplanation]] = []
    planned: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    wanted = set(features) if features is not None else None

    for row in values:
        feature = _report_field(row, "feature")
        if feature is None:
            continue
        feature = str(feature)
        if wanted is not None and feature not in wanted:
            continue
        # ELIGIBILITY IS DECIDED BEFORE THE BUDGET, not after.
        #
        # With the limit checked first, every row past the cap was reported as
        # `explanation_limit_reached` -- including rows that were never
        # eligible at all. A rejected value would be blamed on the budget, and
        # a caller could not tell "we ran out of explanations" from "there was
        # nothing here to explain". These three reasons are answers to
        # different questions and the order made them one.
        if not _report_field(row, "usable"):
            skipped.append({"feature": feature, "reason": "value_not_usable"})
            continue
        if feature not in FEATURES:
            skipped.append({"feature": feature, "reason": "not_a_canonical_feature"})
            continue

        # A PROFILE ANSWER IS NOT A RESULT, and must not consume the budget.
        #
        # `laboratory_values` carries the age, sex and BMI the assessment used
        # alongside the values the laboratory printed. They were candidates
        # here, so on an eleven-row report three model calls could be spent
        # writing "this test measures your age" -- which is not a sentence any
        # reader is waiting for -- while a real cholesterol result went
        # unexplained for want of budget.
        #
        # `source` is the field to branch on. NOT `origin`: the ai-service
        # stamps `report_transcription` on profile-derived rows (MEMORY.md 6w,
        # still open at source), so `origin` says the opposite of the truth
        # here.
        #
        # POSITIVE PROOF ONLY. `source` is `Optional[str] = None` on the
        # schema, so a row can genuinely arrive without one -- from an older
        # stored report, or a caller that builds rows by hand. Requiring it to
        # EQUAL "lab_report" would skip every such row and explain nothing at
        # all; a missing field is not evidence that a value came from the
        # profile. Excluded only when the row says outright that it did.
        source = _report_field(row, "source")
        if source is not None and source != SOURCE_LAB_REPORT:
            skipped.append({"feature": feature, "reason": "not_a_laboratory_value"})
            continue

        if len(explanations) >= max(0, int(max_explanations)):
            skipped.append({"feature": feature, "reason": "explanation_limit_reached"})
            continue
        planned.append(
            dict(
                feature=feature,
                value=_report_field(row, "value"),
                unit=_report_field(row, "unit"),
                reference_low=_report_field(row, "reference_low"),
                reference_high=_report_field(row, "reference_high"),
                status=_report_field(row, "status"),
                conditions=tuple(dict.fromkeys(by_feature.get(feature, ()))),
            )
        )
        explanations.append(None)  # placeholder, filled in below

    # ---- run the per-feature generations CONCURRENTLY -------------------
    #
    # Each explanation is an independent model call: it retrieves on its own
    # feature, grounds on its own numbers, and is validated on its own. Running
    # them one after another made the whole endpoint O(n) in a round trip that
    # is inherently slow, because `gemini-3.6-flash` is a THINKING model and
    # spends reasoning tokens before emitting any prose.
    #
    # That was not a tuning nicety, it was a live end-to-end failure: six
    # usable values at roughly 25s each ran past the backend's 120s stage
    # timeout, so the analyze pipeline recorded
    # `explanation: {ok: false, AI_SERVICE_TIMEOUT}` and the patient received
    # the fallback instead of an explanation. Concurrently the wall time is
    # about that of the slowest single call.
    #
    # Order is preserved by writing each result back into its own slot, so the
    # response still follows the report's laboratory-value order rather than
    # whichever call happened to finish first. Bounded deliberately: this is a
    # third-party API with rate limits, and an unbounded pool would turn a long
    # report into a burst.
    if planned:
        max_workers = min(len(planned), _EXPLANATION_CONCURRENCY)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    explain_feature,
                    job["feature"],
                    value=job["value"],
                    unit=job["unit"],
                    reference_low=job["reference_low"],
                    reference_high=job["reference_high"],
                    status=job["status"],
                    conditions=job["conditions"],
                    llm=llm,
                    settings=settings,
                ): slot
                for slot, job in enumerate(planned)
            }
            for future in as_completed(futures):
                explanations[futures[future]] = future.result()

    return ReportExplanationSet(
        explanations=tuple(explanations),
        generated_count=sum(1 for e in explanations if e.outcome == OUTCOME_GENERATED),
        withheld_count=sum(1 for e in explanations if e.outcome != OUTCOME_GENERATED),
        skipped=tuple(skipped),
    )


def explanation_policy_document() -> Dict[str, Any]:
    """Machine-readable statement of what this module does and refuses to do."""
    return {
        "module": 23,
        "version": EXPLANATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "policy": EXPLANATION_POLICY,
        "pipeline": [
            "structured findings + retrieved knowledge",
            "LLM",
            "Module 24 safety validation",
            "approved response",
        ],
        "outcomes": list(OUTCOMES),
        "prohibitions_in_prompt": list(PROHIBITIONS),
        "grounding_top_k": GROUNDING_TOP_K,
        "retrieval_default_top_k": DEFAULT_TOP_K,
        "generation_attempts": 2,
        "retry_policy": (
            "A second attempt is made ONLY after a safety rejection, and only "
            "with the violated codes and offending spans quoted back into the "
            "prompt. Transport failures are not retried here -- the Gemini "
            "client already retried them with backoff."
        ),
        "notices": {
            "not_grounded": NOT_GROUNDED_NOTICE,
            "model_unavailable": MODEL_UNAVAILABLE_NOTICE,
        },
    }


__all__ = [
    "DEFAULT_MAX_EXPLANATIONS",
    "EXPLANATION_POLICY",
    "EXPLANATION_VERSION",
    "GROUNDING_TOP_K",
    "MODEL_UNAVAILABLE_NOTICE",
    "NOT_GROUNDED_NOTICE",
    "OUTCOMES",
    "OUTCOME_GENERATED",
    "OUTCOME_MODEL_UNAVAILABLE",
    "OUTCOME_NOT_GROUNDED",
    "OUTCOME_UNKNOWN_SUBJECT",
    "OUTCOME_WITHHELD_BY_SAFETY",
    "ExplanationSource",
    "PatientExplanation",
    "ReportExplanationSet",
    "SafetyOutcome",
    "explain_feature",
    "explain_report",
    "explain_terminology_entry",
    "explanation_policy_document",
    "to_explanation_source",
]
