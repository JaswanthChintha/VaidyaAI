from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from app.core.auth import SERVICE_KEY_HEADER
from app.data.feature_catalog import CANONICAL_FEATURES
from tests.conftest import TEST_SERVICE_KEY
from tests.trend_payloads import rejection, report, vf

TRENDS = "/api/v1/timeline/trends"
POLICY = "/api/v1/timeline/policy"

ROUTES = [("post", TRENDS), ("get", POLICY)]


def body(reports: List[Dict[str, Any]], **options: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"reports": reports}
    if options:
        payload["options"] = options
    return payload


HBA1C_RISING = [
    report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
    report("r2", "2024-03-01T00:00:00Z", {"hba1c": vf("hba1c", 6.4, "%")}),
    report("r3", "2024-06-01T00:00:00Z", {"hba1c": vf("hba1c", 6.8, "%")}),
]


def test_the_specification_example_round_trips_through_http(client):
    response = client.post(TRENDS, json=body(HBA1C_RISING))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["success"] is True
    data = payload["data"]
    assert set(data) >= {
        "policy_version",
        "generated_at",
        "reports",
        "features",
        "summary",
        "warnings",
        "disclaimer",
    }
    assert [ref["report_id"] for ref in data["reports"]] == ["r1", "r2", "r3"]

    hba1c = data["features"]["hba1c"]
    assert hba1c["outcome"] == "TREND_CLASSIFIED"
    assert hba1c["trend"] == "worsening"
    assert hba1c["direction"] == "rising"
    assert [point["value"] for point in hba1c["points"]] == [6.1, 6.4, 6.8]
    assert data["summary"]["worsening"] == 1
    assert data["disclaimer"]


def test_the_patient_ref_is_echoed_and_nothing_else_identifying_is_added(client):
    response = client.post(
        TRENDS, json=dict(body(HBA1C_RISING), patient_ref="patient-1")
    )
    data = response.json()["data"]
    assert data["patient_ref"] == "patient-1"


def test_a_relayed_envelope_is_not_read_as_an_empty_request(client):
    response = client.post(TRENDS, json={"data": body(HBA1C_RISING)})
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["report_count"] == 3


def test_insufficient_data_arrives_as_an_explicit_null_trend(client):
    response = client.post(
        TRENDS,
        json=body(
            [
                report(
                    "r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}
                ),
                report("r2", "2024-06-01T00:00:00Z", {}),
            ]
        ),
    )
    hba1c = response.json()["data"]["features"]["hba1c"]

    assert "trend" in hba1c
    assert hba1c["trend"] is None
    assert hba1c["outcome"] == "INSUFFICIENT_DATA"
    assert hba1c["change"] is None
    assert hba1c["reason"]
    assert hba1c["gaps"][0]["report_id"] == "r2"
    assert "value" not in hba1c["gaps"][0]


def test_a_rejected_reading_never_crosses_the_wire_as_a_value(client):
    response = client.post(
        TRENDS,
        json=body(
            [
                report(
                    "r1",
                    "2024-01-01T00:00:00Z",
                    {"creatinine": vf("creatinine", 1.0, "mg/dl")},
                ),
                report(
                    "r2",
                    "2024-06-01T00:00:00Z",
                    {},
                    rejected={"creatinine": rejection("creatinine")},
                ),
            ],
            features=["creatinine"],
        ),
    )
    data = response.json()["data"]
    gap = data["features"]["creatinine"]["gaps"][0]
    assert gap["availability"] == "rejected"
    assert gap["reason_code"] == "IMPLAUSIBLE_VALUE_HIGH"
    assert "value" not in gap
    assert "9999" not in json.dumps(data)


def test_an_undeclared_polarity_refuses_over_http_with_its_arithmetic(client):
    response = client.post(
        TRENDS,
        json=body(
            [
                report(
                    "r1",
                    "2024-01-01T00:00:00Z",
                    {"blood_glucose": vf("blood_glucose", 90.0, "mg/dl")},
                ),
                report(
                    "r2",
                    "2024-06-01T00:00:00Z",
                    {"blood_glucose": vf("blood_glucose", 180.0, "mg/dl")},
                ),
            ]
        ),
    )
    glucose = response.json()["data"]["features"]["blood_glucose"]
    assert glucose["outcome"] == "CLINICAL_DIRECTION_UNKNOWN"
    assert glucose["trend"] is None
    assert glucose["direction"] == "rising"
    assert glucose["change"]["absolute_change"] == 90.0
    assert glucose["polarity"]["kind"] == "undeclared"


