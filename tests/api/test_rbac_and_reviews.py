"""Role boundaries and final human-review decisions."""

from __future__ import annotations

from sqlalchemy import select

from apps.api.app.models import AuditEvent, Offer

OFFER_PAYLOAD = {
    "external_id": "qa-seller-100",
    "seller": "QA Seller",
    "title": "Acme QA Product",
    "currency": "thb",
}


def test_create_offer_enforces_role_hierarchy(
    api_client, reviewer_headers, operator_headers
) -> None:
    missing = api_client.post("/api/v1/offers", json=OFFER_PAYLOAD)
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "missing_role"

    invalid = api_client.post(
        "/api/v1/offers",
        headers={"X-Role": "superuser"},
        json=OFFER_PAYLOAD,
    )
    assert invalid.status_code == 403
    assert invalid.json()["detail"]["code"] == "invalid_role"

    insufficient = api_client.post("/api/v1/offers", headers=reviewer_headers, json=OFFER_PAYLOAD)
    assert insufficient.status_code == 403
    assert insufficient.json()["detail"]["code"] == "insufficient_role"

    created = api_client.post("/api/v1/offers", headers=operator_headers, json=OFFER_PAYLOAD)
    assert created.status_code == 201
    assert created.json()["external_id"] == OFFER_PAYLOAD["external_id"]
    assert created.json()["currency"] == "THB"


def test_duplicate_offer_is_a_conflict(api_client, operator_headers) -> None:
    first = api_client.post("/api/v1/offers", headers=operator_headers, json=OFFER_PAYLOAD)
    second = api_client.post("/api/v1/offers", headers=operator_headers, json=OFFER_PAYLOAD)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_external_id"


def test_matched_review_updates_offer_once_and_appends_audit(
    api_client,
    db_session_factory,
    reviewer_headers,
) -> None:
    review_id = "10000000-0000-4000-8000-000000000001"
    with db_session_factory() as db:
        offer = db.get(Offer, 2)
        assert offer is not None
        offer.canonical_product_id = None
        db.commit()

    missing_product = api_client.post(
        f"/api/v1/reviews/{review_id}/resolve",
        headers=reviewer_headers,
        json={"resolution": "matched", "notes": "Missing target should fail"},
    )
    assert missing_product.status_code == 422

    resolved = api_client.post(
        f"/api/v1/reviews/{review_id}/resolve",
        headers=reviewer_headers,
        json={
            "resolution": "matched",
            "resolved_product_id": "DEMO-1002",
            "notes": "Brand, form factor, and model family verified.",
        },
    )

    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolution"] == "matched"
    assert body["resolved_product_id"] == "DEMO-1002"
    assert body["resolved_by"] == "qa-reviewer"
    with db_session_factory() as db:
        assert db.get(Offer, 2).canonical_product_id == "DEMO-1002"
        events = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "review.resolved",
                    AuditEvent.resource_id == review_id,
                )
            )
        )
        assert len(events) == 1
        assert events[0].actor == "qa-reviewer"

    repeated = api_client.post(
        f"/api/v1/reviews/{review_id}/resolve",
        headers=reviewer_headers,
        json={"resolution": "no_match", "notes": "Cannot rewrite a final decision"},
    )
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "review_already_resolved"


def test_review_cannot_resolve_to_unknown_product(api_client, reviewer_headers) -> None:
    response = api_client.post(
        "/api/v1/reviews/10000000-0000-4000-8000-000000000002/resolve",
        headers=reviewer_headers,
        json={"resolution": "matched", "resolved_product_id": "missing-product"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
