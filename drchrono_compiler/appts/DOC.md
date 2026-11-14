# appts/

Part of the [DrChrono PDF Compiler](../../README.md). Shows a patient's eligible past visits so the user can tick which ones go into the PDF. Reached from a [search](../search/DOC.md) result; submits to [`pdf`](../pdf/DOC.md).

## views.py

- **`appointment_list(request, patient_id)`** (`/appts/patient/<id>/`, protected by [`require_auth`](../verify/DOC.md)) — Makes three DrChrono calls with `request.drchrono_token`:
  - [`core.drchrono.patient`](../core/DOC.md), for the heading ("Past Appointments for Jane Doe")
  - [`eligible_appointments`](../core/DOC.md), the visits (every page, newest first)
  - [`line_items(patient=…)`](../core/DOC.md), grouped with `by_visit`, to mark each visit with no charges (`no_charges`)

  On a `DrChronoError` it shows `core.drchrono.user_message` and an empty list ("No historical appointments found for this patient."). A rejected token (401) raises `DrChronoAuthError` instead, which `require_auth` turns into the sign-in page.

## urls.py

- `patient/<int:patient_id>/` → `historical_list`. Only the ID is in the URL: the patient's name is fetched from DrChrono, so names never reach request logs or browser history. Opening the list costs 1 call for the patient, 1 per 25 visits, and 1 per page of line items.

## templates/appts/historical_list.html

One row per visit (date/time, reason) with a checkbox, all ticked by default. A visit with no charges shows a **No charges** tag (hover: the PDF includes its clinical note but no claim form). Below the rows is a "Generate PDF Report for Selected" button that POSTs the ticked IDs to `pdf_app:generate_selected` for this patient. If PDF generation fails, `pdf` redirects back here by patient ID. "Back to Patient Search" returns to the stored [search results](../search/DOC.md).

## Tests (`tests.py`)

The three DrChrono calls are patched on `appts.views.drchrono`. Tests cover the heading, the ticked rows, the No charges tag, that no patient name appears in the URL or the form, a plain message for errors, and sign-in for a 401.
