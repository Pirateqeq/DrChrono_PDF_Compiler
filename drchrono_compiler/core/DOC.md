# core/

Part of the [DrChrono PDF Compiler](../../README.md). The DrChrono API client: every DrChrono **data** call (patients, appointments, line items, patient search) goes through `drchrono.py`. Sign-in and token calls live in [`verify`](../verify/DOC.md). No models, views or routes.

Callers pass the access token that [`require_auth`](../verify/DOC.md) puts on `request.drchrono_token`; nothing outside `core` builds URLs or auth headers for DrChrono data.

## drchrono.py

### Requests and errors

- **`get(token, path_or_url, **params)`** — The one place that calls DrChrono for data. Prefixes `https://app.drchrono.com` (unless given a full URL), adds `Authorization: Bearer <token>`, sends `params` as the query string, and uses a 10-second timeout.
- **`DrChronoError`** — Raised for any failure: network error, timeout, non-2xx status or unreadable reply. `.status` is the HTTP status code (401, 403, 404, 429, 5xx…), or `None` when DrChrono never answered. Callers decide what each status means for the user (see `search/services.py`).
- **`get_all(token, path, **params)`** — For list endpoints. DrChrono returns `{"previous", "results", "next"}` with `next` set to the full URL of the next page (query already included), so it keeps calling `get` on `next` until it's empty and returns every `results` item.

### Endpoint helpers

| Function | Endpoint | Notes |
|---|---|---|
| `patient(token, patient_id)` | `GET /api/patients/{id}` | Demographics for the balance report and HCFA form. |
| `appointment(token, appt_id)` | `GET /api/appointments/{id}?verbose=true` | `verbose` adds `clinical_note`. |
| `line_items(token, **filters)` | `GET /api/line_items` | Pass `appointment=` or `patient=`; every page is read. |
| `eligible_appointments(token, patient_id)` | `GET /api/appointments` | See below. |

### `eligible_appointments`

The single definition of which visits can go into a PDF, used by the appointment list (`appts`) and the balance report (`pdf`).

1. Reads **every page** of `/api/appointments` with `patient`, `verbose=true`, `exclude_membership=true` (drops DrChrono's membership-charge placeholders), `page_size=25` and `occurred_since` = 3 years ago.
   - `occurred_since` filters on the **scheduled** time. DrChrono's `since` filters on when a record was last updated or created, so it isn't used.
   - DrChrono caps appointment pages at 20–25, so reading every page matters. Before this client, only the first page was read and patients with many visits lost some.
2. Keeps a visit only if:
   - its status isn't `Rescheduled`, `Cancelled` or `No Show`
   - it has a date (`scheduled_time`, falling back to `date`) of today or earlier
   - it has a clinical note PDF URL (`clinical_note` is either `{"pdf": url}` or the URL itself)
3. Returns **copies** with `scheduled_time` parsed to a `datetime` (the list template formats it), newest first. DrChrono's data is never modified.

### API limits

- 500 calls per hour per app; over it DrChrono answers `429` (`DrChronoError.status == 429`).
- Each page of a list is one call: a patient with 60 visits in 3 years costs 3 calls for `eligible_appointments`.

## testing.py

Test-only helpers imported by every app's `tests.py`:

- `make_patient`, `make_appointment`, `make_line_item`, `make_pdf_bytes` — fake DrChrono records and PDFs.
- `fake_response(json_data, status, content)` — stand-in for `requests.Response` (`.json()`, `.content`, `.raise_for_status()`).
- `FakeDrChrono(routes)` — stands in for `requests.get`. Patch `core.drchrono.requests.get` with its `.get` (or replace a module's `requests` with it, as `pdf` does for note downloads). Routes are keyed by URL without the host:
  - a key with a query (`'/api/line_items?appointment=1'`) matches that path with exactly those params
  - a bare path (`'/api/appointments'`) matches any params
  - full URLs work for other hosts (clinical note files)
  - unknown URLs fail the test; every call is recorded in `.calls`
- `message_texts(response)` — the flash messages a request produced.

## tests.py

Covers `drchrono.py` with `FakeDrChrono`: URL, header, params and timeout; error status on HTTP and network failures; following `next` across pages; each helper; and every `eligible_appointments` rule, including the request parameters and that the input data is left unchanged.
