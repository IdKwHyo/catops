"""Dependency-free matcher data-contract tests."""

from __future__ import annotations

import pytest

from services.matcher import CanonicalProduct, ProductListing


def test_product_mapping_accepts_wdc_aliases_and_preserves_extra_attributes() -> None:
    product = CanonicalProduct.from_mapping(
        {
            "cluster_id": "entity-7",
            "product_title": "Example Camera",
            "manufacturer": "Optic Co",
            "price": "49.95",
            "priceCurrency": "EUR",
            "mpn": "OPT-7",
            "colour": "black",
        }
    )

    assert product.product_id == "entity-7"
    assert product.title == "Example Camera"
    assert product.brand == "Optic Co"
    assert product.price == 49.95
    assert product.identifiers == {"mpn": "OPT-7"}
    assert product.attributes == {"colour": "black"}


def test_listing_mapping_normalizes_truth_and_boolean_fields() -> None:
    listing = ProductListing.from_mapping(
        {
            "offer_id": 41,
            "name": "Example listing",
            "cluster_id": "unknown",
            "unseen": "YES",
            "price": "not-a-number",
        }
    )

    assert listing.listing_id == "41"
    assert listing.canonical_product_id is None
    assert listing.unseen is True
    assert listing.price is None


@pytest.mark.parametrize(
    ("factory", "row", "message"),
    [
        (CanonicalProduct.from_mapping, {"title": "No id"}, "product_id"),
        (CanonicalProduct.from_mapping, {"id": "x"}, "missing a title"),
        (ProductListing.from_mapping, {"title": "No id"}, "listing_id"),
        (ProductListing.from_mapping, {"id": "x"}, "missing a title"),
    ],
)
def test_required_mapping_fields_fail_loudly(factory, row: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory(row)
