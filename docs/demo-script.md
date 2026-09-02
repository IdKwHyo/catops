# 90-second demo script

## Goal

Show that CatalogOps is more than a matching model: it turns uncertainty into a controlled, reviewable operation and makes every consequential action attributable.

This is a recording script, not evidence that a video or public deployment already exists.

## Preflight

Before recording:

```bash
make up
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/api/v1/audit/verify \
  -H 'X-Role: operator' \
  -H 'X-Actor: demo-preflight'
```

If the recording is meant to show the trained classifier, run `make dvc-repro` before `make up` and confirm predictions report `catalogops-tfidf-logreg-v1`. Otherwise name the default `catalogops-lexical-v1` scorer honestly in the narration.

Use seeded/sample records whose expected routes are known. Keep the browser at `/overview`, with `/reviews`, `/incidents`, `/audit`, and `/docs` ready. Hide terminals containing unrelated environment variables.

## Script

### 0:00–0:10 — The problem

**Screen:** Overview.

**Say:** “Marketplaces receive the same product written dozens of ways. A wrong link can merge incompatible variants, while a cautious model can bury reviewers. CatalogOps makes that tradeoff measurable and auditable.”

Point to model/policy version, decision distribution, queue health, and service health. Do not call seeded values live production metrics.

### 0:10–0:28 — Evidence, not a magic answer

**Screen:** Submit or open a messy sample offer, then show the prediction response/card.

**Say:** “The matcher normalizes the listing, ranks canonical candidates, and preserves the signals behind its score. Policy is separate from the model: at 0.85 or above the demo auto-matches; between 0.55 and 0.85 it asks a human; below 0.55 it refuses the match.”

Point to candidate ID, score, evidence, model ID, route, and thresholds.

### 0:28–0:47 — Human review

**Screen:** `/reviews`; open a medium-confidence case.

**Say:** “This case is ambiguous, so it enters a review queue instead of being forced through. The reviewer can compare fields and resolve it as matched, no match, duplicate, or needing more information. I’ll match this one explicitly.”

Resolve the case. Show queue/status feedback and actor attribution.

### 0:47–1:12 — Bounded investigation and approval

**Screen:** `/incidents`; open the seeded quality/drift incident and investigation.

**Say:** “This demo uses a deterministic investigator to assemble structured metrics and queue evidence. It cannot chat its way into production or run arbitrary tools. It can only propose a rollback, threshold adjustment, or review batch; a future model-assisted diagnosis must keep this same boundary.”

Show cited evidence and one proposal.

**Say:** “Proposal is not execution. A human approves the exact action, then the executor validates it again.”

Approve and execute the seeded safe action. If the local rollback only updates control-plane state, call it a “rollback control-flow demonstration,” not a deployed-model rollback.

### 1:12–1:25 — Audit verification

**Screen:** `/audit`.

**Say:** “The review, approval, and execution are linked to actors in a hash-chained log. The verifier detects application-level edits or reordering. For production, I would also anchor signed chain roots outside the primary database.”

Run or show audit verification success.

### 1:25–1:30 — Close with evidence status

**Screen:** Benchmark-results page or repository documentation.

**Say:** “The repository ships a reproducible smoke run and WDC importer. Full WDC metrics are deliberately marked TBD until the frozen benchmark is run—because auditability starts with honest claims.”

## Shot checklist

- [ ] Overview identifies all values as sample/demo where appropriate
- [ ] Prediction shows candidate evidence and model/policy versions
- [ ] Medium-confidence route visibly enters review
- [ ] Review resolution shows success and actor
- [ ] Investigation cites evidence and shows only an allowlisted action
- [ ] Approval and execution are visibly separate
- [ ] Audit view includes review, approval, and execution entries
- [ ] Chain verification succeeds
- [ ] Benchmark page clearly distinguishes smoke from WDC TBD
- [ ] No credentials, local usernames, or unrelated browser tabs appear

## Failure/rollback alternate take

For a longer technical walkthrough:

1. Attempt execution before approval and show the API refusing it.
2. Approve the proposal with an operator identity.
3. Execute it and show the new model/policy control-plane state.
4. Compare audit entries for proposal, approval, and execution.
5. Explain what remains to connect to a signed registry-backed canary rollback.

This refusal is stronger portfolio evidence than a happy path alone because it demonstrates the invariant: no operational action executes solely because an investigator proposed it.

## Publishing notes

- Record against a tagged commit and name it in the video description.
- Link the live demo only if it is actually reachable and safe; otherwise link local-run instructions.
- Add screenshots only after the UI matches the tagged release.
- Never label sample metrics as WDC results or seeded incidents as detected production drift.
