from __future__ import annotations


def test_health_returns_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "ok"
    assert data["module"].startswith("4")
    assert data["limits"]["max_page_count"] >= 1
    assert set(data["limits"]["supported_types"]) == {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }


def test_health_reports_configured_model_name(client):
    data = client.get("/api/v1/health").json()["data"]
    assert data["model"] == "gemini-3.6-flash"
    assert "prompt_version" in data


def test_health_never_leaks_the_api_key(client):
    raw = client.get("/api/v1/health").text
    assert "api_key" not in raw.lower() or "model_configured" in raw
    body = client.get("/api/v1/health").json()["data"]
    assert isinstance(body["model_configured"], bool)
    assert "AIza" not in raw
    assert "AQ." not in raw


def test_root_endpoint_lists_routes(client):
    body = client.get("/").json()
    assert body["success"] is True
    assert body["data"]["health"] == "/api/v1/health"


def test_unknown_route_uses_the_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert isinstance(body["error"]["message"], str)
