"""Reproducible evaluation-metric contracts for model comparison and CI gates."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from evaluation.metrics import evaluate_matcher
from services.matcher import (
    EntityMatcher,
    MatchCandidate,
    MatchDecision,
    MatchResult,
    ProductListing,
)


def _candidate(product_id: str, confidence: float) -> MatchCandidate:
    return MatchCandidate(
        product_id=product_id,
        title=f"Product {product_id}",
        brand="Acme",
        confidence=confidence,
        retrieval_score=confidence,
    )


def _result(
    listing_id: str,
    decision: MatchDecision,
    confidence: float,
    ranked_ids: tuple[str, ...],
    *,
    latency_ms: float,
) -> MatchResult:
    proposed = ranked_ids[0] if decision is not MatchDecision.NO_MATCH else None
    matched = ranked_ids[0] if decision is MatchDecision.AUTO_MATCH else None
    return MatchResult(
        listing_id=listing_id,
        decision=decision,
        proposed_product_id=proposed,
        matched_product_id=matched,
        confidence=confidence,
        margin=0.1,
        candidates=tuple(_candidate(item, confidence) for item in ranked_ids),
        reasons=("test fixture",),
        model_id="fixture-model",
        latency_ms=latency_ms,
    )


@dataclass
class DeterministicMatcher:
    """Small matcher double that isolates arithmetic from ranking implementation."""

    results: list[MatchResult]

    catalog_ids = frozenset({"p1", "p2"})
    config = SimpleNamespace(
        auto_match_threshold=0.85,
        review_threshold=0.55,
        minimum_auto_margin=0.06,
    )

    def match_many(self, listings, top_k: int = 5) -> list[MatchResult]:
        assert len(list(listings)) == len(self.results)
        assert top_k == 2
        return self.results

    def metadata(self) -> dict[str, object]:
        return {"model_id": "fixture-model", "catalog_size": 2}


def test_evaluate_matcher_calculates_classification_ranking_calibration_and_slices() -> None:
    listings = [
        ProductListing("l1", "one", canonical_product_id="p1"),
        ProductListing("l2", "two", canonical_product_id="p2", unseen=True),
        ProductListing("l3", "unknown"),
        ProductListing("l4", "four", canonical_product_id="p2"),
    ]
    matcher = DeterministicMatcher(
        [
            _result("l1", MatchDecision.AUTO_MATCH, 0.9, ("p1", "p2"), latency_ms=10),
            _result("l2", MatchDecision.AUTO_MATCH, 0.8, ("p1", "p2"), latency_ms=20),
            _result("l3", MatchDecision.AUTO_MATCH, 0.7, ("p1", "p2"), latency_ms=30),
            _result("l4", MatchDecision.REVIEW, 0.6, ("p2", "p1"), latency_ms=40),
        ]
    )

    report = evaluate_matcher(matcher, listings, ks=(2, 1, 2), calibration_bins=2)

    assert report["classification"] == {
        "precision": 0.333333,
        "recall": 0.333333,
        "f1": 0.333333,
        "true_positive": 1,
        "false_positive": 2,
        "false_negative": 2,
        "auto_match_predictions": 3,
        "matchable_listings": 3,
        "auto_match_coverage": 0.75,
        "review_rate": 0.25,
        "no_match_rate": 0.0,
        "decision_counts": {"auto_match": 3, "review": 1},
    }
    assert report["ranking"] == {
        "eligible_queries": 3,
        "recall_at_k": {"1": 0.666667, "2": 1.0},
        "mrr": 0.833333,
    }
    assert report["calibration"]["ece"] == 0.25
    assert sum(item["count"] for item in report["calibration"]["bins"]) == 4
    assert report["latency_ms"] == {
        "mean": 25.0,
        "p50": 25.0,
        "p95": 38.5,
        "min": 10,
        "max": 40,
    }
    assert report["slices"]["seen"] == {
        "count": 2,
        "matchable": 2,
        "top1_accuracy": 1.0,
        "auto_match_accuracy": 1.0,
        "auto_match_count": 1,
    }
    assert report["slices"]["unseen"]["top1_accuracy"] == 0.0
    assert report["slices"]["unknown"]["matchable"] == 0
    failures = {failure["listing_id"]: failure for failure in report["failures"]}
    assert set(failures) == {"l2", "l3", "l4"}
    assert failures["l2"]["failure_type"] == "wrong_top_candidate"
    assert failures["l3"]["failure_type"] == "false_auto_match"
    assert failures["l4"]["failure_type"] == "routed_to_review"
    assert report["review_cases"] == [
        {
            "listing_id": "l4",
            "truth": "p2",
            "top_candidate": "p2",
            "confidence": 0.6,
            "top_candidate_correct": True,
        }
    ]


def test_evaluate_matcher_integrates_with_real_matcher(
    lexical_matcher: EntityMatcher,
) -> None:
    listings = [
        ProductListing(
            "seen",
            "Acme blue trail shoe 42",
            brand="Acme",
            identifiers={"mpn": "AC-42-B"},
            canonical_product_id="p-blue",
        ),
        ProductListing(
            "unseen",
            "Zen prime camera lens 50mm",
            brand="Zen",
            identifiers={"mpn": "ZEN-50-MM"},
            canonical_product_id="p-lens",
            unseen=True,
        ),
        ProductListing("unknown", "Generic kitchen storage bundle"),
    ]

    report = evaluate_matcher(lexical_matcher, listings, ks=(1, 2), calibration_bins=5)

    assert report["dataset"] == {
        "listings": 3,
        "known_entities": 2,
        "unknown_entities": 1,
        "unseen_entities": 1,
    }
    assert report["classification"]["precision"] == 1.0
    assert report["classification"]["recall"] == 1.0
    assert report["ranking"]["recall_at_k"] == {"1": 1.0, "2": 1.0}
    assert report["ranking"]["mrr"] == 1.0
    assert report["slices"]["seen"]["count"] == 1
    assert report["slices"]["unseen"]["count"] == 1
    assert report["slices"]["unknown"]["count"] == 1


@pytest.mark.parametrize(
    ("listings", "ks", "bins", "message"),
    [
        ([], (1,), 10, "at least one listing"),
        ([ProductListing("l1", "item")], (0, -1), 10, "positive ranking K"),
        ([ProductListing("l1", "item")], (1,), 1, "at least 2"),
    ],
)
def test_evaluate_matcher_rejects_invalid_evaluation_policy(
    listings: list[ProductListing],
    ks: tuple[int, ...],
    bins: int,
    message: str,
) -> None:
    matcher = DeterministicMatcher([])

    with pytest.raises(ValueError, match=message):
        evaluate_matcher(matcher, listings, ks=ks, calibration_bins=bins)
