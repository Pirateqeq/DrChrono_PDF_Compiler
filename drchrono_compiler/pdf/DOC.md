# pdf/

Part of the [DrChrono PDF Compiler](../../README.md). Builds the billing PDF for the visits ticked on the [appointment list](../appts/DOC.md): a balance report, then each visit's clinical note and HCFA-1500 claim form(s).

## Flow

```
views.generate ──> packet.load ──> core.drchrono (about 3 calls)
               └─> packet.build ──> balance.balance_report
                                ├─> packet.download_note   (per visit)
                                └─> hcfa.claim_forms        (per visit)
```

1. **`views.generate(request, patient_id)`** (`POST /pdf/patient/<id>/generate-selected/`, POST only, [`require_auth`](../verify/DOC.md)) reads the ticked visit IDs. If none were ticked, it returns to the list with "No appointments were selected for PDF generation."
2. **`packet.load(token, patient_id, selected_ids)`** fetches everything once:
   - `drchrono.patient`
   - `eligible_appointments` (every page)
   - `line_items(patient=…)` (every page), grouped by visit

   Then it:
   - **Checks the ticked IDs** are this patient's eligible visits. A stale or altered form can't put another visit on the claims: "The visit list changed. Reload the page and try again."
   - **Checks the details every claim needs** with `hcfa.missing_details`: the patient's name, date of birth, sex, address, city, state, zip code and cell phone, plus the `PROVIDER_*`, `FEDERAL_TAX_ID` and `PHYSICIAN_SIGNATURE` settings. If any are missing it stops with, for example, "Can't build claim forms: missing patient zip code."
   - **Orders the ticked visits oldest first** by `scheduled_time`.
   - **Uses the visit list's `icd10_codes`.** Only a visit that lacks the key is fetched individually (`drchrono.appointment`).
3. **`packet.build(packet)`** assembles the PDF:
   - **Balance report** (`balance.py`), covering all eligible visits, not just the ticked ones.
   - **For each ticked visit:** its clinical note (`download_note`), then its claim form(s) (`hcfa.claim_forms`).
   - **Failures are skipped and listed.** A note that can't be included (`NoteError`) or a claim that can't be built (`ClaimError`) is left out, and a first page titled **"Not included"** lists each one, for example "Mar 10, 2025 clinical note: couldn't download it".
4. The view returns the PDF as `Patient_<First>_<Last>_REPORT.pdf`.

**Cost:** about 3 DrChrono calls (plus one per extra page of visits or line items), plus one note download per ticked visit. All go through `core.drchrono.session`, so connections are reused.

## Errors

| Situation | Result |
|---|---|
| Nothing ticked | Back to the list with a warning |
| `PacketError`: ticked visit not on the patient's list, or details every claim needs are missing | Back to the list with that message |
| `DrChronoError` (DrChrono down, rate limit, 404…) | Back to the list with [`core.drchrono.user_message`](../core/DOC.md) |
| DrChrono rejects the token (401) | `DrChronoAuthError` reaches `require_auth`: sign-in page |
| One visit's note or claim can't be built | PDF still downloads; listed on the "Not included" page |

No `except Exception` anywhere: each handler catches a specific error type.

## packet.py

- **`load`**, **`build`**: as above. `load` returns a dict: `patient`, `appointments` (all eligible), `selected` (ticked, oldest first), `line_items` (visit ID → list).
- **`download_note(visit)`**: `GET` the note's PDF URL (from [`drchrono.note_pdf_url`](../core/DOC.md), no auth header, 15 s timeout). Raises `NoteError` when there's no URL, the download fails, or the file isn't a readable PDF (checked here so a bad file never reaches the merge).

## balance.py

- **`balance_report(patient, appointments, line_items) -> bytes`**: pure, with no DrChrono calls. Lists every line item with a non-zero `balance_total` (compared as a number) across the eligible visits, newest first, with the total. The header shows `PROVIDER_NAME` (default "Unknown Provider"). Columns: Date, Debit, Auto Accident Claim (fixed text in every row), Description ("Appointment [id] date name: reason Code code"). With nothing owed: "$0.00" and "No billable transactions found."

## hcfa.py

- **`claim_forms(patient, visit, charges) -> list[bytes]`**: one filled form per **6 charges** (box 24 has six service lines). More charges continue on extra forms for the same visit, each with its own box 28 total. Raises `ClaimError` for a visit with no charges, no ICD-10 codes, or a clinical note with no `updated_at` (the signature date).
- **`missing_details(patient)`**: the patient fields and practice settings every claim needs that are empty.
- **Layout as data**: `CHECKS` (always-ticked boxes), `SEX_CHECKS`, `TEXT` (field → every position it's printed at), `LINE_X` (box 24 columns, lines 24 points apart) and the box 21 ICD-10 positions. All positions are `(x, y)` with y measured down from the top of a 620×800 page, hand-tuned to `forms/HCFA.pdf` and copied unchanged from the original code. Checkmarks are drawn before the font switches to Courier 10, as before.
- **Phone numbers**: 10 digits print as area code + `555-0123`. Anything else prints as given in the number box, with no area code.
- **Overlay**: each form is drawn on a ReportLab canvas and merged onto a fresh copy of the template (`PdfWriter(clone_from=TEMPLATE)`), which keeps working in pypdf 7.

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

Signature dates (boxes 12 and 31) come from the clinical note's `updated_at`.

## forms/HCFA.pdf

The blank HCFA-1500 template, opened by an absolute path built from `Path(__file__)` (works from any working directory). It lives outside `static/`, so `collectstatic` doesn't publish it. Every coordinate in `hcfa.py` is tuned to this exact file.

## Tests (`tests.py`, `golden.py`)

- **Golden output**: `golden.py` holds what the pre-overhaul code drew for a 5-charge visit (every `drawString` x, y and text) and the balance report's text. The tests require the new code to produce exactly the same. To change the layout on purpose, regenerate them as `golden.py` explains.
- **DrChrono and note files**: faked with `FakeDrChrono` patched on `core.drchrono.session.get`. Tests cover the 3-call fetch, the visit check, missing details, the ICD-10 fallback, page order, skip-and-list, extra forms past 6 charges, plain messages, and 401 → sign-in.
