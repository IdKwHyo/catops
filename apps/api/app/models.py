"""Relational domain models for matching, review, incidents, and operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_string() -> str:
    return str(uuid4())


class CanonicalProduct(Base):
    __tablename__ = "canonical_products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    mpn: Mapped[str | None] = mapped_column(String(128), index=True)
    gtin: Mapped[str | None] = mapped_column(String(32), index=True)
    category: Mapped[str | None] = mapped_column(String(160), index=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    seller: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    mpn: Mapped[str | None] = mapped_column(String(128), index=True)
    gtin: Mapped[str | None] = mapped_column(String(32), index=True)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    source: Mapped[str] = mapped_column(String(80), default="api")
    canonical_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    canonical_product: Mapped[CanonicalProduct | None] = relationship()


class MatchPrediction(Base):
    __tablename__ = "match_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    offer_id: Mapped[int | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), index=True
    )
    proposed_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="SET NULL"), index=True
    )
    decision: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    candidates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    request_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    offer: Mapped[Offer | None] = relationship()
    proposed_product: Mapped[CanonicalProduct | None] = relationship()


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("match_predictions.id", ondelete="SET NULL"), index=True
    )
    candidate_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="SET NULL"), index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(160), index=True)
    resolution: Mapped[str | None] = mapped_column(String(40))
    resolved_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(160))

    offer: Mapped[Offer] = relationship(foreign_keys=[offer_id])
    prediction: Mapped[MatchPrediction | None] = relationship(foreign_keys=[prediction_id])
    candidate_product: Mapped[CanonicalProduct | None] = relationship(
        foreign_keys=[candidate_product_id]
    )
    resolved_product: Mapped[CanonicalProduct | None] = relationship(
        foreign_keys=[resolved_product_id]
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    metric_name: Mapped[str] = mapped_column(String(120), index=True)
    observed_value: Mapped[float | None] = mapped_column(Float)
    expected_value: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    proposed_action: Mapped[dict] = mapped_column(JSON, nullable=False)
    execution_result: Mapped[dict | None] = mapped_column(JSON)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(160))
    approval_notes: Mapped[str | None] = mapped_column(Text)
    executed_by: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    incident: Mapped[Incident] = relationship()


class OperationalSetting(Base):
    __tablename__ = "operational_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    updated_by: Mapped[str] = mapped_column(String(160), default="system")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_resource", "resource_type", "resource_id"),)

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, default=uuid_string)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


@event.listens_for(AuditEvent, "before_update", propagate=True)
def _reject_audit_update(_mapper, _connection, _target) -> None:  # type: ignore[no-untyped-def]
    raise RuntimeError("Audit events are immutable")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def _reject_audit_delete(_mapper, _connection, _target) -> None:  # type: ignore[no-untyped-def]
    raise RuntimeError("Audit events are immutable")
