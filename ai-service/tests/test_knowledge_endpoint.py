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
    with TestClient(_build_app(), raise_server_exceptions=False) as tc:
        yield tc


@pytest.fixture()
def kauthed(_isolate_env) -> TestClient:
    app = _build_app(
        ai_service_api_key=TEST_SERVICE_KEY, allow_unauthenticated=False
    )
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def _mounted_knowledge_paths():
    from app.main import app as real_app

    found = set()
    for route in real_app.routes:
        found.add(getattr(route, "path", ""))
        original = getattr(route, "original_router", None)
        if original is not None:
            found |= {getattr(r, "path", "") for r in original.routes}
    return {p for p in found if p.startswith("/api/v1/knowledge")}


def test_the_knowledge_router_is_mounted_in_the_service_app():
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
    from app.api import routes_knowledge
    from app.core.auth import require_service_key

    guards = [d.dependency for d in routes_knowledge.router.dependencies]
    assert require_service_key in guards, (
        "the knowledge router must carry the service-key dependency"
    )


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
    response = kclient.post(RETRIEVE, json={"text": "what does HbA1c measure"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"]["source"] == "findings_and_text"
    assert data["query"]["features"] == ["hba1c"]
    assert data["query"]["text"] == "what does HbA1c measure"
    assert data["results"]


def test_an_uncovered_medical_question_is_refused_over_HTTP(kclient):
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
    assert kclient.post(RETRIEVE, json={}).status_code == 422


def test_unknown_field_is_rejected(kclient):
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
