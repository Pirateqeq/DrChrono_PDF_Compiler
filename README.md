# DrChrono PDF Compiler

Django 5.2 app that signs in to DrChrono (EHR) via OAuth2 and builds a single billing PDF for a patient: a balance report, plus the clinical note and a filled HCFA-1500 claim form for each selected appointment.

Internal tool for one practice. It handles real PHI and billing data; practice details come from environment variables.

<img width="1842" height="995" alt="image" src="https://github.com/user-attachments/assets/c024e34c-0a59-41b8-910e-fe9bf66f51c4" />

## How it works

1. **Connect** — log in through DrChrono. Tokens are stored per user and refreshed when expired.
2. **Search** — find a patient by first name, last name, and/or date of birth.
3. **Select** — pick from the patient's past appointments (last 3 years, with a clinical note PDF).
4. **Generate** — download one merged PDF:
   - balance report for the patient
   - per selected appointment (oldest first): clinical note PDF, then HCFA-1500 form

## Project layout

All code lives in `drchrono_compiler/`. See [`SYSTEM_MAP.md`](SYSTEM_MAP.md) for how the parts connect; each app has a `DOC.md` with details.

| Path | Purpose |
|---|---|
| [`drchrono_compiler/`](drchrono_compiler/drchrono_compiler/DOC.md) | Settings, root URLs, WSGI, shared `templates/layout.html` |
| [`verify/`](drchrono_compiler/verify/DOC.md) | OAuth2 login, token storage/refresh, `require_auth` decorator |
| [`search/`](drchrono_compiler/search/DOC.md) | Patient search form and results |
| [`appts/`](drchrono_compiler/appts/DOC.md) | Appointment list with checkboxes |
| [`pdf/`](drchrono_compiler/pdf/DOC.md) | Balance report, clinical notes, HCFA-1500, final merge |
| [`core/`](drchrono_compiler/core/DOC.md) | Shared DrChrono API helpers |

## Local setup

Requires Python 3.11+. Run everything from `drchrono_compiler/` (the HCFA template is loaded by relative path).

```bash
cd drchrono_compiler
```

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

Create your `.env` from the template and fill in the blanks:

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

The template already has the local values: SQLite, `DEBUG=True` (which also allows `localhost`), the `http://localhost:8000/oauth/callback` redirect URI (register it in your DrChrono app) and `OAUTHLIB_INSECURE_TRANSPORT=1` for OAuth over plain HTTP.

```bash
python manage.py migrate
```

```bash
python manage.py runserver
```

## Tests

pytest with pytest-django, run from `drchrono_compiler/`. Tests use `drchrono_compiler/settings_test.py` (in-memory SQLite, dummy credentials), so no environment variables are needed. DrChrono is always mocked; any real network call fails the test.

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

```bash
pytest --cov --cov-report=term-missing
```

- Each app's tests live in its `tests.py`; project-wide checks are in `drchrono_compiler/tests.py`.
- Shared fixtures (signed-in client, credential, request builder) are in `conftest.py`; fake DrChrono data and responses are in `core/testing.py`.
- GitHub Actions runs the suite on every push and pull request (`.github/workflows/tests.yml`).

## Environment variables

Locally they come from `drchrono_compiler/.env` (git-ignored; template in `.env.example`). On Render, set them in the dashboard; real environment variables override `.env`.

| Variable | Used for |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for local dev; anything else is off |
| `DATABASE_URL` | Database connection string |
| `DRCHRONO_CLIENT_ID` / `DRCHRONO_CLIENT_SECRET` | DrChrono OAuth app credentials |
| `DRCHRONO_REDIRECT_URI` | OAuth callback URL (`<host>/oauth/callback`) |
| `DRCHRONO_SCOPES` | Space-separated OAuth scopes |
| `PROVIDER_NAME` | Balance report header |
| `PROVIDER_NPI` | HCFA boxes 24J and 33a |
| `FEDERAL_TAX_ID` | HCFA box 25 |
| `PROVIDER_ACCOUNT_NUMBER` | HCFA box 26 |
| `PHYSICIAN_SIGNATURE` | HCFA box 31 |
| `PROVIDER_OFFICE_NAME` | HCFA box 32 |
| `PROVIDER_ADDRESS` / `PROVIDER_CITY_STATE` | HCFA boxes 32 and 33 |
| `PROVIDER_PHONE` | HCFA box 33; format `555 123-4567` (area code, one space, number) |
| `PROVIDER_INFO` | HCFA box 33 name line |

Every HCFA variable above is required — PDF generation fails if any is missing. `PROVIDER_NAME` falls back to `Unknown Provider`.

## Deployment (Render)

- **Build:** `./build.sh` (installs requirements, `collectstatic`, `migrate`)
- **Start:** `gunicorn drchrono_compiler.wsgi:application`
- **Root directory:** `drchrono_compiler/`

Render terminates TLS; settings force HTTPS, secure cookies, and HSTS when `DEBUG` is off. Static files are served by WhiteNoise.

## DrChrono API endpoints

| Endpoint | Used by |
|---|---|
| `POST /o/token/` | Token exchange and refresh (`verify`) |
| `GET /api/users/current` | Identify the user after login (`verify`) |
| `GET /api/patients_summary` | Patient search (`search`) |
| `GET /api/appointments` | Appointment history (`core`) |
| `GET /api/appointments/{id}` | Single appointment (`core`) |
| `GET /api/line_items?appointment={id}` | Billing line items (`core`) |
| `GET /api/patients/{id}` | Patient demographics (`core`) |
| Clinical note `pdf` URL | Clinical note download (`pdf`) |
