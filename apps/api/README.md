# CatalogOps API

FastAPI service for offer ingestion, entity matching, human review, quality incidents,
approval-gated remediation, and a tamper-evident audit trail.

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

The default database is `sqlite:///./catalogops.db`. Deterministic demo records are
inserted on first startup. OpenAPI is available at <http://localhost:8000/docs> and
health at <http://localhost:8000/health>.

To use PostgreSQL instead:

```bash
export DATABASE_URL='postgresql+psycopg://catalogops:password@localhost:5432/catalogops'
```

You can also supply `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.

## Demo authorization

Read-only matching, metrics, review queue, incidents, and investigations are public in
the local demo. Mutations use these headers:

```text
X-Role: reviewer | operator | admin
X-Actor: a stable user or service identifier
```

Roles are hierarchical: reviewers resolve review records; operators also ingest offers,
create incidents, run investigations, and execute approved actions; admins additionally
approve or reject proposed actions. This header mechanism demonstrates authorization
boundaries only. Deployments should authenticate users with OIDC/JWT before assigning a
role.

## Key requests

```bash
curl http://localhost:8000/api/v1/metrics/summary

curl -X POST http://localhost:8000/api/v1/matches/predict \
  -H 'Content-Type: application/json' \
  -d '{"title":"Air Pods Pro Gen 2 USB C MTJV3","brand":"Apple","mpn":"MTJV3"}'

curl -X POST http://localhost:8000/api/v1/reviews/10000000-0000-4000-8000-000000000001/resolve \
  -H 'Content-Type: application/json' \
  -H 'X-Role: reviewer' -H 'X-Actor: demo-reviewer' \
  -d '{"resolution":"matched","resolved_product_id":"DEMO-1002","notes":"Verified MPN."}'
```

The decision policy is configurable with `CATALOGOPS_AUTO_MATCH_THRESHOLD` and
`CATALOGOPS_REVIEW_THRESHOLD`; defaults are 0.85 and 0.55. Audit rows are append-only,
hash chained, and protected from update/delete by database triggers on SQLite.

