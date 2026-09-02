"""Conservative product text normalization and structured signal extraction."""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

_HTML_TAG = re.compile(r"<[^>]+>")
_NON_WORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_SPACE = re.compile(r"\s+")
_LABELED_ID = re.compile(
    r"\b(?P<label>mpn|model(?:\s*(?:no|number))?|part(?:\s*(?:no|number))?|sku|asin)"
    r"\s*[:#-]?\s*(?P<value>[a-z0-9][a-z0-9._/-]{2,})\b",
    flags=re.IGNORECASE,
)
_MODEL_TOKEN = re.compile(
    r"\b(?=[a-z0-9-]{4,}\b)(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)+\b", re.I
)
_MIXED_MODEL_TOKEN = re.compile(
    r"\b(?=[a-z0-9]{4,}\b)(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]+\b", re.I
)
_DIGITS = re.compile(r"(?<!\d)(\d{8}|\d{12,14})(?!\d)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MEASUREMENT_MODEL = re.compile(
    r"^(?:\d+(?:gb|tb|mb|mah|mm|cm|in|qt|oz|ml|w|v|hz|mp)|\d+(?:in|x)\d+)$", re.I
)
_CORPORATE_SUFFIX = re.compile(
    r"(?:\s+(?:inc(?:orporated)?|corp(?:oration)?|co(?:mpany)?|ltd|llc))+$", re.I
)

_UNIT_REPLACEMENTS = (
    (re.compile(r"\b(?:inches|inch|in\.)\b", re.I), " in "),
    (re.compile(r"\b(?:gigabytes|gigabyte|gbytes|gbyte)\b", re.I), " gb "),
    (re.compile(r"\b(?:terabytes|terabyte|tbytes|tbyte)\b", re.I), " tb "),
    (re.compile(r"\b(?:millilitres|milliliters|millilitre|milliliter)\b", re.I), " ml "),
    (re.compile(r"\b(?:litres|liters|litre|liter)\b", re.I), " l "),
    (re.compile(r"\b(?:quarts|quart)\b", re.I), " qt "),
    (re.compile(r"\b(?:ounces|ounce)\b", re.I), " oz "),
)


def normalize_text(value: Any) -> str:
    """Normalize Unicode, markup, punctuation, and common product units.

    The function deliberately does not remove model numbers, colors, storage, or
    stop words because those tokens often distinguish nearby product variants.
    """

    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", html.unescape(str(value))).casefold()
    text = _HTML_TAG.sub(" ", text)
    text = text.replace("&", " and ").replace("×", " x ")
    for pattern, replacement in _UNIT_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = _NON_WORD.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def normalize_brand(value: Any) -> str:
    normalized = normalize_text(value)
    while _CORPORATE_SUFFIX.search(normalized):
        normalized = _CORPORATE_SUFFIX.sub("", normalized).strip()
    return normalized


def tokens(value: Any) -> tuple[str, ...]:
    return tuple(token for token in normalize_text(value).split() if token)


def numeric_tokens(value: Any) -> frozenset[str]:
    return frozenset(_NUMBER.findall(normalize_text(value)))


def _valid_gtin(value: str) -> bool:
    if not value.isdigit() or len(value) not in {8, 12, 13, 14}:
        return False
    digits = [int(char) for char in value]
    body = digits[:-1]
    total = sum(digit * (3 if (len(body) - index) % 2 else 1) for index, digit in enumerate(body))
    return (10 - total % 10) % 10 == digits[-1]


def extract_identifiers(text: Any, explicit: Mapping[str, Any] | None = None) -> frozenset[str]:
    """Return normalized GTIN and labeled/model-like identifiers.

    Invalid GTIN checksums are ignored. Explicit identifiers are trusted because
    seller feeds commonly store internal MPNs that do not match a generic regex.
    """

    found: set[str] = set()
    if explicit:
        for value in explicit.values():
            normalized = re.sub(r"[^a-z0-9]", "", normalize_text(value))
            if len(normalized) >= 3:
                found.add(normalized)

    original = unicodedata.normalize("NFKC", str(text or "")).casefold()
    for match in _LABELED_ID.finditer(original):
        value = re.sub(r"[^a-z0-9]", "", match.group("value"))
        # Unstructured text like "OLED model white" must not turn "white"
        # into a hard identifier. Letter-only MPNs remain supported explicitly.
        if len(value) >= 3 and any(character.isdigit() for character in value):
            found.add(value)
    for match in _MODEL_TOKEN.finditer(original):
        value = re.sub(r"[^a-z0-9]", "", match.group(0))
        if len(value) >= 4 and not _MEASUREMENT_MODEL.fullmatch(value):
            found.add(value)
    for match in _MIXED_MODEL_TOKEN.finditer(original):
        value = match.group(0).casefold()
        if not _MEASUREMENT_MODEL.fullmatch(value):
            found.add(value)
    for value in _DIGITS.findall(original):
        if _valid_gtin(value):
            found.add(value)
    return frozenset(found)


def infer_brand(title: Any, known_brands: Iterable[str]) -> str:
    """Infer the longest catalog brand occurring as complete title tokens."""

    normalized_title = f" {normalize_text(title)} "
    candidates = sorted(
        {normalize_brand(brand) for brand in known_brands if normalize_brand(brand)},
        key=lambda item: (-len(item), item),
    )
    for brand in candidates:
        if f" {brand} " in normalized_title:
            return brand
    return ""
