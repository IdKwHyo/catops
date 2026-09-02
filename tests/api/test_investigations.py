"""Controlled investigation, approval, and execution state machine."""

from __future__ import annotations

from sqlalchemy import select

from apps.api.app.models import AuditEvent, Incident, OperationalSetting


def test_investigation_requires_admin_approval_before_bounded_execution(
    api_client,
    db_session_factory,
    operator_headers,
    admin_headers,
) -> None:
    incident_response = api_client.post(
        "/api/v1/incidents",
        headers=operator_headers,
        json={
            "title": "Confidence calibration drift",
            "severity": "high",
            "metric_name": "ece",
            "observed_value": 0.12,
            "expected_value": 0.05,
            "description": "ECE exceeded the production quality gate.",
        },
    )
    assert incident_response.status_code == 201
    incident_id = incident_response.json()["id"]

    proposed = api_client.post(
        "/api/v1/investigations/run",
        headers=operator_headers,
        json={
            "incident_id": incident_id,
            "proposed_action": {
                "type": "adjust_threshold",
                "parameters": {"auto_match": 0.9, "review": 0.6},
                "rationale": "Reduce automatic decisions while calibration is investigated.",
            },
        },
    )
    assert proposed.status_code == 201
    investigation_id = proposed.json()["id"]
    assert proposed.json()["status"] == "proposed"
    assert len(proposed.json()["evidence"]) >= 3

    before_approval = api_client.post(
        f"/api/v1/investigations/{investigation_id}/execute",
        headers=operator_headers,
        json={"dry_run": False},
    )
    assert before_approval.status_code == 409
    assert before_approval.json()["detail"]["code"] == "approval_required"

    operator_cannot_approve = api_client.post(
        f"/api/v1/investigations/{investigation_id}/approve",
        headers=operator_headers,
        json={"notes": "Self-approval must fail"},
    )
    assert operator_cannot_approve.status_code == 403

    approved = api_client.post(
        f"/api/v1/investigations/{investigation_id}/approve",
        headers=admin_headers,
        json={"notes": "Approved as a bounded and reversible policy change."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "qa-admin"

    executed = api_client.post(
        f"/api/v1/investigations/{investigation_id}/execute",
        headers=operator_headers,
        json={"dry_run": False},
    )
    assert executed.status_code == 200
    execution = executed.json()
    assert execution["status"] == "executed"
    assert execution["executed_by"] == "qa-operator"
    assert execution["execution_result"] == {
        "action": "adjust_threshold",
        "previous": {"auto_match": 0.85, "review": 0.55},
        "applied": {"auto_match": 0.9, "review": 0.6},
        "dry_run": False,
    }

    with db_session_factory() as db:
        assert db.get(OperationalSetting, "matching_thresholds").value == {
            "auto_match": 0.9,
            "review": 0.6,
        }
        assert db.get(Incident, incident_id).status == "mitigating"
        actions = list(
            db.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.resource_id == investigation_id)
                .order_by(AuditEvent.sequence)
            )
        )
        assert actions == [
            "investigation.proposed",
            "investigation.approved",
            "investigation.executed",
        ]


def test_dry_run_does_not_consume_approval_or_change_model(
    api_client, db_session_factory, operator_headers, admin_headers
) -> None:
    incident_id = "20000000-0000-4000-8000-000000000001"
    proposed = api_client.post(
        "/api/v1/investigations/run",
        headers=operator_headers,
        json={
            "incident_id": incident_id,
            "proposed_action": {
                "type": "rollback_model",
                "parameters": {"target_version": "catalogops-lexical-v0"},
                "rationale": "Exercise the rollback plan without mutating the registry.",
            },
        },
    )
    investigation_id = proposed.json()["id"]
    approved = api_client.post(
        f"/api/v1/investigations/{investigation_id}/approve",
        headers=admin_headers,
        json={},
    )
    assert approved.status_code == 200

    dry_run = api_client.post(
        f"/api/v1/investigations/{investigation_id}/execute",
        headers=operator_headers,
        json={"dry_run": True},
    )

    assert dry_run.status_code == 200
    assert dry_run.json()["status"] == "approved"
    assert dry_run.json()["execution_result"] is None
    with db_session_factory() as db:
        assert db.get(OperationalSetting, "current_model").value == {
            "version": "catalogops-lexical-v1"
        }


def test_invalid_threshold_action_is_rejected(api_client, operator_headers) -> None:
    response = api_client.post(
        "/api/v1/investigations/run",
        headers=operator_headers,
        json={
            "incident_id": "20000000-0000-4000-8000-000000000001",
            "proposed_action": {
                "type": "adjust_threshold",
                "parameters": {"auto_match": 0.5, "review": 0.7},
                "rationale": "Invalid ordering must never reach approval.",
            },
        },
    )

    assert response.status_code == 422


def test_unregistered_rollback_target_is_rejected(api_client, operator_headers) -> None:
    response = api_client.post(
        "/api/v1/investigations/run",
        headers=operator_headers,
        json={
            "incident_id": "20000000-0000-4000-8000-000000000001",
            "proposed_action": {
                "type": "rollback_model",
                "parameters": {"target_version": "attacker-controlled-model"},
                "rationale": "An arbitrary artifact name must not enter the approval flow.",
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Rollback target is not the registered previous stable model"
    )
