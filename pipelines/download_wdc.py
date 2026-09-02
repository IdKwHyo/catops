"""Explicitly download the official WDC Products 80% corner-case archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_URL = "https://data.dws.informatik.uni-mannheim.de/largescaleproductcorpus/data/wdc-products/80multi.zip"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="data/wdc/80multi.zip")
    parser.add_argument("--sha256", help="optional expected SHA-256 supplied by the operator")
    parser.add_argument("--force", action="store_true", help="replace an existing archive")
    args = parser.parse_args(argv)

    destination = Path(args.output)
    if destination.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {destination}; pass --force explicitly")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(args.url, headers={"User-Agent": "CatalogOps/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    actual = _sha256(partial)
    if args.sha256 and actual.casefold() != args.sha256.casefold():
        partial.unlink(missing_ok=True)
        raise SystemExit("downloaded archive failed SHA-256 verification")
    partial.replace(destination)
    manifest = {
        "source_url": args.url,
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": actual,
        "downloaded_at": datetime.now(UTC).isoformat(),
    }
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
