"""Module 25 -- Medical Terminology Explainer.

Spec Module 25: explain terms such as HbA1c, LDL, HDL, creatinine, SGPT and
eGFR -- what the test measures, why it is performed, what the value represents,
general reference information, and why it may matter.

==========================================================================
THE HAZARD THIS MODULE IS BUILT AROUND
==========================================================================

Module 23 retrieves from CANONICAL FINDINGS, so its query vocabulary is
guaranteed to exist in the corpus. Module 25 is the only place in VaidyaAI
where a HUMAN-TYPED STRING reaches retrieval, and that is a different problem.

The shipped retriever is TF-IDF, and the Module 21/22 build measured what that
means for coverage: terms the corpus does NOT cover (TSH, ferritin, WBC, ALT,
PSA, CRP) score 0.141-0.271, while terms it DOES cover score 0.121-0.27. Those
ranges OVERLAP COMPLETELY. No similarity floor separates a question the corpus
can answer from one it cannot. Concretely, `"what does my TSH mean"` retrieves
TRIGLYCERIDE content and scores it respectably.

A module that retrieved on the raw string and explained whatever came back
would therefore, sooner or later, confidently explain triglycerides to someone
who asked about their thyroid -- in fluent, safety-validated, well-cited prose,
because every one of those controls would pass. Module 24 checks that text is
safe; it has no way to know it is about the wrong organ.

So this module does NOT retrieve on free text. Ever.

    term  ->  EXACT MAPPING to a canonical feature or a named document
          ->  if it maps:      serve THAT document
          ->  if it does not:  say the term is not covered. Stop.

`resolve_term` is that mapping, and it is exact-key lookup against tables the
platform already maintains (`feature_catalog.SYNONYM_INDEX` via
`lookup_test_name`, plus the curated `TERM_ALIASES` below for terms the corpus
covers that are not canonical features). There is no similarity, no threshold,
no nearest match, and no fallback to search. An unmapped term is refused.

The cost of this design is real and is accepted: the spec names SGPT, and the
corpus holds no liver-enzyme document, so SGPT is REFUSED rather than answered.
That is a Module 22 content gap, and the honest failure is a refusal.

==========================================================================
WHY THE DEFAULT PATH DOES NOT USE THE LLM
==========================================================================

The curated corpus was written to be read by patients and is scanned for
unsafe wording at import (`app/data/knowledge_safety.py`). For "what does
HbA1c measure", an LLM adds nothing a reviewer wrote it does not already say,
and adds a hallucination surface. So the default is `serve_from_knowledge_base`
and the LLM is opt-in (`simplify=True`), gated by exactly the same
`guarded_generation` as Module 23.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.core.logging import get_logger, safe_meta
from app.data.feature_catalog import FEATURES, lookup_test_name, normalize_test_name
from app.data.knowledge_base import DOCUMENTS, documents_for_feature
from app.data.knowledge_types import (
    TOPIC_EDUCATION,
    TOPIC_LAB_TEST,
    TOPIC_REFERENCE,
    TOPIC_TERMINOLOGY,
    KnowledgeDocument,
)
from app.data.recommendation_catalog import (
    DISCUSS_WITH_CLINICIAN,
    NOT_A_DIAGNOSIS,
    recommendation,
)
from app.rag.chunking import chunk_document
from app.rag.index import ScoredChunk
from app.safety import SafeFallback, SafetyContext, safe_fallback, validate_text
from app.safety.validator import REJECT
from app.services.explanation import (
    ExplanationSource,
    PatientExplanation,
    SafetyOutcome,
    to_explanation_source,
    explain_terminology_entry,
)

logger = get_logger(__name__)

TERMINOLOGY_VERSION = "1.0.0"

#: Terms are short. A "term" of paragraph length is not a term.
MAX_TERM_CHARS = 80

#: What may be echoed back to the reader when a term is refused. Anything else
#: in the submitted string is dropped before it is put in a sentence -- the
#: refusal message is the one place user input reaches patient-facing output.
_ECHOABLE = re.compile(r"[^A-Za-z0-9 /()\-.,%+']")


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------

OUTCOME_SERVED_FROM_KNOWLEDGE_BASE = "served_from_knowledge_base"
OUTCOME_GENERATED = "generated"
OUTCOME_NOT_COVERED = "term_not_covered"
OUTCOME_WITHHELD_BY_SAFETY = "withheld_by_safety"
OUTCOME_MODEL_UNAVAILABLE = "model_unavailable"

TERMINOLOGY_OUTCOMES: Tuple[str, ...] = (
    OUTCOME_SERVED_FROM_KNOWLEDGE_BASE,
    OUTCOME_GENERATED,
    OUTCOME_NOT_COVERED,
    OUTCOME_WITHHELD_BY_SAFETY,
    OUTCOME_MODEL_UNAVAILABLE,
)

RESOLUTION_CANONICAL_FEATURE = "canonical_feature"
RESOLUTION_CURATED_ALIAS = "curated_alias"
RESOLUTION_UNMAPPED = "unmapped"
RESOLUTION_NO_CORPUS_COVERAGE = "no_corpus_coverage"
RESOLUTION_EMPTY = "empty_term"


TERMINOLOGY_POLICY = (
    "A submitted term is mapped EXACTLY onto a canonical feature or a named "
    "curated document before anything is retrieved. A term that does not map "
    "is refused, and no search of any kind is run on it. This is deliberate: "
    "the shipped retriever is TF-IDF, and its similarity scores for terms the "
    "corpus does not cover overlap completely with its scores for terms it "
    "does, so a threshold cannot tell the two apart. Answering an unmapped "
    "term would mean explaining whichever document happened to rank first."
)


# --------------------------------------------------------------------------
# The curated alias table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TermTarget:
    """What a recognised term resolves to.

    `doc_ids` is the AUTHORITATIVE selection when present: the documents a
    reviewer decided answer this term. `feature` is the canonical feature the
    term names, used both for citation and to select feature-tagged documents
    when no explicit `doc_ids` were given.
    """

    label: str
    feature: Optional[str] = None
    doc_ids: Tuple[str, ...] = ()


def _alias(label: str, *terms: str, feature: Optional[str] = None, docs: Tuple[str, ...] = ()) -> Dict[str, TermTarget]:
    target = TermTarget(label=label, feature=feature, doc_ids=docs)
    out: Dict[str, TermTarget] = {}
    for term in terms:
        key = normalize_test_name(term)
        if not key:
            raise ValueError(f"alias {term!r} normalises to an empty key")
        out[key] = target
    return out


def _build_aliases() -> Dict[str, TermTarget]:
    """Terms the corpus covers that are NOT canonical features.

    Every entry names the document(s) a reviewer chose. `_self_check` below
    verifies at import that each named document exists, so a corpus edit that
    removes a document breaks the service at start-up rather than producing a
    terminology answer with no content.
    """
    table: Dict[str, TermTarget] = {}
    for group in (
        _alias(
            "eGFR",
            "eGFR",
            "e GFR",
            "GFR",
            "estimated GFR",
            "glomerular filtration rate",
            "estimated glomerular filtration rate",
            feature="creatinine",
            docs=("term_egfr",),
        ),
        _alias(
            "LDL cholesterol",
            "LDL",
            "LDL Cholesterol",
            "LDL-C",
            "low density lipoprotein",
            "bad cholesterol",
            feature="cholesterol",
            docs=("term_ldl_hdl",),
        ),
        _alias(
            "HDL cholesterol",
            "HDL",
            "HDL Cholesterol",
            "HDL-C",
            "high density lipoprotein",
            "good cholesterol",
            feature="cholesterol",
            docs=("term_ldl_hdl",),
        ),
        _alias(
            "reference range",
            "reference range",
            "reference interval",
            "normal range",
            "normal values",
            docs=("term_reference_interval",),
        ),
        _alias(
            "fasting sample",
            "fasting",
            "fasting sample",
            "fasting test",
            "non fasting",
            docs=("term_fasting_sample",),
        ),
        _alias(
            "anaemia",
            "anaemia",
            "anemia",
            feature="hemoglobin",
            docs=("term_anaemia_word", "cond_anemia"),
        ),
        _alias(
            "risk factor",
            "risk factor",
            "risk factors",
            docs=("term_risk_factor",),
        ),
        _alias(
            "mg/dL",
            "mg/dL",
            "mmol/L",
            "mg per dL",
            "mmol per L",
            docs=("term_units_mgdl_mmoll",),
        ),
    ):
        for key, target in group.items():
            if key in table:
                raise ValueError(f"duplicate terminology alias key {key!r}")
            table[key] = target
    return table


TERM_ALIASES: Dict[str, TermTarget] = _build_aliases()


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


class TermResolution(BaseModel):
    """The mapping decision, separated from the answer so it can be tested."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    term: str
    normalised: str
    covered: bool
    resolution: str
    canonical_feature: Optional[str] = None
    doc_ids: Tuple[str, ...] = ()
    label: Optional[str] = None


