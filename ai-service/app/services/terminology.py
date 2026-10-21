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

MAX_TERM_CHARS = 80

_ECHOABLE = re.compile(r"[^A-Za-z0-9 /()\-.,%+']")


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


@dataclass(frozen=True)
class TermTarget:

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
        _alias(
            "ALT (SGPT)",
            "ALT",
            "SGPT",
            "S.G.P.T",
            "SGPT (ALT)",
            "ALT (SGPT)",
            "SGPT/ALT",
            "ALT/SGPT",
            "Serum SGPT",
            "SGPT Serum",
            "Serum ALT",
            "alanine aminotransferase",
            "alanine transaminase",
            "alanine aminotransferase (ALT)",
            "alanine aminotransferase (SGPT)",
            "alanine aminotransferase (ALT/SGPT)",
            "alanine aminotransferase (SGPT/ALT)",
            "serum glutamic pyruvic transaminase",
            docs=("term_alt_sgpt",),
        ),
        _alias(
            "AST (SGOT)",
            "AST",
            "SGOT",
            "S.G.O.T",
            "SGOT (AST)",
            "AST (SGOT)",
            "SGOT/AST",
            "AST/SGOT",
            "Serum SGOT",
            "SGOT Serum",
            "Serum AST",
            "aspartate aminotransferase",
            "aspartate transaminase",
            "aspartate aminotransferase (AST)",
            "aspartate aminotransferase (SGOT)",
            "aspartate aminotransferase (AST/SGOT)",
            "aspartate aminotransferase (SGOT/AST)",
            "serum glutamic oxaloacetic transaminase",
            docs=("term_ast_sgot",),
        ),
    ):
        for key, target in group.items():
            if key in table:
                raise ValueError(f"duplicate terminology alias key {key!r}")
            table[key] = target
    return table


TERM_ALIASES: Dict[str, TermTarget] = _build_aliases()


class TermResolution(BaseModel):

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


_TERM_TOPICS: Tuple[str, ...] = (
    TOPIC_LAB_TEST,
    TOPIC_TERMINOLOGY,
    TOPIC_REFERENCE,
    TOPIC_EDUCATION,
)


def _feature_documents(feature: str) -> List[KnowledgeDocument]:
    docs = documents_for_feature(feature)
    ordered = [d for topic in _TERM_TOPICS for d in docs if d.topic == topic]
    seen: Dict[str, None] = {}
    out: List[KnowledgeDocument] = []
    for doc in ordered:
        if doc.doc_id not in seen:
            seen[doc.doc_id] = None
            out.append(doc)
    return out


def resolve_term(term: str) -> TermResolution:
    raw = (term or "").strip()[:MAX_TERM_CHARS]
    normalised = normalize_test_name(raw)
    if not normalised:
        return TermResolution(
            term=raw,
            normalised="",
            covered=False,
            resolution=RESOLUTION_EMPTY,
        )

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
    labels = {t.label for t in TERM_ALIASES.values()}
    for feature in FEATURES:
        if _feature_documents(feature):
            labels.add(feature)
    return tuple(sorted(labels))


class TerminologyAnswer(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 25
    version: str = TERMINOLOGY_VERSION
    term: str
    covered: bool
    resolution: str
    canonical_feature: Optional[str] = None
    outcome: str
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
    parts: List[str] = []
    for doc in docs:
        parts.append(doc.summary.strip())
        for paragraph in doc.paragraphs:
            parts.append(paragraph)
    parts.append(recommendation(NOT_A_DIAGNOSIS).text)
    parts.append(recommendation(DISCUSS_WITH_CLINICIAN).text)
    out: List[str] = []
    for part in parts:
        if part and (not out or out[-1] != part):
            out.append(part)
    return "\n\n".join(out)


def _scored(docs: Sequence[KnowledgeDocument]) -> List[ScoredChunk]:
    out: List[ScoredChunk] = []
    for doc in docs:
        for chunk in chunk_document(doc):
            out.append(ScoredChunk(chunk=chunk, score=1.0, text_score=1.0, tag_score=1.0))
    return out


def _not_covered(resolution: TermResolution) -> TerminologyAnswer:
    bare_echo = _echoable(resolution.term)
    echo_verdict = validate_text(
        bare_echo,
        SafetyContext(
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
    resolution = resolve_term(term)
    if not resolution.covered:
        return _not_covered(resolution)

    docs = [DOCUMENTS[d] for d in resolution.doc_ids if d in DOCUMENTS]
    if not docs:
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


KNOWN_GAPS: Tuple[str, ...] = (
    "Other liver tests (alkaline phosphatase, bilirubin, GGT, albumin)",
    "TSH and thyroid tests",
    "ferritin and iron studies",
    "full blood count parameters (WBC, RBC, platelets)",
    "PSA",
    "CRP and other inflammatory markers",
)


def _self_check() -> None:
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
