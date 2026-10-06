"""The Modules 21-22 HTTP surface.

Response-shape, validation and auth behaviour for `/api/v1/knowledge/*`.
`tests/test_auth.py` already walks the whole route tree and fails if any
`/api/v1` route lacks the service-key dependency; the auth tests here are the
specific, readable version of that guarantee for this router.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data.conditions import DIABETES
from app.data.knowledge_base import DOCUMENTS
from app.rag.index import SIMILARITY_FLOOR
from tests.conftest import TEST_SERVICE_KEY

RETRIEVE = "/api/v1/knowledge/retrieve"
INDEX = "/api/v1/knowledge/index"
COVERAGE = "/api/v1/knowledge/coverage"
DOCS = "/api/v1/knowledge/documents"


def _build_app(**settings_overrides):
    """A FastAPI app carrying the knowledge router and main.py's handlers.

    The router is NOT mounted by this module -- `app/main.py` belongs to the
    integrator, who adds the `include_router` line. Building the app here means
    these tests exercise the router the moment it exists, rather than being
    blocked on that one line, and they keep passing unchanged afterwards.

    The exception handlers are COPIED from `app.main` rather than reimplemented,
    so the error envelopes asserted below are the real ones. A test that
    asserted a hand-rolled envelope would pass while the service returned
    something else.
    """
    from fastapi import FastAPI

    from app.api import routes_knowledge
    from app.config import Settings, get_settings
    from app.main import app as real_app

    test_app = FastAPI()
    test_app.include_router(routes_knowledge.router)
    for exc_type, handler in real_app.exception_handlers.items():
        test_app.add_exception_handler(exc_type, handler)

    if settings_overrides:
        test_settings = Settings(_env_file=None, **settings_overrides)
        test_app.dependency_overrides[get_settings] = lambda: test_settings
    return test_app


@pytest.fixture()
def kclient(_isolate_env) -> TestClient:
    """Unauthenticated client (the suite runs with ALLOW_UNAUTHENTICATED)."""
    with TestClient(_build_app(), raise_server_exceptions=False) as tc:
        yield tc


@pytest.fixture()
def kauthed(_isolate_env) -> TestClient:
    """A client whose settings REQUIRE the service key."""
    app = _build_app(
        ai_service_api_key=TEST_SERVICE_KEY, allow_unauthenticated=False
    )
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def _mounted_knowledge_paths():
    """Knowledge paths reachable on the real service app, if any."""
    from app.main import app as real_app

    found = set()
    for route in real_app.routes:
        found.add(getattr(route, "path", ""))
        original = getattr(route, "original_router", None)
        if original is not None:
            found |= {getattr(r, "path", "") for r in original.routes}
    return {p for p in found if p.startswith("/api/v1/knowledge")}


def test_the_knowledge_router_is_mounted_in_the_service_app():
    """Modules 21-22 are reachable on the real app.

    `app/main.py` belongs to the integrator, who adds exactly one line:

        app.include_router(routes_knowledge.router)

    This SKIPS while that line is absent rather than failing, so it cannot
    break the integrator's baseline before they have had a chance to add it,
    and it becomes a real assertion the moment they do. Every other test in
    this module exercises the router directly and does not depend on the mount.
    """
    mounted = _mounted_knowledge_paths()
    if not mounted:
        pytest.skip(
            "the knowledge router is not yet mounted in app/main.py -- add "
            "`app.include_router(routes_knowledge.router)` and this test "
            "activates automatically"
        )
    assert f"{RETRIEVE}" in mounted, mounted
    assert f"{INDEX}" in mounted, mounted


def test_every_knowledge_route_requires_the_service_key():
    """A retrieval request is a clinical statement about a patient.

    Router-level dependency, so this holds for routes added later too.
    `tests/test_auth.py` enforces the same thing across the whole app once the
    router is mounted; this is the module-local, always-active version.
    """
    from app.api import routes_knowledge
    from app.core.auth import require_service_key

    guards = [d.dependency for d in routes_knowledge.router.dependencies]
    assert require_service_key in guards, (
        "the knowledge router must carry the service-key dependency"
    )


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------


def test_spec_example_returns_grounded_chunks(kclient):
    response = kclient.post(
        RETRIEVE, json={"conditions": [DIABETES], "features": ["hba1c", "blood_glucose"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    data = body["data"]
    assert data["grounding_available"] is True
    assert data["returned"] == len(data["results"])
    assert data["results"]
    assert data["query"]["conditions"] == [DIABETES]
    assert data["query"]["source"] == "findings"
    assert data["similarity_floor"] == SIMILARITY_FLOOR


def test_every_returned_chunk_carries_its_provenance(kclient):
    response = kclient.post(RETRIEVE, json={"conditions": [DIABETES], "top_k": 5})
    for chunk in response.json()["data"]["results"]:
        for key in ("chunk_id", "doc_id", "title", "topic", "text", "basis",
                    "features", "conditions", "last_reviewed", "score",
                    "text_score", "tag_score"):
            assert key in chunk, key
        assert chunk["basis"].strip()
        assert chunk["doc_id"] in DOCUMENTS
        assert chunk["score"] >= SIMILARITY_FLOOR


def test_free_text_retrieval_works(kclient):
    """Free text still retrieves -- but ANCHORED, which the echo now shows.

    `source` was asserted to be `"text"`, and that assertion encoded the
    defect rather than the requirement: it recorded that this endpoint
    retrieved on the raw words, which is precisely what sections 6k D7 and
    6r D1 were about. The words are now resolved to canonical features first
    and retrieved on those, so the query is `findings_and_text` -- the text is
    still echoed, and what it resolved to is visible beside it.
    """
    response = kclient.post(RETRIEVE, json={"text": "what does HbA1c measure"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"]["source"] == "findings_and_text"
    assert data["query"]["features"] == ["hba1c"]
    assert data["query"]["text"] == "what does HbA1c measure"
    assert data["results"]


def test_an_uncovered_medical_question_is_refused_over_HTTP(kclient):
    """The defect, at the layer it was actually reachable from.

    `test_off_domain_query_returns_empty_not_junk` passed throughout, because
    a bicycle puncture is far enough off-domain for the similarity floor to
    catch it. The queries that got through were MEDICAL ones this corpus does
    not cover -- they score inside the same range as covered terms, so no
    floor can separate them, and only anchoring can.
    """
    response = kclient.post(
        RETRIEVE, json={"text": "my ALP and GGT liver enzymes are high"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["results"] == []
    assert data["returned"] == 0
    assert data["grounding_available"] is False


@pytest.mark.parametrize(
    "text",
    ["how do I fix a puncture on my bicycle tyre", "asdfghjkl qwertyuiop"],
)
def test_off_domain_query_returns_empty_not_junk(kclient, text):
    """A successful 200 with no results -- 'no good grounding' is a real answer."""
    response = kclient.post(RETRIEVE, json={"text": text})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["results"] == []
    assert data["returned"] == 0
    assert data["grounding_available"] is False


def test_non_canonical_condition_is_a_422(kclient):
    response = kclient.post(RETRIEVE, json={"conditions": ["diabetes"]})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNKNOWN_VOCABULARY"


def test_non_canonical_feature_is_a_422(kclient):
    response = kclient.post(RETRIEVE, json={"features": ["HbA1c"]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_VOCABULARY"


def test_empty_request_is_rejected(kclient):
    """An empty retrieval request has no defensible answer, so it is not guessed."""
    assert kclient.post(RETRIEVE, json={}).status_code == 422


def test_unknown_field_is_rejected(kclient):
    """`extra=forbid`: a misspelled field must not silently change the query."""
    response = kclient.post(RETRIEVE, json={"condition": [DIABETES]})
    assert response.status_code == 422


@pytest.mark.parametrize("top_k", [0, -1, 1000])
def test_out_of_range_top_k_is_rejected(kclient, top_k):
    response = kclient.post(
        RETRIEVE, json={"conditions": [DIABETES], "top_k": top_k}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("floor", [-0.1, 1.5])
def test_out_of_range_floor_is_rejected(kclient, floor):
    response = kclient.post(RETRIEVE, json={"conditions": [DIABETES], "floor": floor})
    assert response.status_code == 422


def test_top_k_is_honoured(kclient):
    response = kclient.post(RETRIEVE, json={"conditions": [DIABETES], "top_k": 2})
    assert len(response.json()["data"]["results"]) <= 2


# --------------------------------------------------------------------------
# Introspection
# --------------------------------------------------------------------------


def test_index_stats(kclient):
    body = kclient.get(INDEX).json()
    assert body["success"] is True
    data = body["data"]
    assert data["module"] == 21
    assert data["index"]["chunks"] > 0
    assert data["index"]["documents"] == len(DOCUMENTS)
    assert data["policy"]["similarity_floor"] == SIMILARITY_FLOOR
    assert "empty_rather_than_irrelevant" in data["policy"]


def test_coverage_endpoint_proves_full_coverage(kclient):
    data = kclient.get(COVERAGE).json()["data"]
    assert data["module"] == 22
    assert data["coverage"]["uncovered_features"] == []
    assert data["coverage"]["uncovered_conditions"] == []


def test_document_listing_and_filters(kclient):
    all_docs = kclient.get(DOCS).json()["data"]
    assert all_docs["total"] == len(DOCUMENTS)
    assert all_docs["returned"] == len(DOCUMENTS)

    filtered = kclient.get(DOCS, params={"condition": DIABETES}).json()["data"]
    assert 0 < filtered["returned"] < all_docs["total"]
    for doc in filtered["documents"]:
        assert DIABETES in doc["conditions"]

    by_topic = kclient.get(DOCS, params={"topic": "laboratory_test"}).json()["data"]
    assert by_topic["returned"] > 0
    for doc in by_topic["documents"]:
        assert doc["topic"] == "laboratory_test"


def test_single_document_returns_full_text(kclient):
    data = kclient.get(f"{DOCS}/lab_hba1c").json()["data"]
    assert data["doc_id"] == "lab_hba1c"
    assert data["body"].strip()
    assert data["paragraphs"]
    assert data["basis"].strip()


def test_unknown_document_is_a_404(kclient):
    response = kclient.get(f"{DOCS}/no_such_document")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_DOCUMENT"


# --------------------------------------------------------------------------
# Auth -- a retrieval request is itself a clinical statement about a patient
# --------------------------------------------------------------------------

PROTECTED = [
    ("POST", RETRIEVE, {"conditions": [DIABETES]}),
    ("GET", INDEX, None),
    ("GET", COVERAGE, None),
    ("GET", DOCS, None),
    ("GET", f"{DOCS}/lab_hba1c", None),
]


def _call(client, method, path, payload, headers=None):
    if method == "POST":
        return client.post(path, json=payload, headers=headers)
    return client.get(path, headers=headers)


@pytest.mark.parametrize("method,path,payload", PROTECTED)
def test_route_rejects_a_caller_with_no_key(kauthed, method, path, payload):
    response = _call(kauthed, method, path, payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("method,path,payload", PROTECTED)
def test_route_rejects_a_wrong_key(kauthed, method, path, payload):
    response = _call(
        kauthed, method, path, payload, {"X-Service-Key": "wrong-key-value"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,payload", PROTECTED)
def test_route_accepts_the_correct_key(kauthed, method, path, payload):
    response = _call(
        kauthed, method, path, payload, {"X-Service-Key": TEST_SERVICE_KEY}
    )
    assert response.status_code == 200