def _documents_for(target: TermTarget) -> List[KnowledgeDocument]:
    if target.doc_ids:
        return [DOCUMENTS[d] for d in target.doc_ids if d in DOCUMENTS]
    if target.feature:
        return _feature_documents(target.feature)
    return []


#: Topics that answer "what is this test". A condition document explains a
#: disease and is not what someone asking "what is creatinine" wants first.
_TERM_TOPICS: Tuple[str, ...] = (
    TOPIC_LAB_TEST,
    TOPIC_TERMINOLOGY,
    TOPIC_REFERENCE,
    # The profile parameters (age, BMI, gender, smoking history, and the two
    # history flags) are documented under `educational_explanation` rather
    # than `laboratory_test`, because they are not tests. They are still
    # canonical features a reader may ask about by name.
    TOPIC_EDUCATION,
)


def _feature_documents(feature: str) -> List[KnowledgeDocument]:
    docs = documents_for_feature(feature)
    ordered = [d for topic in _TERM_TOPICS for d in docs if d.topic == topic]
    # De-duplicate, preserving the topic ordering above.
    seen: Dict[str, None] = {}
    out: List[KnowledgeDocument] = []
    for doc in ordered:
        if doc.doc_id not in seen:
            seen[doc.doc_id] = None
            out.append(doc)
    return out


