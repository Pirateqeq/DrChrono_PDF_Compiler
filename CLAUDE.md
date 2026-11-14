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

**Auth (`verify`)** — OAuth2 authorization-code flow with plain `requests` (no OAuth library; DrChrono URLs live in `verify/services.py`). `/` is a sign-in page, `/authorize/` saves a random `state` in the session and redirects to DrChrono, `/oauth/callback` checks `state`, exchanges the code, and creates a passwordless Django `User` keyed by DrChrono username. `save_token` is the only place tokens are written to `DrChronoCredential` (one-to-one). Every protected view is wrapped by `verify.services.require_auth` (via `method_decorator(..., name='dispatch')` on CBVs), which calls `get_access_token` (refreshes when under 5 minutes are left, under `select_for_update`) and sets `request.drchrono_token`, or redirects to `/` with a message. Downstream code reads the token from that attribute. Every sign-in failure and `CSRF_FAILURE_VIEW` return to `/` with a message. The navbar's **Log out** (POST `/logout/`) signs out of this app only: revokes the token at DrChrono (best effort), deletes the credential, ends the session, and returns to `/`. The user's DrChrono session is untouched.

**DrChrono access (`core/drchrono.py`)** — every DrChrono data call goes through `drchrono.get(token, path, **params)` (base URL, Bearer header, 10s timeout; failures raise `DrChronoError` with `.status`). `get_all` follows `next` page links. Helpers: `patient`, `appointment`, `line_items(appointment= or patient=)`, `eligible_appointments`. Callers pass `request.drchrono_token`. `eligible_appointments` is the single definition of an "eligible" visit (every page, `occurred_since` 3 years ago, `exclude_membership`, not cancelled/rescheduled/no-show, dated today or earlier with `date` fallback, has a clinical note PDF; returns copies, newest first) and is shared by the appointment list and the balance report. DrChrono caps appointment pages at 20–25, so always page.

**Flow** — `search` (two function views) stores one slim session entry, `patient_search` (`patients` with only id/names/DOB/chart ID, a `more` flag, the `query`), between the form POST and `/search/results/`. The appointment list is `/appts/patient/<id>/`: only the ID is in the URL, and the name is fetched from DrChrono. `pdf` redirects back there by ID. Views catch `DrChronoError`, re-raise a 401 (so `require_auth` sends the user to sign in) and show `core.drchrono.user_message(e)` for anything else. Sessions last 12 hours (`SESSION_COOKIE_AGE`).

**PDF (`pdf`)** — `GenerateSelectedPDFView.post` merges with pypdf: balance report (all eligible visits, not just selected), then for each selected appointment, oldest first, the downloaded clinical note and an HCFA form. Any exception redirects back to the appointment list with the messages. `fetch_hcfa_data` builds the form dict and raises `Exception(list_of_missing_fields)`. `generate_hcfa_bill` draws text at hand-tuned coordinates on a ReportLab canvas (620×800) and overlays it on `pdf/static/HCFA.pdf`; coordinates only match that template. Practice identity (`PROVIDER_*`, `FEDERAL_TAX_ID`, `PHYSICIAN_SIGNATURE`) is read with `os.getenv` at call time, not from Django settings.

## Tests

- pytest + pytest-django; `pytest.ini` selects `drchrono_compiler/settings_test.py` (in-memory SQLite, dummy DrChrono settings, HTTPS redirect off).
- `conftest.py` autouse fixtures: block all real HTTP (`requests.Session.request` raises), set fake `PROVIDER_*` env vars, `chdir` to the project dir. Shared fixtures: `credential`, `auth_client` (signed-in client with a valid token), `make_request` (request with session + messages).
- `core/testing.py` has fake records (`make_patient`, `make_appointment`, `make_line_item`, `make_pdf_bytes`), `fake_response`, `message_texts`, and `FakeDrChrono`. Patch `core.drchrono.requests.get` with `FakeDrChrono(...).get`; routes are keyed by URL without the host, `'/api/line_items?appointment=1'` matches that path with those exact params, a bare path matches any params, unknown URLs fail the test. `pdf` tests also replace `pdf.services.requests` with it for clinical-note downloads.
- Two tests fail on purpose, one per known bug, each marked with a `# Known bug:` comment (both in `pdf`): non-10-digit phone on the HCFA form, and the empty note buffer breaking the merge. Fix the code, not the assertions.
- `verify` tests patch `verify.services.requests.request` (every DrChrono call in `verify` goes through it).
- When moving code between modules, update `patch(...)` targets; a failure there doesn't mean behavior changed.

## Gotchas

- `requirements.txt` is UTF-16 LE with CRLF line endings. Edit it with code that preserves that encoding; `requirements-dev.txt` is plain UTF-8 and includes it with `-r`.
- `generate_hcfa_bill` merges onto a page not attached to a writer; pypdf warns this breaks in pypdf 7. Don't upgrade past 6.x without fixing it.
- `STATICFILES_STORAGE` in settings is ignored by Django 5.2 (use `STORAGES` if static storage matters).
- Keep `README.md`, `SYSTEM_MAP.md` and the app `DOC.md` files in sync with behavior changes; the owner wants docs short and to the point.
