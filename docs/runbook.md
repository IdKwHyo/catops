# Operations runbook

## Purpose

This runbook covers the local portfolio demo and the operational control flow it illustrates. It does not replace production service ownership, incident management, backup/restore, security, or deployment procedures.

## Service map

| Surface | Default address | Check |
| --- | --- | --- |
| Web | <http://localhost:8080> | Overview renders and API health is visible |
| API | <http://localhost:8000> | `GET /health` returns healthy |
| OpenAPI | <http://localhost:8000/docs> | Schemas and endpoints render |
| PostgreSQL | `127.0.0.1:5432` | Compose health check passes; not exposed beyond loopback |
| Redis | `127.0.0.1:6379` | Compose health check passes; provisioned seam, not used by the synchronous path |

## Start and verify

From the repository root:

```bash
make up
```

`make up` runs Compose with build and health waiting. For an API-only demonstration with PostgreSQL and Redis, use `make lite`.

In a second terminal:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/api/v1/metrics/summary
curl -fsS http://localhost:8000/api/v1/audit/verify \
  -H 'X-Role: operator' \
  -H 'X-Actor: runbook-check'
```

Open the web application and confirm the overview, reviews, incidents, and audit routes render. The generated API docs are authoritative if an example in this runbook falls behind a schema change.

Run the bounded smoke checks:

```bash
make smoke
```

## Local identity convention

State-changing workflows accept:

```text
X-Role: reviewer | operator | admin
X-Actor: a human-readable demo identity
```

The role hierarchy allows the more privileged operational roles to perform lower-level actions where the endpoint policy specifies it. Omit or reduce the role in tests to verify denial behavior.

These headers are a local demonstration only. Do not expose this mode to an untrusted network; a caller can forge both values.

## Normal matching workflow

### 1. Create or select an offer

```bash
curl -sS -X POST http://localhost:8000/api/v1/offers \
  -H 'Content-Type: application/json' \
  -H 'X-Role: operator' \
  -H 'X-Actor: demo-operator' \
  -d '{"external_id":"demo-xm5-001","seller":"Demo Seller","title":"Sony WH-1000XM5 Wireless Headphones Black","brand":"Sony","currency":"USD"}'
```

### 2. Predict

```bash
curl -sS -X POST http://localhost:8000/api/v1/matches/predict \
  -H 'Content-Type: application/json' \
  -d '{"title":"Sony WH-1000XM5 Wireless Headphones Black","brand":"Sony"}'
```

Check the candidate ID, score, evidence, model identifier, route, and policy thresholds. The default demo policy routes `>=0.85` to automatic match, `[0.55,0.85)` to review, and `<0.55` to no match.

### 3. Resolve an ambiguous case

List the queue:

```bash
curl -sS http://localhost:8000/api/v1/reviews
```

Resolve using the exact enum in OpenAPI:

```bash
curl -sS -X POST http://localhost:8000/api/v1/reviews/REVIEW_ID/resolve \
  -H 'Content-Type: application/json' \
  -H 'X-Role: reviewer' \
  -H 'X-Actor: demo-reviewer' \
  -d '{"resolution":"matched","resolved_product_id":"DEMO-1002","notes":"Title, brand, and model family agree"}'
```

Verify that the queue state and audit entries changed together.

## Incident investigation workflow

### 1. Inspect or create an incident

```bash
curl -sS http://localhost:8000/api/v1/incidents
```

For a manually created demo incident, use the schema in OpenAPI and include evidence references rather than unsupported prose.

### 2. Run bounded investigation

```bash
curl -sS -X POST http://localhost:8000/api/v1/investigations/run \
  -H 'Content-Type: application/json' \
  -H 'X-Role: operator' \
  -H 'X-Actor: demo-operator' \
  -d '{"incident_id":"INCIDENT_ID"}'
```

Confirm that the response cites the incident/metrics/records it inspected and contains at most one supported action: `rollback_model`, `adjust_threshold`, or `create_review_batch`.

### 3. Approve separately

```bash
curl -sS -X POST http://localhost:8000/api/v1/investigations/INVESTIGATION_ID/approve \
  -H 'Content-Type: application/json' \
  -H 'X-Role: admin' \
  -H 'X-Actor: demo-admin' \
  -d '{"notes":"Evidence and bounded impact reviewed"}'
```

Approval should record who approved exactly which proposal. In a production configuration, bind approval to a proposal hash and require a different actor or stronger role for high-risk changes.

### 4. Execute and verify

```bash
curl -sS -X POST http://localhost:8000/api/v1/investigations/INVESTIGATION_ID/execute \
  -H 'Content-Type: application/json' \
  -H 'X-Role: operator' \
  -H 'X-Actor: demo-executor' \
  -d '{"dry_run":false}'

