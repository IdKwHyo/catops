"""Train and persist the Phase-1 matcher artifact.

Example:
    python -m pipelines.train_baseline
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.matcher import EntityMatcher, MatcherConfig

from .ingest import load_canonical_products, load_product_listings, sha256_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/sample/catalog.csv")
    parser.add_argument("--offers", default="data/sample/offers.jsonl")
    parser.add_argument("--artifact", default="data/sample/artifacts/baseline")
    parser.add_argument("--train-split", default="train")
    parser.add_argument(
        "--allow-all",
        action="store_true",
        help="explicitly train on every offer if the requested split is absent",
    )
    parser.add_argument("--force-lexical", action="store_true")
    parser.add_argument("--auto-threshold", type=float, default=0.85)
    parser.add_argument("--review-threshold", type=float, default=0.55)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = load_canonical_products(args.catalog)
    offers = load_product_listings(args.offers)
    train = [offer for offer in offers if offer.split == args.train_split]
    if not train:
        available = sorted({offer.split or "<empty>" for offer in offers})
        if not args.allow_all:
            raise SystemExit(
                f"missing train split {args.train_split!r}; available splits: {', '.join(available)}"
            )
        train = offers
    config = MatcherConfig(
        auto_match_threshold=args.auto_threshold,
        review_threshold=args.review_threshold,
        prefer_sklearn=not args.force_lexical,
    )
    matcher = EntityMatcher(config).fit(catalog, train)
    artifact = matcher.save(
        Path(args.artifact),
        provenance={
            "catalog_path": str(args.catalog),
            "catalog_sha256": sha256_file(args.catalog),
            "offers_path": str(args.offers),
            "offers_sha256": sha256_file(args.offers),
            "train_split": args.train_split,
            "training_listings": len(train),
            "allow_all_split_fallback": bool(args.allow_all),
        },
    )
    print(json.dumps({"artifact": str(artifact), **matcher.metadata()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
