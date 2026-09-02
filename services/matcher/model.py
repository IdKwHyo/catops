"""Deterministic TF-IDF retrieval and pair-classification baseline."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .features import PairFeatureExtractor, evidence_reasons
from .normalization import normalize_text
from .schemas import (
    CanonicalProduct,
    MatchCandidate,
    MatchDecision,
    MatchResult,
    ProductListing,
)

try:  # Optional by design: API imports still work in a minimal Python image.
    import joblib  # type: ignore[import-untyped]
    import sklearn  # type: ignore[import-untyped]
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
    from sklearn.pipeline import FeatureUnion  # type: ignore[import-untyped]
    from sklearn.preprocessing import normalize as sparse_normalize  # type: ignore[import-untyped]

    SKLEARN_AVAILABLE = True
    SKLEARN_VERSION: str | None = str(sklearn.__version__)
    JOBLIB_VERSION: str | None = str(joblib.__version__)
except ImportError:  # pragma: no cover - exercised in dependency-minimal images.
    joblib = None  # type: ignore[assignment]
    TfidfVectorizer = None  # type: ignore[assignment,misc]
    LogisticRegression = None  # type: ignore[assignment,misc]
    FeatureUnion = None  # type: ignore[assignment,misc]
    sparse_normalize = None  # type: ignore[assignment]
    SKLEARN_AVAILABLE = False
    SKLEARN_VERSION = None
    JOBLIB_VERSION = None


ARTIFACT_FORMAT_VERSION = 1
SKLEARN_MODEL_ID = "catalogops-tfidf-logreg-v1"
LEXICAL_MODEL_ID = "catalogops-lexical-v1"


@dataclass(frozen=True, slots=True)
class MatcherConfig:
    """Decision and training policy.

    Confidence >= 0.85 is auto-matched (subject to a small ambiguity margin),
    0.55--0.85 is reviewed, and lower confidence is rejected by default.
    """

    auto_match_threshold: float = 0.85
    review_threshold: float = 0.55
    minimum_auto_margin: float = 0.06
    candidate_pool_size: int = 25
    max_training_negatives: int = 8
    random_state: int = 42
    prefer_sklearn: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_threshold < self.auto_match_threshold <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= review < auto_match <= 1")
        if not 0.0 <= self.minimum_auto_margin <= 1.0:
            raise ValueError("minimum_auto_margin must be between 0 and 1")
        if self.candidate_pool_size < 1 or self.max_training_negatives < 1:
            raise ValueError("candidate pool and training negatives must be positive")


class EntityMatcher:
    """Auditable matcher with a stable API and an optional sklearn backend."""

    def __init__(self, config: MatcherConfig | None = None) -> None:
        self.config = config or MatcherConfig()
        self._catalog: dict[str, CanonicalProduct] = {}
        self._catalog_ids: list[str] = []
        self._vectorizer: Any = None
        self._catalog_matrix: Any = None
        self._classifier: Any = None
        self._extractor = PairFeatureExtractor()
        self._fitted = False
        self.model_id = LEXICAL_MODEL_ID
        self.training_summary: dict[str, Any] = {
            "backend": "lexical",
            "labeled_pairs": 0,
            "positive_pairs": 0,
            "negative_pairs": 0,
        }

    @property
    def catalog_size(self) -> int:
        return len(self._catalog)

    @property
    def catalog_ids(self) -> frozenset[str]:
        """Read-only IDs for evaluation and service health metadata."""

        return frozenset(self._catalog)

    @property
    def backend(self) -> str:
        if self._classifier is not None:
            return "tfidf_logistic_regression"
        if self._vectorizer is not None:
            return "tfidf_lexical_calibration"
        return "lexical_fallback"

    def fit(
        self,
        canonical_products: Iterable[CanonicalProduct],
        labeled_listings: Iterable[ProductListing] | None = None,
    ) -> EntityMatcher:
        """Fit retrieval over a catalog and optionally train the pair classifier."""

        products = sorted(canonical_products, key=lambda item: item.product_id)
        if not products:
            raise ValueError("at least one canonical product is required")
        ids = [product.product_id for product in products]
        if len(ids) != len(set(ids)):
            raise ValueError("canonical product_id values must be unique")

        self._catalog = {product.product_id: product for product in products}
        self._catalog_ids = ids
        brands = tuple(sorted({product.brand for product in products if product.brand}))
        self._extractor = PairFeatureExtractor(brands)
        self._classifier = None
        self._vectorizer = None
        self._catalog_matrix = None
        self.model_id = LEXICAL_MODEL_ID

        if self.config.prefer_sklearn and SKLEARN_AVAILABLE:
            self._fit_retrieval(products)

        listings = list(labeled_listings or ())
        if listings and self._vectorizer is not None:
            self._fit_supervised(listings)

        self._fitted = True
        return self

    def _fit_retrieval(self, products: Sequence[CanonicalProduct]) -> None:
        word = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            max_df=1.0,
            sublinear_tf=True,
            lowercase=False,
            strip_accents=None,
        )
        char = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            sublinear_tf=True,
            lowercase=False,
            strip_accents=None,
        )
        self._vectorizer = FeatureUnion(
            [("word", word), ("char", char)], transformer_weights={"word": 0.65, "char": 0.35}
        )
        # FeatureUnion feeds the same input to multiple transformers; materialize
        # once so its word branch cannot exhaust a generator before the char branch.
        documents = [self._product_document(product) for product in products]
        matrix = self._vectorizer.fit_transform(documents)
        self._catalog_matrix = sparse_normalize(matrix, copy=False)

    def _fit_supervised(self, listings: Sequence[ProductListing]) -> None:
        vectors: list[list[float]] = []
        labels: list[int] = []
        for listing in sorted(listings, key=lambda item: item.listing_id):
            truth = listing.canonical_product_id
            truth_is_known = truth in self._catalog
            retrieval = self._retrieval_scores(listing)
            ranked = self._rank_retrieval(
                retrieval,
                max(self.config.candidate_pool_size, self.config.max_training_negatives),
            )
            selected: list[str] = []
            if truth_is_known:
                selected.append(str(truth))
            for product_id, _ in ranked:
                pair_limit = self.config.max_training_negatives + int(truth_is_known)
                if product_id != truth and len(selected) < pair_limit:
                    selected.append(product_id)
            for product_id in selected:
                features = self._extractor.extract(
                    listing, self._catalog[product_id], retrieval.get(product_id, 0.0)
                )
                vectors.append(self._extractor.vector(features))
                labels.append(int(product_id == truth and truth_is_known))
        self._train_classifier(vectors, labels)

    def fit_pair_examples(
        self,
        examples: Iterable[tuple[ProductListing, CanonicalProduct, int | bool]],
    ) -> EntityMatcher:
        """Train from WDC-style labeled pairs after ``fit(catalog)``.

        This is useful for pairwise WDC variants where the right offer is treated
        as the candidate. Retrieval is still fitted on the canonical catalog.
        """

        self._require_fitted_catalog()
        vectors: list[list[float]] = []
        labels: list[int] = []
        for listing, product, label in examples:
            retrieval_score = self._lexical_retrieval(listing, product)
            features = self._extractor.extract(listing, product, retrieval_score)
            vectors.append(self._extractor.vector(features))
            labels.append(int(bool(label)))
        self._train_classifier(vectors, labels)
        self._fitted = True
        return self

    def _train_classifier(self, vectors: list[list[float]], labels: list[int]) -> None:
        positives = sum(labels)
        negatives = len(labels) - positives
        if not vectors or not positives or not negatives or not SKLEARN_AVAILABLE:
            self.training_summary = {
                "backend": self.backend,
                "labeled_pairs": len(labels),
                "positive_pairs": positives,
                "negative_pairs": negatives,
                "classifier_trained": False,
                "reason": "both positive and negative labels plus sklearn are required",
            }
            return
        self._classifier = LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=1000,
            random_state=self.config.random_state,
            solver="liblinear",
        )
        self._classifier.fit(vectors, labels)
        self.model_id = SKLEARN_MODEL_ID
        self.training_summary = {
            "backend": self.backend,
            "labeled_pairs": len(labels),
            "positive_pairs": positives,
            "negative_pairs": negatives,
            "classifier_trained": True,
            "feature_names": list(self._extractor.feature_names),
        }

    def match(self, listing: ProductListing, top_k: int = 5) -> MatchResult:
        """Rank candidates and convert confidence into a bounded decision."""

        self._require_fitted_catalog()
        if top_k < 1:
            raise ValueError("top_k must be positive")
        started = time.perf_counter()
        retrieval = self._retrieval_scores(listing)
        pool_size = min(len(self._catalog), max(top_k, self.config.candidate_pool_size))
        ranked_retrieval = self._rank_retrieval(retrieval, pool_size)
        scored: list[MatchCandidate] = []
        for product_id, retrieval_score in ranked_retrieval:
            product = self._catalog[product_id]
            features = self._extractor.extract(listing, product, retrieval_score)
            confidence = self._confidence(features)
            scored.append(
                MatchCandidate(
                    product_id=product_id,
                    title=product.title,
                    brand=product.brand,
                    confidence=round(confidence, 6),
                    retrieval_score=round(retrieval_score, 6),
                    reasons=evidence_reasons(features),
                    features={key: round(value, 6) for key, value in features.items()},
                )
            )
        scored.sort(key=lambda item: (-item.confidence, -item.retrieval_score, item.product_id))
        candidates = tuple(scored[: min(top_k, len(scored))])
        top = candidates[0]
        runner_up = scored[1].confidence if len(scored) > 1 else 0.0
        margin = max(0.0, top.confidence - runner_up)
        has_exact_identifier = top.features.get("identifier_exact", 0.0) >= 1.0

        if top.confidence >= self.config.auto_match_threshold and (
            margin >= self.config.minimum_auto_margin or has_exact_identifier
        ):
            decision = MatchDecision.AUTO_MATCH
            decision_reason = "confidence and ambiguity margin pass auto-match policy"
        elif top.confidence >= self.config.review_threshold:
            decision = MatchDecision.REVIEW
            decision_reason = (
                "candidate is plausible but requires human review"
                if top.confidence < self.config.auto_match_threshold
                else "high confidence but competing candidates are too close"
            )
        else:
            decision = MatchDecision.NO_MATCH
            decision_reason = "no candidate reaches the review threshold"

        proposed = top.product_id if decision is not MatchDecision.NO_MATCH else None
        matched = top.product_id if decision is MatchDecision.AUTO_MATCH else None
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return MatchResult(
            listing_id=listing.listing_id,
            decision=decision,
            proposed_product_id=proposed,
            matched_product_id=matched,
            confidence=top.confidence,
            margin=round(margin, 6),
            candidates=candidates,
            reasons=(decision_reason, *top.reasons),
            model_id=self.model_id,
            latency_ms=round(elapsed_ms, 4),
        )

    def match_many(self, listings: Iterable[ProductListing], top_k: int = 5) -> list[MatchResult]:
        return [self.match(listing, top_k=top_k) for listing in listings]

    def _confidence(self, features: dict[str, float]) -> float:
        if self._classifier is not None:
            vector = [self._extractor.vector(features)]
            value = float(self._classifier.predict_proba(vector)[0][1])
        else:
            raw = (
                0.30 * features["retrieval_score"]
                + 0.16 * features["token_jaccard"]
                + 0.13 * features["token_containment"]
                + 0.10 * features["character_ratio"]
                + 0.10 * features["brand_exact"]
                + 0.13 * features["identifier_exact"]
                + 0.05 * features["number_jaccard"]
                + 0.03 * features["description_jaccard"]
            )
            value = 1.0 / (1.0 + math.exp(-9.0 * (raw - 0.47)))

        # Hard structured evidence is intentionally explicit and auditable.
        if features["identifier_exact"] >= 1.0:
            value = max(value, 0.995)
        elif (
            features["brand_exact"] >= 1.0
            and features["retrieval_score"] >= 0.78
            and features["token_containment"] >= 0.70
        ):
            value = max(value, 0.90)
        if features["identifier_conflict"] >= 1.0:
            value = min(value, 0.22)
        if features["brand_conflict"] >= 1.0:
            value = min(value, 0.48)
        return max(0.0, min(1.0, value))

    def _retrieval_scores(self, listing: ProductListing) -> dict[str, float]:
        if self._vectorizer is not None and self._catalog_matrix is not None:
            query = self._vectorizer.transform([self._listing_document(listing)])
            query = sparse_normalize(query, copy=False)
            values = (query @ self._catalog_matrix.T).toarray()[0]
            return {
                product_id: max(0.0, min(1.0, float(values[index])))
                for index, product_id in enumerate(self._catalog_ids)
            }
        return {
            product_id: self._lexical_retrieval(listing, self._catalog[product_id])
            for product_id in self._catalog_ids
        }

    @staticmethod
    def _rank_retrieval(scores: dict[str, float], limit: int) -> list[tuple[str, float]]:
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]

    def _lexical_retrieval(self, listing: ProductListing, product: CanonicalProduct) -> float:
        features = self._extractor.extract(listing, product, 0.0)
        value = (
            0.40 * features["token_jaccard"]
            + 0.25 * features["token_containment"]
            + 0.20 * features["character_ratio"]
            + 0.10 * features["brand_exact"]
            + 0.05 * features["number_jaccard"]
        )
        return max(0.0, min(1.0, value))

    @staticmethod
    def _product_document(product: CanonicalProduct) -> str:
        identifier_text = " ".join(product.identifiers.values())
        return normalize_text(
            f"{product.brand} {product.title} {identifier_text} {product.category} {product.description[:300]}"
        )

    @staticmethod
    def _listing_document(listing: ProductListing) -> str:
        identifier_text = " ".join(listing.identifiers.values())
        return normalize_text(
            f"{listing.brand} {listing.title} {identifier_text} {listing.description[:300]}"
        )

    def _require_fitted_catalog(self) -> None:
        if not self._catalog:
            raise RuntimeError("matcher is not fitted; call fit(canonical_products) first")

    def metadata(self) -> dict[str, Any]:
        self._require_fitted_catalog()
        return {
            "model_id": self.model_id,
            "backend": self.backend,
            "catalog_size": self.catalog_size,
            "sklearn_available": SKLEARN_AVAILABLE,
            "runtime": {
                "python": platform.python_version(),
                "sklearn": SKLEARN_VERSION,
                "joblib": JOBLIB_VERSION,
            },
            "config": asdict(self.config),
            "training": self.training_summary,
            "feature_names": list(self._extractor.feature_names),
        }

    def save(
        self,
        artifact_directory: str | Path,
        provenance: Mapping[str, Any] | None = None,
    ) -> Path:
        """Persist catalog, config, checksums, and optional sklearn state.

        ``model.joblib`` must only be loaded from a trusted CatalogOps artifact
        directory; its SHA-256 is verified before deserialization.
        """

        self._require_fitted_catalog()
        destination = Path(artifact_directory)
        destination.mkdir(parents=True, exist_ok=True)
        catalog_path = destination / "catalog.jsonl"
        catalog_payload = "".join(
            json.dumps(self._catalog[product_id].to_dict(), sort_keys=True) + "\n"
            for product_id in self._catalog_ids
        )
        catalog_path.write_text(catalog_payload, encoding="utf-8")
        checksums = {catalog_path.name: _sha256(catalog_path)}

        if self._vectorizer is not None and joblib is not None:
            model_path = destination / "model.joblib"
            joblib.dump(
                {
                    "vectorizer": self._vectorizer,
                    "catalog_matrix": self._catalog_matrix,
                    "classifier": self._classifier,
                    "training_summary": self.training_summary,
                    "model_id": self.model_id,
                },
                model_path,
                compress=3,
            )
            checksums[model_path.name] = _sha256(model_path)

        manifest = {
            "artifact_format_version": ARTIFACT_FORMAT_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": self.metadata(),
            "provenance": dict(provenance or {}),
            "checksums": checksums,
        }
        manifest_path = destination / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return destination

    @classmethod
    def load(cls, artifact_directory: str | Path) -> EntityMatcher:
        source = Path(artifact_directory)
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("artifact_format_version") != ARTIFACT_FORMAT_VERSION:
            raise ValueError("unsupported matcher artifact format")
        checksums = manifest.get("checksums", {})
        if not isinstance(checksums, dict) or "catalog.jsonl" not in checksums:
            raise ValueError("artifact manifest is missing the catalog checksum")
        unexpected = set(checksums) - {"catalog.jsonl", "model.joblib"}
        if unexpected:
            raise ValueError(f"artifact manifest contains unexpected files: {sorted(unexpected)}")
        for filename, expected in checksums.items():
            path = source / filename
            if not path.is_file() or _sha256(path) != expected:
                raise ValueError(f"artifact checksum mismatch: {filename}")

        config = MatcherConfig(**manifest["metadata"]["config"])
        matcher = cls(config)
        products = [
            CanonicalProduct.from_mapping(json.loads(line))
            for line in (source / "catalog.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        matcher.fit(products)
        model_path = source / "model.joblib"
        # Ignore a stale unmanifested file if a lexical artifact reused a
        # directory previously occupied by an sklearn artifact.
        if "model.joblib" in checksums and joblib is not None and SKLEARN_AVAILABLE:
            payload = joblib.load(model_path)
            matcher._vectorizer = payload["vectorizer"]
            matcher._catalog_matrix = payload["catalog_matrix"]
            matcher._classifier = payload["classifier"]
            matcher.training_summary = payload["training_summary"]
            matcher.model_id = payload["model_id"]
        matcher._fitted = True
        return matcher


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
