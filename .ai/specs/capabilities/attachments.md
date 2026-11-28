# Capability: attachments

Lets the owner pin a ticket, voucher or screenshot to an item or a day and read it back.

## Requirement: Per-file upload limit
The system SHALL refuse an uploaded attachment larger than **4 MiB** with `attachment_too_large`, and SHALL keep serving stored attachments up to 10 MiB.

### Scenario: A file just over the limit
- WHEN the owner uploads a PDF of 4 MiB + 1 byte
- THEN the upload is refused with `attachment_too_large` and nothing is stored
- AND the frontend tells the user before sending, in the user's language, that the limit is 4 MB

### Scenario: A file at the limit
- WHEN the owner uploads a PDF of exactly 4 MiB
- THEN it is stored

### Scenario: An attachment stored before the change
- WHEN the owner opens a 9 MB attachment uploaded under the old limit
- THEN it downloads in full, on both targets

Frozen by: `backend/tests/test_attachments_api.py` (`test_a_file_one_byte_over_the_cap_is_refused`, `test_a_file_of_exactly_the_cap_is_stored`)

Source: .ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md
