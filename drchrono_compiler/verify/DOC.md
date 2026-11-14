# verify/

DrChrono OAuth2 sign-in and per-user token storage, with plain `requests` calls (no OAuth library). Every other app relies on `require_auth` from here. Part of the [DrChrono PDF Compiler](../../README.md).

## services.py

- **`authorize_url(state)`** — DrChrono's `/o/authorize/` URL with client ID, redirect URI, scopes and `state`.
- **`request_token(**data)`** — POST to `/o/token/` for the code exchange or a refresh; adds the client credentials.
- **`fetch_current_user(access_token)`** — `GET /api/users/current`.
- **`save_token(user, token)`** — The only place tokens are written. Keeps the old refresh token if DrChrono sends none.
- **`get_access_token(user)`** — Returns the token, refreshing it when less than 5 minutes are left. The refresh runs under a row lock and re-checks, so two requests never spend the same refresh token.
- **`require_auth`** — View decorator: sets `request.drchrono_token`, or redirects to `/` (with "session expired" if a refresh failed).
- **`get_valid_access_token(request)`** — Kept for `search`, `appts` and `pdf` until they read `request.drchrono_token`.

All DrChrono failures raise `DrChronoAuthError` (`exceptions.py`).

## views.py

- **`connect_drchrono`** (`/`) — Sign-in page (`templates/verify/connect.html`); users with a usable token go straight to search.
- **`authorize`** (`/authorize/`) — Saves a random `state` in the session and redirects to DrChrono.
- **`oauth_callback`** (`/oauth/callback`) — Rejects a cancel or a missing/mismatched `state`, exchanges the code, looks up the username, creates the user (unusable password) if new, always saves the tokens, logs in. Every failure returns to `/` with a message.
- **`csrf_failure`** — Project-wide CSRF failure handler; same return to `/`.

## models.py / admin.py

- **`DrChronoCredential`** — One-to-one with `User`: tokens, `expires_at`, `scope`, timestamps; `is_expired` for the admin list.
- The admin edit form never shows the tokens.
