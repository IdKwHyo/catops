# Benchmark results

## Evidence status

This page intentionally separates a **sample smoke run** from the **full WDC benchmark**. A green local demo is not evidence of real marketplace accuracy.

| Evaluation | Dataset | Purpose | Status |
| --- | --- | --- | --- |
| Sample smoke | Checked-in `data/sample/` records | Verify pipeline, metrics, and deterministic reporting | Generated and checked in |
| WDC full | Official WDC Products configuration | Measure generalization and compare model variants | **TBD — not yet run/published** |
| Load test | Local health endpoint, 500 requests at concurrency 20 | Exercise the HTTP service and load-test harness | Recorded below; not an inference benchmark |

No number on this page should be copied from the WDC paper or another implementation and presented as CatalogOps performance.

## Sample smoke run

Run `make evaluate` from a clean checkout, or invoke the evaluator directly after installing the Python 3.12 runtime dependencies:

```bash
python -m evaluation.run \
  --offers data/sample/offers.jsonl \
  --catalog data/sample/catalog.csv \
  --output evaluation/results/sample-baseline.json \
  --check-thresholds
```

Result artifact: `evaluation/results/sample-baseline.json`.

Fixture identity for this recorded result:

| Artifact | SHA-256 |
| --- | --- |
| `data/sample/catalog.csv` | `f570b091a3402de7de03603c74b49b938ca4ec058d877e31cb6c74cf208cae0f` |
| `data/sample/offers.jsonl` | `0084d05932986e503b458f19bafd8a0d7ca0adb638c0afefc1328bd13c56f5f3` |

The generated report contains a timestamp and machine-dependent latency values, so its file hash changes on a valid rerun. Record that report hash in a tagged-release manifest rather than treating it as a dataset identity.

| Metric | Smoke result | Interpretation |
| --- | ---: | --- |
| Training / test offers | 22 / 19 | Original hand-authored fixture; 12 catalog entities |
| Test composition | 13 matchable / 6 unknown | Three matchable test offers are marked unseen in training |
| Precision | 1.000000 | 12 automatic matches, all correct |
| Recall | 0.923077 | One correct candidate was routed to review and counts as a selective false negative |
| F1 | 0.960000 | Auto-match decision metric, not top-1 accuracy |
| Recall@1 / @3 / @5 | 1.000000 / 1.000000 / 1.000000 | All 13 matchable truths were retrieved first |
| MRR | 1.000000 | Ranking check on 13 eligible queries |
| ECE / Brier | 0.077617 / 0.015338 | Computed output; sample is far too small to establish calibration |
| Auto / review / no-match rate | 0.631579 / 0.052632 / 0.315789 | 12 / 1 / 6 test decisions |
| p50 / p95 inference latency | 11.2589 / 17.3127 ms | Informational checked-in local run; not a load test |

The fitted backend was `catalogops-tfidf-logreg-v1`. It generated 194 training pairs from the 22 training offers (18 positive, 176 negative). The only selective-classification failure was `O1019`: its correct top candidate `P1005` scored `0.788210` and was safely routed to review rather than auto-matched.

The result should be treated as a test fixture. Its high ranking score reflects a tiny original dataset with clear catalog titles and identifiers. The report embeds `allow_all_split_fallback=false`, both dataset hashes, Python `3.12.13`, scikit-learn `1.8.0`, and joblib `1.5.3`. Latency is not a load test and can vary between runs; hardware and concurrency were not recorded, so it cannot support infrastructure comparison.

## Local HTTP load smoke

The committed `evaluation/results/api-load-test.json` records a bounded run against a locally started API health endpoint: 500 requests at concurrency 20, 0% errors, 423.28 requests/second, p50 38.82 ms, and p95 103.57 ms. The harness enforced a 1% maximum error rate and 500 ms p95 ceiling.

This proves only that the load-test script and HTTP path executed successfully in that local runtime. It did not call model inference, its transient server ran at `127.0.0.1:8765`, and the artifact does not record hardware or container overhead. Do not use it as production capacity evidence. Re-run against `/api/v1/matches/predict` with a representative payload, declared hardware, warm-up, and storage settings before publishing a serving SLO.

### Dependency-free fallback smoke ablation

The deterministic fallback can be reproduced without replacing the committed classifier report:

```bash
python -m evaluation.run \
  --force-lexical \
  --output /tmp/catalogops-sample-lexical.json
```

| Sample-only model | Precision | Recall | F1 | R@1/3/5 | MRR | ECE | Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TF-IDF + logistic regression | 1.000000 | 0.923077 | 0.960000 | 1 / 1 / 1 | 1.000000 | 0.077617 | 0.015338 |
| Dependency-free lexical fallback | 1.000000 | 0.846154 | 0.916667 | 1 / 1 / 1 | 1.000000 | 0.075511 | 0.040172 |

