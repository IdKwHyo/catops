# Matcher service

```python
from services.matcher import EntityMatcher, MatcherConfig
from pipelines.ingest import load_canonical_products, load_product_listings

catalog = load_canonical_products("data/sample/catalog.csv")
offers = load_product_listings("data/sample/offers.jsonl")
matcher = EntityMatcher(MatcherConfig()).fit(
    catalog, [offer for offer in offers if offer.split == "train"]
)
result = matcher.match(offers[-1], top_k=5)
print(result.to_dict())
```

The stable output fields are `listing_id`, `decision`,
`proposed_product_id`, `matched_product_id`, `confidence`, `margin`,
`candidates`, `reasons`, `model_id`, and `latency_ms`. A review result proposes
a product but does not claim a match; only an `auto_match` result sets
`matched_product_id`.

Default policy:

- confidence >= 0.85 and sufficient runner-up margin: `auto_match`
- confidence >= 0.55: `review`
- confidence < 0.55: `no_match`

Exact identifiers can satisfy the ambiguity guard, while conflicting identifiers
or brands cap confidence. Every candidate carries the feature values and concise
reasons used by the decision, making the baseline suitable for an audit UI.

## Backends and limitations

With scikit-learn, the service retrieves with normalized word/character TF-IDF
and trains a class-balanced logistic regression over interpretable pair features.
Without it, deterministic token/character scoring preserves the same API and
artifact format. The fallback is resilience, not equivalent model quality.

This Phase-1 baseline is English-oriented and does not resolve bundles, category
taxonomies, seller trust, or learned semantic synonyms. Price is retained for
analysis but deliberately excluded from matching because promotions and currency
conversion can create brittle leakage. Thresholds require calibration on each
market's representative validation set. Joblib artifacts must come from a
trusted source and are checksum-verified before loading.

