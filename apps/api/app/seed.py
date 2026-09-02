"""Deterministic records that make the local product demo useful immediately."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .audit import append_audit_event
from .config import Settings
from .models import (
    CanonicalProduct,
    Incident,
    MatchPrediction,
    Offer,
    OperationalSetting,
    Review,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


PRODUCTS = [
    {
        "id": "DEMO-1001",
        "title": "Apple AirPods Pro (2nd generation) with USB-C",
        "brand": "Apple",
        "mpn": "MTJV3",
        "gtin": "0195949052125",
        "category": "Headphones",
        "description": "Wireless noise-cancelling earbuds with MagSafe charging case.",
        "attributes": {"colour": "white", "connector": "USB-C"},
    },
    {
        "id": "DEMO-1002",
        "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
        "brand": "Sony",
        "mpn": "WH1000XM5/B",
        "gtin": "0027242923317",
        "category": "Headphones",
        "description": "Over-ear Bluetooth headphones in black.",
        "attributes": {"colour": "black", "form": "over-ear"},
    },
    {
        "id": "DEMO-1003",
        "title": "Nintendo Switch OLED Model White Joy-Con",
        "brand": "Nintendo",
        "mpn": "HEGSKAAAA",
        "gtin": "0045496883447",
        "category": "Game consoles",
        "description": "OLED console with white Joy-Con controllers and dock.",
        "attributes": {"colour": "white", "storage": "64GB"},
    },
    {
        "id": "DEMO-1004",
        "title": "Samsung Galaxy S24 5G 256GB Onyx Black",
        "brand": "Samsung",
        "mpn": "SM-S921BZKDEUB",
        "gtin": "8806095299786",
        "category": "Smartphones",
        "description": "Unlocked Android smartphone with 256GB storage.",
        "attributes": {"colour": "onyx black", "storage": "256GB"},
    },
    {
        "id": "DEMO-1005",
        "title": "Logitech MX Master 3S Wireless Performance Mouse Graphite",
        "brand": "Logitech",
        "mpn": "910-006556",
        "gtin": "0097855175052",
        "category": "Computer mice",
        "description": "Quiet-click ergonomic productivity mouse.",
        "attributes": {"colour": "graphite", "connectivity": "wireless"},
    },
]


OFFERS = [
    {
        "id": 1,
        "external_id": "shop-a-8841",
        "seller": "Bangkok Digital",
        "title": "Air Pods Pro Gen 2 USB C - MTJV3 (TH warranty)",
        "brand": "Apple",
        "description": "New sealed earbuds and charging case",
        "mpn": "MTJV3",
        "gtin": None,
        "price": 249.0,
        "currency": "USD",
        "source": "demo",
        "canonical_product_id": "DEMO-1001",
        "created_at": _dt("2026-08-29T09:00:00"),
    },
    {
        "id": 2,
        "external_id": "market-b-5502",
        "seller": "Audio Outlet",
        "title": "Sony XM5 ANC Bluetooth headset black",
        "brand": "Sony",
        "description": "Over ear headphones, imported stock",
        "mpn": None,
        "gtin": None,
        "price": 318.0,
        "currency": "USD",
        "source": "demo",
        "canonical_product_id": "DEMO-1002",
        "created_at": _dt("2026-08-29T10:00:00"),
    },
    {
        "id": 3,
        "external_id": "seller-c-1009",
        "seller": "Console World",
        "title": "N.Switch OLED white set 64G HEGSKAAAA",
        "brand": "Nintendo",
        "description": "Console, two controllers and dock",
        "mpn": "HEGSKAAAA",
        "gtin": None,
        "price": 329.0,
        "currency": "USD",
        "source": "demo",
        "canonical_product_id": "DEMO-1003",
        "created_at": _dt("2026-08-30T08:30:00"),
    },
    {
        "id": 4,
        "external_id": "phones-r-us-44",
        "seller": "Phones R Us",
        "title": "Galaxy S24 black 256 gig international version",
        "brand": "Samsung",
        "description": "5G smartphone, unlocked",
        "mpn": None,
        "gtin": None,
        "price": 699.0,
        "currency": "USD",
        "source": "demo",
        "canonical_product_id": "DEMO-1004",
        "created_at": _dt("2026-08-30T12:15:00"),
    },
    {
        "id": 5,
        "external_id": "office-pro-774",
        "seller": "Office Pro",
        "title": "MX3S silent wireless mouse graphite 910006556",
        "brand": "Logi",
        "description": "Ergonomic mouse for Windows and Mac",
        "mpn": "910-006556",
        "gtin": None,
        "price": 94.0,
        "currency": "USD",
        "source": "demo",
        "canonical_product_id": "DEMO-1005",
        "created_at": _dt("2026-08-31T07:45:00"),
    },
    {
        "id": 6,
        "external_id": "unknown-330",
        "seller": "Daily Deals",
        "title": "Premium wireless buds newest model free case",
        "brand": None,
        "description": "Generic Bluetooth earbuds",
        "mpn": None,
        "gtin": None,
        "price": 29.0,
        "currency": "USD",
        "source": "demo",
        "canonical_product_id": None,
        "created_at": _dt("2026-08-31T09:20:00"),
    },
]


def seed_demo_data(db: Session, settings: Settings) -> None:
    if db.get_bind().dialect.name == "postgresql":
        # Multiple uvicorn workers run lifespan concurrently. The transaction-scoped
        # lock makes the existence check and first seed commit deterministic.
        db.execute(text("SELECT pg_advisory_xact_lock(730190042)"))
    existing = db.scalar(select(func.count()).select_from(CanonicalProduct)) or 0
    if existing:
        _ensure_settings(db, settings)
        db.commit()
        return

    db.add_all([CanonicalProduct(**item) for item in PRODUCTS])
    db.add_all([Offer(**item) for item in OFFERS])
    db.flush()

    predictions = [
        MatchPrediction(
            id="00000000-0000-4000-8000-000000000001",
            offer_id=1,
            proposed_product_id="DEMO-1001",
            decision="auto_match",
            confidence=0.972,
            model_version=settings.model_version,
            latency_ms=28.4,
            candidates=[
                {
                    "product_id": "DEMO-1001",
                    "title": PRODUCTS[0]["title"],
                    "brand": "Apple",
                    "score": 0.972,
                    "evidence": ["exact MPN", "brand exact"],
                }
            ],
            evidence=["exact MPN", "brand exact"],
            request_snapshot={"title": OFFERS[0]["title"], "brand": "Apple"},
            created_at=_dt("2026-08-31T10:00:00"),
        ),
        MatchPrediction(
            id="00000000-0000-4000-8000-000000000002",
            offer_id=2,
            proposed_product_id="DEMO-1002",
            decision="review",
            confidence=0.781,
            model_version=settings.model_version,
            latency_ms=31.7,
            candidates=[
                {
                    "product_id": "DEMO-1002",
                    "title": PRODUCTS[1]["title"],
                    "brand": "Sony",
                    "score": 0.781,
                    "evidence": ["brand exact", "model token partial"],
                }
            ],
            evidence=["model token partial", "missing identifier"],
            request_snapshot={"title": OFFERS[1]["title"], "brand": "Sony"},
            created_at=_dt("2026-08-31T10:02:00"),
        ),
        MatchPrediction(
            id="00000000-0000-4000-8000-000000000003",
            offer_id=6,
            proposed_product_id=None,
            decision="no_match",
            confidence=0.224,
            model_version=settings.model_version,
            latency_ms=25.9,
            candidates=[],
            evidence=["generic title", "no identifier", "no brand"],
            request_snapshot={"title": OFFERS[5]["title"]},
            created_at=_dt("2026-08-31T10:04:00"),
        ),
    ]
    db.add_all(predictions)
    db.flush()

    db.add_all(
        [
            Review(
                id="10000000-0000-4000-8000-000000000001",
                offer_id=2,
                prediction_id=predictions[1].id,
                candidate_product_id="DEMO-1002",
                confidence=0.781,
                status="pending",
                priority="high",
                reason_codes=["missing_identifier", "abbreviated_model_name"],
                assigned_to=None,
                created_at=_dt("2026-08-31T10:03:00"),
            ),
            Review(
                id="10000000-0000-4000-8000-000000000002",
                offer_id=4,
                candidate_product_id="DEMO-1004",
                confidence=0.746,
                status="pending",
                priority="normal",
                reason_codes=["regional_variant", "missing_gtin"],
                assigned_to="demo-reviewer",
                created_at=_dt("2026-08-31T11:10:00"),
            ),
            Review(
                id="10000000-0000-4000-8000-000000000003",
                offer_id=3,
                candidate_product_id="DEMO-1003",
                confidence=0.892,
                status="resolved",
                priority="normal",
                reason_codes=["abbreviated_title"],
                assigned_to="demo-reviewer",
                resolution="matched",
                resolved_product_id="DEMO-1003",
                notes="MPN and bundle contents verified.",
                resolved_at=_dt("2026-08-31T12:00:00"),
                resolved_by="demo-reviewer",
                created_at=_dt("2026-08-31T09:30:00"),
            ),
        ]
    )

    incident = Incident(
        id="20000000-0000-4000-8000-000000000001",
        title="Unseen-entity recall dropped for audio accessories",
        severity="high",
        status="open",
        metric_name="unseen_entity_recall",
        observed_value=0.811,
        expected_value=0.9,
        description=(
            "The seven-day unseen-entity slice fell below its quality gate after a seller "
            "feed introduced abbreviated model names."
        ),
        detected_at=_dt("2026-08-31T13:00:00"),
    )
    db.add(incident)
    _ensure_settings(db, settings)
    db.flush()
    append_audit_event(
        db,
        actor="seed-system",
        role="system",
        action="demo_data.seeded",
        resource_type="dataset",
        resource_id="catalogops-demo-v1",
        payload={"products": len(PRODUCTS), "offers": len(OFFERS), "policy": "demo"},
    )
    append_audit_event(
        db,
        actor="monitor",
        role="system",
        action="incident.detected",
        resource_type="incident",
        resource_id=incident.id,
        payload={
            "metric_name": incident.metric_name,
            "observed_value": incident.observed_value,
            "expected_value": incident.expected_value,
        },
    )
    db.commit()


def _ensure_settings(db: Session, settings: Settings) -> None:
    defaults = {
        "current_model": {"version": settings.model_version},
        "matching_thresholds": {
            "auto_match": settings.auto_match_threshold,
            "review": settings.review_threshold,
        },
        "previous_stable_model": {"version": "catalogops-lexical-v0"},
    }
    for key, value in defaults.items():
        if db.get(OperationalSetting, key) is None:
            db.add(OperationalSetting(key=key, value=value, updated_by="seed-system"))
