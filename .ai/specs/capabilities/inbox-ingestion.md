# Capability: inbox-ingestion

Lets the owner forward a reservation confirmation to one address and have it stored, ingested and routed without any action.

## Requirement: Ingestion is triggered by receipt on the Lambda target
The system SHALL, on the Lambda target, start an ingestion pass after it durably records a verified SNS receipt, without delaying the SNS acknowledgement.

### Scenario: A forwarded confirmation arrives while the app is idle
- WHEN SNS delivers a verified receipt to the web function
- THEN the receipt is committed, `200` is returned, and the worker function is invoked asynchronously
- AND the message reaches `ingested` (or its next state) without waiting for a schedule

### Scenario: The kick fails
- WHEN the asynchronous invoke of the worker function raises
- THEN the SNS request still answers `200` (the row is durable), the failure is logged, and the next scheduled pass processes the message

Source: .ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md

## Requirement: Scheduled passes on the Lambda target
The system SHALL run an ingestion and cleanup pass on a schedule of `INBOX_WORKER_SCHEDULE` (default 6 hours) on the Lambda target, so retries, `deferred` messages and S3 cleanup proceed with no traffic.

### Scenario: A model outage cleared overnight
- WHEN a message stays `received` because the model failed, and no new mail arrives
- THEN the next scheduled pass retries it

The compose target keeps today's 30 s in-process loop unchanged; `backend/tests/test_scheduler.py` keeps pinning it.

Source: .ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md
