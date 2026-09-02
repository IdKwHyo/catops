"""Public health and inference response contracts."""

from __future__ import annotations

from datetime import datetime


def test_health_reports_database_and_matcher_readiness(api_client) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["service"] == "CatalogOps API"
    assert body["version"] == "1.0.0"
    assert body["matcher"] in {
        "fallback-ready",
        "fallback-baseline",
        "services.matcher",
    }
    datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))


def test_predict_returns_ranked_evidence_without_persisting(api_client) -> None:
    response = api_client.post(
        "/api/v1/matches/predict",
        json={
            "title": "Air Pods Pro Gen 2 USB C MTJV3",
            "brand": "Apple",
            "mpn": "MTJV3",
            "top_k": 2,
            "persist": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_id"] is None
    assert body["offer_id"] is None
    assert body["decision"] == "auto_match"
    assert body["confidence"] >= body["thresholds"]["auto_match"]
    assert body["thresholds"] == {"auto_match": 0.85, "review": 0.55}
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["product_id"] == "DEMO-1001"
    assert 0 <= body["candidates"][0]["score"] <= 1
    assert body["evidence"]
    assert body["latency_ms"] >= 0


def test_predict_persists_trace_and_rejects_missing_input(api_client) -> None:
    invalid = api_client.post("/api/v1/matches/predict", json={"persist": False})
    assert invalid.status_code == 422

    response = api_client.post(
        "/api/v1/matches/predict",
        headers={"X-Actor": "qa-client"},
        json={"offer_id": 1, "top_k": 3, "persist": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_id"]
    assert body["offer_id"] == 1
    assert body["decision"] == "auto_match"


def test_predict_returns_not_found_for_unknown_offer(api_client) -> None:
    response = api_client.post(
        "/api/v1/matches/predict", json={"offer_id": 999_999, "persist": False}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
