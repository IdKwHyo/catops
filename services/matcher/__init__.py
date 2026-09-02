"""Public interface for the deterministic CatalogOps baseline matcher.

The package intentionally keeps scikit-learn optional.  When it is installed the
matcher uses TF-IDF retrieval and a logistic-regression pair classifier; otherwise
the same API falls back to deterministic lexical ranking.
"""

from .model import EntityMatcher, MatcherConfig
from .schemas import (
    CanonicalProduct,
    MatchCandidate,
    MatchDecision,
    MatchResult,
    ProductListing,
)

__all__ = [
    "CanonicalProduct",
    "EntityMatcher",
    "MatchCandidate",
    "MatchDecision",
    "MatchResult",
    "MatcherConfig",
    "ProductListing",
]
