"""Append-only, hash-chained audit event helpers."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AuditEvent, uuid_string

GENESIS_HASH = "0" * 64
_append_lock = threading.Lock()


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _event_document(
    *,
    sequence: int,
    event_id: str,
    occurred_at: datetime,
    actor: str,
    role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any],
    previous_hash: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "event_id": event_id,
        "occurred_at": _utc_iso(occurred_at),
        "actor": actor,
        "role": role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload,
        "previous_hash": previous_hash,
    }


def _hash_document(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def append_audit_event(
    db: Session,
    *,
    actor: str,
    role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event in the caller's transaction.

    The process lock serializes local SQLite writers. PostgreSQL connections also
    acquire a transaction-scoped advisory lock before reading the chain head, so
    separate API workers cannot append from the same predecessor.
    """

    with _append_lock:
        if db.get_bind().dialect.name == "postgresql":
            # Serialize chain-head reads across API worker processes until the
            # caller commits or rolls back the surrounding transaction.
            db.execute(text("SELECT pg_advisory_xact_lock(730190041)"))
        previous = db.scalars(
            select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1).with_for_update()
        ).first()
        sequence = 1 if previous is None else previous.sequence + 1
        previous_hash = GENESIS_HASH if previous is None else previous.event_hash
        event_id = uuid_string()
        occurred_at = datetime.now(UTC)
        safe_payload = payload or {}
        document = _event_document(
            sequence=sequence,
            event_id=event_id,
            occurred_at=occurred_at,
            actor=actor,
            role=role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=safe_payload,
            previous_hash=previous_hash,
        )
        event = AuditEvent(
            sequence=sequence,
            event_id=event_id,
            occurred_at=occurred_at,
            actor=actor,
            role=role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=safe_payload,
            previous_hash=previous_hash,
            event_hash=_hash_document(document),
        )
        db.add(event)
        db.flush()
        return event


def verify_audit_chain(db: Session) -> tuple[bool, int, str, int | None]:
    events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.sequence.asc())))
    previous_hash = GENESIS_HASH
    for expected_sequence, event in enumerate(events, start=1):
        if event.sequence != expected_sequence or event.previous_hash != previous_hash:
            return False, len(events), previous_hash, event.sequence
        document = _event_document(
            sequence=event.sequence,
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            actor=event.actor,
            role=event.role,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            payload=event.payload,
            previous_hash=event.previous_hash,
        )
        calculated_hash = _hash_document(document)
        if calculated_hash != event.event_hash:
            return False, len(events), previous_hash, event.sequence
        previous_hash = event.event_hash
    return True, len(events), previous_hash, None
