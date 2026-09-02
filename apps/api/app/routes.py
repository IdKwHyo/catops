"""Versioned CatalogOps REST endpoints."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .audit import append_audit_event, verify_audit_chain
from .config import Settings, get_settings
from .database import get_db
from .matcher_adapter import MatcherAdapter
from .models import (
    AuditEvent,
    CanonicalProduct,
    Incident,
    Investigation,
    MatchPrediction,
    Offer,
    OperationalSetting,
    Review,
    utcnow,
)
from .schemas import (
    AuditEventOut,
    AuditListResponse,
    AuditVerification,
    HealthResponse,
    IncidentCreate,
    IncidentListResponse,
    IncidentOut,
    InvestigationApproval,
    InvestigationExecute,
    InvestigationListResponse,
    InvestigationOut,
    InvestigationRun,
    MatchCandidate,
    MatchRequest,
    MatchResponse,
    MetricCounts,
    MetricsSummary,
    OfferCreate,
    OfferListResponse,
    OfferOut,
    ReviewCreate,
    ReviewListResponse,
    ReviewOut,
    ReviewResolve,
)
from .security import AdminPrincipal, OperatorPrincipal, ReviewerPrincipal

router = APIRouter()
settings: Settings = get_settings()
matcher = MatcherAdapter(settings)


def _not_found(resource: str, resource_id: object) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message": f"{resource} {resource_id} was not found"},
    )


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


def _setting(db: Session, key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    item = db.get(OperationalSetting, key)
    return dict(item.value) if item else fallback


def _policy(db: Session) -> tuple[float, float]:
    policy = _setting(
        db,
        "matching_thresholds",
        {"auto_match": settings.auto_match_threshold, "review": settings.review_threshold},
    )
    return float(policy["auto_match"]), float(policy["review"])


def _model_version(db: Session) -> str:
    return str(_setting(db, "current_model", {"version": settings.model_version})["version"])


def _catalog_mapping(product: CanonicalProduct) -> dict[str, Any]:
    return {
        "id": product.id,
        "title": product.title,
        "brand": product.brand,
        "description": product.description,
        "mpn": product.mpn,
        "gtin": product.gtin,
        "category": product.category,
        "attributes": product.attributes,
    }


def _review_out(review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        offer_id=review.offer_id,
        offer_title=review.offer.title,
        candidate_product_id=review.candidate_product_id,
        candidate_title=(review.candidate_product.title if review.candidate_product else None),
        confidence=review.confidence,
        status=cast(Literal["pending", "resolved"], review.status),
        priority=review.priority,
        reason_codes=review.reason_codes,
        assigned_to=review.assigned_to,
        resolution=review.resolution,
        resolved_product_id=review.resolved_product_id,
        notes=review.notes,
        created_at=review.created_at,
        resolved_at=review.resolved_at,
        resolved_by=review.resolved_by,
    )


def _review_query() -> Select[tuple[Review]]:
    return select(Review).options(
        selectinload(Review.offer),
        selectinload(Review.candidate_product),
        selectinload(Review.resolved_product),
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    database_status: Literal["ok", "error"] = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"
    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        service=settings.app_name,
        version="1.0.0",
        environment=settings.environment,
        database=database_status,
        matcher=matcher.status,
        timestamp=datetime.now(UTC),
    )


@router.get("/api/v1/offers", response_model=OfferListResponse, tags=["offers"])
def list_offers(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = Query(default=None, max_length=200),
    seller: str | None = Query(default=None, max_length=160),
    matched: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OfferListResponse:
    filters = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Offer.title.ilike(pattern), Offer.external_id.ilike(pattern)))
    if seller:
        filters.append(Offer.seller == seller)
    if matched is True:
        filters.append(Offer.canonical_product_id.is_not(None))
    elif matched is False:
        filters.append(Offer.canonical_product_id.is_(None))
    total = db.scalar(select(func.count()).select_from(Offer).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Offer)
            .where(*filters)
            .order_by(Offer.created_at.desc(), Offer.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return OfferListResponse(
        items=[OfferOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/v1/offers",
    response_model=OfferOut,
    status_code=status.HTTP_201_CREATED,
    tags=["offers"],
)
def create_offer(
    body: OfferCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: OperatorPrincipal,
) -> Offer:
    values = body.model_dump()
    values["currency"] = body.currency.upper()
    offer = Offer(**values)
    db.add(offer)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict("duplicate_external_id", "external_id already exists") from exc
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="offer.created",
        resource_type="offer",
        resource_id=str(offer.id),
        payload={"external_id": offer.external_id, "seller": offer.seller},
    )
    db.commit()
    db.refresh(offer)
    return offer


@router.post("/api/v1/matches/predict", response_model=MatchResponse, tags=["matching"])
def predict_match(
    body: MatchRequest,
    db: Annotated[Session, Depends(get_db)],
    x_actor: Annotated[str | None, Header(alias="X-Actor")] = None,
) -> MatchResponse:
    linked_offer: Offer | None = None
    if body.offer_id is not None:
        linked_offer = db.get(Offer, body.offer_id)
        if linked_offer is None:
            raise _not_found("offer", body.offer_id)

    listing = {
        "offer_id": linked_offer.id if linked_offer else None,
        "title": body.title or (linked_offer.title if linked_offer else ""),
        "brand": body.brand
        if body.brand is not None
        else (linked_offer.brand if linked_offer else None),
        "description": (
            body.description
            if body.description is not None
            else (linked_offer.description if linked_offer else None)
        ),
        "mpn": body.mpn if body.mpn is not None else (linked_offer.mpn if linked_offer else None),
        "gtin": body.gtin
        if body.gtin is not None
        else (linked_offer.gtin if linked_offer else None),
        "price": body.price
        if body.price is not None
        else (linked_offer.price if linked_offer else None),
        "currency": body.currency or (linked_offer.currency if linked_offer else "USD"),
    }
    products = list(db.scalars(select(CanonicalProduct).order_by(CanonicalProduct.id)))
    result = matcher.predict(
        listing,
        [_catalog_mapping(product) for product in products],
        top_k=body.top_k,
    )
    auto_threshold, review_threshold = _policy(db)
    if result.confidence >= auto_threshold:
        policy_decision: Literal["auto_match", "review", "no_match"] = "auto_match"
    elif result.confidence >= review_threshold:
        policy_decision = "review"
    else:
        policy_decision = "no_match"
    # Threshold changes may make a result more conservative, but they must never
    # bypass matcher safety rules such as the minimum top-two ambiguity margin.
    if result.decision == "no_match":
        decision: Literal["auto_match", "review", "no_match"] = "no_match"
    elif result.decision == "review" and policy_decision == "auto_match":
        decision = "review"
    else:
        decision = policy_decision
    candidates = [MatchCandidate(**candidate) for candidate in result.candidates]
    proposed_product_id = (
        candidates[0].product_id if candidates and decision != "no_match" else None
    )
    prediction: MatchPrediction | None = None
    if body.persist:
        prediction = MatchPrediction(
            offer_id=linked_offer.id if linked_offer else None,
            proposed_product_id=proposed_product_id,
            decision=decision,
            confidence=result.confidence,
            model_version=result.model_version,
            latency_ms=result.latency_ms,
            candidates=[candidate.model_dump() for candidate in candidates],
            evidence=result.evidence,
            request_snapshot=listing,
        )
        db.add(prediction)
        db.flush()
        if decision == "review" and linked_offer is not None:
            review = Review(
                offer_id=linked_offer.id,
                prediction_id=prediction.id,
                candidate_product_id=proposed_product_id,
                confidence=result.confidence,
                priority="normal",
                reason_codes=["medium_confidence", "policy_routed"],
            )
            db.add(review)
            db.flush()
            append_audit_event(
                db,
                actor="match-router",
                role="system",
                action="review.routed",
                resource_type="review",
                resource_id=review.id,
                payload={"prediction_id": prediction.id, "confidence": result.confidence},
            )
        append_audit_event(
            db,
            actor=(x_actor or "api-client"),
            role="inference-client",
            action="match.predicted",
            resource_type="prediction",
            resource_id=prediction.id,
            payload={
                "decision": decision,
                "confidence": result.confidence,
                "offer_id": linked_offer.id if linked_offer else None,
                "model_version": prediction.model_version,
            },
        )
        db.commit()
    return MatchResponse(
        prediction_id=prediction.id if prediction else None,
        offer_id=linked_offer.id if linked_offer else None,
        decision=decision,
        confidence=result.confidence,
        candidates=candidates,
        evidence=result.evidence,
        model_version=result.model_version,
        latency_ms=result.latency_ms,
        thresholds={"auto_match": auto_threshold, "review": review_threshold},
    )


@router.get("/api/v1/reviews", response_model=ReviewListResponse, tags=["reviews"])
def list_reviews(
    db: Annotated[Session, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|resolved)$"),
    priority: str | None = Query(default=None, pattern="^(low|normal|high|critical)$"),
    assigned_to: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReviewListResponse:
    filters = []
    if status_filter:
        filters.append(Review.status == status_filter)
    if priority:
        filters.append(Review.priority == priority)
    if assigned_to:
        filters.append(Review.assigned_to == assigned_to)
    total = db.scalar(select(func.count()).select_from(Review).where(*filters)) or 0
    pending = (
        db.scalar(select(func.count()).select_from(Review).where(Review.status == "pending")) or 0
    )
    resolved = (
        db.scalar(select(func.count()).select_from(Review).where(Review.status == "resolved")) or 0
    )
    reviews = list(
        db.scalars(
            _review_query()
            .where(*filters)
            .order_by(
                Review.status.asc(),
                Review.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return ReviewListResponse(
        items=[_review_out(item) for item in reviews],
        total=total,
        pending=pending,
        resolved=resolved,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/v1/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    tags=["reviews"],
)
def create_review(
    body: ReviewCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: ReviewerPrincipal,
) -> ReviewOut:
    offer = db.get(Offer, body.offer_id)
    if offer is None:
        raise _not_found("offer", body.offer_id)
    prediction = db.get(MatchPrediction, body.prediction_id) if body.prediction_id else None
    if body.prediction_id and prediction is None:
        raise _not_found("prediction", body.prediction_id)
    if prediction and prediction.offer_id not in (None, body.offer_id):
        raise _conflict("prediction_offer_mismatch", "prediction belongs to another offer")
    candidate_id = body.candidate_product_id or (
        prediction.proposed_product_id if prediction else None
    )
    if candidate_id and db.get(CanonicalProduct, candidate_id) is None:
        raise _not_found("canonical product", candidate_id)
    review = Review(
        offer_id=body.offer_id,
        prediction_id=body.prediction_id,
        candidate_product_id=candidate_id,
        confidence=(
            body.confidence
            if body.confidence is not None
            else (prediction.confidence if prediction else None)
        ),
        priority=body.priority,
        reason_codes=body.reason_codes,
        assigned_to=body.assigned_to,
    )
    db.add(review)
    db.flush()
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="review.created",
        resource_type="review",
        resource_id=review.id,
        payload={"offer_id": review.offer_id, "reason_codes": review.reason_codes},
    )
    db.commit()
    stored = db.scalar(_review_query().where(Review.id == review.id))
    assert stored is not None
    return _review_out(stored)


@router.post(
    "/api/v1/reviews/{review_id}/resolve",
    response_model=ReviewOut,
    tags=["reviews"],
)
def resolve_review(
    review_id: str,
    body: ReviewResolve,
    db: Annotated[Session, Depends(get_db)],
    principal: ReviewerPrincipal,
) -> ReviewOut:
    review = db.scalar(_review_query().where(Review.id == review_id))
    if review is None:
        raise _not_found("review", review_id)
    if review.status == "resolved":
        raise _conflict(
            "review_already_resolved", "Review decisions are final; create a new review"
        )
    if body.resolved_product_id and db.get(CanonicalProduct, body.resolved_product_id) is None:
        raise _not_found("canonical product", body.resolved_product_id)
    review.status = "resolved"
    review.resolution = body.resolution
    review.resolved_product_id = body.resolved_product_id
    review.notes = body.notes
    review.resolved_at = utcnow()
    review.resolved_by = principal.actor
    if body.resolution == "matched" and body.resolved_product_id:
        review.offer.canonical_product_id = body.resolved_product_id
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="review.resolved",
        resource_type="review",
        resource_id=review.id,
        payload={
            "resolution": body.resolution,
            "resolved_product_id": body.resolved_product_id,
            "previous_candidate_id": review.candidate_product_id,
        },
    )
    db.commit()
    stored = db.scalar(_review_query().where(Review.id == review.id))
    assert stored is not None
    return _review_out(stored)


@router.get("/api/v1/metrics/summary", response_model=MetricsSummary, tags=["metrics"])
def metrics_summary(db: Annotated[Session, Depends(get_db)]) -> MetricsSummary:
    auto_threshold, review_threshold = _policy(db)
    prediction_count = db.scalar(select(func.count()).select_from(MatchPrediction)) or 0
    decision_counts: dict[str, int] = {
        str(decision): int(count)
        for decision, count in db.execute(
            select(MatchPrediction.decision, func.count()).group_by(MatchPrediction.decision)
        ).all()
    }
    latencies = sorted(float(value) for value in db.scalars(select(MatchPrediction.latency_ms)))
    evaluated_rows = list(
        db.execute(
            select(MatchPrediction, Offer)
            .join(Offer, MatchPrediction.offer_id == Offer.id)
            .order_by(MatchPrediction.created_at, MatchPrediction.id)
        ).all()
    )

    true_positives = 0
    false_positives = 0
    false_negatives = 0
    ranking_hits = 0
    reciprocal_rank_total = 0.0
    calibration_errors: list[float] = []
    known_entity_rows = 0
    for prediction, offer in evaluated_rows:
        truth = offer.canonical_product_id
        proposed = prediction.proposed_product_id
        if truth is not None:
            known_entity_rows += 1
            if proposed == truth:
                true_positives += 1
            else:
                false_negatives += 1
                if proposed is not None:
                    false_positives += 1
            candidate_ids = [str(item.get("product_id")) for item in prediction.candidates]
            if truth in candidate_ids[:5]:
                ranking_hits += 1
                reciprocal_rank_total += 1.0 / (candidate_ids.index(truth) + 1)
        elif proposed is not None:
            false_positives += 1

        top_candidate_id = (
            str(prediction.candidates[0].get("product_id")) if prediction.candidates else None
        )
        top_is_correct = bool(truth is not None and top_candidate_id == truth)
        calibration_errors.append(abs(prediction.confidence - float(top_is_correct)))

    precision_denominator = true_positives + false_positives
    precision = true_positives / precision_denominator if precision_denominator else 0.0
    recall_denominator = true_positives + false_negatives
    recall = true_positives / recall_denominator if recall_denominator else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    recall_at_5 = ranking_hits / known_entity_rows if known_entity_rows else 0.0
    mrr = reciprocal_rank_total / known_entity_rows if known_entity_rows else 0.0
    calibration_proxy = (
        sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0
    )

    def percentile(values: list[float], percentage: float, default: float) -> float:
        if not values:
            return default
        index = min(len(values) - 1, max(0, math.ceil(percentage * len(values)) - 1))
        return round(values[index], 3)

    denominator = max(1, prediction_count)
    open_incidents = (
        db.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.status.in_(["open", "investigating", "mitigating"]))
        )
        or 0
    )
    highest_severity = db.scalars(
        select(Incident.severity).where(
            Incident.status.in_(["open", "investigating", "mitigating"])
        )
    ).all()
    drift_status: Literal["stable", "warning", "critical"] = (
        "critical"
        if "critical" in highest_severity
        else "warning"
        if any(level in {"high", "medium"} for level in highest_severity)
        else "stable"
    )
    return MetricsSummary(
        window="current persisted demo predictions",
        dataset_label="seeded six-offer smoke fixture; not the WDC benchmark",
        evidence_status="demo_only_not_published_benchmark",
        evaluated_predictions=len(evaluated_rows),
        model_version=matcher.active_model_version,
        policy_label=(
            f"active demo policy: auto >= {auto_threshold:.2f}, "
            f"review {review_threshold:.2f}-{auto_threshold:.2f}, "
            f"no-match < {review_threshold:.2f}"
        ),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        recall_at_5=round(recall_at_5, 4),
        mrr=round(mrr, 4),
        ece=round(calibration_proxy, 4),
        p50_latency_ms=percentile(latencies, 0.50, 29.1),
        p95_latency_ms=percentile(latencies, 0.95, 63.8),
        auto_match_rate=round(decision_counts.get("auto_match", 0) / denominator, 4),
        review_rate=round(decision_counts.get("review", 0) / denominator, 4),
        no_match_rate=round(decision_counts.get("no_match", 0) / denominator, 4),
        drift_status=drift_status,
        counts=MetricCounts(
            offers=db.scalar(select(func.count()).select_from(Offer)) or 0,
            predictions=prediction_count,
            pending_reviews=db.scalar(
                select(func.count()).select_from(Review).where(Review.status == "pending")
            )
            or 0,
            open_incidents=open_incidents,
        ),
        generated_at=datetime.now(UTC),
    )


@router.get("/api/v1/incidents", response_model=IncidentListResponse, tags=["operations"])
def list_incidents(
    db: Annotated[Session, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
) -> IncidentListResponse:
    filters = [Incident.status == status_filter] if status_filter else []
    items = list(
        db.scalars(
            select(Incident).where(*filters).order_by(Incident.detected_at.desc(), Incident.id)
        )
    )
    return IncidentListResponse(
        items=[IncidentOut.model_validate(item) for item in items], total=len(items)
    )


@router.post(
    "/api/v1/incidents",
    response_model=IncidentOut,
    status_code=status.HTTP_201_CREATED,
    tags=["operations"],
)
def create_incident(
    body: IncidentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: OperatorPrincipal,
) -> Incident:
    incident = Incident(**body.model_dump())
    db.add(incident)
    db.flush()
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="incident.created",
        resource_type="incident",
        resource_id=incident.id,
        payload={"severity": incident.severity, "metric_name": incident.metric_name},
    )
    db.commit()
    return incident


def _default_investigation_action(incident: Incident, db: Session) -> dict[str, Any]:
    previous_model = _setting(db, "previous_stable_model", {"version": "catalogops-lexical-v0"})[
        "version"
    ]
    if "latency" in incident.metric_name.lower():
        return {
            "type": "rollback_model",
            "parameters": {"target_version": previous_model},
            "rationale": "Latency regression is consistent with the current deployment; rollback is reversible.",
        }
    return {
        "type": "create_review_batch",
        "parameters": {"limit": 25, "metric_slice": incident.metric_name},
        "rationale": "A bounded review batch gathers labels without changing production decisions.",
    }


def _validate_action(action: dict[str, Any], db: Session | None = None) -> None:
    action_type = action.get("type")
    parameters = action.get("parameters") or {}
    if action_type not in {"rollback_model", "adjust_threshold", "create_review_batch"}:
        raise HTTPException(status_code=422, detail="Unsupported investigation action")
    if action_type == "rollback_model":
        target = parameters.get("target_version")
        if not isinstance(target, str) or not target.strip() or len(target) > 160:
            raise HTTPException(status_code=422, detail="A valid target_version is required")
        if db is not None:
            previous_model = _setting(
                db,
                "previous_stable_model",
                {"version": "catalogops-lexical-v0"},
            )["version"]
            if target != previous_model:
                raise HTTPException(
                    status_code=422,
                    detail="Rollback target is not the registered previous stable model",
                )
    elif action_type == "adjust_threshold":
        try:
            auto = float(parameters["auto_match"])
            review = float(parameters["review"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="Both numeric thresholds are required"
            ) from exc
        if not 0 < review < auto <= 1:
            raise HTTPException(
                status_code=422, detail="Thresholds must satisfy 0 < review < auto_match <= 1"
            )
    else:
        limit = parameters.get("limit", 25)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise HTTPException(
                status_code=422, detail="Review batch limit must be between 1 and 100"
            )


@router.get(
    "/api/v1/investigations",
    response_model=InvestigationListResponse,
    tags=["operations"],
)
def list_investigations(
    db: Annotated[Session, Depends(get_db)],
    incident_id: str | None = None,
) -> InvestigationListResponse:
    filters = [Investigation.incident_id == incident_id] if incident_id else []
    items = list(
        db.scalars(
            select(Investigation)
            .where(*filters)
            .order_by(Investigation.created_at.desc(), Investigation.id)
        )
    )
    return InvestigationListResponse(
        items=[InvestigationOut.model_validate(item) for item in items], total=len(items)
    )


@router.post(
    "/api/v1/investigations/run",
    response_model=InvestigationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["operations"],
)
def run_investigation(
    body: InvestigationRun,
    db: Annotated[Session, Depends(get_db)],
    principal: OperatorPrincipal,
) -> Investigation:
    incident = db.get(Incident, body.incident_id)
    if incident is None:
        raise _not_found("incident", body.incident_id)
    if incident.status == "resolved":
        raise _conflict("incident_resolved", "Cannot investigate a resolved incident")
    action = (
        body.proposed_action.model_dump()
        if body.proposed_action is not None
        else _default_investigation_action(incident, db)
    )
    _validate_action(action, db)
    delta = (
        round(incident.observed_value - incident.expected_value, 6)
        if incident.observed_value is not None and incident.expected_value is not None
        else None
    )
    current_model = _model_version(db)
    pending_review_count = (
        db.scalar(select(func.count()).select_from(Review).where(Review.status == "pending")) or 0
    )
    evidence = [
        {
            "source": "incident_metric",
            "metric": incident.metric_name,
            "observed": incident.observed_value,
            "expected": incident.expected_value,
            "delta": delta,
        },
        {"source": "model_registry", "current_model": current_model},
        {
            "source": "review_queue",
            "pending_records": pending_review_count,
            "interpretation": "Existing labels can be compared before a model-changing action.",
        },
        {
            "source": "model_card",
            "known_limitation": "Abbreviations and unseen regional variants reduce recall.",
        },
    ]
    diagnosis = (
        f"{incident.metric_name} is {abs(delta):.3f} below its expected value. "
        if delta is not None and delta < 0
        else f"{incident.metric_name} triggered an operational quality alert. "
    )
    diagnosis += (
        "Affected records should be labeled through a bounded review workflow before "
        "changing the active model or decision policy."
    )
    investigation = Investigation(
        incident_id=incident.id,
        status="proposed",
        diagnosis=diagnosis,
        evidence=evidence,
        proposed_action=action,
        requested_by=principal.actor,
    )
    db.add(investigation)
    incident.status = "investigating"
    db.flush()
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="investigation.proposed",
        resource_type="investigation",
        resource_id=investigation.id,
        payload={"incident_id": incident.id, "proposed_action": action},
    )
    db.commit()
    return investigation


@router.post(
    "/api/v1/investigations/{investigation_id}/approve",
    response_model=InvestigationOut,
    tags=["operations"],
)
def approve_investigation(
    investigation_id: str,
    body: InvestigationApproval,
    db: Annotated[Session, Depends(get_db)],
    principal: AdminPrincipal,
) -> Investigation:
    investigation = db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("investigation", investigation_id)
    if investigation.status != "proposed":
        raise _conflict(
            "invalid_investigation_state",
            f"Only proposed investigations can be approved (current: {investigation.status})",
        )
    _validate_action(investigation.proposed_action, db)
    investigation.status = "approved"
    investigation.approved_by = principal.actor
    investigation.approval_notes = body.notes
    investigation.approved_at = utcnow()
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="investigation.approved",
        resource_type="investigation",
        resource_id=investigation.id,
        payload={"action": investigation.proposed_action, "notes": body.notes},
    )
    db.commit()
    return investigation


@router.post(
    "/api/v1/investigations/{investigation_id}/reject",
    response_model=InvestigationOut,
    tags=["operations"],
)
def reject_investigation(
    investigation_id: str,
    body: InvestigationApproval,
    db: Annotated[Session, Depends(get_db)],
    principal: AdminPrincipal,
) -> Investigation:
    investigation = db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("investigation", investigation_id)
    if investigation.status != "proposed":
        raise _conflict(
            "invalid_investigation_state", "Only proposed investigations can be rejected"
        )
    investigation.status = "rejected"
    investigation.approved_by = principal.actor
    investigation.approval_notes = body.notes
    investigation.approved_at = utcnow()
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action="investigation.rejected",
        resource_type="investigation",
        resource_id=investigation.id,
        payload={"notes": body.notes},
    )
    db.commit()
    return investigation


def _execute_action(
    db: Session, investigation: Investigation, actor: str, *, dry_run: bool
) -> dict[str, Any]:
    action = investigation.proposed_action
    _validate_action(action, db)
    action_type = action["type"]
    parameters = action.get("parameters") or {}
    if action_type == "rollback_model":
        setting = db.get(OperationalSetting, "current_model")
        old_version = (setting.value if setting else {"version": settings.model_version})["version"]
        target = parameters["target_version"]
        result = {"action": action_type, "from_version": old_version, "to_version": target}
        if not dry_run:
            if setting is None:
                setting = OperationalSetting(key="current_model", value={"version": target})
                db.add(setting)
            else:
                setting.value = {"version": target}
            setting.updated_by = actor
    elif action_type == "adjust_threshold":
        current_auto, current_review = _policy(db)
        proposed = {
            "auto_match": float(parameters["auto_match"]),
            "review": float(parameters["review"]),
        }
        result = {
            "action": action_type,
            "previous": {"auto_match": current_auto, "review": current_review},
            "applied": proposed,
        }
        if not dry_run:
            setting = db.get(OperationalSetting, "matching_thresholds")
            if setting is None:
                setting = OperationalSetting(key="matching_thresholds", value=proposed)
                db.add(setting)
            else:
                setting.value = proposed
            setting.updated_by = actor
    else:
        limit = int(parameters.get("limit", 25))
        reviewed_offer_ids = select(Review.offer_id).where(Review.status == "pending")
        candidates = list(
            db.scalars(
                select(MatchPrediction)
                .where(
                    MatchPrediction.offer_id.is_not(None),
                    MatchPrediction.proposed_product_id.is_not(None),
                    MatchPrediction.offer_id.not_in(reviewed_offer_ids),
                )
                .order_by(MatchPrediction.confidence.asc(), MatchPrediction.created_at.desc())
                .limit(limit)
            )
        )
        result = {
            "action": action_type,
            "selected_records": len(candidates),
            "offer_ids": [item.offer_id for item in candidates],
            "limit": limit,
        }
        if not dry_run:
            for prediction in candidates:
                db.add(
                    Review(
                        offer_id=prediction.offer_id,
                        prediction_id=prediction.id,
                        candidate_product_id=prediction.proposed_product_id,
                        confidence=prediction.confidence,
                        priority="high",
                        reason_codes=[
                            "agent_investigation_batch",
                            parameters.get("metric_slice", "quality_alert"),
                        ],
                    )
                )
    result["dry_run"] = dry_run
    return result


@router.post(
    "/api/v1/investigations/{investigation_id}/execute",
    response_model=InvestigationOut,
    tags=["operations"],
)
def execute_investigation(
    investigation_id: str,
    body: InvestigationExecute,
    db: Annotated[Session, Depends(get_db)],
    principal: OperatorPrincipal,
) -> Investigation:
    investigation = db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("investigation", investigation_id)
    if investigation.status != "approved":
        raise _conflict(
            "approval_required",
            f"Execution requires approved status (current: {investigation.status})",
        )
    result = _execute_action(db, investigation, principal.actor, dry_run=body.dry_run)
    append_audit_event(
        db,
        actor=principal.actor,
        role=principal.role.value,
        action=("investigation.dry_run" if body.dry_run else "investigation.executed"),
        resource_type="investigation",
        resource_id=investigation.id,
        payload={"approved_by": investigation.approved_by, "result": result},
    )
    if not body.dry_run:
        investigation.status = "executed"
        investigation.execution_result = result
        investigation.executed_by = principal.actor
        investigation.executed_at = utcnow()
        investigation.incident.status = "mitigating"
    db.commit()
    return investigation


@router.get(
    "/api/v1/audit",
    response_model=AuditListResponse,
    tags=["audit"],
)
def list_audit_events(
    db: Annotated[Session, Depends(get_db)],
    principal: OperatorPrincipal,
    resource_type: str | None = Query(default=None, max_length=80),
    resource_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditListResponse:
    del principal
    filters = []
    if resource_type:
        filters.append(AuditEvent.resource_type == resource_type)
    if resource_id:
        filters.append(AuditEvent.resource_id == resource_id)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    items = list(
        db.scalars(
            select(AuditEvent)
            .where(*filters)
            .order_by(AuditEvent.sequence.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return AuditListResponse(
        items=[AuditEventOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/api/v1/audit/verify",
    response_model=AuditVerification,
    tags=["audit"],
)
def verify_audit(
    db: Annotated[Session, Depends(get_db)],
    principal: OperatorPrincipal,
) -> AuditVerification:
    del principal
    valid, checked, head_hash, broken_sequence = verify_audit_chain(db)
    return AuditVerification(
        valid=valid,
        checked_events=checked,
        head_hash=head_hash,
        broken_sequence=broken_sequence,
    )
