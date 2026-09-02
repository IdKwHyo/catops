"""Pure-Python moderate-volume smoke coverage for matcher output invariants."""

from __future__ import annotations

from services.matcher import CanonicalProduct, EntityMatcher, MatcherConfig, ProductListing


def test_batch_matching_keeps_contracts_under_moderate_volume() -> None:
    products = [
        CanonicalProduct(
            product_id=f"product-{index:03d}",
            title=f"Acme Widget Model {index:03d}",
            brand="Acme",
            identifiers={"mpn": f"AC-{index:03d}"},
        )
        for index in range(60)
    ]
    listings = [
        ProductListing(
            listing_id=f"offer-{index:03d}",
            title=f"ACME widget {index % 60:03d}",
            brand="Acme",
            identifiers={"mpn": f"AC-{index % 60:03d}"},
        )
        for index in range(180)
    ]
    matcher = EntityMatcher(MatcherConfig(prefer_sklearn=False, candidate_pool_size=5)).fit(
        products
    )

    results = matcher.match_many(listings, top_k=3)

    assert len(results) == len(listings)
    for listing, result in zip(listings, results, strict=True):
        expected_id = f"product-{int(listing.listing_id.removeprefix('offer-')) % 60:03d}"
        assert result.listing_id == listing.listing_id
        assert result.candidates
        assert len(result.candidates) <= 3
        assert result.candidates[0].product_id == expected_id
        assert result.to_dict()["decision"] in {"auto_match", "review", "no_match"}
        assert 0 <= result.confidence <= 1
