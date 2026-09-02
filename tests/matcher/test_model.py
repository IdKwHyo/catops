"""Ranking and bounded-decision behavior of the dependency-light matcher."""

from __future__ import annotations

import json

import pytest

from services.matcher import (
    CanonicalProduct,
    EntityMatcher,
    MatchDecision,
    MatcherConfig,
    ProductListing,
)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"review_threshold": 0.85, "auto_match_threshold": 0.85},
        {"review_threshold": -0.01},
        {"auto_match_threshold": 1.01},
        {"minimum_auto_margin": -0.01},
        {"candidate_pool_size": 0},
        {"max_training_negatives": 0},
    ],
)
def test_matcher_config_rejects_unsafe_policy(kwargs: dict[str, float | int]) -> None:
    with pytest.raises(ValueError):
        MatcherConfig(**kwargs)


def test_exact_identifier_ranks_first_and_allows_auto_match(
    lexical_matcher: EntityMatcher,
) -> None:
    result = lexical_matcher.match(
        ProductListing(
            listing_id="offer-1",
            title="ACME blue trail shoe size 42",
            brand="Acme",
            identifiers={"mpn": "AC-42-B"},
        ),
        top_k=2,
    )

    assert result.decision is MatchDecision.AUTO_MATCH
    assert result.proposed_product_id == "p-blue"
    assert result.matched_product_id == "p-blue"
    assert result.confidence >= 0.995
    assert result.candidates[0].product_id == "p-blue"
    assert "exact identifier" in result.candidates[0].reasons


def test_high_confidence_but_ambiguous_candidates_are_sent_to_review(
    lexical_matcher: EntityMatcher,
) -> None:
    result = lexical_matcher.match(
        ProductListing(
            listing_id="offer-2",
            title="Acme Trail Runner 42",
            brand="Acme",
        ),
        top_k=3,
    )

    assert result.confidence >= lexical_matcher.config.auto_match_threshold
    assert result.margin < lexical_matcher.config.minimum_auto_margin
    assert result.decision is MatchDecision.REVIEW
    assert result.proposed_product_id in {"p-blue", "p-black"}
    assert result.matched_product_id is None
    assert "competing candidates are too close" in result.reasons[0]


def test_unrelated_listing_is_rejected_without_proposed_match(
    lexical_matcher: EntityMatcher,
) -> None:
    result = lexical_matcher.match(
        ProductListing(listing_id="offer-3", title="Generic kitchen storage bundle"),
        top_k=2,
    )

    assert result.decision is MatchDecision.NO_MATCH
    assert result.confidence < lexical_matcher.config.review_threshold
    assert result.proposed_product_id is None
    assert result.matched_product_id is None


def test_brand_conflict_caps_confidence_below_default_review_threshold(
    lexical_matcher: EntityMatcher,
) -> None:
    result = lexical_matcher.match(
        ProductListing(
            listing_id="offer-4",
            title="Acme Trail Runner 42 Blue",
            brand="Definitely Not Acme",
        )
    )

    assert result.candidates[0].features["brand_conflict"] == 1.0
    assert result.confidence <= 0.48
    assert result.decision is MatchDecision.NO_MATCH


def test_ranking_has_stable_product_id_tie_break() -> None:
    products = [
        CanonicalProduct(product_id="z-product", title="Identical Item", brand="Acme"),
        CanonicalProduct(product_id="a-product", title="Identical Item", brand="Acme"),
    ]
    matcher = EntityMatcher(MatcherConfig(prefer_sklearn=False)).fit(products)

    result = matcher.match(
        ProductListing(listing_id="offer-tie", title="Identical Item", brand="Acme"), top_k=2
    )

    assert [candidate.product_id for candidate in result.candidates] == [
        "a-product",
        "z-product",
    ]
    assert result.margin == 0.0
    assert result.decision is MatchDecision.REVIEW


def test_match_result_serializes_to_stable_json_contract(lexical_matcher: EntityMatcher) -> None:
    result = lexical_matcher.match(
        ProductListing(
            listing_id="offer-json",
            title="Zen Camera Lens 50mm",
            brand="Zen",
            identifiers={"mpn": "ZEN-50-MM"},
        ),
        top_k=1,
    )

    payload = result.to_dict()
    assert payload["decision"] == "auto_match"
    assert payload["listing_id"] == "offer-json"
    assert isinstance(payload["candidates"], list)
    assert isinstance(payload["candidates"][0]["reasons"], list)
    json.dumps(payload)


def test_matcher_lifecycle_and_input_guards(canonical_catalog: list[CanonicalProduct]) -> None:
    matcher = EntityMatcher(MatcherConfig(prefer_sklearn=False))
    listing = ProductListing(listing_id="offer", title="Any product")

    with pytest.raises(RuntimeError, match="not fitted"):
        matcher.match(listing)
    with pytest.raises(ValueError, match="at least one"):
        matcher.fit([])
    with pytest.raises(ValueError, match="unique"):
        matcher.fit([canonical_catalog[0], canonical_catalog[0]])

    matcher.fit(canonical_catalog)
    with pytest.raises(ValueError, match="top_k"):
        matcher.match(listing, top_k=0)


def test_saved_artifact_detects_catalog_tampering(
    tmp_path, canonical_catalog: list[CanonicalProduct]
) -> None:
    matcher = EntityMatcher(MatcherConfig(prefer_sklearn=False)).fit(canonical_catalog)
    artifact = matcher.save(tmp_path / "matcher")
    catalog_path = artifact / "catalog.jsonl"
    catalog_path.write_text(catalog_path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        EntityMatcher.load(artifact)
