"""POST /api/v1/safety/validate -- the Module 24 endpoint.

Thin HTTP wrapper. All logic lives in `app.safety`, whose `validate_text`,
`guarded_generation` and `safe_fallback` are importable and callable
in-process -- which is how Module 23 will use them on every generation, exactly
as `evaluate_rules`, `fuse_decisions` and `generate_report` are used today. The
endpoint exists for the Node backend and for review, not because the layer
needs a server to work.

The router lives in its own file and carries its own prefix so it can be
mounted alongside the other routers without either module owning the other.

AUTH: the text submitted here is an explanation ABOUT a patient's report and
will routinely restate their values, so it is PHI-bearing and carries the same
service-key dependency as `routes_report.py`, `routes_rules.py`,
`routes_ml.py` and `routes_decisions.py`. `tests/test_auth.py` walks the route
tree recursively and fails if any `/api/v1` route lacks it. The introspection
routes carry it too: they publish no PHI, but an unauthenticated reader of the
rule table is an unauthenticated reader of exactly what would have to be
evaded.

LOGGING: this route never logs the submitted text. `app.safety.validator`
logs the verdict, the counts and the codes; nothing here adds to that.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.safety.fallback import FALLBACK_NOTICE, safe_fallback
from app.safety.policy import (
    MODIFICATION_POLICY,
    SAFETY_LAYER_VERSION,
    SAFETY_POLICY,
    rule_document,
)
from app.safety.schemas import (
    SafetyValidationData,
    SafetyValidationRequest,
    SafetyValidationResponse,
)
from app.safety.validator import (
    APPROVE,
    APPROVE_WITH_MODIFICATION,
    MAX_TEXT_LENGTH,
    REJECT,
    REDACTION_NOTICE,
    validate_text,
)

router = APIRouter(
    prefix="/api/v1/safety",
    tags=["medical-safety"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/validate",
    response_model=SafetyValidationResponse,
    response_model_exclude_none=False,
    summary="Validate patient-facing text before it is shown (spec section 14)",
)
async def validate(request: SafetyValidationRequest) -> SafetyValidationResponse:
    """Run the safety layer over one piece of text and return the verdict.

    The response carries `verdict.approved_text` -- the ONLY string a caller
    may show a patient -- and, on a rejection, the fallback to render instead.
    A caller that renders `verdict.analysed_text` has bypassed the layer.
    """
    verdict = validate_text(request.text, request.to_context())
    fallback = safe_fallback(verdict) if verdict.verdict == REJECT else None
    return SafetyValidationResponse(
        success=True,
        data=SafetyValidationData(verdict=verdict, fallback=fallback),
    )


@router.get(
    "/policy",
    summary="What the safety layer enforces, what it may modify, and what it cannot guarantee",
)
async def policy() -> dict:
    """The safety policy, in machine-readable form.

    Exposed for the same reason the rule table, the model metrics and the
    fusion policy are: a documented rule nobody can retrieve from the running
    service is not an accountability mechanism. That includes the
    LIMITATIONS -- a safety layer that publishes only its strengths is
    advertising, not accountability. Shape and policy only -- no PHI.
    """
    return {
        "success": True,
        "data": {
            "medical_safety": {
                "module": 24,
                "version": SAFETY_LAYER_VERSION,
                "policy": SAFETY_POLICY,
                "verdicts": [APPROVE, APPROVE_WITH_MODIFICATION, REJECT],
                "modification": MODIFICATION_POLICY,
                "max_text_length": MAX_TEXT_LENGTH,
                "redaction_notice": REDACTION_NOTICE,
                "fallback_notice": FALLBACK_NOTICE,
            }
        },
    }


@router.get(
    "/rules",
    summary="Every safety rule, its code, its severity, and whether it is a blocklist rule",
)
async def rules() -> dict:
    """The rule table itself.

    Each rule is labelled `blocklist`, `positive_control` or `fail_closed`, and
    the counts are published, so a reader can see for themselves how much of
    this layer is an enumeration of things somebody thought of. Patterns are
    NOT published: they are the exact map of what to paraphrase around.
    """
    return {"success": True, "data": {"module": 24, **rule_document()}}
