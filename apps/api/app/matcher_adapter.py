"""Adapter for ``services.matcher`` with a deterministic dependency-free fallback."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .config import Settings

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalise(value: str | None) -> str:
    return " ".join(TOKEN_RE.findall((value or "").lower()))


def _tokens(value: str | None) -> set[str]:
    return set(TOKEN_RE.findall((value or "").lower()))


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


@dataclass(slots=True)
class AdapterResult:
    decision: str
    confidence: float
    candidates: list[dict[str, Any]]
    evidence: list[str]
    model_version: str
    latency_ms: float


class MatcherAdapter:
    """Load the repository matcher when available; otherwise use a local baseline."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._matcher: Any | None = None
        self._catalog_fingerprint: tuple[tuple[str, str], ...] | None = None
        self._external_error: str | None = None

    @property
    def status(self) -> str:
        if self._matcher is not None:
            return "services.matcher"
        if self._external_error:
            return "fallback-baseline"
        return "fallback-ready"

    @property
    def active_model_version(self) -> str:
        """Return the identity of the scorer actually loaded by this process."""

        if self._matcher is not None:
            return str(getattr(self._matcher, "model_id", self.settings.model_version))
        if self._external_error:
            return "catalogops-api-lexical-fallback-v1"
        return self.settings.model_version

    def _ensure_external(self, catalog: list[dict[str, Any]]) -> Any | None:
        fingerprint = tuple((str(item["id"]), str(item["title"])) for item in catalog)
        if self._matcher is not None and fingerprint == self._catalog_fingerprint:
            return self._matcher
        try:
            from services.matcher import (  # type: ignore[import-not-found]
                CanonicalProduct,
                EntityMatcher,
                MatcherConfig,
            )

            artifact = self.settings.matcher_artifact_path
            if artifact and Path(artifact).exists():
                matcher = EntityMatcher.load(artifact)
            else:
                config = MatcherConfig(
                    auto_match_threshold=self.settings.auto_match_threshold,
                    review_threshold=self.settings.review_threshold,
                )
                products = []
                for item in catalog:
                    mapping = {
                        **item,
                        "product_id": item["id"],
                        "canonical_id": item["id"],
                    }
                    products.append(CanonicalProduct.from_mapping(mapping))
                matcher = EntityMatcher(config).fit(products)
            self._matcher = matcher
            self._catalog_fingerprint = fingerprint
            self._external_error = None
            return matcher
        except Exception as exc:  # The fallback is an explicit demo reliability feature.
            self._external_error = f"{type(exc).__name__}: {exc}"
            self._matcher = None
            return None

    def predict(
        self,
        listing: dict[str, Any],
        catalog: list[dict[str, Any]],
        *,
        top_k: int,
    ) -> AdapterResult:
        started = time.perf_counter()
        matcher = self._ensure_external(catalog)
        if matcher is not None:
            try:
                from services.matcher import ProductListing  # type: ignore[import-not-found]

                mapped_listing = {
                    **listing,
                    "listing_id": str(listing.get("offer_id") or "api-request"),
                    "id": str(listing.get("offer_id") or "api-request"),
                }
                result = matcher.match(ProductListing.from_mapping(mapped_listing), top_k=top_k)
                return self._normalise_external(result.to_dict(), catalog, started)
            except Exception as exc:
                self._external_error = f"{type(exc).__name__}: {exc}"
        return self._fallback(listing, catalog, top_k=top_k, started=started)

    def _normalise_external(
        self,
        raw: dict[str, Any],
        catalog: list[dict[str, Any]],
        started: float,
    ) -> AdapterResult:
        products = {str(item["id"]): item for item in catalog}
        candidates: list[dict[str, Any]] = []
        for candidate in raw.get("candidates", []):
            product_id = str(
                candidate.get("product_id")
                or candidate.get("canonical_product_id")
                or candidate.get("id")
            )
            product = products.get(product_id, {})
            candidates.append(
                {
                    "product_id": product_id,
                    "title": candidate.get("title") or product.get("title") or product_id,
                    "brand": candidate.get("brand") or product.get("brand"),
                    "score": _clamp(float(candidate.get("score", candidate.get("confidence", 0)))),
                    "evidence": list(candidate.get("evidence") or candidate.get("reasons") or []),
                }
            )
        decision = str(raw.get("decision", "no_match"))
        if decision == "reject":
            decision = "no_match"
        return AdapterResult(
            decision=decision,
            confidence=_clamp(float(raw.get("confidence", 0))),
            candidates=candidates,
            evidence=list(raw.get("reasons") or raw.get("evidence") or []),
            model_version=str(
                raw.get("model_id") or raw.get("model_version") or self.settings.model_version
            ),
            latency_ms=round(
                float(raw.get("latency_ms") or (time.perf_counter() - started) * 1000), 3
            ),
        )

    def _fallback(
        self,
        listing: dict[str, Any],
        catalog: list[dict[str, Any]],
        *,
        top_k: int,
        started: float,
    ) -> AdapterResult:
        query_title = _normalise(str(listing.get("title") or ""))
        query_tokens = _tokens(query_title)
        query_brand = _normalise(str(listing.get("brand") or ""))
        query_ids = {
            _normalise(str(value)) for value in (listing.get("mpn"), listing.get("gtin")) if value
        }
        scored: list[dict[str, Any]] = []
        for product in catalog:
            product_title = _normalise(str(product.get("title") or ""))
            product_tokens = _tokens(product_title)
            intersection = query_tokens & product_tokens
            union = query_tokens | product_tokens
            jaccard = len(intersection) / len(union) if union else 0.0
            coverage = len(intersection) / len(query_tokens) if query_tokens else 0.0
            sequence = SequenceMatcher(None, query_title, product_title).ratio()
            product_brand = _normalise(str(product.get("brand") or ""))
            if query_brand and product_brand:
                brand_score = 1.0 if query_brand == product_brand else 0.0
            else:
                brand_score = 0.45
            product_ids = {
                _normalise(str(value))
                for value in (product.get("mpn"), product.get("gtin"))
                if value
            }
            identifier_exact = bool(query_ids & product_ids)
            identifier_score = 1.0 if identifier_exact else (0.25 if not query_ids else 0.0)
            query_numbers = {token for token in query_tokens if any(ch.isdigit() for ch in token)}
            product_numbers = {
                token for token in product_tokens if any(ch.isdigit() for ch in token)
            }
            number_score = (
                len(query_numbers & product_numbers) / len(query_numbers) if query_numbers else 0.5
            )
            score = (
                0.28 * sequence
                + 0.26 * coverage
                + 0.10 * jaccard
                + 0.16 * brand_score
                + 0.15 * identifier_score
                + 0.05 * number_score
            )
            if identifier_exact:
                score += 0.12
            evidence = [
                f"title token coverage {coverage:.0%}",
                f"character similarity {sequence:.0%}",
            ]
            if query_brand:
                evidence.append("brand exact" if brand_score == 1 else "brand mismatch")
            if identifier_exact:
                evidence.append("exact manufacturer/GTIN identifier")
            if query_numbers:
                evidence.append(f"numeric token agreement {number_score:.0%}")
            scored.append(
                {
                    "product_id": str(product["id"]),
                    "title": str(product["title"]),
                    "brand": product.get("brand"),
                    "score": _clamp(score),
                    "evidence": evidence,
                }
            )
        scored.sort(key=lambda item: (-item["score"], item["product_id"]))
        candidates = scored[:top_k]
        confidence = candidates[0]["score"] if candidates else 0.0
        if confidence >= self.settings.auto_match_threshold:
            decision = "auto_match"
        elif confidence >= self.settings.review_threshold:
            decision = "review"
        else:
            decision = "no_match"
        evidence = list(candidates[0]["evidence"]) if candidates else ["catalog is empty"]
        if self._external_error:
            evidence.append("repository matcher unavailable; deterministic fallback used")
        return AdapterResult(
            decision=decision,
            confidence=confidence,
            candidates=candidates,
            evidence=evidence,
            model_version="catalogops-api-lexical-fallback-v1",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
