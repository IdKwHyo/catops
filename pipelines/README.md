# Data and training pipelines

The loaders accept CSV, JSON arrays, JSON Lines, and gzip-compressed variants.
They support WDC multi-class fields (`id`, `brand`, `title`, `description`,
`price`, `priceCurrency`, `cluster_id`/`label`, `unseen`) and pairwise fields
(`*_left`, `*_right`, `pair_id`, `label`, `is_hard_negative`). No network call
runs during import, training, testing, or evaluation.

```bash
# Instant local sample
python -m pipelines.train_baseline

# Optional, explicit official benchmark download (not bundled)
python -m pipelines.download_wdc --output data/wdc/80multi.zip

# Prepare an extracted WDC JSONL split
python -m pipelines.prepare_wdc train.json.gz \
  --split train --catalog-output data/wdc/catalog.csv \
  --offers-output data/wdc/train.jsonl
```

`train_baseline` persists a checksum manifest, normalized catalog, and—when
scikit-learn is installed—the TF-IDF vectorizers and logistic-regression state.
Only load joblib artifacts created by a trusted CatalogOps run.

When deriving a canonical catalog from clustered offers, representatives are
selected from `train` by default. Validation/test-only clusters are not promoted
into the catalog, preventing display-text leakage. Pass another
`--catalog-split` only when the benchmark protocol explicitly permits it.
Preparing a validation/test-only file therefore writes a header-only catalog;
that catalog is intentionally unused while its split-labeled offers are combined
with the training offers for evaluation.
