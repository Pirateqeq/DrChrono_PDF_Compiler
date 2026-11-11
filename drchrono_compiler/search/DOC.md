# search/

Patient lookup by name and/or date of birth. Results are kept in the session, not the database. Part of the [DrChrono PDF Compiler](../../README.md).

## forms.py

- **`PatientSearchForm`** — `first_name`, `last_name`, `date_of_birth` (accepts `YYYY-MM-DD` or `MM/DD/YYYY`). Each is optional, but `clean()` requires at least one.

## services.py

- **`search_patients(request, search_filters)`** — `GET /api/patients_summary` with `first_name`, `last_name`, `date_of_birth`, `chart_id` (others ignored). `page_size` defaults to 50, max 200. Returns `(patients, next_cursor)`.
  - 401/403 → `DrChronoAuthError`; other HTTP errors → `RuntimeError("client error" | "server error")`.
  - Wrapped in `login_required` and [`require_auth`](../verify/DOC.md) even though it's a helper, not a routed view.

## views.py

- **`PatientSearchView`** (`/search/`) — Renders the form. On submit, calls `search_patients`, stores results/filters/cursor in the session, and redirects to results. No matches or errors re-render the form with a message.
- **`PatientResultsView`** (`/search/results/`) — Renders the results stored in the session. Empty session → "no results" notice.

Both are protected by `require_auth`.

## templates/search/

- **`search.html`** — The search form.
- **`results.html`** — One card per patient (name, DOB, chart ID) linking to that patient's [appointment list](../appts/DOC.md). Warns when more than 30 results come back.
