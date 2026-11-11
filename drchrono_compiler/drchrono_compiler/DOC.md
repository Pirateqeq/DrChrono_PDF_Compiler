# drchrono_compiler/ (project config)

Settings and routing for the [DrChrono PDF Compiler](../../README.md). No business logic.

## settings.py

- Secrets, database, and DrChrono client settings come from env vars (see the [README](../../README.md#environment-variables)). DrChrono's auth/token/revoke URLs are hardcoded.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` list only the Render domain — add `localhost` for local runs.
- When `DEBUG` is off: HTTPS redirect, secure session/CSRF cookies. HSTS (1 year, subdomains, preload) is always set. `SECURE_PROXY_SSL_HEADER` trusts Render's `X-Forwarded-Proto`.
- `WhiteNoiseMiddleware` serves static files directly from gunicorn.
- `CSRF_FAILURE_VIEW` = [`verify.views.csrf_failure`](../verify/DOC.md): a CSRF failure sends the user back to log in instead of a 403.
- `TEMPLATES['DIRS']` points at the project-level `templates/` folder.

## urls.py

| Prefix | App | Namespace |
|---|---|---|
| `admin/` | Django admin | — |
| `''` | [`verify`](../verify/DOC.md) | `verify_app` |
| `search/` | [`search`](../search/DOC.md) | `search_app` |
| `appts/` | [`appts`](../appts/DOC.md) | `appts_app` |
| `pdf/` | [`pdf`](../pdf/DOC.md) | `pdf_app` |

[`core`](../core/DOC.md) has no routes. Because `verify` is mounted at the root, `/` starts the DrChrono login.

## wsgi.py

Entry point for gunicorn in production.

## templates/layout.html

Base template every page extends: nav bar with connection status, flash messages (dismissible), and footer. Defines `title`, `extra_head`, `content`, and `extra_js` blocks.
