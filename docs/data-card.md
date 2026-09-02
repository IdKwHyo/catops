# Data card

## Summary

CatalogOps has two distinct data profiles:

| Profile | Purpose | Claim level |
| --- | --- | --- |
| Checked-in sample | Fast local smoke test and UI demonstration | Functional wiring only |
| WDC Products benchmark | Reproducible entity-matching evaluation | Supported import path; full results TBD |

The small sample must never be described as representative marketplace evidence. It exists so a reviewer can trace a prediction from source row through match evidence, review, incident response, and audit entry.

## Public benchmark

The target public dataset is the official [WDC Products benchmark](https://webdatacommons.org/largescaleproductcorpus/wdc-products/), derived from real product offers in the Web Data Commons product corpus.

The official benchmark page reports:

- 11,715 product offers;
- 2,162 canonical product entities;
- difficult corner cases and unseen entities;
- nine train/validation/test sets, combinable into 27 benchmark variants;
- compressed JSON Lines downloads and documented fields.

CatalogOps does not redistribute those downloads. Users should obtain them from the official source, retain source filenames/checksums, and comply with the benchmark's current terms and any underlying source obligations. A public URL is not itself a blanket license for unrelated commercial use.

## Sample records

The repository sample lives under `data/sample/` and is expected to contain:

- `catalog.csv`: canonical entity records;
- `offers.jsonl`: seller offers and known labels for smoke evaluation.

The sample is manually inspectable and may include purpose-built wording, abbreviation, punctuation, and variant cases. It is not scraped user data and should not contain personal information.

## Internal record model

Import maps source fields into a stable logical shape. Optional fields may be absent rather than filled with invented values.

| Field | Meaning | Required for matching |
| --- | --- | --- |
| `listing_id` | Stable source-offer identifier; imported from `listing_id`, `offer_id`, or source `id` | Yes |
| `title` | Seller-provided listing title | Yes |
| `brand` | Raw or extracted brand | No |
| `description` | Seller listing description | No |
| `identifiers` | GTIN/MPN/SKU-like values where available | No |
| `price` | Price and currency if retained | No |
| `source` | Source/domain or dataset namespace | Recommended |
| `canonical_product_id` | Canonical/ground-truth entity identifier | Evaluation only |
| `split` | Train, validation, or test designation | Evaluation only |
| `unseen` | Source flag used for held-out/unseen slicing | Evaluation only |

The importer preserves source IDs and split metadata wherever present. Unknown identifiers remain unknown; they must not be generated from title similarity.

Canonical catalog rows use `product_id`, `title`, and optional `brand`, `description`, `category`, `price`, `currency`, `identifiers`, and `attributes`. The multi-class loader recognizes common WDC aliases including `id`, `cluster_id`/`label`, `priceCurrency`, `brand`/`manufacturer`, and structured identifiers. Pairwise rows use `*_left`/`*_right` or nested `left`/`right` records plus a binary `label`; they intentionally take a separate parsing path.

## WDC import path

The optional downloader makes network access explicit and records the resulting file hash:

```bash
python -m pipelines.download_wdc --output data/wdc/80multi.zip
```

Prefer `--sha256 EXPECTED_HASH` when a hash has been verified independently. Extract the archive without committing it.

For one extracted WDC multi-class training split:

```bash
python -m pipelines.prepare_wdc /path/to/train.json.gz \
  --split train \
  --catalog-output data/processed/catalog.csv \
  --offers-output data/processed/train.jsonl \
  --catalog-split train
```

Prepare validation/test files separately with `--split validation` or `--split test`; write their unused catalog output to a separate path, then combine the unchanged JSON Lines offer outputs only after every row carries its split:

```bash
cat data/processed/train.jsonl \
  data/processed/validation.jsonl \
  data/processed/test.jsonl \
  > data/processed/offers.jsonl
```

The evaluator will fit the requested train split and evaluate the requested test split; it fails closed on a missing split unless the explicitly unsafe exploratory `--allow-all` flag is provided. The validation rows remain available for a separate, explicit threshold/calibration workflow; `evaluation.run` does not tune on them automatically.

Accepted inputs are CSV, JSON arrays, JSON Lines, and gzip-compressed variants. The importer normalizes container format and field names; it should not reshuffle official split membership.

Before publishing a result, record:

```text
source URL:
downloaded at (UTC):
source filename:
SHA-256:
WDC configuration / corner case:
split counts:
importer commit:
```

Then validate the processed artifact and evaluate without fitting on the test split:

```bash
python -m evaluation.run \
  --catalog data/processed/catalog.csv \
  --offers data/processed/offers.jsonl \
  --train-split train \
  --eval-split test \
  --output evaluation/results/wdc-full.json
```

The current preparation command processes one multi-class file at a time. `pipelines.ingest.load_wdc_pairs` safely parses WDC pairwise rows, but the main `evaluation.run` command is a multi-class catalog evaluation rather than a published pairwise WDC protocol. Do not claim pairwise benchmark coverage from the loader alone, concatenate split files before they are labeled, or treat a binary pair label as a cluster ID.

## Preparation policy

Permitted deterministic transformations include:

- Unicode normalization and case folding;
- whitespace and punctuation normalization;
- unit and common abbreviation normalization when rules are versioned;
- brand/identifier cleanup without fabricating missing fields;
- stable deduplication by documented source ID;
- parsing compressed JSON Lines without reordering split semantics.

Forbidden evaluation shortcuts include:

- learning vocabulary, calibration, or thresholds on the held-out test split;
- merging train and test records before candidate construction when the configuration tests unseen entities;
- deleting difficult negatives based on model output;
- reporting metrics on a hand-selected subset without labeling it as such;
- using canonical labels in features or prompts at inference time.

## Splits and leakage controls

WDC configurations differ in whether entities are seen or unseen and in the corner cases they emphasize. Results must name the exact configuration. An aggregate number without configuration and split semantics is not comparable.

Leakage checks should include:

- identical `listing_id` values across splits;
- exact or normalized-title duplicates across splits;
- entity overlap relative to the intended seen/unseen protocol;
- identifiers copied from labels into model inputs;
- fitted normalizers or calibrators that have observed test labels.

## Quality and representativeness

Product catalogs are long-tailed and change over time. WDC is useful because it provides real offers and controlled splits, but it does not establish performance for every language, region, taxonomy, seller behavior, image modality, or current marketplace.

Known sources of error include:

- missing or incorrect brands and identifiers;
- pack-size, capacity, color, regional, and generation variants;
- accessory-versus-main-product confusion;
- reused titles and seller keyword stuffing;
- multilingual or transliterated listings;
- stale canonical catalogs;
- label noise and ambiguous product identity.

## Privacy, safety, and governance

This project is designed for product metadata, not customer profiles. Do not import buyer/seller contact details, free-form messages, addresses, credentials, or payment data. If a real catalog contains personal information, establish a lawful basis, minimize fields, restrict access, define retention, and create deletion/export procedures before ingestion.

Dataset artifacts should be versioned by content hash. Production training access should be separate from online serving access. Reviewer corrections are valuable labels but can also be poisoned; preserve actor, timestamp, prior value, and sampling policy, and audit label-quality disagreements.

## Maintenance

A publishable benchmark run should freeze:

- source and processed-data checksums;
- importer and matcher commits;
- split/configuration identifier;
- dependency lockfiles;
- random seeds;
- hardware/runtime details;
- result JSON and human-readable report.

Any material transformation change requires a new data-card revision and a new evaluation artifact.
