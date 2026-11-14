# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Django 5.2 internal tool for one medical practice: signs in to DrChrono (EHR) via OAuth2 and builds one billing PDF per patient (balance report, then a clinical note + HCFA-1500 claim form per selected appointment). It handles real PHI. See `README.md` for setup, `SYSTEM_MAP.md` for the user journey and diagrams, and each app's `DOC.md` for per-file detail.

## Commands

Run everything from `drchrono_compiler/` (where `manage.py` and `pytest.ini` live). `pdf/static/HCFA.pdf` is opened by relative path, so other working directories break PDF generation.

```bash
pip install -r requirements-dev.txt                       # app + pytest tooling
python manage.py migrate
python manage.py runserver                                # http://localhost:8000
pytest                                                    # full suite
pytest pdf/tests.py                                       # one app
pytest pdf/tests.py::TestGenerateHcfaBill::test_sex_checkbox   # one test
pytest -k callback                                        # by name
pytest --cov --cov-report=term-missing                    # with coverage
```

No linter or formatter is configured. CI (`.github/workflows/tests.yml`) runs `pytest --cov` on Python 3.13 for every push and PR. Render runs `build.sh` (install, `collectstatic`, `migrate`) and `gunicorn drchrono_compiler.wsgi:application`.

## Local environment

- `settings.py` calls `load_dotenv(BASE_DIR / '.env')`, so `drchrono_compiler/.env` (git-ignored) supplies local config. **Real environment variables override `.env`**: a stray `DATABASE_URL` or `DEBUG` in the shell or a VS Code-injected env file silently wins.
- Local needs `DEBUG=True` (otherwise HTTPS redirect, and `localhost` is only added to `ALLOWED_HOSTS` when `DEBUG` is on), `DATABASE_URL=sqlite:///db.sqlite3`, `DRCHRONO_REDIRECT_URI=http://localhost:8000/oauth/callback` (if it's the Render URL, DrChrono sends local sign-ins to the live site). Use `http://localhost:8000`, not `127.0.0.1`: the OAuth `state` lives in a host-specific session cookie.
- Never point local runs at the production `DATABASE_URL`, and never commit `.env`, generated PDFs, or real patient data.

## Architecture

Apps under `drchrono_compiler/`, all mounted in `drchrono_compiler/urls.py` with namespaces `verify_app` (at `/`), `search_app`, `appts_app`, `pdf_app`. `core` has no routes.

**Auth (`verify`)** — OAuth2 authorization-code flow with plain `requests` (no OAuth library; DrChrono URLs live in `verify/services.py`). `/` is a sign-in page, `/authorize/` saves a random `state` in the session and redirects to DrChrono, `/oauth/callback` checks `state`, exchanges the code, and creates a passwordless Django `User` keyed by DrChrono username. `save_token` is the only place tokens are written to `DrChronoCredential` (one-to-one). Every protected view is wrapped by `verify.services.require_auth` (via `method_decorator(..., name='dispatch')` on CBVs), which calls `get_access_token` (refreshes when under 5 minutes are left, under `select_for_update`) and sets `request.drchrono_token`, or redirects to `/` with a message. Downstream code still calls `get_valid_access_token(request)` again instead of reading that attribute. Every sign-in failure and `CSRF_FAILURE_VIEW` return to `/` with a message.

**DrChrono access (`core/services.py`)** — fetch helpers take the `requests` module and auth `headers` as arguments instead of importing them. Callers pass their own module-level `requests`, which is why tests patch e.g. `pdf.services.requests` and `pdf.views.requests`, not `core.services`. `get_valid_appointments` is the single definition of an "eligible" appointment (past, not cancelled/rescheduled/no-show, has a clinical note PDF, first page of 50 only) and is shared by the appointment list and the balance report.

**Flow** — `search` stores results in the session (`patient_search_results`) between the form POST and `/search/results/`. The appointment list URL carries the patient name in the path (`patient/<id>_<name>/historical/`), and the list form posts that name back as a hidden field so `pdf` can redirect there on failure.

**PDF (`pdf`)** — `GenerateSelectedPDFView.post` merges with pypdf: balance report (all eligible visits, not just selected), then for each selected appointment, oldest first, the downloaded clinical note and an HCFA form. Any exception redirects back to the appointment list with the messages. `fetch_hcfa_data` builds the form dict and raises `Exception(list_of_missing_fields)`. `generate_hcfa_bill` draws text at hand-tuned coordinates on a ReportLab canvas (620×800) and overlays it on `pdf/static/HCFA.pdf`; coordinates only match that template. Practice identity (`PROVIDER_*`, `FEDERAL_TAX_ID`, `PHYSICIAN_SIGNATURE`) is read with `os.getenv` at call time, not from Django settings.

## Tests

- pytest + pytest-django; `pytest.ini` selects `drchrono_compiler/settings_test.py` (in-memory SQLite, dummy DrChrono settings, HTTPS redirect off).
- `conftest.py` autouse fixtures: block all real HTTP (`requests.Session.request` raises), set fake `PROVIDER_*` env vars, `chdir` to the project dir. Shared fixtures: `credential`, `auth_client` (signed-in client with a valid token), `make_request` (request with session + messages).
- `core/testing.py` has fake records (`make_patient`, `make_appointment`, `make_line_item`, `make_pdf_bytes`), `fake_response`, `message_texts`, and `FakeDrChrono`, which replaces the `requests` module and routes `get()` by URL with the `https://app.drchrono.com` prefix stripped (e.g. `'/api/line_items?appointment=1'`); unknown URLs fail the test.
- Four tests fail on purpose, one per known bug, each marked with a `# Known bug:` comment: `scheduled_time` KeyError on the `date` fallback, non-10-digit phone on the HCFA form, empty note buffer breaking the merge, and the `appts:` namespace typo when no visits are selected. Fix the code, not the assertions.
- `verify` tests patch `verify.services.requests.request` (every DrChrono call in `verify` goes through it).
- When moving code between modules, update `patch(...)` targets; a failure there doesn't mean behavior changed.

## Gotchas

- `requirements.txt` is UTF-16 LE with CRLF line endings. Edit it with code that preserves that encoding; `requirements-dev.txt` is plain UTF-8 and includes it with `-r`.
- `generate_hcfa_bill` merges onto a page not attached to a writer; pypdf warns this breaks in pypdf 7. Don't upgrade past 6.x without fixing it.
- `STATICFILES_STORAGE` in settings is ignored by Django 5.2 (use `STORAGES` if static storage matters).
- Keep `README.md`, `SYSTEM_MAP.md` and the app `DOC.md` files in sync with behavior changes; the owner wants docs short and to the point.
