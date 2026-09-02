"""Dependency-free data contracts shared by the API, pipelines, and evaluator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_present(row: Mapping[str, Any], *keys: str) -> Any:
    """Return the first non-null/non-empty value while preserving numeric zero."""

    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _identifiers(row: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    embedded = row.get("identifiers")
    if isinstance(embedded, Mapping):
        result.update(
            {
                _clean_string(key).casefold(): _clean_string(value)
                for key, value in embedded.items()
                if _clean_string(value)
            }
        )
    for key in (
        "gtin",
        "gtin8",
        "gtin12",
        "gtin13",
        "gtin14",
        "ean",
        "upc",
        "mpn",
        "model",
        "model_number",
        "sku",
        "asin",
    ):
        value = _clean_string(row.get(key))
        if value:
            result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class CanonicalProduct:
    """A trusted entity in the canonical product catalog."""

    product_id: str
    title: str
    brand: str = ""
    description: str = ""
    identifiers: dict[str, str] = field(default_factory=dict)
    category: str = ""
    price: float | None = None
    currency: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> CanonicalProduct:
        product_id = _clean_string(
            _first_present(row, "product_id", "canonical_product_id", "cluster_id", "id")
        )
        if not product_id:
            raise ValueError("canonical product is missing product_id/id")
        title = _clean_string(_first_present(row, "title", "name", "product_title"))
        if not title:
            raise ValueError(f"canonical product {product_id!r} is missing a title")
        known = {
            "product_id",
            "canonical_product_id",
            "cluster_id",
            "id",
            "title",
            "name",
            "product_title",
            "brand",
            "manufacturer",
            "description",
            "category",
            "price",
            "currency",
            "priceCurrency",
            "identifiers",
            "attributes",
            "gtin",
            "gtin8",
            "gtin12",
            "gtin13",
            "gtin14",
            "ean",
            "upc",
            "mpn",
            "model",
            "model_number",
            "sku",
            "asin",
        }
        embedded_attributes = row.get("attributes")
        attributes = dict(embedded_attributes) if isinstance(embedded_attributes, Mapping) else {}
        attributes.update(
            {
                str(key): value
                for key, value in row.items()
                if key not in known and value not in (None, "")
            }
        )
        return cls(
            product_id=product_id,
            title=title,
            brand=_clean_string(_first_present(row, "brand", "manufacturer")),
            description=_clean_string(row.get("description")),
            identifiers=_identifiers(row),
            category=_clean_string(row.get("category")),
            price=_optional_float(row.get("price")),
            currency=_clean_string(_first_present(row, "currency", "priceCurrency")),
            attributes=attributes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProductListing:
    """A seller offer to match; ``canonical_product_id`` is optional gold data."""

    listing_id: str
    title: str
    brand: str = ""
    description: str = ""
    identifiers: dict[str, str] = field(default_factory=dict)
    source: str = ""
    price: float | None = None
    currency: str = ""
    canonical_product_id: str | None = None
    split: str = ""
    unseen: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> ProductListing:
        listing_id = _clean_string(_first_present(row, "listing_id", "offer_id", "id", "pair_id"))
        if not listing_id:
            raise ValueError("listing is missing listing_id/offer_id/id")
        title = _clean_string(_first_present(row, "title", "name", "product_title"))
        if not title:
            raise ValueError(f"listing {listing_id!r} is missing a title")

        truth = row.get("canonical_product_id")
        if truth in (None, ""):
            truth = row.get("cluster_id")
        # ``label`` is a cluster label in WDC multi-class files, but a binary
        # target in pairwise files. Pairwise rows are handled by load_wdc_pairs.
        if truth in (None, "") and "_left" not in " ".join(map(str, row.keys())):
            truth = row.get("label")
        truth_text = _clean_string(truth)
        if truth_text.casefold() in {"", "none", "null", "unknown", "-1"}:
            truth_text = ""

        known = {
            "listing_id",
            "offer_id",
            "id",
            "pair_id",
            "title",
            "name",
            "product_title",
            "brand",
            "manufacturer",
            "description",
            "source",
            "price",
            "currency",
            "priceCurrency",
            "canonical_product_id",
            "cluster_id",
            "label",
            "split",
            "unseen",
            "identifiers",
            "attributes",
            "gtin",
            "gtin8",
            "gtin12",
            "gtin13",
            "gtin14",
            "ean",
            "upc",
            "mpn",
            "model",
            "model_number",
            "sku",
            "asin",
        }
        embedded_attributes = row.get("attributes")
        attributes = dict(embedded_attributes) if isinstance(embedded_attributes, Mapping) else {}
        attributes.update(
            {
                str(key): value
                for key, value in row.items()
                if key not in known and value not in (None, "")
            }
        )
        return cls(
            listing_id=listing_id,
            title=title,
            brand=_clean_string(_first_present(row, "brand", "manufacturer")),
            description=_clean_string(row.get("description")),
            identifiers=_identifiers(row),
            source=_clean_string(row.get("source")),
            price=_optional_float(row.get("price")),
            currency=_clean_string(_first_present(row, "currency", "priceCurrency")),
            canonical_product_id=truth_text or None,
            split=_clean_string(row.get("split")),
            unseen=_bool(row.get("unseen")),
            attributes=attributes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MatchDecision(StrEnum):
    AUTO_MATCH = "auto_match"
    REVIEW = "review"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    product_id: str
    title: str
    brand: str
    confidence: float
    retrieval_score: float
    reasons: tuple[str, ...] = ()
    features: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


@dataclass(frozen=True, slots=True)
class MatchResult:
    listing_id: str
    decision: MatchDecision
    proposed_product_id: str | None
    matched_product_id: str | None
    confidence: float
    margin: float
    candidates: tuple[MatchCandidate, ...]
    reasons: tuple[str, ...]
    model_id: str
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "decision": self.decision.value,
            "proposed_product_id": self.proposed_product_id,
            "matched_product_id": self.matched_product_id,
            "confidence": self.confidence,
            "margin": self.margin,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "reasons": list(self.reasons),
            "model_id": self.model_id,
            "latency_ms": self.latency_ms,
        }
