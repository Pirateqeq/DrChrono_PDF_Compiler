# DrChrono PDF Compiler

A Django 5.2 web application that connects to the DrChrono EHR API via OAuth2 and compiles composite PDF billing packets for patient appointments. For each selected appointment, it bundles a patient balance statement, the clinical note, and a completed HCFA-1500 billing form into a single downloadable PDF.

**Status:** Internal tool built for one specific medical practice's billing workflow. It processes real patient health information (PHI) and billing data (including SSN/EIN and insurance details). It is not a general-purpose or multi-tenant product — provider identity and billing details are configured for a single practice via environment variables.

---

## What It Does

1. **Connect** — The user authenticates via DrChrono's OAuth2 flow. Tokens are stored per-user in the database and refreshed automatically when expired.
2. **Search** — The user searches for a patient by first name, last name, or date of birth. Results come directly from the DrChrono API.
3. **Select Appointments** — The app fetches the patient's historical appointments (past 3 years, with clinical note PDFs available) and displays them in a table with checkboxes.
4. **Generate PDF** — The user selects one or more appointments and submits. The app builds a composite PDF containing:
   - A balance report (generated with ReportLab)
   - Clinical note PDFs (downloaded from DrChrono)
   - HCFA-1500 billing forms (ReportLab canvas overlay merged onto a blank HCFA template via pypdf)

---

## App Structure

```
drchrono_compiler/
├── verify/        # OAuth2 flow, token storage, auth decorator
├── search/        # Patient search form and results view
├── appts/         # Historical appointment list with filtering
├── pdf/           # PDF generation (balance report, clinical notes, HCFA-1500)
├── core/          # Shared DrChrono API helpers (appointment, line item, patient)
└── drchrono_compiler/  # Project settings, root URL conf
```

Each folder above has its own `DOC.md` with a closer, file-by-file and function-by-function look at how it works — start with [`drchrono_compiler/drchrono_compiler/DOC.md`](drchrono_compiler/drchrono_compiler/DOC.md) for settings/routing, then follow the links from there into each app.

### App Responsibilities

**[`verify`](drchrono_compiler/verify/DOC.md)**
- `DrChronoCredential` model — stores access/refresh tokens per user with expiry tracking
- `require_auth` decorator — validates token before any protected view runs, sets `request.drchrono_token`
- `get_valid_access_token` — refreshes token automatically if expired
- Views: `connect_drchrono` (starts OAuth), `oauth_callback` (handles redirect, creates/updates user)

**[`search`](drchrono_compiler/search/DOC.md)**
- `PatientSearchForm` — requires at least one of: first name, last name, or date of birth
- `search_patients` — calls `/api/patients_summary` with filters, returns paginated results
- Session-based result storage between search and results views

**[`appts`](drchrono_compiler/appts/DOC.md)**
- `HistoricalAppointmentsView` — fetches appointments for a patient and filters to: past dates only, non-cancelled/rescheduled/no-show statuses, and appointments that have a clinical note PDF

**[`pdf`](drchrono_compiler/pdf/DOC.md)**
- `generate_balance_report` — builds a ReportLab PDF table of all billable line items
- `generate_clinical_notes` — downloads the clinical note PDF from DrChrono
- `fetch_hcfa_data` — assembles and validates the data dict for the HCFA form
- `generate_hcfa_bill` — draws text/checkmarks onto a ReportLab canvas, merges it onto `HCFA.pdf` template
- `GenerateSelectedPDFView` — orchestrates all of the above and returns a single merged PDF as a file download

**[`core`](drchrono_compiler/core/DOC.md)**
- `fetch_appointment`, `fetch_lineitem`, `fetch_patient` — thin wrappers around DrChrono API endpoints

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL (or use SQLite for local dev by overriding `DATABASE_URL`)

### Installation

```bash
# Clone the repo
git clone <repo-url>
cd drchrono_compiler

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py migrate

# Run the dev server
python manage.py runserver
```

### Environment Variables

The app reads all configuration from environment variables. Set these in your shell, your process manager, or the Render dashboard — there is no `.env` loader wired in, so a `.env` file on its own will not populate them.

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Set to `True` for local dev, `False` for production |
| `DATABASE_URL` | PostgreSQL connection string |
| `DRCHRONO_CLIENT_ID` | DrChrono OAuth app client ID |
| `DRCHRONO_CLIENT_SECRET` | DrChrono OAuth app client secret |
| `DRCHRONO_REDIRECT_URI` | OAuth callback URL (must match DrChrono app settings) |
| `DRCHRONO_SCOPES` | Space-separated DrChrono API scopes |
| `PROVIDER_NAME` | Practice name shown on the balance report |
| `PROVIDER_NPI` | Provider NPI printed on the HCFA form |
| `FEDERAL_TAX_ID` | Federal tax ID printed on the HCFA form |
| `PROVIDER_ACCOUNT_NUMBER` | Practice account number printed on the HCFA form |
| `PHYSICIAN_SIGNATURE` | Physician signature text printed on the HCFA form |
| `PROVIDER_OFFICE_NAME` | Practice office name printed on the HCFA form |
| `PROVIDER_ADDRESS` | Practice address printed on the HCFA form |
| `PROVIDER_CITY_STATE` | Practice city/state printed on the HCFA form |
| `PROVIDER_PHONE` | Practice phone number printed on the HCFA form |
| `PROVIDER_INFO` | Additional provider info printed on the HCFA form |

---

## Security

- **Authentication** — Users authenticate through DrChrono's OAuth2 flow. Access and refresh tokens are stored per Django user in the `DrChronoCredential` model and refreshed automatically before they expire.
- **Secrets** — All credentials and provider-identifying information are supplied via environment variables and are never committed to source control.
- **Patient data** — This application handles real protected health information (PHI) and billing data, including SSN/EIN and insurance details, for one specific medical practice. It is not built or intended for multi-tenant or public use.
- **Transport** — The production deployment runs behind HTTPS on Render.

---

## Deployment (Render)

The app is deployed on Render as a Web Service.

**Build command:**
```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

**Start command:**
```bash
gunicorn drchrono_compiler.wsgi:application
```

Static files are served by WhiteNoise. The `STATICFILES_STORAGE` is set to `whitenoise.storage.CompressedManifestStaticFilesStorage`.

---

## Key Dependencies

| Package | Purpose |
|---|---|
| Django 5.2 | Web framework |
| requests-oauthlib | OAuth2 session management |
| pypdf | PDF merging (HCFA overlay onto template) |
| reportlab | PDF generation (balance report, HCFA canvas) |
| whitenoise | Static file serving in production |
| dj-database-url | PostgreSQL URL parsing |
| psycopg2-binary | PostgreSQL adapter |
| gunicorn | WSGI server |

---

## DrChrono API Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /api/users/current` | Fetch authenticated user info after OAuth |
| `GET /api/patients_summary` | Search patients by name / DOB |
| `GET /api/appointments` | Fetch appointment history for a patient |
| `GET /api/appointments/{id}` | Fetch single appointment detail |
| `GET /api/line_items?appointment={id}` | Fetch billing line items for an appointment |
| `GET /api/patients/{id}` | Fetch patient demographic data |
| `POST /o/token/` | Exchange auth code / refresh token |
