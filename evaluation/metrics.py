"""Metrics for selective entity matching, retrieval, calibration, and latency."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from statistics import fmean
from typing import Any

from services.matcher import EntityMatcher, MatchDecision, MatchResult, ProductListing


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _classification(
    listings: Sequence[ProductListing],
    results: Sequence[MatchResult],
    catalog_ids: set[str],
) -> dict[str, Any]:
    predicted = 0
    correct = 0
    matchable = 0
    wrong_auto = 0
    for listing, result in zip(listings, results, strict=True):
        truth = listing.canonical_product_id
        is_matchable = bool(truth and truth in catalog_ids)
        matchable += int(is_matchable)
        if result.decision is MatchDecision.AUTO_MATCH:
            predicted += 1
            if is_matchable and result.matched_product_id == truth:
                correct += 1
            else:
                wrong_auto += 1
    false_negative = matchable - correct
    precision = _safe_divide(correct, predicted)
    recall = _safe_divide(correct, matchable)
    f1 = _safe_divide(2.0 * precision * recall, precision + recall)
    decisions = Counter(result.decision.value for result in results)
    total = len(results)
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "true_positive": correct,
        "false_positive": wrong_auto,
        "false_negative": false_negative,
        "auto_match_predictions": predicted,
        "matchable_listings": matchable,
        "auto_match_coverage": round(_safe_divide(predicted, total), 6),
        "review_rate": round(_safe_divide(decisions[MatchDecision.REVIEW.value], total), 6),
        "no_match_rate": round(_safe_divide(decisions[MatchDecision.NO_MATCH.value], total), 6),
        "decision_counts": dict(sorted(decisions.items())),
    }


def _ranking(
    listings: Sequence[ProductListing],
    results: Sequence[MatchResult],
    catalog_ids: set[str],
    ks: Sequence[int],
) -> dict[str, Any]:
    reciprocal_ranks: list[float] = []
    hits = {k: 0 for k in ks}
    eligible = 0
    for listing, result in zip(listings, results, strict=True):
        truth = listing.canonical_product_id
        if not truth or truth not in catalog_ids:
            continue
        eligible += 1
        ranked_ids = [candidate.product_id for candidate in result.candidates]
        try:
            rank = ranked_ids.index(truth) + 1
        except ValueError:
            rank = 0
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        for k in ks:
            hits[k] += int(bool(rank and rank <= k))
    return {
        "eligible_queries": eligible,
        "recall_at_k": {str(k): round(_safe_divide(hits[k], eligible), 6) for k in sorted(ks)},
        "mrr": round(fmean(reciprocal_ranks), 6) if reciprocal_ranks else 0.0,
    }


def _calibration(
    listings: Sequence[ProductListing],
    results: Sequence[MatchResult],
    catalog_ids: set[str],
    bins: int,
) -> dict[str, Any]:
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    squared_errors: list[float] = []
    for listing, result in zip(listings, results, strict=True):
        truth = listing.canonical_product_id
        correct = float(
            bool(truth and truth in catalog_ids and result.candidates[0].product_id == truth)
        )
        confidence = max(0.0, min(1.0, result.confidence))
        squared_errors.append((confidence - correct) ** 2)
        index = min(int(confidence * bins), bins - 1)
        buckets[index].append((confidence, correct))

    details: list[dict[str, Any]] = []
    error = 0.0
    total = len(results)
    for index, bucket in enumerate(buckets):
        mean_confidence = fmean(value[0] for value in bucket) if bucket else 0.0
        accuracy = fmean(value[1] for value in bucket) if bucket else 0.0
        error += _safe_divide(len(bucket), total) * abs(accuracy - mean_confidence)
        details.append(
            {
                "lower": round(index / bins, 4),
                "upper": round((index + 1) / bins, 4),
                "count": len(bucket),
                "mean_confidence": round(mean_confidence, 6),
                "accuracy": round(accuracy, 6),
            }
        )
    return {
        "ece": round(error, 6),
        "brier_score": round(fmean(squared_errors), 6) if squared_errors else 0.0,
        "bin_count": bins,
        "bins": details,
    }


def _slice_summary(
    listings: Sequence[ProductListing],
    results: Sequence[MatchResult],
    catalog_ids: set[str],
) -> dict[str, Any]:
    if not listings:
        return {"count": 0, "top1_accuracy": 0.0, "auto_match_accuracy": 0.0}
    top_correct = 0
    top_eligible = 0
    auto_correct = 0
    auto_count = 0
    for listing, result in zip(listings, results, strict=True):
        truth = listing.canonical_product_id
        if truth and truth in catalog_ids:
            top_eligible += 1
            top_correct += int(result.candidates[0].product_id == truth)
        if result.decision is MatchDecision.AUTO_MATCH:
            auto_count += 1
            auto_correct += int(bool(truth and result.matched_product_id == truth))
    return {
        "count": len(listings),
        "matchable": top_eligible,
        "top1_accuracy": round(_safe_divide(top_correct, top_eligible), 6),
        "auto_match_accuracy": round(_safe_divide(auto_correct, auto_count), 6),
        "auto_match_count": auto_count,
    }


def evaluate_matcher(
    matcher: EntityMatcher,
    listings: Iterable[ProductListing],
    ks: Sequence[int] = (1, 3, 5),
    calibration_bins: int = 10,
) -> dict[str, Any]:
    """Evaluate one already-fitted matcher using a single inference pass."""

    offers = list(listings)
    if not offers:
        raise ValueError("evaluation requires at least one listing")
    normalized_ks = tuple(sorted({int(k) for k in ks if int(k) > 0}))
    if not normalized_ks:
        raise ValueError("at least one positive ranking K is required")
    if calibration_bins < 2:
        raise ValueError("calibration_bins must be at least 2")
    top_k = max(normalized_ks)
    results = matcher.match_many(offers, top_k=top_k)
    catalog_ids = set(matcher.catalog_ids)
    latency = [result.latency_ms for result in results]

    slices: dict[str, Any] = {}
    masks = {
        "seen": [not item.unseen and bool(item.canonical_product_id) for item in offers],
        "unseen": [item.unseen and bool(item.canonical_product_id) for item in offers],
        "unknown": [not item.canonical_product_id for item in offers],
    }
    for name, mask in masks.items():
        slice_offers = [item for item, include in zip(offers, mask, strict=True) if include]
        slice_results = [item for item, include in zip(results, mask, strict=True) if include]
        slices[name] = _slice_summary(slice_offers, slice_results, catalog_ids)

    failures = []
    review_cases = []
    for listing, result in zip(offers, results, strict=True):
        truth = listing.canonical_product_id
        top_id = result.candidates[0].product_id
        known_truth = bool(truth and truth in catalog_ids)
        if result.decision is MatchDecision.REVIEW:
            review_cases.append(
                {
                    "listing_id": listing.listing_id,
                    "truth": truth,
                    "top_candidate": top_id,
                    "confidence": result.confidence,
                    "top_candidate_correct": bool(known_truth and top_id == truth),
                }
            )
        if (
            (known_truth and top_id != truth)
            or (not known_truth and result.decision is MatchDecision.AUTO_MATCH)
            or (known_truth and result.decision in {MatchDecision.REVIEW, MatchDecision.NO_MATCH})
        ):
            if known_truth and top_id != truth:
                failure_type = "wrong_top_candidate"
            elif known_truth and result.decision is MatchDecision.REVIEW:
                failure_type = "routed_to_review"
            elif known_truth:
                failure_type = "missed_known_match"
            else:
                failure_type = "false_auto_match"
            failures.append(
                {
                    "listing_id": listing.listing_id,
                    "truth": truth,
                    "top_candidate": top_id,
                    "decision": result.decision.value,
                    "confidence": result.confidence,
                    "failure_type": failure_type,
                }
            )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "model": matcher.metadata(),
        "dataset": {
            "listings": len(offers),
            "known_entities": sum(item.canonical_product_id in catalog_ids for item in offers),
            "unknown_entities": sum(
                item.canonical_product_id not in catalog_ids for item in offers
            ),
            "unseen_entities": sum(item.unseen for item in offers),
        },
        "policy": {
            "auto_match": f">={matcher.config.auto_match_threshold}",
            "review": f">={matcher.config.review_threshold} and <{matcher.config.auto_match_threshold}",
            "no_match": f"<{matcher.config.review_threshold}",
            "minimum_auto_margin": matcher.config.minimum_auto_margin,
        },
        "classification": _classification(offers, results, catalog_ids),
        "ranking": _ranking(offers, results, catalog_ids, normalized_ks),
        "calibration": _calibration(offers, results, catalog_ids, calibration_bins),
        "latency_ms": {
            "mean": round(fmean(latency), 4),
            "p50": round(_percentile(latency, 0.50), 4),
            "p95": round(_percentile(latency, 0.95), 4),
            "min": round(min(latency), 4),
            "max": round(max(latency), 4),
        },
        "slices": slices,
        "failures": failures[:100],
        "review_cases": review_cases[:100],
    }
