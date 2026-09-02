"""Interpretable pair features for the baseline classifier and audit UI."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher
from math import isfinite

from .normalization import (
    extract_identifiers,
    infer_brand,
    normalize_brand,
    normalize_text,
    numeric_tokens,
)
from .schemas import CanonicalProduct, ProductListing

FEATURE_NAMES = (
    "retrieval_score",
    "token_jaccard",
    "token_containment",
    "character_ratio",
    "brand_exact",
    "brand_conflict",
    "identifier_exact",
    "identifier_conflict",
    "number_jaccard",
    "description_jaccard",
    "length_ratio",
)


def _jaccard(left: set[str] | frozenset[str], right: set[str] | frozenset[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _containment(left: set[str], right: set[str]) -> float:
    denominator = min(len(left), len(right))
    return len(left & right) / denominator if denominator else 0.0


def _identifier_match(left: frozenset[str], right: frozenset[str]) -> bool:
    if left & right:
        return True
    # Seller feeds often omit a short manufacturer prefix (WH-1000XM5 versus
    # 1000XM5). Restrict fuzzy agreement to a long suffix to avoid SKU collisions.
    return any(
        min(len(left_id), len(right_id)) >= 6
        and (left_id.endswith(right_id) or right_id.endswith(left_id))
        for left_id in left
        for right_id in right
    )


class PairFeatureExtractor:
    """Produces a fixed, documented feature vector without mutable state."""

    feature_names = FEATURE_NAMES

    def __init__(self, known_brands: tuple[str, ...] = ()) -> None:
        self.known_brands = known_brands

    def extract(
        self,
        listing: ProductListing,
        product: CanonicalProduct,
        retrieval_score: float = 0.0,
    ) -> dict[str, float]:
        listing_title = normalize_text(listing.title)
        product_title = normalize_text(product.title)
        listing_tokens = set(listing_title.split())
        product_tokens = set(product_title.split())

        listing_brand = normalize_brand(listing.brand) or infer_brand(
            listing.title, self.known_brands
        )
        product_brand = normalize_brand(product.brand) or infer_brand(
            product.title, self.known_brands
        )
        brand_exact = float(
            bool(listing_brand and product_brand and listing_brand == product_brand)
        )
        brand_conflict = float(
            bool(listing_brand and product_brand and listing_brand != product_brand)
        )

        listing_ids = extract_identifiers(
            f"{listing.title} {listing.description}", listing.identifiers
        )
        product_ids = extract_identifiers(
            f"{product.title} {product.description}", product.identifiers
        )
        ids_agree = _identifier_match(listing_ids, product_ids)
        identifier_exact = float(ids_agree)
        identifier_conflict = float(bool(listing_ids and product_ids and not ids_agree))

        listing_numbers = numeric_tokens(listing.title)
        product_numbers = numeric_tokens(product.title)
        listing_description = set(normalize_text(listing.description).split())
        product_description = set(normalize_text(product.description).split())

        longest = max(len(listing_title), len(product_title), 1)
        shortest = min(len(listing_title), len(product_title))
        safe_retrieval = float(retrieval_score) if isfinite(float(retrieval_score)) else 0.0
        return {
            "retrieval_score": max(0.0, min(1.0, safe_retrieval)),
            "token_jaccard": _jaccard(listing_tokens, product_tokens),
            "token_containment": _containment(listing_tokens, product_tokens),
            "character_ratio": SequenceMatcher(None, listing_title, product_title).ratio(),
            "brand_exact": brand_exact,
            "brand_conflict": brand_conflict,
            "identifier_exact": identifier_exact,
            "identifier_conflict": identifier_conflict,
            "number_jaccard": _jaccard(listing_numbers, product_numbers),
            "description_jaccard": _jaccard(listing_description, product_description),
            "length_ratio": shortest / longest,
        }

    def vector(self, features: Mapping[str, float]) -> list[float]:
        return [float(features.get(name, 0.0)) for name in self.feature_names]


def evidence_reasons(features: Mapping[str, float]) -> tuple[str, ...]:
    reasons: list[str] = []
    if features.get("identifier_exact", 0.0) >= 1.0:
        reasons.append("exact identifier")
    if features.get("brand_exact", 0.0) >= 1.0:
        reasons.append("brand agrees")
    if features.get("retrieval_score", 0.0) >= 0.75:
        reasons.append("strong title similarity")
    elif features.get("token_containment", 0.0) >= 0.65:
        reasons.append("most title tokens overlap")
    if features.get("number_jaccard", 0.0) >= 0.5:
        reasons.append("numeric attributes agree")
    if features.get("identifier_conflict", 0.0) >= 1.0:
        reasons.append("identifier conflict")
    if features.get("brand_conflict", 0.0) >= 1.0:
        reasons.append("brand conflict")
    return tuple(reasons[:4])
