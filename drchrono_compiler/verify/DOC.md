# verify/

DrChrono OAuth2 login and per-user token storage. Every other app relies on `require_auth` from here. Part of the [DrChrono PDF Compiler](../../README.md).

## services.py

- **`refresh_token(cred)`** — Exchanges the stored refresh token for a new access token and saves it. Raises `DrChronoAuthError` on any failure.
- **`get_valid_access_token(request)`** — Returns the user's access token, refreshing it first if expired. Raises `DrChronoAuthError` if the user has no credential.
- **`require_auth`** — View decorator. Redirects to login if the user is anonymous or no valid token can be obtained; otherwise sets `request.drchrono_token` and runs the view.

## views.py

- **`connect_drchrono`** (`/`) — Builds DrChrono's authorization URL, stores the OAuth `state` in the session, and redirects to DrChrono.
- **`oauth_callback`** (`/oauth/callback`) — Exchanges the code for tokens, looks up the DrChrono username, creates or updates a matching passwordless Django `User` and its `DrChronoCredential`, logs in, and redirects to search. If the user is already logged in as that same DrChrono user, it redirects to search without saving the new tokens.
- **`csrf_failure`** — Project-wide CSRF failure handler: shows "session expired" and redirects to login.

## models.py

- **`DrChronoCredential`** — One-to-one with `User`: `access_token`, `refresh_token`, `expires_at`, `scope`, timestamps. `is_expired` is `True` when `expires_at` is missing or past.

## exceptions.py

- **`DrChronoAuthError(message, code=None)`** — Raised for any token/auth failure. Callers respond by sending the user back to log in.

## admin.py

Registers `DrChronoCredential` (user, created, expiry, expired status).
