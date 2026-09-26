# D25 — AWS SES delivers inbound reservation mail to the app

- Date, owner: 2026-09-26, Michal Klosinski
- Context and options weighed: the reservation inbox spec initially proposed polling a dedicated IMAP mailbox. The owner asked to change the design to AWS SES forwarding mail to the application's endpoint. Direct SNS receipt actions cap email at 150 KB, so a full reservation message with attachments needs SES S3 delivery and an S3-action SNS notification.
- Decision and why: SES receives mail for the one account-level address, stores raw MIME temporarily in private S3, and publishes an SNS notification to one HTTPS endpoint. The endpoint verifies the SNS signature, topic and SES/S3 locator before recording the delivery; a worker retrieves accepted MIME from S3. Only the owner can approve a resulting plan change.
- Consequences, and what would make us revisit it: one explicitly public route is added to `PUBLIC_PATHS`; AWS S3 holds an external temporary copy of mail; the SNS subscription needs retry, a dead-letter queue and operational alarms. IMAP polling and UID cursors leave the implementation plan. Revisit if SES receiving is unavailable in the deployment region or the required AWS setup is disproportionate to inbox use.
- Status: active
