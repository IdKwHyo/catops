"""Interpretable pair-feature contracts used by ranking and audit evidence."""

from __future__ import annotations

from math import nan

import pytest

from services.matcher import CanonicalProduct, ProductListing
from services.matcher.features import FEATURE_NAMES, PairFeatureExtractor, evidence_reasons


def test_pair_features_expose_agreement_and_conflict_signals() -> None:
    extractor = PairFeatureExtractor(("Acme", "Zen"))
    product = CanonicalProduct(
        product_id="p1",
        title="Acme Trail Runner 42 Blue",
        brand="Acme",
        identifiers={"mpn": "AC-42-B"},
    )
    listing = ProductListing(
        listing_id="l1",
        title="ACME runner blue size 42",
        identifiers={"seller_mpn": "AC-42-B"},
    )

    features = extractor.extract(listing, product, retrieval_score=1.7)

    assert tuple(features) == FEATURE_NAMES
    assert features["retrieval_score"] == 1.0
    assert features["brand_exact"] == 1.0
    assert features["brand_conflict"] == 0.0
    assert features["identifier_exact"] == 1.0
    assert features["number_jaccard"] == 1.0
    assert "exact identifier" in evidence_reasons(features)


def test_pair_features_clamp_non_finite_retrieval_and_report_conflicts() -> None:
    extractor = PairFeatureExtractor()
    product = CanonicalProduct(
        product_id="p1",
        title="Acme Phone 12",
        brand="Acme",
        identifiers={"mpn": "ACME-12"},
    )
    listing = ProductListing(
        listing_id="l1",
        title="Zen Phone 13",
        brand="Zen",
        identifiers={"mpn": "ZEN-13"},
    )

    features = extractor.extract(listing, product, retrieval_score=nan)

    assert features["retrieval_score"] == 0.0
    assert features["brand_conflict"] == 1.0
    assert features["identifier_conflict"] == 1.0
    assert evidence_reasons(features)[-2:] == ("identifier conflict", "brand conflict")
    assert extractor.vector({"brand_exact": 1}) == pytest.approx([0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0])
