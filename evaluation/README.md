# Baseline evaluation

Run the reproducible sample benchmark from the repository root:

```bash
python -m evaluation.run --check-thresholds
```

The command fits only the `train` offers, evaluates only `test`, and writes
`evaluation/results/sample-baseline.json`. The report includes selective
auto-match precision/recall/F1, Recall@K, MRR, expected calibration error (ECE),
p50/p95 inference latency, decision coverage, and seen/unseen/unknown slices.
Calibration includes both ECE and Brier score for top-candidate correctness.

The CI gate defaults are precision >= 0.75, recall >= 0.55, F1 >= 0.63, and
Recall@5 >= 0.90. These are starter-dataset regression guards, not production
SLOs. For the dependency-free ablation, add `--force-lexical` and write to a
separate output path.

Precision and recall intentionally count only `auto_match` decisions as system
predictions; review-routed cases are false negatives for auto-match recall. This
makes the metric reflect the deployed threshold policy instead of hiding manual
work inside accuracy.

Split selection fails closed. A missing or misspelled `train`/`test` split stops
the run and prints available split names. `--allow-all` exists only for explicit
exploratory use; reports produced with it must not be presented as held-out
benchmark results.
