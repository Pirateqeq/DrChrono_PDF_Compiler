# verify/

Part of the [DrChrono PDF Compiler](../../README.md), which connects to DrChrono (a cloud-based EHR / practice-management platform) to generate billing PDFs. This doc covers the `verify/` app only.

Handles the DrChrono OAuth2 login flow and holds each user's access/refresh tokens. Every other app depends on this one — `require_auth` and `get_valid_access_token` are what let [`search`](../search/DOC.md), [`appts`](../appts/DOC.md), and [`pdf`](../pdf/DOC.md) call the DrChrono API on a user's behalf.

## services.py

The core of the app — token lifecycle logic used by every protected view in the project.

- **`refresh_token(cred)`** — Posts the stored refresh token to DrChrono's token endpoint, then updates and saves the credential with the new access token and expiry. Raises `DrChronoAuthError` if DrChrono rejects the refresh (expired/revoked) or the request fails outright.
- **`get_valid_access_token(request)`** — The function everything else calls. Returns the current user's access token as-is if still valid, otherwise refreshes it first. Raises `DrChronoAuthError` if the user has no stored credential at all.
- **`require_auth`** — Decorator applied to every protected view (in [`search`](../search/DOC.md), [`appts`](../appts/DOC.md), and [`pdf`](../pdf/DOC.md)). Redirects anonymous users to `connect_drchrono`; otherwise fetches a valid token and attaches it to `request.drchrono_token`. Any auth failure sends the user back into the OAuth flow instead of raising an error.

## views.py

The three entry points to the login flow.

- **`connect_drchrono`** — Builds DrChrono's authorization URL from the client ID/scopes, saves a CSRF state value to the session, and redirects the user to DrChrono to approve access. This is the site's landing page.
- **`oauth_callback`** — Where DrChrono redirects back to after approval. Exchanges the auth code for tokens, fetches the DrChrono user's identity, and creates/updates a matching local Django `User` (passwordless — this app never authenticates a password, DrChrono is the sole identity provider) along with its `DrChronoCredential`. Logs the user in and sends them to patient search.
- **`csrf_failure`** — Wired up in [`settings.py`](../drchrono_compiler/DOC.md) as `CSRF_FAILURE_VIEW`. Replaces Django's default 403 page with a "please relogin" message and a redirect back to `connect_drchrono` — mainly matters if a session goes stale mid-OAuth.

## models.py

- **`DrChronoCredential`** — One-to-one with Django's `User`. Stores `access_token`, `refresh_token`, `expires_at`, and `scope`. The `is_expired` property (treats a missing `expires_at` as expired) is what `require_auth` checks before deciding whether to refresh.

## exceptions.py

- **`DrChronoAuthError`** — Raised anywhere the OAuth/token flow fails. Every place it's caught across the codebase does the same thing: send the user back to log in.

## urls.py

Two routes under the `verify_app` namespace: `connect_drchrono` at the app root and `oauth/callback` for DrChrono's redirect. Because this app is mounted at `''` in the root URL conf, `connect_drchrono` is effectively the site's homepage.

## admin.py

Registers `DrChronoCredential` in the Django admin (user, timestamps, expiry status) for support/debugging visibility into whose token is active or stale.

## apps.py / migrations/

Standard Django boilerplate — no custom logic.
