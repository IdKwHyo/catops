# Generated reports

`python -m evaluation.run` writes machine-readable benchmark reports here.
Latency fields vary by machine; committed reports should identify the runtime.

- `sample-baseline.json` is the checked-in model smoke report.
- `dvc-baseline.json` is the optional DVC stage output.
- `api-load-test.json` is a bounded local health-endpoint smoke, not an inference benchmark.
