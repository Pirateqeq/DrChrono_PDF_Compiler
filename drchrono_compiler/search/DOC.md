# search/

Part of the [DrChrono PDF Compiler](../../README.md), which connects to DrChrono (a cloud-based EHR / practice-management platform) to generate billing PDFs. This doc covers the `search/` app only.

Lets a logged-in user look up a DrChrono patient by name and/or date of birth. No database model of its own — search results are kept in the session between the search and results pages, not persisted.

## services.py

- **`search_patients(request, search_filters)`** — Calls DrChrono's `/api/patients_summary` with whatever filters were provided (`first_name`, `last_name`, `date_of_birth`, `chart_id`), capping `page_size` at 200. If a DOB comes in as `MM/DD/YYYY` it's converted to `YYYY-MM-DD` before the request, since that's what the API expects. Returns `(patients, next_cursor)`. Raises [`DrChronoAuthError`](../verify/DOC.md) on a 401/403 (bad token or missing scope) and `ValueError` for any other API or network failure. It's wrapped in `@require_auth`/`@login_required` (see [`verify`](../verify/DOC.md)) even though it's a plain helper function rather than a URL-routed view — it's only ever called from `PatientSearchView`, which has already enforced auth by the time this runs.

## views.py

- **`PatientSearchView`** — Renders the search form. On a valid submit, calls `search_patients`, then stores the results, the filters used, and the pagination cursor in the session before redirecting to the results page. Auth errors, request errors, and unexpected exceptions each get a distinct user-facing message via Django's messages framework. Gated by `require_auth`, same as every other protected view — see [`verify`](../verify/DOC.md).
- **`PatientResultsView`** — Plain GET view that reads the patient list, filters, and cursor back out of the session and renders them. If the session is empty (e.g. direct navigation without a prior search), it just shows "no results."

## forms.py

- **`PatientSearchForm`** — All three fields (`first_name`, `last_name`, `date_of_birth`) are individually optional. The actual requirement lives in `clean()`: at least one of the three must be filled in, or the form is rejected with a validation error.

## templates/search/

- **`search.html`** — The search form itself: first name, last name, and date of birth inputs.
- **`results.html`** — Renders the patient list from `PatientSearchView`'s session data as a table (name, DOB, chart ID), with a link per row into [`appts`](../appts/DOC.md)'s historical appointment list for that patient.

## urls.py

Two routes under the `search_app` namespace: `''` → `PatientSearchView` (`search`), `results/` → `PatientResultsView` (`results`).

## apps.py

Standard Django boilerplate — no custom logic.
