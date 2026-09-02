#!/usr/bin/env sh
set -eu

api_url="${1:-http://localhost:8000}"
web_url="${2:-http://localhost:8080}"

request() {
  label="$1"
  url="$2"
  if ! curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
    echo "Smoke check failed: $label ($url)" >&2
    exit 1
  fi
  echo "ok - $label"
}

request "API health" "$api_url/health"
request "OpenAPI schema" "$api_url/openapi.json"
request "web application" "$web_url/"

