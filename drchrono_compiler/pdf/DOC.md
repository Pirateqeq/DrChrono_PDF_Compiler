# pdf/

Part of the [DrChrono PDF Compiler](../../README.md), which connects to DrChrono (a cloud-based EHR / practice-management platform) to generate billing PDFs. This doc covers the `pdf/` app only.

Where the actual deliverable gets built. Turns a patient + a set of selected appointments (chosen on [`appts`](../appts/DOC.md)'s list) into one merged PDF: a balance report, each appointment's clinical note, and a filled HCFA-1500 form (the standard paper claim form used to bill insurance for a visit).

## services.py

- **`generate_balance_report(patient_id, token, provider_name=None)`** — Builds the ReportLab balance report. Fetches the patient, pulls their appointments from the last 3 years (excluding cancelled/rescheduled/no-show, and only ones with a clinical note PDF), then fetches line items per appointment, drops any with a zero balance, sums the total, and renders it all as a table (date, debit, claim type, description). Runs once per PDF, not once per selected appointment. Uses [`core`](../core/DOC.md)'s `fetch_patient` and `fetch_lineitem` for the underlying API calls.
- **`generate_clinical_notes(request, appt)`** — Downloads the clinical note PDF DrChrono already generated for one appointment. If there's no note URL or the download fails, it warns the user and returns an empty buffer rather than breaking the whole merge.
- **`fetch_hcfa_data(patient_json, appt_json, line_item_json)`** — Assembles the full data dict needed to fill one HCFA-1500 form: patient demographics, insured info, ICD-10 codes (diagnosis codes), per-line-item service dates/codes/charges, and the practice's own identity fields (NPI, tax ID, address, etc.) pulled from environment variables. Normalizes the patient's phone number into a fixed grouping. Before returning, it checks every required scalar field and raises with a list of exactly what's missing — so an incomplete patient record fails loudly here instead of producing a bill with blank boxes.
- **`generate_hcfa_bill(request, data)`** — Draws checkmarks and text onto a ReportLab canvas at fixed pixel coordinates, then merges that overlay onto the blank `HCFA.pdf` template with pypdf. Every coordinate (sex/insurance checkboxes, name and address blocks, DOB, ICD-10 codes, per-line service rows, provider signature block) is hand-tuned to this one template's exact layout — it isn't dynamic form-field filling, it's print-registration by pixel position.

## views.py

- **`GenerateSelectedPDFView`** — The orchestrator for the "Generate PDF" button, reached from [`appts`](../appts/DOC.md)'s appointment list. Gated by `require_auth`, same as every other protected view — see [`verify`](../verify/DOC.md). Reads the checked appointment IDs, builds one balance report, then for each selected appointment appends its clinical note and a freshly generated HCFA bill — merging everything into a single file with pypdf's `PdfWriter`. Fetches raw appointment/line-item/patient data via [`core`](../core/DOC.md)'s `fetch_appointment`, `fetch_lineitem`, and `fetch_patient`. Returns the result as a download named after the patient. Any failure anywhere in that chain sends the user back to the appointment list with an error message instead of a partial PDF.

## static/HCFA.pdf

The blank HCFA-1500 template that `generate_hcfa_bill`'s overlay gets merged onto. The coordinate values in that function only make sense relative to this exact file — swapping the template would require re-deriving every position.

## urls.py

One route: `patient/<int:patient_id>/generate-selected/` → `GenerateSelectedPDFView`, named `generate_selected` under the `pdf_app` namespace.

## apps.py

Standard Django boilerplate. No `models.py` or `admin.py` — this app generates files on request, it doesn't store anything.
