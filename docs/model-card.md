# Model card

## Model details

| Item | Value |
| --- | --- |
| Name | CatalogOps lexical product matcher |
| Model identifier | `catalogops-tfidf-logreg-v1` when the trained classifier artifact is available |
| No-artifact baseline | `catalogops-lexical-v1` |
| API-local degraded fallback | `catalogops-api-lexical-fallback-v1` |
| Task | Candidate product entity matching from messy offer metadata |
| Output | Ranked candidates, score/evidence, and policy route |
| Status | Local baseline; not approved for unattended production matching |

This card describes the checked-in reproducible baseline. It does **not** claim that a sentence-transformer retriever, `pgvector` index, cross-encoder, or statistically calibrated probability is already deployed. Those components should receive separate cards and result artifacts when implemented.

### Serving versus evaluation

| Path | Reported model ID | What runs |
| --- | --- | --- |
| Checked sample evaluation | `catalogops-tfidf-logreg-v1` | Train-split word/character TF-IDF retrieval plus the 11-feature logistic classifier |
| Default API with no artifact | `catalogops-lexical-v1` | In-memory catalog fit; TF-IDF retrieval when available plus deterministic evidence scoring |
| API after `make dvc-repro` | `catalogops-tfidf-logreg-v1` | Read-only mounted trained artifact from `artifacts/baseline` |
| Repository matcher failure | `catalogops-api-lexical-fallback-v1` | API-local dependency-free scoring, explicitly identified as a degraded fallback |

The API must persist and return the scorer identity that actually produced each prediction. A dashboard's seeded operational label is not evidence that a trained artifact was loaded.

## Intended use

The model is intended to:

- establish a measurable entity-matching baseline;
- retrieve and score plausible canonical products;
- expose enough evidence for a reviewer to understand a proposed match;
- feed a configurable operational policy;
- support repeatable comparison with later retrieval/reranking models.

It is not intended to:

- identify people, infer protected attributes, or process customer content;
- set prices, remove listings, or penalize sellers autonomously;
- treat its score as a universal probability of correctness;
- replace a reviewer for high-cost or legally significant decisions;
- generalize to a marketplace/language not represented in validation evidence.

## Inputs and outputs

Primary inputs are product title plus optional brand, description, and structured identifiers. The matcher normalizes text, creates lexical features, and scores offer/entity compatibility. The API output should retain:

- candidate entity ID and display fields;
- model score;
- rank;
- available matching signals/evidence;
- model and policy versions;
- the selected route: `auto_match`, `review`, or `no_match`.

Missing fields are valid inputs. The system must not fill them using ground-truth labels.

## Baseline approach

The baseline is designed for legibility rather than novelty:

1. normalize case, Unicode, punctuation, whitespace, and versioned unit rules;
2. extract brand/identifier signals when present;
3. create TF-IDF lexical representations;
4. retrieve a top-25 candidate pool with word and character TF-IDF;
5. score candidate pairs with 11 explicit similarity/conflict features and a class-balanced logistic regression when fitted;
6. apply exact-identifier and identifier/brand-conflict evidence rules;
7. fall back to deterministic lexical similarity if the classifier artifact is unavailable;
8. rank candidates and apply the separately configured decision policy.

The fallback prevents a missing model artifact from crashing the demo, but it is a distinct model ID and must not be mixed with classifier results.

The training pipeline writes a manifest with creation time, runtime versions, input paths/hashes, split/count metadata, and artifact checksums. Checksums detect accidental substitution, but joblib deserialization can execute code; load artifacts only from a trusted CatalogOps build boundary.

## Decision policy

The default local-demo thresholds are:

| Score | Route | Intended action |
| --- | --- | --- |
| `>= 0.85` plus ambiguity guard | `auto_match` | Accept only if the top candidate also leads by `0.06`, unless an exact identifier agrees |
| `>= 0.55` and `< 0.85` | `review` | Create or expose a review case |
| `< 0.55` | `no_match` | Do not link automatically |

