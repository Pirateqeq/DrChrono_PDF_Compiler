# appts/

Shows a patient's eligible past appointments so the user can pick which ones go into the PDF. Part of the [DrChrono PDF Compiler](../../README.md).

## views.py

- **`HistoricalAppointmentsView`** (`ListView`, protected by [`require_auth`](../verify/DOC.md)) — Gets the list from [`core.drchrono.eligible_appointments`](../core/DOC.md) with `request.drchrono_token`. Any exception shows an error message and an empty list.

## urls.py

- `patient/<int:patient_id>_<str:patient_name>/historical/` → `historical_list`. The name is in the URL so the page can show it without another API call.

## templates/appts/historical_list.html

One row per appointment (date/time, reason) with a checkbox, all checked by default. Submits to [`pdf_app:generate_selected`](../pdf/DOC.md), passing `patient_name` as a hidden field so errors can redirect back here.
