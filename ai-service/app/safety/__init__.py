"""Module 24 -- the Medical Safety and Validation Layer.

Spec section 14 fixes the pipeline as

    LLM Output  ->  Safety Validation  ->  Approved Educational Response

and NOT

    LLM Output  ->  Directly shown to patient

This package is the middle box. Everything a patient could read that was not
drawn from the reviewed catalogue passes through `validate_text` first, and
`validate_text` returns a VERDICT -- approve / approve_with_modification /
reject -- that Module 23 acts on programmatically.

Import surface (deliberately small; Module 23 needs only these):

    validate_text(text, context=...)   -> SafetyVerdict
    SafetyContext(...)                 -> what grounding/policy applies
    SafetyVerdict.verdict              -> APPROVE | APPROVE_WITH_MODIFICATION
                                          | REJECT
    SafetyVerdict.approved_text        -> what may be shown (None on REJECT)
    guarded_generation(...)            -> generate, validate, retry, fall back
    safe_fallback(...)                 -> what to show when nothing was approved

Nothing in this package imports FastAPI. `app/api/routes_safety.py` is a thin
HTTP wrapper over it, exactly as `routes_report.py` is over the report builder.
"""

from __future__ import annotations

from app.safety.policy import (
    SAFETY_LAYER_VERSION,
    SAFETY_POLICY,
    MODIFICATION_POLICY,
    Severity,
    ViolationCode,
    RULES,
    rule_document,
)
from app.safety.validator import (
    APPROVE,
    APPROVE_WITH_MODIFICATION,
    REJECT,
    MAX_TEXT_LENGTH,
    REDACTION_NOTICE,
    SafetyContext,
    SafetyModification,
    SafetyVerdict,
    SafetyViolation,
    UnsafeGeneratedContentError,
    assert_safe_for_patient,
    validate_text,
)
from app.safety.fallback import (
    FALLBACK_NOTICE,
    GuardedGenerationResult,
    SafeFallback,
    guarded_generation,
    safe_fallback,
)

__all__ = [
    "APPROVE",
    "APPROVE_WITH_MODIFICATION",
    "FALLBACK_NOTICE",
    "MAX_TEXT_LENGTH",
    "MODIFICATION_POLICY",
    "REDACTION_NOTICE",
    "REJECT",
    "RULES",
    "SAFETY_LAYER_VERSION",
    "SAFETY_POLICY",
    "GuardedGenerationResult",
    "SafeFallback",
    "SafetyContext",
    "SafetyModification",
    "SafetyVerdict",
    "SafetyViolation",
    "Severity",
    "UnsafeGeneratedContentError",
    "ViolationCode",
    "assert_safe_for_patient",
    "guarded_generation",
    "rule_document",
    "safe_fallback",
    "validate_text",
]
