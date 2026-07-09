# drchrono_compiler/ (project settings)

Part of the [DrChrono PDF Compiler](../../README.md), which connects to DrChrono (a cloud-based EHR / practice-management platform) to generate billing PDFs. This doc covers project-wide config and routing only — no patient data logic lives here.

## settings.py

- Secrets, DB URL, and DrChrono client ID/secret/redirect/scopes all come from env vars. DrChrono's actual auth/token/revoke URLs are hardcoded (they don't change).
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` are hardcoded to the Render domain only — running `manage.py runserver` locally will hit `DisallowedHost` unless you add `localhost` yourself.
- `WhiteNoiseMiddleware` sits right after `SecurityMiddleware` so static files are served straight from gunicorn, no separate static host. Requires `collectstatic` (already in `build.sh`).
- `CSRF_FAILURE_VIEW` is overridden to [`verify.views.csrf_failure`](../verify/DOC.md) — a CSRF failure (e.g. stale session mid-OAuth) redirects back into the login flow with a message instead of Django's default 403 page.

## urls.py

- Root routing only, one line per app: `''` → [`verify`](../verify/DOC.md) (namespace `verify_app`), `search/` → [`search`](../search/DOC.md) (`search_app`), `appts/` → [`appts`](../appts/DOC.md) (`appts_app`), `pdf/` → [`pdf`](../pdf/DOC.md) (`pdf_app`).
- `verify` sits at the site root, so its OAuth entry point is effectively the landing page.
- [`core`](../core/DOC.md) has no `urls.py` — it's a shared service layer, not URL-routed.

## wsgi.py / asgi.py

- `wsgi.py` is what gunicorn actually runs in production. `asgi.py` is unused leftover from `startproject`.

## templates/base.html (project root)

The shared layout every app's templates extend via `{% extends "base.html" %}` — navbar, alert/message rendering, and footer. It lives here at the project root's `templates/` folder (rather than inside any one app) because `TEMPLATES['DIRS']` in `settings.py` points at this location.
