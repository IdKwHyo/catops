"""Pydantic request/response contracts exposed by the REST API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Role(StrEnum):
    reviewer = "reviewer"
    operator = "operator"
    admin = "admin"


class Principal(ApiModel):
    actor: str
    role: Role


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    database: Literal["ok", "error"]
    matcher: str
    timestamp: datetime


class OfferCreate(ApiModel):
    external_id: str = Field(min_length=1, max_length=128)
    seller: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=2, max_length=500)
    brand: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    mpn: str | None = Field(default=None, max_length=128)
    gtin: str | None = Field(default=None, max_length=32)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    source: str = Field(default="api", min_length=1, max_length=80)


class OfferOut(ApiModel):
    id: int
    external_id: str
    seller: str
    title: str
    brand: str | None
    description: str | None
    mpn: str | None
    gtin: str | None
    price: float | None
    currency: str
    source: str
    canonical_product_id: str | None
    created_at: datetime


class OfferListResponse(ApiModel):
    items: list[OfferOut]
    total: int
    limit: int
    offset: int


class MatchRequest(ApiModel):
    offer_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=2, max_length=500)
    brand: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    mpn: str | None = Field(default=None, max_length=128)
    gtin: str | None = Field(default=None, max_length=32)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    top_k: int = Field(default=5, ge=1, le=20)
    persist: bool = True

    @model_validator(mode="after")
    def _has_offer_or_title(self) -> MatchRequest:
        if self.offer_id is None and not self.title:
            raise ValueError("Either offer_id or title is required")
        return self


class MatchCandidate(ApiModel):
    product_id: str
    title: str
    brand: str | None
    score: float = Field(ge=0, le=1)
    evidence: list[str]


class MatchResponse(ApiModel):
    prediction_id: str | None = None
    offer_id: int | None
    decision: Literal["auto_match", "review", "no_match"]
    confidence: float = Field(ge=0, le=1)
    candidates: list[MatchCandidate]
    evidence: list[str]
    model_version: str
    latency_ms: float = Field(ge=0)
    thresholds: dict[str, float]


class ReviewCreate(ApiModel):
    offer_id: int = Field(ge=1)
    prediction_id: str | None = None
    candidate_product_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    reason_codes: list[str] = Field(default_factory=lambda: ["manual_review"])
    assigned_to: str | None = Field(default=None, max_length=160)


class ReviewResolve(ApiModel):
    resolution: Literal["matched", "no_match", "duplicate", "needs_more_information"]
    resolved_product_id: str | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _matched_requires_product(self) -> ReviewResolve:
        if self.resolution == "matched" and not self.resolved_product_id:
            raise ValueError("resolved_product_id is required for a matched resolution")
        return self


class ReviewOut(ApiModel):
    id: str
    offer_id: int
    offer_title: str
    candidate_product_id: str | None
    candidate_title: str | None
    confidence: float | None
    status: Literal["pending", "resolved"]
    priority: str
    reason_codes: list[str]
    assigned_to: str | None
    resolution: str | None
    resolved_product_id: str | None
    notes: str | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None


class ReviewListResponse(ApiModel):
    items: list[ReviewOut]
    total: int
    pending: int
    resolved: int
    limit: int
    offset: int


class MetricCounts(ApiModel):
    offers: int
    predictions: int
    pending_reviews: int
    open_incidents: int


class MetricsSummary(ApiModel):
    window: str
    dataset_label: str
    evidence_status: str
    evaluated_predictions: int
    model_version: str
    policy_label: str
    precision: float
    recall: float
    f1: float
    recall_at_5: float
    mrr: float
    ece: float
    p50_latency_ms: float
    p95_latency_ms: float
    auto_match_rate: float
    review_rate: float
    no_match_rate: float
    drift_status: Literal["stable", "warning", "critical"]
    counts: MetricCounts
    generated_at: datetime


class IncidentCreate(ApiModel):
    title: str = Field(min_length=3, max_length=300)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    metric_name: str = Field(min_length=1, max_length=120)
    observed_value: float | None = None
    expected_value: float | None = None
    description: str = Field(default="", max_length=5000)


class IncidentOut(ApiModel):
    id: str
    title: str
    severity: str
    status: str
    metric_name: str
    observed_value: float | None
    expected_value: float | None
    description: str
    detected_at: datetime
    resolved_at: datetime | None


class IncidentListResponse(ApiModel):
    items: list[IncidentOut]
    total: int


ActionType = Literal["rollback_model", "adjust_threshold", "create_review_batch"]


class ProposedAction(ApiModel):
    type: ActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=3, max_length=2000)


class InvestigationRun(ApiModel):
    incident_id: str
    proposed_action: ProposedAction | None = None


class InvestigationApproval(ApiModel):
    notes: str | None = Field(default=None, max_length=5000)


class InvestigationExecute(ApiModel):
    dry_run: bool = False


class InvestigationOut(ApiModel):
    id: str
    incident_id: str
    status: str
    diagnosis: str
    evidence: list[dict[str, Any]]
    proposed_action: dict[str, Any]
    execution_result: dict[str, Any] | None
    requested_by: str
    approved_by: str | None
    approval_notes: str | None
    executed_by: str | None
    created_at: datetime
    approved_at: datetime | None
    executed_at: datetime | None


class InvestigationListResponse(ApiModel):
    items: list[InvestigationOut]
    total: int


class AuditEventOut(ApiModel):
    sequence: int
    event_id: str
    occurred_at: datetime
    actor: str
    role: str
    action: str
    resource_type: str
    resource_id: str
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str


class AuditListResponse(ApiModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


class AuditVerification(ApiModel):
    valid: bool
    checked_events: int
    head_hash: str
    broken_sequence: int | None = None


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(ApiModel):
    error: ErrorBody
