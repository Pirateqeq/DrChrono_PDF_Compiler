# verify/

Part of the [DrChrono PDF Compiler](../../README.md). Signs staff in with their own DrChrono accounts (OAuth2 authorization-code flow), stores each person's DrChrono tokens, and keeps them fresh. Every other app relies on `require_auth` from here.

The flow uses plain `requests` calls, following DrChrono's own documented example, instead of an OAuth library. Each person signs in as themselves, so DrChrono's audit trail shows who accessed which patient.

## Sign-in flow

1. **`/` (`connect_drchrono`)** shows the sign-in page (`templates/verify/connect.html`) with a "Sign in with DrChrono" button. Messages from failed sign-ins and expired sessions appear here. A user who is already signed in with a usable token goes straight to search instead.
2. **`/authorize/` (`authorize`)** creates a random `state` (`secrets.token_urlsafe(32)`), saves it in the session, and redirects to DrChrono's `/o/authorize/` page.
3. The user approves (or cancels) on DrChrono, which redirects to **`/oauth/callback` (`oauth_callback`)**. That path is registered in the DrChrono app settings, so it must not change. The callback:
   1. Removes the saved `state` from the session, so each sign-in can be completed only once.
   2. Stops if DrChrono sent `error` (the user clicked Cancel).
   3. Stops if `state` is missing or doesn't match the saved one (`secrets.compare_digest`). This rejects a sign-in that wasn't started in this browser session.
   4. Exchanges the one-time `code` at `/o/token/`. DrChrono's code expires within seconds, so this happens immediately.
   5. Looks up the DrChrono username at `/api/users/current`.
   6. Gets or creates a Django `User` with that username. New users get an unusable password: DrChrono is the only way in.
   7. Saves the tokens (always, including for a user who is already signed in) and logs the user in.

Every failure goes through `_back_to_sign_in`, which sets an error message and returns to `/`:

| Situation | Message on the sign-in page |
|---|---|
| Cancel on DrChrono's screen | "Sign-in was cancelled." |
| `state` missing, wrong, or callback opened directly | "Sign-in expired, please try again." |
| Token exchange or user lookup fails (network, HTTP error, unexpected reply) | "Couldn't sign in to DrChrono, please try again." |
| CSRF check fails anywhere in the site (`csrf_failure`, set as `CSRF_FAILURE_VIEW`) | "Your session has expired, please sign in again." |
| Token can't be refreshed on a protected page (`require_auth`) | "Your DrChrono session expired, please sign in again." |

## Tokens and refresh

DrChrono access tokens last 48 hours. One PDF build makes many API calls, so a token that expires midway would break it.

- **`save_token(user, token)`** is the only place tokens are written. It stores the access token, the refresh token, `expires_at` (now + `expires_in`) and `scope`. The docs don't say whether a refresh returns a new refresh token, so the old one is kept when none comes back.
- **`get_access_token(user)`** returns the stored access token while more than 5 minutes are left. Otherwise it refreshes:
  1. Opens a transaction and locks the credential row (`select_for_update`).
  2. Re-checks the expiry, because another request may have refreshed it while this one waited. If so, it returns that token.
  3. Otherwise posts the refresh token to `/o/token/` and saves the result.

  The lock matters because a refresh token may be single-use: two tabs refreshing at once could otherwise invalidate each other and log the user out.
- **`require_auth`** wraps every protected view. Signed-out users go to `/`. Otherwise it calls `get_access_token`, puts the token on `request.drchrono_token`, and runs the view, or returns to `/` with the "session expired" message if the refresh fails. Class-based views use it through `method_decorator(require_auth, name='dispatch')`.
- **`get_valid_access_token(request)`** is kept so `search`, `appts` and `pdf` keep working; they can switch to `request.drchrono_token`.

## DrChrono calls (`services.py`)

All requests go through `_call`, which adds a 10-second timeout and turns any `requests` failure (network error, non-2xx status, unreadable JSON) into `DrChronoAuthError`.

| Function | DrChrono endpoint | Notes |
|---|---|---|
| `authorize_url(state)` | `/o/authorize/` | Builds the URL only; no request. Sends client ID, redirect URI, scopes and `state`. |
| `request_token(**data)` | `POST /o/token/` | Code exchange or refresh. Adds `client_id` and `client_secret` in this one place. |
| `fetch_current_user(access_token)` | `GET /api/users/current` | DrChrono redirects this to `/api/users/{id}`; `requests` follows it with the same header. |

Settings used: `DRCHRONO_CLIENT_ID`, `DRCHRONO_CLIENT_SECRET`, `DRCHRONO_REDIRECT_URI`, `DRCHRONO_SCOPES` (all from environment variables). The DrChrono base URL is a constant in `services.py`.

Rate limit: DrChrono allows 500 calls per hour per app. A sign-in costs 2 calls and a refresh 1.

## Models, admin, errors

- **`DrChronoCredential`** (`models.py`) — One per user (`user.drchrono_cred`): `access_token`, `refresh_token`, `expires_at`, `scope`, `created_at`, `updated_at`. `is_expired` (missing or past `expires_at`) is shown in the admin list; refresh decisions use the 5-minute margin in `services.py` instead.
- **Admin** (`admin.py`) — Lists user, created, expiry and expired status. The edit form excludes both tokens, so live credentials are never displayed or edited there.
- **`DrChronoAuthError`** (`exceptions.py`) — Raised for every DrChrono sign-in or token failure. `.message` returns the text (used by `search`).

## Local development

- `DRCHRONO_REDIRECT_URI` must be `http://localhost:8000/oauth/callback` and registered in the DrChrono app alongside the Render URL. If it points at Render, DrChrono finishes local sign-ins on the live site.
- Open the app at `http://localhost:8000`, not `127.0.0.1`. The saved `state` lives in a session cookie for whichever host started the sign-in, and DrChrono returns to `localhost`.

## Tests (`tests.py`)

Every DrChrono call in `verify` goes through `requests.request`, so tests patch `verify.services.requests.request`. The `drchrono_http` fixture answers with a token; `drchrono_login` answers both the token exchange and the user lookup. `sign_in(client)` starts at `/authorize/` and returns to the callback with the saved `state`.
