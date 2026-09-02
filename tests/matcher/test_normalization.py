"""Contracts for conservative product normalization and identifier extraction."""

from __future__ import annotations

import pytest

from services.matcher.normalization import (
    extract_identifiers,
    infer_brand,
    normalize_brand,
    normalize_text,
    numeric_tokens,
    tokens,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("  Sony&nbsp;<b>WH‑1000XM5</b> &amp; case  ", "sony wh 1000xm5 and case"),
        ("Fullwidth ＡＢＣ１２３", "fullwidth abc123"),
        ("12 inches / 256 gigabytes × 2; 1 litre", "12 in 256 gb x 2 1 l"),
    ],
)
def test_normalize_text_is_unicode_and_markup_safe(raw: object, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalization_preserves_variant_bearing_tokens() -> None:
    raw = "Galaxy S24 Ultra, 256.5GB - Onyx Black"

    assert tokens(raw) == ("galaxy", "s24", "ultra", "256", "5gb", "onyx", "black")
    assert numeric_tokens(raw) == frozenset({"24", "256", "5"})


def test_normalize_brand_removes_common_legal_suffixes() -> None:
    assert normalize_brand("  ACME Corporation, Inc. ") == "acme"


def test_extract_identifiers_combines_explicit_labeled_model_and_valid_gtin() -> None:
    identifiers = extract_identifiers(
        "MPN: WH-1000XM5/B; model XPS-13-9315; GTIN 4006381333931",
        explicit={"seller_mpn": " Custom / 77-A ", "empty": None},
    )

    assert "wh1000xm5b" in identifiers
    assert "xps139315" in identifiers
    assert "4006381333931" in identifiers
    assert "custom77a" in identifiers


def test_invalid_gtin_checksum_is_not_trusted_when_only_in_free_text() -> None:
    assert "1234567890123" not in extract_identifiers("GTIN 1234567890123")


def test_explicit_identifier_is_trusted_and_canonicalized() -> None:
    assert extract_identifiers("", {"mpn": " SM-S921B/ZK "}) == frozenset({"sms921bzk"})


def test_infer_brand_uses_longest_complete_token_match() -> None:
    brands = ("Pro", "Acme", "Acme Pro", "Cam")

    assert infer_brand("Case for ACME PRO Camera", brands) == "acme pro"
    assert infer_brand("Camera accessory", brands) == ""