def resolve_term(term: str) -> TermResolution:
    """Map a submitted term onto curated content, or refuse it.

    EXACT mapping only. Returns `covered=False` for anything the tables do not
    name; the caller must not then "try a search anyway". See the module
    docstring for the measurement that makes that non-negotiable.
    """
    raw = (term or "").strip()[:MAX_TERM_CHARS]
    normalised = normalize_test_name(raw)
    if not normalised:
        return TermResolution(
            term=raw,
            normalised="",
            covered=False,
            resolution=RESOLUTION_EMPTY,
        )

    # A canonical feature name IS a term. Exact DICTIONARY MEMBERSHIP after
    # the platform's own normalisation -- "BMI", "bmi" and "Vitamin B12" all
    # resolve; "hba1c and thyroid" does not, because the key it produces is
    # simply not in the dictionary. No similarity is involved.
    canonical = normalised.replace(" ", "_")
    if canonical in FEATURES and _feature_documents(canonical):
        return TermResolution(
            term=raw,
            normalised=normalised,
            covered=True,
            resolution=RESOLUTION_CANONICAL_FEATURE,
            canonical_feature=canonical,
            doc_ids=tuple(d.doc_id for d in _feature_documents(canonical)),
            label=canonical,
        )

    target = TERM_ALIASES.get(normalised)
    if target is not None:
        return TermResolution(
            term=raw,
            normalised=normalised,
            covered=True,
            resolution=RESOLUTION_CURATED_ALIAS,
            canonical_feature=target.feature,
            doc_ids=tuple(d.doc_id for d in _documents_for(target)),
            label=target.label,
        )

    match, _reason = lookup_test_name(raw)
    if match is not None and match.feature in FEATURES:
        docs = _feature_documents(match.feature)
        if docs:
            return TermResolution(
                term=raw,
                normalised=normalised,
                covered=True,
                resolution=RESOLUTION_CANONICAL_FEATURE,
                canonical_feature=match.feature,
                doc_ids=tuple(d.doc_id for d in docs),
                label=match.matched_term,
            )
        # The vocabulary knows the term but the corpus has nothing to say about
        # it. Refusing is the only honest answer; retrieving would return the
        # nearest unrelated document.
        return TermResolution(
            term=raw,
            normalised=normalised,
            covered=False,
            resolution=RESOLUTION_NO_CORPUS_COVERAGE,
            canonical_feature=match.feature,
        )

    return TermResolution(
        term=raw,
        normalised=normalised,
        covered=False,
        resolution=RESOLUTION_UNMAPPED,
    )


