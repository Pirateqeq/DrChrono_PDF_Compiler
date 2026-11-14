# pdf/

Builds the final merged PDF. Part of the [DrChrono PDF Compiler](../../README.md).

## views.py

- **`GenerateSelectedPDFView`** (`POST pdf/patient/<id>/generate-selected/`, protected by [`require_auth`](../verify/DOC.md)) — Builds the PDF in this order:
  1. Balance report
  2. For each selected appointment, oldest first: clinical note, then HCFA-1500

  Returns it as a download named `Patient_<First>_<Last>_REPORT.pdf`. Any exception redirects back to the [appointment list](../appts/DOC.md) with the error messages.

## services.py

- **`generate_balance_report(patient_id, token, provider_name=None)`** — ReportLab table of every non-zero line item across all of the patient's [eligible appointments](../core/DOC.md) (not just the selected ones), newest first, with the total balance. Header uses `PROVIDER_NAME`.
- **`generate_clinical_notes(request, appt)`** — Downloads the appointment's clinical note PDF. On a missing URL or failed download, adds a warning and returns an empty buffer.
- **`fetch_hcfa_data(patient_json, appt_json, line_item_json)`** — Builds the HCFA data dict from patient demographics, the appointment's ICD-10 codes, line items (date, CPT code, price), and provider env vars. Raises an `Exception` listing every missing field.
- **`generate_hcfa_bill(request, data)`** — Draws text and checkmarks at fixed coordinates on a ReportLab canvas and overlays it on `static/HCFA.pdf`.

### Hardcoded HCFA values

| Field | Value |
|---|---|
| Insured | Same as patient (self) |
| Box 10 employment / other accident | No |
| Box 10 auto accident | Yes |
| Box 11d another health plan | No |
| Box 12 / 13 signatures | "Signature on File" |
| Box 21 ICD indicator | `0` (ICD-10) |
| Box 24B place of service | `11` (office) |
| Box 24E diagnosis pointer | `a` |
| Box 24G days/units | `1` |
| Box 25 | EIN |
| Box 27 accept assignment | Yes |

Signature dates come from the clinical note's `updated_at`.

## static/HCFA.pdf

Blank HCFA-1500 template. Loaded via the relative path `pdf/static/HCFA.pdf`, so the app must run from `drchrono_compiler/`. All coordinates in `generate_hcfa_bill` are tuned to this exact file.