def test_a_unit_mismatch_refuses_over_http_and_converts_nothing(client):
    response = client.post(
        TRENDS,
        json=body(
            [
                report(
                    "r1",
                    "2024-01-01T00:00:00Z",
                    {"creatinine": vf("creatinine", 1.0, "mg/dl")},
                ),
                report(
                    "r2",
                    "2024-06-01T00:00:00Z",
                    {"creatinine": vf("creatinine", 88.4, "umol/l")},
                ),
            ]
        ),
    )
    creatinine = response.json()["data"]["features"]["creatinine"]
    assert creatinine["outcome"] == "UNIT_MISMATCH"
    assert creatinine["trend"] is None
    assert [p["value"] for p in creatinine["points"]] == [1.0, 88.4]


def test_no_feature_ever_comes_back_as_stable_when_nothing_was_measured(client):
    response = client.post(
        TRENDS,
        json=body(
            [
                report("r1", "2024-01-01T00:00:00Z", {}),
                report("r2", "2024-06-01T00:00:00Z", {}),
            ],
            include_all_canonical=True,
        ),
    )
    data = response.json()["data"]
    assert len(data["features"]) == len(CANONICAL_FEATURES)
    for name, feature in data["features"].items():
        assert feature["trend"] is None, name
        assert feature["outcome"] != "TREND_CLASSIFIED"
    assert data["summary"]["stable"] == 0
    assert data["summary"]["not_determinable"] == len(CANONICAL_FEATURES)
    assert '"trend": "stable"' not in json.dumps(data)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"reports": [{"report_id": "r1"}]}, id="no_chrono_date"),
        pytest.param(
            {"reports": [{"chrono_date": "2024-01-01T00:00:00Z"}]}, id="no_report_id"
        ),
        pytest.param(
            {
                "reports": [
                    report("r1", "2024-01-01T00:00:00Z", {}),
                    report("r1", "2024-02-01T00:00:00Z", {}),
                ]
            },
            id="duplicate_report_id",
        ),
        pytest.param(
            {
                "reports": [report("r1", "2024-01-01T00:00:00Z", {})],
                "options": {"features": ["not_a_feature"]},
            },
            id="unknown_feature",
        ),
        pytest.param(
            {"reports": [{"report_id": "r1", "chrono_date": "not-a-date"}]},
            id="unparseable_date",
        ),
        pytest.param({"reports": "hba1c"}, id="reports_not_a_list"),
    ],
)
def test_malformed_requests_are_422_and_not_a_partial_answer(client, payload):
    response = client.post(TRENDS, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_an_empty_report_list_is_accepted_and_answers_with_a_refusal(client):
    response = client.post(TRENDS, json={"reports": []})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["features"] == {}
    assert data["summary"]["report_count"] == 0
    assert any("No reports" in warning for warning in data["warnings"])


def test_the_policy_endpoint_publishes_the_tables_behind_every_answer(client):
    response = client.get(POLICY)
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"analyzer", "polarity"}

    polarity = data["polarity"]
    assert set(polarity["features"]) == set(CANONICAL_FEATURES)
    assert polarity["features"]["hba1c"]["direction_of_harm"] == "increase"
    assert polarity["features"]["vitamin_d"]["optimal_low"] == 30.0
    assert polarity["features"]["blood_glucose"]["kind"] == "undeclared"
    for name, entry in polarity["features"].items():
        assert entry["basis"].strip(), f"{name} publishes no basis"
    assert data["analyzer"]["absence_policy"]
    assert data["analyzer"]["unit_policy"]


def test_the_policy_endpoint_is_a_rule_dump_and_holds_no_request_state(client):
    before = client.get(POLICY).json()
    client.post(
        TRENDS,
        json=dict(
            body(
                [
                    report(
                        "report-marker-aaa",
                        "2024-01-01T00:00:00Z",
                        {"hba1c": vf("hba1c", 6.1, "%")},
                    ),
                    report(
                        "report-marker-bbb",
                        "2024-06-01T00:00:00Z",
                        {"hba1c": vf("hba1c", 6.8, "%")},
                    ),
                ]
            ),
            patient_ref="patient-marker-ccc",
        ),
    )
    after = client.get(POLICY).json()

    assert before == after
    text = json.dumps(after)
    for leak in ("report-marker", "patient-marker", "2024-01-01"):
        assert leak not in text


def _call(client, method: str, path: str, headers=None):
    if method == "post":
        return client.post(path, json={"reports": []}, headers=headers)
    return client.get(path, headers=headers)


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_timeline_route_rejects_a_caller_without_the_key(
    authed_client, method, path
):
    response = _call(authed_client, method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_timeline_route_accepts_the_right_key(authed_client, method, path):
    response = _call(
        authed_client, method, path, {SERVICE_KEY_HEADER: TEST_SERVICE_KEY}
    )
    assert response.status_code != 401


def test_the_router_declares_the_auth_dependency_once_for_every_route():
    from app.api import routes_timeline
    from app.core.auth import require_service_key

    assert routes_timeline.router.routes, "the router declares no routes"
    dependencies = [
        dependency.dependency
        for dependency in routes_timeline.router.dependencies
    ]
    assert require_service_key in dependencies
