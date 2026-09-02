"""Convert a WDC multi-class JSONL/JSON.GZ file to CatalogOps files."""

from __future__ import annotations

import argparse
from dataclasses import replace

from .ingest import (
    build_catalog_from_clusters,
    load_product_listings,
    write_catalog_csv,
    write_listings_jsonl,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="WDC multi-class CSV/JSONL/JSON.GZ")
    parser.add_argument("--catalog-output", required=True)
    parser.add_argument("--offers-output", required=True)
    parser.add_argument(
        "--split",
        choices=("train", "validation", "test"),
        help="assign this split when source records do not contain one",
    )
    parser.add_argument(
        "--catalog-split",
        default="train",
        help="only this split may supply canonical representatives (default: train)",
    )
    args = parser.parse_args(argv)

    offers = load_product_listings(args.input)
    if args.split:
        offers = [replace(item, split=item.split or args.split) for item in offers]
    catalog, offers = build_catalog_from_clusters(
        offers, representative_splits=(args.catalog_split,)
    )
    write_catalog_csv(catalog, args.catalog_output)
    write_listings_jsonl(offers, args.offers_output)
    print(f"wrote {len(catalog)} entities and {len(offers)} offers")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
