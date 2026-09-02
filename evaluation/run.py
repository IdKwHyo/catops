"""Train on one split, evaluate another, write JSON, and optionally gate CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipelines.ingest import load_canonical_products, load_product_listings, sha256_file
from services.matcher import EntityMatcher, MatcherConfig

from .metrics import evaluate_matcher

DEFAULT_GATES = {
    "precision": 0.75,
    "recall": 0.55,
    "f1": 0.63,
    "recall_at_5": 0.90,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/sample/catalog.csv")
    parser.add_argument("--offers", default="data/sample/offers.jsonl")
    parser.add_argument("--output", default="evaluation/results/sample-baseline.json")
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--eval-split", default="test")
    parser.add_argument(
        "--allow-all",
        action="store_true",
        help="explicitly use all offers when a requested split is absent (unsafe for benchmark claims)",
    )
    parser.add_argument("--ks", default="1,3,5")
    parser.add_argument("--force-lexical", action="store_true")
    parser.add_argument("--artifact", help="optional directory for the fitted artifact")
    parser.add_argument("--check-thresholds", action="store_true")
    parser.add_argument("--min-precision", type=float, default=DEFAULT_GATES["precision"])
    parser.add_argument("--min-recall", type=float, default=DEFAULT_GATES["recall"])
    parser.add_argument("--min-f1", type=float, default=DEFAULT_GATES["f1"])
    parser.add_argument("--min-recall-at-5", type=float, default=DEFAULT_GATES["recall_at_5"])
    return parser


def _gate(report: dict[str, Any], args: argparse.Namespace) -> list[str]:
    classification = report["classification"]
    recall_at_5 = report["ranking"]["recall_at_k"].get("5", 0.0)
    checks = (
        ("precision", classification["precision"], args.min_precision),
        ("recall", classification["recall"], args.min_recall),
        ("f1", classification["f1"], args.min_f1),
        ("recall@5", recall_at_5, args.min_recall_at_5),
    )
    return [
        f"{name}={actual:.4f} < {minimum:.4f}"
        for name, actual, minimum in checks
        if actual < minimum
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    catalog = load_canonical_products(args.catalog)
    offers = load_product_listings(args.offers)
    train = [offer for offer in offers if offer.split == args.train_split]
    evaluate = [offer for offer in offers if offer.split == args.eval_split]
    available_splits = sorted({offer.split or "<empty>" for offer in offers})
    if not train or not evaluate:
        missing = []
        if not train:
            missing.append(f"train split {args.train_split!r}")
        if not evaluate:
            missing.append(f"evaluation split {args.eval_split!r}")
        if not args.allow_all:
            raise SystemExit(
                "missing "
                + " and ".join(missing)
                + "; available splits: "
                + ", ".join(available_splits)
            )
        if not train:
            train = offers
        if not evaluate:
            evaluate = offers

    matcher = EntityMatcher(MatcherConfig(prefer_sklearn=not args.force_lexical)).fit(
        catalog, train
    )
    if args.artifact:
        matcher.save(args.artifact)
    ks = tuple(int(value) for value in args.ks.split(",") if value.strip())
    report = evaluate_matcher(matcher, evaluate, ks=ks)
    report["dataset"].update(
        {
            "catalog_path": str(args.catalog),
            "catalog_sha256": sha256_file(args.catalog),
            "offers_path": str(args.offers),
            "offers_sha256": sha256_file(args.offers),
            "train_split": args.train_split,
            "evaluation_split": args.eval_split,
            "training_listings": len(train),
            "allow_all_split_fallback": bool(args.allow_all),
        }
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "model_id": report["model"]["model_id"],
        "precision": report["classification"]["precision"],
        "recall": report["classification"]["recall"],
        "f1": report["classification"]["f1"],
        "recall_at_k": report["ranking"]["recall_at_k"],
        "mrr": report["ranking"]["mrr"],
        "ece": report["calibration"]["ece"],
        "brier_score": report["calibration"]["brier_score"],
        "p95_latency_ms": report["latency_ms"]["p95"],
        "report": str(destination),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    failures = _gate(report, args) if args.check_thresholds else []
    if failures:
        print("evaluation gate failed: " + "; ".join(failures))
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
