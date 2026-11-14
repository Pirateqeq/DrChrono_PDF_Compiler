# search/

Part of the [DrChrono PDF Compiler](../../README.md). Finds a patient in DrChrono by first name, last name and/or date of birth, and shows the matches. Each match links to that patient's [appointment list](../appts/DOC.md).

## Flow

1. **`/search/` (`views.search`)** shows the form. On a valid POST it calls `search_patients` with `request.drchrono_token`.
   - **Matches:** stores them in the session under one key, `patient_search` (`{'patients', 'more', 'query'}`), shows "Found N matching patient(s).", and redirects to the results page.
   - **No matches:** shows the form again with "No patients found matching your criteria."
   - **Invalid form** (all fields empty): "Please provide at least one of: First Name, Last Name, or Date Of Birth". DrChrono isn't called.
2. **`/search/results/` (`views.results`)** renders whatever is in `patient_search`. With nothing there (a direct visit, or after logging out), it shows "No search results available in this session."

The redirect between the two pages means refreshing the results page never resubmits the search, and "Back to Patient Search" from the appointment list returns to the same results. Both views use [`require_auth`](../verify/DOC.md).

## What the session holds

Only what the results page shows: for each patient `id`, `first_name`, `last_name`, `date_of_birth` and `chart_id`, plus the `more` flag and the search terms (`query`, for the "matching …" line). DrChrono's full patient record never goes into the session. The entry is replaced by the next search and goes away when the session ends: on logout, or after 12 hours (`SESSION_COOKIE_AGE`).

## services.py

- **`search_patients(token, first_name='', last_name='', date_of_birth=None)`** — One `GET /api/patients_summary` through [`core.drchrono.get`](../core/DOC.md), sending only the fields that were filled in (date as `YYYY-MM-DD`) and `page_size=50`. Returns `(patients, more)`: the slimmed patients, and `True` when DrChrono has more than 50 matches (its reply includes `next`). DrChrono errors propagate as `DrChronoError`.

## Errors

The view catches `DrChronoError`:
- **401 (token rejected):** `core.drchrono` raises `DrChronoAuthError` instead, which isn't a `DrChronoError`, so the view can't catch it; `require_auth` sends the user to sign in with "Your DrChrono session expired, please sign in again."
- **Anything else:** shows [`core.drchrono.user_message`](../core/DOC.md), for example "DrChrono isn't responding. Try again in a moment.", and the form again.

## forms.py

- **`PatientSearchForm`** — `first_name`, `last_name`, `date_of_birth` (accepts `YYYY-MM-DD` or `MM/DD/YYYY`). Each is optional; `clean()` requires at least one.

## templates/search/

- **`search.html`** — The form ("Enter a first name, last name or date of birth.").
- **`results.html`** — One card per patient (name, DOB, chart ID), each linking to `/appts/patient/<id>/`. When `more` is set: "DrChrono found more than 50 matches. Add details to narrow the search."

## Tests (`tests.py`)

`search_patients` and the views run against `FakeDrChrono` (patched on `core.drchrono.requests.get`): the parameters sent, slimming, the `more` flag, the session contents, no matches, a plain message for errors, and sign-in for a 401.