def covered_terms() -> Tuple[str, ...]:
    """Every term this module will answer, for the "not covered" reply.

    Derived from the same tables `resolve_term` consults, so the published list
    cannot drift from what actually resolves.
    """
    labels = {t.label for t in TERM_ALIASES.values()}
    for feature in FEATURES:
        if _feature_documents(feature):
            labels.add(feature)
    return tuple(sorted(labels))


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------


class TerminologyAnswer(BaseModel):
    """One terminology answer, or the reason there is not one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 25
    version: str = TERMINOLOGY_VERSION
    term: str
    covered: bool
    resolution: str
    canonical_feature: Optional[str] = None
    outcome: str
    #: The ONLY string a caller may show. Either reviewed corpus text or
    #: `guarded_generation().approved_text` -- never raw model output.
    explanation: Optional[str] = None
    source_kind: str = Field(
        description=(
            "curated_knowledge_base | llm_validated | none. Says which of the "
            "two safety arguments applies to `explanation`."
        )
    )
    notice: Optional[str] = None
    fallback: Optional[SafeFallback] = None
    sources: Tuple[ExplanationSource, ...] = ()
    covered_terms: Tuple[str, ...] = ()
    safety: SafetyOutcome


def _echoable(term: str) -> str:
    cleaned = _ECHOABLE.sub("", (term or ""))
    cleaned = " ".join(cleaned.split())[:MAX_TERM_CHARS]
    return cleaned


def _not_covered_notice(term: str) -> str:
    """Fixed wording, with the submitted term echoed only after filtering.

    This is the single place a human-typed string reaches patient-facing
    output, so it is filtered to a conservative character set AND the finished
    sentence is put through Module 24 by the caller. If the validator refuses
    it, `_not_covered_notice_anonymous` is used instead.
    """
    safe = _echoable(term)
    if not safe:
        return _not_covered_notice_anonymous()
    return (
        f"This platform does not hold reviewed information about the term "
        f"'{safe}', "
        "so no explanation of it was produced. Nothing was guessed and no "
        "similar-sounding term was substituted. A qualified healthcare "
        "professional can explain a term this platform does not cover."
    )


def _not_covered_notice_anonymous() -> str:
    return (
        "This platform does not hold reviewed information about the term that "
        "was submitted, so no explanation of it was produced. Nothing was "
        "guessed and no similar-sounding term was substituted. A qualified "
        "healthcare professional can explain a term this platform does not "
        "cover."
    )


def _assemble(docs: Sequence[KnowledgeDocument]) -> str:
    """Build the served answer from curated text ONLY.

    Composition is concatenation: no sentence here was written at runtime
    except the two catalogue lines appended at the end, both of which are read
    from `recommendation_catalog` by code rather than typed in.
    """
    parts: List[str] = []
    for doc in docs:
        parts.append(doc.summary.strip())
        for paragraph in doc.paragraphs:
            parts.append(paragraph)
    parts.append(recommendation(NOT_A_DIAGNOSIS).text)
    parts.append(recommendation(DISCUSS_WITH_CLINICIAN).text)
    # De-duplicate adjacent repeats (a summary that restates its first
    # paragraph is common in the corpus).
    out: List[str] = []
    for part in parts:
        if part and (not out or out[-1] != part):
            out.append(part)
    return "\n\n".join(out)


def _scored(docs: Sequence[KnowledgeDocument]) -> List[ScoredChunk]:
    """Real `Chunk`s for the selected documents, at score 1.0.

    1.0 records that these were SELECTED BY EXACT MAPPING, not ranked by
    similarity. Reusing `chunk_document` rather than inventing a second
    representation keeps the citation shape identical to Module 21's.
    """
    out: List[ScoredChunk] = []
    for doc in docs:
        for chunk in chunk_document(doc):
            out.append(ScoredChunk(chunk=chunk, score=1.0, text_score=1.0, tag_score=1.0))
    return out


def _not_covered(resolution: TermResolution) -> TerminologyAnswer:
    # STEP 1 -- validate the ECHO ON ITS OWN, before it is wrapped.
    #
    # Validating only the finished sentence was not enough, and the reason is
    # subtle enough to be worth writing down. `_drop_disclaimed_replacements`
    # excuses a REPLACES_PROFESSIONAL_CONSULTATION hit when a negator sits in
    # the 60 characters before it, inside the same sentence. The template's own
    # opening -- "This platform DOES NOT hold reviewed information about the
    # term '<echo>'" -- puts a negator there every single time. So the carve-out
    # was disarmed BY CONSTRUCTION for every echo, and
    #
    #     explain_term("there is no need to see a doctor")
    #
    # returned that phrase verbatim to the patient inside an otherwise safe
    # sentence. Medication and dosage injections were caught, because those
    # rules have no negation carve-out; only this class leaked.
    #
    # Checking the bare echo first removes the template's negator from the
    # picture entirely, so the phrase is judged on its own words.
    bare_echo = _echoable(resolution.term)
    echo_verdict = validate_text(
        bare_echo,
        SafetyContext(
            # A bare term is not a sentence, so the positive controls that
            # require sentence structure are off here. Only the PROHIBITION
            # rules matter for this check: does the submitted string itself
            # contain something we refuse to repeat back?
            require_referral=False,
            check_numeric_grounding=False,
            purpose="module_25_echo",
        ),
    )
    echo_is_unsafe = bool(echo_verdict.violations)

    notice = (
        _not_covered_notice_anonymous()
        if echo_is_unsafe
        else _not_covered_notice(resolution.term)
    )

    # STEP 2 -- validate the assembled sentence as before. Defence in depth:
    # step 1 judges the echo, step 2 judges what the reader actually sees.
    verdict = validate_text(
        notice,
        SafetyContext(
            require_referral=True,
            check_numeric_grounding=False,
            purpose="module_25_refusal",
        ),
    )
    echoed = "" if echo_is_unsafe else bare_echo
    if echo_is_unsafe or verdict.verdict == REJECT or verdict.approved_text is None:
        # The echoed term made the sentence unsafe -- which is exactly what a
        # prompt-injection attempt through the `term` field would look like.
        # The echo is dropped from the WHOLE response, not just the sentence:
        # a `term` field carrying "take metformin" is the same leak in a
        # different key.
        notice = _not_covered_notice_anonymous()
        echoed = ""
    else:
        notice = verdict.approved_text
    logger.info(
        "terminology_refused %s",
        safe_meta(module=25, resolution=resolution.resolution),
    )
    return TerminologyAnswer(
        term=echoed,
        covered=False,
        resolution=resolution.resolution,
        canonical_feature=resolution.canonical_feature,
        outcome=OUTCOME_NOT_COVERED,
        explanation=None,
        source_kind="none",
        notice=notice,
        fallback=safe_fallback(None),
        sources=(),
        covered_terms=covered_terms(),
        safety=SafetyOutcome(
            validated=True, verdict=verdict.verdict, attempts=0
        ),
    )


def explain_term(
    term: str,
    *,
    simplify: bool = False,
    llm: Any = None,
    settings: Optional[Settings] = None,
) -> TerminologyAnswer:
    """Explain one medical term, or refuse it.

    Default path serves the curated corpus verbatim. `simplify=True` asks the
    LLM to rewrite that same curated text in plainer language, gated by the
    same `guarded_generation` Module 23 uses -- and still only for a term that
    already mapped.
    """
    resolution = resolve_term(term)
    if not resolution.covered:
        return _not_covered(resolution)

    docs = [DOCUMENTS[d] for d in resolution.doc_ids if d in DOCUMENTS]
    if not docs:  # pragma: no cover -- `_self_check` makes this unreachable
        return _not_covered(
            resolution.model_copy(
                update={"covered": False, "resolution": RESOLUTION_NO_CORPUS_COVERAGE}
            )
        )

    scored = _scored(docs)
    sources = tuple(to_explanation_source(s) for s in scored)

    if simplify:
        generated: PatientExplanation = explain_terminology_entry(
            term=_echoable(resolution.term) or (resolution.label or "this term"),
            canonical_feature=resolution.canonical_feature,
            scored_chunks=scored,
            llm=llm,
            settings=settings,
        )
        if generated.explanation is not None:
            return TerminologyAnswer(
                term=_echoable(resolution.term),
                covered=True,
                resolution=resolution.resolution,
                canonical_feature=resolution.canonical_feature,
                outcome=OUTCOME_GENERATED,
                explanation=generated.explanation,
                source_kind="llm_validated",
                notice=None,
                fallback=None,
                sources=generated.sources,
                safety=generated.safety,
            )
        # Generation was refused. Rather than show the fallback, fall back to
        # the CURATED text -- which is a better answer than none and is exactly
        # what the default path would have served.
        logger.info(
            "terminology_generation_withheld %s",
            safe_meta(module=25, outcome=generated.outcome),
        )

    text = _assemble(docs)
    verdict = validate_text(
        text,
        SafetyContext(
            grounding_sources=tuple(s.chunk.text for s in scored),
            require_grounding=False,
            require_referral=True,
            check_numeric_grounding=True,
            purpose="module_25_curated",
        ),
    )
    if verdict.approved_text is None:
        # Reviewed corpus text that the safety layer refuses is a defect in the
        # corpus, not a reason to show it anyway.
        logger.warning(
            "terminology_curated_text_rejected %s",
            safe_meta(
                module=25,
                codes=",".join(sorted(set(verdict.codes))),
                doc_count=len(docs),
            ),
        )
        return TerminologyAnswer(
            term=_echoable(resolution.term),
            covered=True,
            resolution=resolution.resolution,
            canonical_feature=resolution.canonical_feature,
            outcome=OUTCOME_WITHHELD_BY_SAFETY,
            explanation=None,
            source_kind="none",
            notice=None,
            fallback=safe_fallback(verdict),
            sources=sources,
            safety=SafetyOutcome(
                validated=True,
                verdict=verdict.verdict,
                violation_codes=tuple(sorted(set(verdict.codes))),
                modification_count=len(verdict.modifications),
                attempts=0,
            ),
        )

    return TerminologyAnswer(
        term=_echoable(resolution.term),
        covered=True,
        resolution=resolution.resolution,
        canonical_feature=resolution.canonical_feature,
        outcome=OUTCOME_SERVED_FROM_KNOWLEDGE_BASE,
        explanation=verdict.approved_text,
        source_kind="curated_knowledge_base",
        notice=None,
        fallback=None,
        sources=sources,
        safety=SafetyOutcome(
            validated=True,
            verdict=verdict.verdict,
            violation_codes=tuple(sorted(set(verdict.codes))),
            modification_count=len(verdict.modifications),
            attempts=0,
        ),
    )


def terminology_policy_document() -> Dict[str, Any]:
    """What this module answers, what it refuses, and why."""
    return {
        "module": 25,
        "version": TERMINOLOGY_VERSION,
        "policy": TERMINOLOGY_POLICY,
        "resolution_kinds": [
            RESOLUTION_CANONICAL_FEATURE,
            RESOLUTION_CURATED_ALIAS,
            RESOLUTION_NO_CORPUS_COVERAGE,
            RESOLUTION_UNMAPPED,
            RESOLUTION_EMPTY,
        ],
        "outcomes": list(TERMINOLOGY_OUTCOMES),
        "free_text_retrieval": False,
        "free_text_retrieval_note": (
            "Disabled by design. Measured TF-IDF similarity for uncovered "
            "terms (0.141-0.271) overlaps the range for covered terms "
            "(0.121-0.27), so no floor separates them and a nearest match is "
            "not evidence of coverage."
        ),
        "covered_terms": list(covered_terms()),
        "known_gaps": list(KNOWN_GAPS),
        "default_source": "curated_knowledge_base",
        "llm_used_by_default": False,
    }


#: Terms the SPEC names that the corpus does not cover, stated openly rather
#: than answered from the nearest document. Reviewed alongside Module 22.
KNOWN_GAPS: Tuple[str, ...] = (
    "SGPT / ALT (liver enzymes) -- spec Module 25 names SGPT and the Module "
    "22 corpus holds no liver document, so it is refused",
    "TSH and thyroid tests",
    "ferritin and iron studies",
    "full blood count parameters (WBC, RBC, platelets)",
    "PSA",
    "CRP and other inflammatory markers",
)


def _self_check() -> None:
    """Import-time guarantees. A broken table stops the service starting."""
    for key, target in TERM_ALIASES.items():
        if not key:
            raise ValueError("empty terminology alias key")
        for doc_id in target.doc_ids:
            if doc_id not in DOCUMENTS:
                raise ValueError(
                    f"terminology alias {target.label!r} names knowledge "
                    f"document {doc_id!r}, which is not in the corpus"
                )
        if target.feature is not None and target.feature not in FEATURES:
            raise ValueError(
                f"terminology alias {target.label!r} names feature "
                f"{target.feature!r}, which is not in the feature catalogue"
            )
        if not target.doc_ids and not target.feature:
            raise ValueError(
                f"terminology alias {target.label!r} resolves to nothing"
            )
    # Every term this module ADVERTISES must actually resolve. Publishing a
    # term in the "not covered" reply that then refuses would be worse than
    # publishing nothing.
    for advertised in covered_terms():
        if not resolve_term(advertised).covered:
            raise ValueError(
                f"terminology advertises {advertised!r} but it does not resolve"
            )


_self_check()


__all__ = [
    "KNOWN_GAPS",
    "MAX_TERM_CHARS",
    "OUTCOME_GENERATED",
    "OUTCOME_MODEL_UNAVAILABLE",
    "OUTCOME_NOT_COVERED",
    "OUTCOME_SERVED_FROM_KNOWLEDGE_BASE",
    "OUTCOME_WITHHELD_BY_SAFETY",
    "RESOLUTION_CANONICAL_FEATURE",
    "RESOLUTION_CURATED_ALIAS",
    "RESOLUTION_EMPTY",
    "RESOLUTION_NO_CORPUS_COVERAGE",
    "RESOLUTION_UNMAPPED",
    "TERMINOLOGY_OUTCOMES",
    "TERMINOLOGY_POLICY",
    "TERMINOLOGY_VERSION",
    "TERM_ALIASES",
    "TermResolution",
    "TermTarget",
    "TerminologyAnswer",
    "covered_terms",
    "explain_term",
    "resolve_term",
    "terminology_policy_document",
]
