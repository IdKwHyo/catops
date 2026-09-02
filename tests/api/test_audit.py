"""Hash-chain verification and storage-level audit immutability."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from apps.api.app import database
from apps.api.app.audit import GENESIS_HASH, append_audit_event, verify_audit_chain
from apps.api.app.database import Base
from apps.api.app.models import AuditEvent


def _append(db: Session, action: str) -> AuditEvent:
    return append_audit_event(
        db,
        actor="qa-operator",
        role="operator",
        action=action,
        resource_type="test",
        resource_id="resource-1",
        payload={"action": action},
    )


def test_audit_events_form_a_verifiable_hash_chain(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = _append(db, "first")
        second = _append(db, "second")
        db.commit()

        valid, checked, head_hash, broken_sequence = verify_audit_chain(db)

        assert valid is True
        assert checked == 2
        assert first.previous_hash == GENESIS_HASH
        assert second.previous_hash == first.event_hash
        assert head_hash == second.event_hash
        assert broken_sequence is None


def test_hash_chain_detects_payload_tampering(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'tamper.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = _append(db, "first")
        _append(db, "second")
        db.commit()
        db.execute(
            update(AuditEvent)
            .where(AuditEvent.sequence == first.sequence)
            .values(payload={"tampered": True})
        )
        db.commit()

        valid, checked, _head_hash, broken_sequence = verify_audit_chain(db)

        assert valid is False
        assert checked == 2
        assert broken_sequence == 1


def test_sqlite_init_installs_update_and_delete_guards(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'immutable.db'}")
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    with Session(engine) as db:
        event = _append(db, "protected")
        db.commit()

        with pytest.raises(DBAPIError) as update_error:
            db.execute(
                update(AuditEvent)
                .where(AuditEvent.sequence == event.sequence)
                .values(payload={"rewritten": True})
            )
        assert "immutable" in str(update_error.value).lower()
        db.rollback()

        with pytest.raises(DBAPIError) as delete_error:
            db.execute(delete(AuditEvent).where(AuditEvent.sequence == event.sequence))
        assert "immutable" in str(delete_error.value).lower()
        db.rollback()

        assert verify_audit_chain(db)[0] is True


def test_audit_verification_endpoint_is_role_protected(api_client, operator_headers) -> None:
    missing = api_client.get("/api/v1/audit/verify")
    assert missing.status_code == 401

    response = api_client.get("/api/v1/audit/verify", headers=operator_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["checked_events"] >= 2
    assert len(body["head_hash"]) == 64
    assert body["broken_sequence"] is None
