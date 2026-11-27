# Checkpoint 1 — steps 0.1..1.5

- Steps: 0.1, 0.2, 1.1, 1.2, 1.3, 1.4, 1.5 (commits 91f9389..f1443dd)
- Touched areas: run folder (Phase 0 findings); backend config, inbox receipt endpoint, `inbound/ses.py` (WorkerKick), scheduler, new `worker_app.py`
- Recorded: 2026-11-27T20:32:57Z

| Check | Result |
|---|---|
| `(cd backend && uv run ruff check .)` | pass |
| `uv run pytest` on test_inbox_receipts, test_worker_kick, test_config, test_scheduler, test_worker_app, test_route_protection, test_inbox_flow, test_inbox_ingest | pass — 159 passed, 0 skipped (live Postgres) |
| Step review (`engine.stepReview: checkpoint`), diff c1757a0..f1443dd | no blocker/major. Note (nit, deferred): routing handles at most `BATCH_SIZE` received messages per pass and the drain loop stops when ingestion returns 0, so a routing backlog > 10 with no new ingestion waits for the next event. Matches the thread's per-tick behaviour |
| UI verification | skipped — no UI touched in this window |
