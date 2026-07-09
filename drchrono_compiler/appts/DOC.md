# appts/

Part of the [DrChrono PDF Compiler](../../README.md), which connects to DrChrono (a cloud-based EHR / practice-management platform) to generate billing PDFs. This doc covers the `appts/` app only.

Given a patient, fetches their appointment history from DrChrono and narrows it down to the appointments that are actually eligible for a PDF report — the list the user checks boxes on before generating anything. Reached from [`search`](../search/DOC.md)'s results page; feeds into [`pdf`](../pdf/DOC.md)'s report generation.

## views.py

- **`HistoricalAppointmentsView`** (`ListView`) — the only real logic in this app, in `get_queryset()`:
  - Gated by `require_auth`, same as every other protected view — see [`verify`](../verify/DOC.md).
  - Pulls appointments for `patient_id` from DrChrono's `/api/appointments`, going back 3 years, `verbose=true`.
  - Drops any appointment with status `Rescheduled`, `Cancelled`, or `No Show`.
  - Reads the appointment date from `scheduled_time` (falling back to `date`), and skips anything dated in the future or missing a usable date.
  - Keeps only appointments that have a clinical note with an actual PDF URL attached — appointments without one can't go into a report, so they're filtered out here rather than downstream.
  - Sorts the remaining appointments newest → oldest before handing them to the template.
  - Wraps all of this in a broad `try/except`: any failure (network, API, parsing) shows an error message and returns an empty list — from the user's perspective, a real failure and "no appointments found" look the same.
  - `get_context_data()` just adds `patient_name`, `patient_id`, and a page title for the template.

## templates/appts/historical_list.html

Renders the filtered appointment list as a table, one checkbox per appointment (checked by default), and submits directly to [`pdf_app:generate_selected`](../pdf/DOC.md) for the current patient. `patient_name` is carried along as both a query param and a hidden field so it survives the redirect back if PDF generation fails.

## urls.py

One route: `patient/<int:patient_id>_<str:patient_name>/historical/` → `HistoricalAppointmentsView`, named `historical_list` under the `appts_app` namespace. Patient ID and name are both encoded in the URL path (rather than name being looked up server-side) so the page title and back-links have a display name without an extra API call.

## apps.py

Standard Django boilerplate — no custom logic. No `models.py` or `admin.py`: this app has no database table of its own, it's a read-through view over the DrChrono API.
