#!/usr/bin/env python3
"""Small dependency-free smoke load test for a deployed CatalogOps endpoint."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Result:
    ok: bool
    latency_ms: float
    status: int | None


def request_once(url: str, timeout: float) -> Result:
    started = time.perf_counter()
    status: int | None = None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            response.read()
            ok = 200 <= status < 400
    except urllib.error.HTTPError as error:
        status = error.code
        ok = False
    except (OSError, TimeoutError):
        ok = False
    return Result(ok=ok, latency_ms=(time.perf_counter() - started) * 1000, status=status)


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1)
    return ordered[max(index, 0)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/health")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests and --concurrency must be positive")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(request_once, args.url, args.timeout) for _ in range(args.requests)
        ]
        results = [future.result() for future in as_completed(futures)]
    duration = time.perf_counter() - started

    latencies = [result.latency_ms for result in results]
    failures = sum(not result.ok for result in results)
    summary = {
        "url": args.url,
        "requests": len(results),
        "concurrency": args.concurrency,
        "duration_s": round(duration, 3),
        "requests_per_second": round(len(results) / duration, 2),
        "error_rate": round(failures / len(results), 6),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
        "thresholds": {
            "max_error_rate": args.max_error_rate,
            "max_p95_ms": args.max_p95_ms,
        },
        "passed": failures / len(results) <= args.max_error_rate
        and percentile(latencies, 0.95) <= args.max_p95_ms,
        "sample_failure": next((asdict(result) for result in results if not result.ok), None),
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
