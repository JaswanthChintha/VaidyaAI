"""Module 24 over HTTP -- POST /api/v1/safety/validate and the introspection.

No API key, no network. The router is mounted on a LOCALLY BUILT app here
rather than taken from `app.main`, because mounting it in `app/main.py` is the
coordinator's edit and this suite must pass either side of it. The two tests at
the bottom cover both worlds: the router's own routes must declare the
service-key dependency, and IF the route is already mounted in `app.main` it
must carry it there too. `tests/test_auth.py` walks the real app recursively
and enforces the same thing once the mount lands.

The endpoint is a thin wrapper. Everything about WHAT is safe is tested in
`tests/test_safety_validator.py`; what is tested here is the contract -- the
envelope, the pydantic v2 enforcement, the fallback on rejection, and that
nothing submitted over the wire reaches the logs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_safety
from app.core.auth import require_service_key
from app.safety.policy import ViolationCode

VALIDATE = "/api/v1/safety/validate"
POLICY = "/api/v1/safety/policy"
RULES = "/api/v1/safety/rules"

SAFE_TEXT = (
    "Your HbA1c sits a little above the band this tool uses. A qualified "
    "healthcare professional can say what that may mean for you."
)
UNSAFE_TEXT = "Take metformin 500 mg twice a day; this confirms you have diabetes."


@pytest.fixture()
def safety_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(routes_safety.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _post(client: TestClient, **payload: Any) -> Dict[str, Any]:
    response = client.post(VALIDATE, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------


def test_a_clean_text_is_approved_in_the_standard_envelope(safety_client) -> None:
    body = _post(safety_client, text=SAFE_TEXT)
    assert body["success"] is True
    verdict = body["data"]["verdict"]
    assert verdict["verdict"] == "approve"
    assert verdict["approved_text"] == SAFE_TEXT
    assert verdict["violations"] == []
    assert verdict["fallback_required"] is False
    assert body["data"]["fallback"] is None


def test_a_rejection_carries_codes_spans_reasons_and_the_fallback(
    safety_client,
) -> None:
    """A rejection has to be actionable over the wire, not just a 'no'.

    Module 23 will call the in-process function, but the backend calls this,
    and a backend that gets `false` back can neither retry nor explain.
    """
    body = _post(safety_client, text=UNSAFE_TEXT)
    verdict = body["data"]["verdict"]
    assert verdict["verdict"] == "reject"
    assert verdict["approved_text"] is None
    assert verdict["fallback_required"] is True

    codes = {v["code"] for v in verdict["violations"]}
    assert ViolationCode.MEDICATION_REFERENCE.value in codes
    assert ViolationCode.MEDICATION_DOSAGE.value in codes
    for violation in verdict["violations"]:
        assert violation["rule_id"]
        assert violation["reason"]
        assert violation["severity"]
        assert (
            verdict["analysed_text"][
                violation["span_start"] : violation["span_end"]
            ]
            == violation["excerpt"]
        )

    fallback = body["data"]["fallback"]
    assert fallback is not None
    assert fallback["generated_explanation_available"] is False
    assert fallback["use_structured_report"] is True
    assert fallback["recommendations"]


def test_approve_with_modification_is_reported_as_such(safety_client) -> None:
    body = _post(
        safety_client,
        text="Your HbA1c sits above the band this tool uses.",
    )
    verdict = body["data"]["verdict"]
    assert verdict["verdict"] == "approve_with_modification"
    assert verdict["modifications"][0]["action"] == "append_safety_framing"
    assert verdict["approved_text"].startswith(
        "Your HbA1c sits above the band this tool uses."
    )


def test_grounding_is_honoured_over_the_wire(safety_client) -> None:
    payload = {
        "text": "Your HbA1c of 6.8% sits above the 9.9% figure this tool uses.",
        "grounding_sources": ["The threshold this tool uses is 6.5%."],
        "permitted_numbers": [6.8],
        "require_referral": False,
    }
    body = _post(safety_client, **payload)
    verdict = body["data"]["verdict"]
    assert verdict["verdict"] == "reject"
    assert ViolationCode.UNGROUNDED_NUMERIC_CLAIM.value in {
        v["code"] for v in verdict["violations"]
    }


# --------------------------------------------------------------------------
# Fail closed at the HTTP edge too
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, 12, [], {}, True])
def test_a_non_string_body_is_a_422_not_an_approval(safety_client, bad) -> None:
    """Pydantic v2 refuses it before the validator sees it. Either way: no pass.

    (The `{success:false, error:{...}}` envelope for a 422 is applied by
    `app/main.py`'s handler, which this locally-mounted app does not carry.
    What matters here is that the request never reaches an approval.)
    """
    response = safety_client.post(VALIDATE, json={"text": bad})
    assert response.status_code == 422
    assert "approved_text" not in response.text


def test_a_missing_text_field_is_a_422(safety_client) -> None:
    response = safety_client.post(VALIDATE, json={})
    assert response.status_code == 422


def test_a_misspelled_field_is_a_422_not_a_weaker_check(safety_client) -> None:
    """`extra="forbid"` is load-bearing here.

    A caller who typed `grounding_source` would otherwise silently get a
    validation with NO numeric grounding and a clean verdict back. In this
    module a typo must be an error, not a quieter check.
    """
    response = safety_client.post(
        VALIDATE,
        json={"text": SAFE_TEXT, "grounding_source": ["oops"]},
    )
    assert response.status_code == 422


def test_an_empty_text_is_rejected_not_approved(safety_client) -> None:
    body = _post(safety_client, text="   ")
    assert body["data"]["verdict"]["verdict"] == "reject"
    assert (
        ViolationCode.EMPTY_OUTPUT.value
        in {v["code"] for v in body["data"]["verdict"]["violations"]}
    )


def test_an_oversized_text_is_rejected(safety_client) -> None:
    body = _post(safety_client, text="a" * 20_001)
    assert body["data"]["verdict"]["verdict"] == "reject"
    assert (
        ViolationCode.INPUT_TOO_LARGE.value
        in {v["code"] for v in body["data"]["verdict"]["violations"]}
    )


# --------------------------------------------------------------------------
# Introspection -- a rule nobody can retrieve is not an accountability
# mechanism, and a layer that publishes only its strengths is advertising
# --------------------------------------------------------------------------


def test_the_policy_endpoint_publishes_the_modification_scope(safety_client) -> None:
    body = safety_client.get(POLICY).json()
    assert body["success"] is True
    safety = body["data"]["medical_safety"]
    assert safety["module"] == 24
    assert safety["verdicts"] == [
        "approve",
        "approve_with_modification",
        "reject",
    ]
    actions = {a["action"] for a in safety["modification"]["permitted_actions"]}
    assert actions == {"append_safety_framing", "redact_sentence"}
    assert safety["policy"]["restricted_classes"]
    assert safety["fallback_notice"]


def test_the_policy_endpoint_publishes_the_limitations(safety_client) -> None:
    """An overstated safety layer is worse than an honestly-scoped one."""
    body = safety_client.get(POLICY).json()
    limitations = body["data"]["medical_safety"]["policy"]["limitations"]
    assert len(limitations) >= 4
    assert "blocklist" in " ".join(limitations).lower()


def test_the_rules_endpoint_lists_rules_without_publishing_the_patterns(
    safety_client,
) -> None:
    """The rule table is publishable; the regexes are the map of what to evade."""
    body = safety_client.get(RULES).json()
    data = body["data"]
    assert data["module"] == 24
    assert data["rule_count"] == len(data["rules"])
    assert data["blocklist_rule_count"] > 0
    assert data["positive_control_rule_count"] > 0
    for rule in data["rules"]:
        assert set(rule) == {"rule_id", "code", "severity", "reason", "kind"}
    assert set(data["codes"]) == {c.value for c in ViolationCode}
    assert "discuss" in data["permitted_directive_verbs"]


def test_the_introspection_endpoints_carry_no_phi(safety_client) -> None:
    """Shape and policy only, like the rule table and the fusion policy."""
    for path in (POLICY, RULES):
        text = safety_client.get(path).text
        assert "patient" not in text.lower() or "patient-facing" in text.lower()


# --------------------------------------------------------------------------
# Auth -- tests/test_auth.py enforces this on the real app once mounted
# --------------------------------------------------------------------------


def _walk_api_routes(routes):
    """Same descent as `tests/test_auth.py`: routers are wrapped, not flat."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _walk_api_routes(original.routes)
        elif getattr(route, "path", "").startswith("/api/v1"):
            yield route


