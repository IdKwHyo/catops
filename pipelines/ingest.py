"""Streaming, dependency-free ingestion for CatalogOps and WDC product data."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Any, TextIO

from services.matcher import CanonicalProduct, ProductListing

_JSON_SUFFIXES = {".json", ".jsonl", ".ndjson"}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_text(path: Path) -> TextIO:
    if path.suffix.casefold() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def _logical_suffix(path: Path) -> str:
    suffixes = [suffix.casefold() for suffix in path.suffixes]
    if suffixes and suffixes[-1] == ".gz" and len(suffixes) > 1:
        return suffixes[-2]
    return suffixes[-1] if suffixes else ""


def iter_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield mappings from CSV, JSON, JSONL, and gzipped equivalents.

    The official WDC starter archive contains gzipped JSON Lines; both
    ``*.json.gz`` and ``*.jsonl.gz`` are treated as streams rather than requiring
    the entire benchmark in memory.
    """

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    suffix = _logical_suffix(source)
    with _open_text(source) as handle:
        if suffix == ".csv":
            for row in csv.DictReader(handle):
                yield _decode_embedded(row)
            return
        if suffix not in _JSON_SUFFIXES:
            raise ValueError(f"unsupported dataset format: {source.name}")

        first = ""
        for line in handle:
            if line.strip():
                first = line
                break
        if not first:
            return
        if first.lstrip().startswith("["):
            payload = json.loads(first + handle.read())
            if not isinstance(payload, list):
                raise ValueError("JSON dataset root must be a list or JSON Lines")
            for row in payload:
                if isinstance(row, Mapping):
                    yield _decode_embedded(dict(row))
            return

        for line in chain((first,), handle):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, Mapping):
                raise ValueError("each JSONL record must be an object")
            yield _decode_embedded(dict(row))


def _decode_embedded(row: Mapping[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for key in ("identifiers", "attributes", "specTableContent"):
        value = decoded.get(key)
        if isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                decoded[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return decoded


def load_canonical_products(path: str | Path) -> list[CanonicalProduct]:
    products: list[CanonicalProduct] = []
    for row in iter_rows(path):
        normalized = dict(row)
        normalized.setdefault(
            "product_id", row.get("canonical_product_id") or row.get("cluster_id") or row.get("id")
        )
        products.append(CanonicalProduct.from_mapping(normalized))
    return products


def load_product_listings(path: str | Path) -> list[ProductListing]:
    return [ProductListing.from_mapping(row) for row in iter_rows(path)]


@dataclass(frozen=True, slots=True)
class PairExample:
    """One WDC pairwise row with complete offers retained on both sides."""

    pair_id: str
    left: ProductListing
    right: CanonicalProduct
    label: int
    is_hard_negative: bool = False


def _side(row: Mapping[str, Any], suffix: str) -> dict[str, Any]:
    marker = f"_{suffix}"
    side = {
        str(key)[: -len(marker)]: value for key, value in row.items() if str(key).endswith(marker)
    }
    # Some prepared variants nest each offer instead of suffixing fields.
    nested = row.get(suffix)
    if isinstance(nested, Mapping):
        side.update(nested)
    return side


def _binary(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return int(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "1.0", "true", "yes", "match", "positive"}:
        return 1
    if normalized in {"0", "0.0", "false", "no", "nonmatch", "negative"}:
        return 0
    raise ValueError(f"invalid pair label: {value!r}")


def load_wdc_pairs(path: str | Path) -> list[PairExample]:
    """Load official pairwise fields such as ``title_left``/``title_right``."""

    examples: list[PairExample] = []
    for index, row in enumerate(iter_rows(path)):
        left_row = _side(row, "left")
        right_row = _side(row, "right")
        if not left_row or not right_row:
            raise ValueError("WDC pair row is missing _left/_right offer fields")
        pair_id = str(row.get("pair_id") or f"pair-{index:07d}")
        left_row["listing_id"] = left_row.get("id") or f"{pair_id}-left"
        # Pair labels must never be interpreted as multi-class ground truth.
        left_row.pop("label", None)
        right_row["product_id"] = right_row.get("id") or f"{pair_id}-right"
        examples.append(
            PairExample(
                pair_id=pair_id,
                left=ProductListing.from_mapping(left_row),
                right=CanonicalProduct.from_mapping(right_row),
                label=_binary(row.get("label")),
                is_hard_negative=bool(_binary(row.get("is_hard_negative", 0))),
            )
        )
    return examples


def build_catalog_from_clusters(
    listings: Iterable[ProductListing],
    representative_splits: Iterable[str] | None = ("train",),
) -> tuple[list[CanonicalProduct], list[ProductListing]]:
    """Choose a deterministic representative per known WDC cluster.

    The most information-rich offer becomes the canonical display record. All
    offers remain in the returned listing set for split-aware training/evaluation.
    This is a benchmark convenience, not a claim that a seller offer is trusted
    production master data.
    """

    offers = list(listings)
    clusters: dict[str, list[ProductListing]] = defaultdict(list)
    for listing in offers:
        if listing.canonical_product_id:
            clusters[listing.canonical_product_id].append(listing)

    permitted_splits = (
        {value.casefold() for value in representative_splits}
        if representative_splits is not None
        else None
    )
    catalog: list[CanonicalProduct] = []
    for cluster_id, members in sorted(clusters.items()):
        eligible = members
        if permitted_splits is not None:
            eligible = [item for item in members if item.split.casefold() in permitted_splits]
        # Never create a catalog entity from validation/test data implicitly.
        # Passing representative_splits=None is an explicit exploratory opt-in.
        if not eligible:
            continue
        representative = sorted(
            eligible,
            key=lambda item: (
                -(len(item.title) + len(item.description) + 20 * len(item.identifiers)),
                item.listing_id,
            ),
        )[0]
        catalog.append(
            CanonicalProduct(
                product_id=cluster_id,
                title=representative.title,
                brand=representative.brand,
                description=representative.description,
                identifiers=dict(representative.identifiers),
                price=representative.price,
                currency=representative.currency,
                attributes={"representative_offer_id": representative.listing_id},
            )
        )
    return catalog, offers


def write_catalog_csv(products: Iterable[CanonicalProduct], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "product_id",
        "title",
        "brand",
        "description",
        "category",
        "price",
        "currency",
        "identifiers",
    ]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for product in products:
            row = product.to_dict()
            row["identifiers"] = json.dumps(row["identifiers"], sort_keys=True)
            writer.writerow({field: row.get(field, "") for field in fields})
    return destination


def write_listings_jsonl(listings: Iterable[ProductListing], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for listing in listings:
            handle.write(json.dumps(listing.to_dict(), sort_keys=True) + "\n")
    return destination