curl -sS http://localhost:8000/api/v1/audit/verify \
  -H 'X-Role: operator' \
  -H 'X-Actor: demo-executor'
```

Execution fails if the investigation is unapproved, the action is unsupported, or the payload is out of bounds. The current demo does not bind approval to a proposal hash/expiry or comprehensively detect all relevant state changes after approval; those checks are production requirements.

## Rollback response procedure

The local demo illustrates the control-plane transition. For a real model-serving incident:

1. Halt further automated release/threshold changes.
2. Record the affected model/policy version, start time, metrics, and representative failures.
3. Compare the current version with the last known healthy version on the same records.
4. Verify the target artifact ID/checksum and input/output schema compatibility.
5. Create a rollback proposal scoped to that immutable target.
6. Obtain the required human approval; use two-person control if customer impact is broad.
7. Deploy to a canary/inactive slot and run health/shadow tests.
8. Shift traffic gradually, watching error, latency, match-quality proxies, and review volume.
9. Verify the audit chain and external deployment/model-registry events.
10. Keep the incident open until delayed quality labels and queue recovery are reviewed.

Do not describe the local state change as a completed artifact deployment unless a registry/deployment adapter and health evidence are present.

## Audit verification failure

If `GET /api/v1/audit/verify` reports a mismatch:

1. stop operational mutations and preserve the database/log snapshot;
2. record the first invalid sequence/entry and current chain head;
3. compare with the most recent external signed checkpoint, if configured;
4. reconcile review, incident, deployment, and model-registry events;
5. rotate potentially compromised write credentials;
6. restore only through an approved recovery process;
7. document whether the cause was corruption, a migration defect, or unauthorized activity.

Do not “repair” hashes in place; doing so destroys evidence.

## Troubleshooting

### API is not healthy

```bash
docker compose ps
docker compose logs api
```

Look for port conflicts, invalid environment values, database readiness, or migration failures. Fix the cause, then rerun the health request.

### Web loads but data is unavailable

Check browser network errors, API health, and the web API-base configuration. A successful Vite page load does not prove the API is reachable. When connectivity fails, the UI switches to a visibly labelled demo fixture; its local decisions and audit rows are not persisted or cryptographically verified by the backend.

### Matcher reports the fallback model

`catalogops-lexical-v1` indicates that the trained TF-IDF/logistic artifact was unavailable or intentionally not loaded. This is the expected default before `make dvc-repro`; it preserves demo availability but changes score semantics. Stop services, run `make dvc-repro`, then `make up` to mount `artifacts/baseline` read-only. A prediction should then report `catalogops-tfidf-logreg-v1`.

`catalogops-api-lexical-fallback-v1` means the repository matcher itself failed and the API-local dependency-free scorer handled the request. Inspect API logs and health metadata. Do not compare any of these model IDs as if their score distributions were interchangeable.

### Review case is not created

Confirm the score lies in `[0.55, 0.85)` or that a score above `0.85` failed the runner-up ambiguity guard, the policy version is current, and the request completed successfully. Check for idempotency/deduplication before creating a duplicate manually.

### Approved action cannot execute

This is normally a safe failure. Confirm action allowlist, approval state, proposal identity/hash, bounds, actor role, and whether the incident/model/policy changed after approval.

### Audit verifies despite deleted newest entries

A local chain cannot detect suffix truncation without an independent checkpoint. This is a known limitation, not a healthy production signal.

### Concurrent audit writes conflict

SQLite uses a process-local append lock and is limited to the one-process demo. PostgreSQL—including Compose—also acquires a transaction-scoped advisory lock before reading the chain head, serializing appends across workers. Production should exercise contention and retry behavior under multi-instance load or move appends behind a dedicated audit-writer boundary. Treat duplicate sequence/hash errors as integrity incidents, never as a reason to disable constraints.

## Stop and reset

Stop services while retaining volumes:

```bash
docker compose down
```

Removing named volumes deletes local database state and audit history. Only do this when intentionally resetting disposable demo data:

```bash
docker compose down --volumes
```

That operation is not a production recovery procedure.

## Pre-release checklist

- [ ] Unit/integration tests and web build pass
- [ ] Sample evaluation artifact matches the current commit/data hash
- [ ] OpenAPI and documented endpoints agree
- [ ] Wrong-role and unapproved-execution checks fail closed
- [ ] Review, incident, and audit UI workflows complete
- [ ] Audit chain verifies before and after the demo
- [ ] No secrets, generated state, WDC downloads, or personal data are committed
- [ ] Limitations and benchmark status remain accurate
- [ ] Screenshots/video, if published, match the tagged release