def test_every_safety_route_declares_the_service_key_dependency() -> None:
    """The text submitted here restates a patient's values. It is PHI-bearing.

    Checked on the router itself so the guarantee holds from the moment the
    file exists, not only once `app/main.py` mounts it.
    """
    app = FastAPI()
    app.include_router(routes_safety.router)
    found = list(_walk_api_routes(app.routes))
    assert {r.path for r in found} == {VALIDATE, POLICY, RULES}
    for route in found:
        deps = getattr(route.dependant, "dependencies", [])
        assert any(
            d.call is require_service_key for d in deps
        ), f"{route.path} is unprotected"


def test_the_mounted_app_protects_the_safety_routes_if_they_are_mounted() -> None:
    """Passes before the mount lands and keeps passing after it.

    The mount itself is the coordinator's edit to `app/main.py`; this asserts
    that when it happens the route arrives protected.
    """
    from app.main import app

    for route in _walk_api_routes(app.routes):
        if not route.path.startswith("/api/v1/safety"):
            continue
        deps = getattr(route.dependant, "dependencies", [])
        assert any(d.call is require_service_key for d in deps), route.path


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


def test_the_endpoint_never_logs_the_submitted_text(safety_client, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    marker = "ZZENDPOINTMARKERZZ"
    _post(safety_client, text=f"{marker} take 500 mg twice a day.")
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert marker not in logged
    assert "500" not in logged
    assert ViolationCode.MEDICATION_DOSAGE.value in logged