High-scoring candidates whose runner-up margin is too small remain in review. These values are configuration, not learned claims. A production policy must be chosen on validation data against explicit costs, capacity, and precision constraints. Threshold changes must be versioned, approved, audited, and evaluated for review-volume impact.

## Training and evaluation data

The local smoke dataset is under `data/sample/`. The target public evaluation is the [WDC Products benchmark](https://webdatacommons.org/largescaleproductcorpus/wdc-products/). See [data-card.md](data-card.md) for provenance, split handling, leakage controls, and import details.

The held-out test split must not be used to fit:

- TF-IDF vocabulary/weights;
- model coefficients;
- score calibration;
- decision thresholds;
- error-category rules added after inspection.

## Metrics

A complete report should include:

| Metric | Question answered |
| --- | --- |
| Precision, recall, F1 | How accurate is the final positive match decision? |
| Recall@K | Does retrieval include the true entity in its top K candidates? |
| MRR | How highly is the true entity ranked? |
| Unseen-entity slice | Does performance survive outside memorized entity coverage? |
| ECE/Brier score | Are scores usable as confidence estimates after calibration? |
| Coverage/review rate | What fraction is automated, reviewed, or rejected at a threshold? |
| p50/p95 latency | What serving delay should users expect under a declared load? |
| Cost per 1,000 offers | What are compute/infrastructure assumptions at a declared volume? |

Sample smoke numbers and full-benchmark status are reported separately in [benchmark-results.md](benchmark-results.md).

## Calibration

Raw lexical or classifier scores are not automatically calibrated probabilities. Calibration should use validation data only, with enough examples per slice, and report Expected Calibration Error plus a proper scoring rule such as Brier score. If no calibrated artifact is fitted, the API and UI should label the value `score` rather than `probability`.

The current evaluator reports ECE and Brier score for the raw/rule-adjusted top-candidate score. No separate Platt, isotonic, or temperature-calibration artifact is fitted.

## Known limitations and failure modes

- Lexical similarity can over-match products that share a family name but differ by generation, capacity, pack size, region, or accessory type.
- It can under-match abbreviations, translations, sparse titles, or legitimate identifier-free listings.
- Popular brands and dense catalog families may dominate candidates.
- An incorrect canonical catalog cannot be repaired by a better matcher.
- A deterministic fallback may have different score distribution from the trained classifier; it requires separate thresholds or validation.
- The sample dataset is too small for robust calibration, subgroup analysis, or drift claims.
- Text-only matching ignores useful product images and structured compatibility information.
- Price is retained as metadata but intentionally excluded from the current matching features to avoid brittle leakage from market/temporal pricing patterns.
- Review outcomes can reflect reviewer inconsistency and must not be treated as flawless labels.

## Fairness and marketplace impact

Product matching is not a protected-attribute task, but errors can still distribute unevenly. Listings from smaller sellers, less-resourced languages, unusual brands, or regions with different naming conventions may be more likely to enter review or be rejected. Publish coverage and error slices by language, category, source, field completeness, and seller cohort where lawful and statistically meaningful.

False matches are often more costly than misses because they can merge reviews, inventory, compatibility, or safety information across different products. Production policy should therefore state the required precision and review capacity, not optimize F1 alone.

## Operational monitoring

Monitor:

- input field completeness and normalized-token shifts;
- score and decision-route distributions;
- review queue size, age, and disagreement;
- precision estimates from delayed labels or sampled review;
- retrieval misses and top confusion pairs;
- latency/error rate by model version;
- threshold/model/policy changes correlated with incidents.

A distribution change is an investigation signal, not proof of model degradation. Rollback or threshold adjustment still requires evidence and human approval.

## Model release checklist

- [ ] Immutable artifact ID and checksum recorded
- [ ] Training/data configuration and commit recorded
- [ ] Leakage checks passed
- [ ] Baseline comparison on identical splits published
- [ ] Required slices and calibration evaluated
- [ ] Latency/load environment declared
- [ ] Thresholds chosen on validation data with business costs
- [ ] Error analysis and limitations reviewed
- [ ] Rollback target and schema compatibility verified
- [ ] Human owner approves release

Unchecked items are not implied by the presence of this card.
