"""Shared lightweight fixtures for CatalogOps contract tests."""

from __future__ import annotations

import pytest

from services.matcher import CanonicalProduct, EntityMatcher, MatcherConfig


@pytest.fixture
def canonical_catalog() -> list[CanonicalProduct]:
    return [
        CanonicalProduct(
            product_id="p-blue",
            title="Acme Trail Runner 42 Blue",
            brand="Acme",
            description="Men's blue trail running shoe",
            identifiers={"mpn": "AC-42-B"},
            category="Footwear",
        ),
        CanonicalProduct(
            product_id="p-black",
            title="Acme Trail Runner 42 Black",
            brand="Acme",
            description="Men's black trail running shoe",
            identifiers={"mpn": "AC-42-K"},
            category="Footwear",
        ),
        CanonicalProduct(
            product_id="p-lens",
            title="Zen Camera Lens 50mm",
            brand="Zen",
            description="Prime camera lens",
            identifiers={"mpn": "ZEN-50-MM"},
            category="Cameras",
        ),
    ]


@pytest.fixture
def lexical_matcher(canonical_catalog: list[CanonicalProduct]) -> EntityMatcher:
    """A deterministic matcher that does not vary with optional sklearn versions."""

    return EntityMatcher(MatcherConfig(prefer_sklearn=False)).fit(canonical_catalog)