This is an implementation smoke ablation, not a meaningful statistical comparison. It suggests only that, on this fixture and policy, the fitted classifier automates one additional correct match. The fallback has a different score distribution and model ID; production thresholds would need independent validation.

## Full WDC Products benchmark

Status: **TBD**.

The official [WDC Products benchmark](https://webdatacommons.org/largescaleproductcorpus/wdc-products/) reports 11,715 offers and 2,162 entities, with nine train/validation/test sets combinable into 27 variants. CatalogOps must name the exact WDC configuration and corner-case setting for every result.

Planned command after downloading and importing one declared configuration:

```bash
python -m pipelines.prepare_wdc /path/to/train.json.gz \
  --split train \
  --catalog-output data/processed/catalog.csv \
  --offers-output data/processed/train.jsonl \
  --catalog-split train

python -m pipelines.prepare_wdc /path/to/test.json.gz \
  --split test \
  --catalog-output data/processed/test-catalog-unused.csv \
  --offers-output data/processed/test.jsonl \
  --catalog-split train

cat data/processed/train.jsonl data/processed/test.jsonl \
  > data/processed/offers.jsonl

python -m evaluation.run \
  --catalog data/processed/catalog.csv \
  --offers data/processed/offers.jsonl \
  --train-split train \
  --eval-split test \
  --output evaluation/results/wdc-full.json
```

This is the current multi-class import/evaluation path. Prepare and use the official validation split for model/threshold selection. Pairwise WDC evaluation requires an explicit pairwise protocol and is not claimed by this table.

### Results table — intentionally unfilled

| Model | WDC configuration | Precision | Recall | F1 | R@1 | R@5 | MRR | ECE | p50/p95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Lexical/TF-IDF baseline | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Bi-encoder retrieval | Not implemented/measured | — | — | — | — | — | — | — | — |
| + cross-encoder reranker | Not implemented/measured | — | — | — | — | — | — | — | — |

### Required experiment metadata

Publish every WDC result with:

- dataset source URL, filename, download timestamp, and SHA-256;
- WDC configuration, corner case, split semantics, and split counts;
- repository commit, dependency lock, model/artifact checksum, and random seed;
- fitting/tuning/calibration splits;
- candidate-catalog construction rules;
- threshold policy and whether metrics are pair, offer, micro, or macro averaged;
- CPU/GPU, RAM, operating system/container, thread count, and batch size;
- warm-up, number of runs, concurrency, and whether I/O is included;
- error slices for unseen entities, category/language/source, and missing fields where available.

## Ablation plan

Use identical splits and report both quality and operational cost:

| Experiment | Change from previous | Primary question |
| --- | --- | --- |
| A | Normalized lexical rules | What does deterministic normalization achieve? |
| B | TF-IDF + classifier | Does learned pair scoring improve final F1/precision? |
| C | Bi-encoder retrieval | Does semantic retrieval improve Recall@K on sparse/unseen offers? |
| D | Cross-encoder reranking | What precision gain justifies added p95 latency/cost? |
| E | Calibration + threshold policy | What automation coverage is possible at a required precision? |

Report confidence intervals or repeated-run variation where meaningful. Do not tune each model against the test set.

## Decision-policy evaluation

Model metrics alone do not show business behavior. For each validated threshold pair, publish:

- automatic-match coverage and precision;
- review rate, queue volume per 1,000 offers, and reviewer yield;
- no-match rate and false-negative rate;
- expected cost under declared false-match, missed-match, and review costs;
- slices that receive disproportionately high review/no-match routing.

The default `0.85` / `0.55` thresholds are demo configuration only. They remain unvalidated for WDC until this section contains a result artifact.

## Latency and cost protocol

For model-only latency, pre-load artifacts and time normalization, candidate scoring, and reranking separately. For API latency, include serialization and storage and report concurrency. Publish p50, p95, p99, throughput, error rate, and sample count.

Cost per 1,000 listings must state:

- hardware or cloud SKU and region/pricing timestamp;
- average candidate count and batch size;
- amortization/window and utilization assumption;
- whether storage, network, idle capacity, and human review are included.

Until those assumptions exist, cost is **TBD**, not zero.

## Publication gate

A result graduates from smoke/TBD to published only when:

- [ ] exact command succeeds from a clean checkout;
- [ ] dataset and model hashes are recorded;
- [ ] official split semantics are preserved;
- [ ] test data was not used for fitting or threshold selection;
- [ ] machine-readable result artifact is committed or permanently linked;
- [ ] environment and latency protocol are declared;
- [ ] result is compared with the checked-in baseline on identical data;
- [ ] known failure modes and error slices are summarized.
