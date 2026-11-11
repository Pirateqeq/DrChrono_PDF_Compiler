# core/

Shared DrChrono API helpers used by [`appts`](../appts/DOC.md) and [`pdf`](../pdf/DOC.md). No models, views, or routes. Part of the [DrChrono PDF Compiler](../../README.md).

## services.py

Each function takes the `requests` module and auth `headers` from the caller, uses a 10s timeout, and raises on HTTP errors.

- **`fetch_appointment(requests, headers, appt_id)`** — `GET /api/appointments/{id}?verbose=true`.
- **`fetch_lineitem(requests, headers, appt_id)`** — `GET /api/line_items?appointment={id}`; returns the `results` list.
- **`fetch_patient(requests, headers, patient_id)`** — `GET /api/patients/{id}`.
- **`get_valid_appointments(requests, headers, patient_id, lookback_days=1095)`** — `GET /api/appointments` for the last 3 years (first page only, up to 50). Keeps appointments that:
  - are not `Rescheduled`, `Cancelled`, or `No Show`
  - are dated today or earlier
  - have a clinical note PDF URL

  Converts `scheduled_time` to a `datetime` and returns the list newest first.

## testing.py

Test-only helpers imported by every app's `tests.py`:
- `make_patient`, `make_appointment`, `make_line_item`, `make_pdf_bytes` — fake DrChrono records and PDFs.
- `fake_response` — stand-in for `requests.Response` (`.json()`, `.content`, `.raise_for_status()`).
- `FakeDrChrono` — replaces the `requests` module; routes `get(url)` to canned responses and fails on unknown URLs.
- `message_texts(response)` — the flash messages a request produced.
