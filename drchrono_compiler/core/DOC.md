# core/

Part of the [DrChrono PDF Compiler](../../README.md), which connects to DrChrono (a cloud-based EHR / practice-management platform) to generate billing PDFs. This doc covers the `core/` app only.

Shared DrChrono API fetch helpers, used by both [`pdf`](../pdf/DOC.md)'s `views.py` and `services.py` so the same appointment/line-item/patient lookups aren't duplicated across the PDF generation code.

## services.py

The only real content in this app.

- **`fetch_appointment(requests, headers, appt_id)`** — `GET /api/appointments/{id}?verbose=true`, returns the parsed JSON.
- **`fetch_lineitem(requests, headers, appt_id)`** — `GET /api/line_items?appointment={id}`, returns just the `results` list.
- **`fetch_patient(requests, headers, patient_id)`** — `GET /api/patients/{id}`, returns the parsed JSON.

All three take `requests` and `headers` in as arguments rather than building them internally, so every caller passes its own already-authenticated headers — keeps these functions stateless and easy to call consistently from both `pdf` files. None of the three set a timeout or call `raise_for_status()`, unlike the equivalent calls in [`search`](../search/DOC.md) and [`appts`](../appts/DOC.md).

## models.py / views.py / admin.py / tests.py

All left as the default empty stubs `startapp` generates. This app was scaffolded as a full Django app but only ever used for its `services.py` — there's no model, no admin registration, and no views of its own.
