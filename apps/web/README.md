# CatalogOps web

React + TypeScript operations dashboard for auditable marketplace product matching. It is a Vite SPA with four routes:

- `/overview` — editorial system state, decision policy, throughput, and calibration signal
- `/reviews` — human review queue with field-level evidence and keyboard actions
- `/incidents` — evidence-bound agent investigation and explicit approval checkpoint
- `/audit` — filterable, exportable decision ledger

## Run locally

```bash
npm ci
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/api` to `http://localhost:8000`.

## API configuration

Set `VITE_API_URL` to a FastAPI base URL. It defaults to `/api/v1`. The client uses:

```text
GET  /metrics/summary
GET  /reviews
POST /reviews/{id}/resolve
GET  /incidents
POST /investigations/run
POST /investigations/{id}/approve
POST /investigations/{id}/execute
GET  /audit
GET  /audit/verify
POST /matches/predict
```

If the initial API requests fail or time out, the interface switches to an explicitly labeled **Demo dataset**. Demo metrics are seeded product-design fixtures and are not claimed WDC benchmark results. Local decisions remain interactive and create local audit entries.

The executable matcher currently shown is the Phase-1 lexical/TF-IDF/logistic baseline family; the exact serving model ID is read from the API. Semantic retrieval and cross-encoder reranking are roadmap work, not represented as live capabilities in this UI.

## Checks

```bash
npm run typecheck
npm run build
```

The overview idle-loads its Lenis/GSAP/Three.js cinematic layer only on capable desktop clients. Reduced-motion, touch, narrow, data-saver, and constrained devices retain the complete static composition, while the operations routes remain independent of the effect. The UI also supports light/dark themes, visible keyboard focus, accessible SVG chart data, responsive master/detail review, and these review shortcuts: `J`/`K` navigate, `A` confirm match, `N` no match, `S` skip.

In live mode, consequential actions are shown as successful only after the API accepts them. The client then reloads the server audit list and `/audit/verify`; if that refresh fails after a committed mutation, the interface marks integrity as unverified instead of inventing a local “verified” audit event.
