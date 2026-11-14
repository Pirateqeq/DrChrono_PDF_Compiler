from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.testing import fake_response, message_texts
from verify.exceptions import DrChronoAuthError
from verify.models import DrChronoCredential
from verify.services import (
    authorize_url,
    fetch_current_user,
    get_access_token,
    get_valid_access_token,
    request_token,
    require_auth,
    save_token,
)

LOGIN_URL = reverse('verify_app:connect_drchrono')
SEARCH_URL = reverse('search_app:search')
CALLBACK_URL = reverse('verify_app:oauth_callback')
NEW_TOKEN = {'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_in': 7200}


def expire(cred, minutes_left=-1):
    cred.expires_at = timezone.now() + timedelta(minutes=minutes_left)
    cred.save()
    return cred


@pytest.fixture
def drchrono_http():
    """Every DrChrono call in verify.services goes through requests.request."""
    with patch('verify.services.requests.request') as request:
        request.return_value = fake_response(dict(NEW_TOKEN))
        yield request


# ── Model ─────────────────────────────────────────────────────────────────────

class TestCredentialExpiry:
    def test_missing_expiry_counts_as_expired(self, credential):
        credential.expires_at = None
        assert credential.is_expired

    def test_past_expiry_is_expired(self, credential):
        assert expire(credential).is_expired

    def test_future_expiry_is_valid(self, credential):
        assert not credential.is_expired


# ── DrChrono calls ────────────────────────────────────────────────────────────

class TestAuthorizeUrl:
    def test_contains_app_settings_and_state(self):
        url = urlparse(authorize_url('abc123'))
        query = parse_qs(url.query)

        assert f'{url.scheme}://{url.netloc}{url.path}' == 'https://app.drchrono.com/o/authorize/'
        assert query == {
            'response_type': ['code'],
            'client_id': ['test-client-id'],
            'redirect_uri': ['https://testserver/oauth/callback'],
            'scope': ['user:read patients:read calendar:read clinical:read billing:read'],
            'state': ['abc123'],
        }


class TestRequestToken:
    def test_adds_client_credentials(self, drchrono_http):
        assert request_token(grant_type='authorization_code', code='abc') == NEW_TOKEN

        method, url = drchrono_http.call_args.args
        assert (method, url) == ('POST', 'https://app.drchrono.com/o/token/')
        assert drchrono_http.call_args.kwargs['data'] == {
            'grant_type': 'authorization_code', 'code': 'abc',
            'client_id': 'test-client-id', 'client_secret': 'test-client-secret',
        }
        assert drchrono_http.call_args.kwargs['timeout'] == 10

    @pytest.mark.parametrize('status', [400, 401, 429, 500])
    def test_http_error_raises(self, status, drchrono_http):
        drchrono_http.return_value = fake_response({}, status=status)
        with pytest.raises(DrChronoAuthError):
            request_token(grant_type='refresh_token', refresh_token='r')

    def test_network_error_raises(self, drchrono_http):
        drchrono_http.side_effect = requests.ConnectionError('down')
        with pytest.raises(DrChronoAuthError):
            request_token(grant_type='refresh_token', refresh_token='r')


class TestFetchCurrentUser:
    def test_sends_bearer_token(self, drchrono_http):
        drchrono_http.return_value = fake_response({'id': 7, 'username': 'drjane'})

        assert fetch_current_user('tok') == {'id': 7, 'username': 'drjane'}
        assert drchrono_http.call_args.args == ('GET', 'https://app.drchrono.com/api/users/current')
        assert drchrono_http.call_args.kwargs['headers'] == {'Authorization': 'Bearer tok'}

    def test_error_raises(self, drchrono_http):
        drchrono_http.return_value = fake_response({}, status=403)
        with pytest.raises(DrChronoAuthError):
            fetch_current_user('tok')


# ── Token storage and refresh ─────────────────────────────────────────────────

class TestSaveToken:
    def test_creates_credential(self, user):
        cred = save_token(user, NEW_TOKEN | {'scope': 'patients:read'})

        assert cred.pk
        assert (cred.access_token, cred.refresh_token, cred.scope) == ('new-access', 'new-refresh', 'patients:read')
        assert cred.expires_at > timezone.now() + timedelta(seconds=7100)

    def test_updates_existing_credential(self, credential):
        save_token(credential.user, NEW_TOKEN)

        assert DrChronoCredential.objects.count() == 1
        credential.refresh_from_db()
        assert credential.access_token == 'new-access'

    def test_keeps_old_refresh_token_when_none_returned(self, credential):
        save_token(credential.user, {'access_token': 'new-access', 'expires_in': 3600})

        credential.refresh_from_db()
        assert credential.refresh_token == 'valid-refresh-token'


class TestGetAccessToken:
    def test_usable_token_returned_without_calling_drchrono(self, credential, drchrono_http):
        assert get_access_token(credential.user) == 'valid-access-token'
        drchrono_http.assert_not_called()

    @pytest.mark.parametrize('minutes_left', [-60, 0, 4])
    def test_refreshes_when_expired_or_within_margin(self, minutes_left, credential, drchrono_http):
        expire(credential, minutes_left)

        assert get_access_token(credential.user) == 'new-access'
        assert drchrono_http.call_args.kwargs['data']['grant_type'] == 'refresh_token'
        assert drchrono_http.call_args.kwargs['data']['refresh_token'] == 'valid-refresh-token'
        credential.refresh_from_db()
        assert credential.refresh_token == 'new-refresh'

    def test_skips_refresh_if_done_while_waiting_for_lock(self, credential, drchrono_http):
        expire(credential)
        # First check sees an old token; the re-check after locking sees a fresh one.
        with patch('verify.services._needs_refresh', side_effect=[True, False]):
            assert get_access_token(credential.user) == 'valid-access-token'
        drchrono_http.assert_not_called()

    def test_failed_refresh_raises(self, credential, drchrono_http):
        expire(credential)
        drchrono_http.return_value = fake_response({}, status=400)

        with pytest.raises(DrChronoAuthError):
            get_access_token(credential.user)

    def test_user_without_credential_raises(self, user):
        with pytest.raises(DrChronoAuthError):
            get_access_token(user)

    def test_request_wrapper(self, credential, make_request):
        assert get_valid_access_token(make_request(credential.user)) == 'valid-access-token'


# ── require_auth ──────────────────────────────────────────────────────────────

@require_auth
def protected_view(request):
    return HttpResponse(request.drchrono_token)


class TestRequireAuth:
    def test_anonymous_user_redirected_to_login(self, make_request):
        request = make_request(AnonymousUser())

        response = protected_view(request)

        assert response.url == LOGIN_URL
        assert list(request._messages) == []

    def test_failed_refresh_redirects_with_message(self, credential, make_request, drchrono_http):
        expire(credential)
        drchrono_http.return_value = fake_response({}, status=401)
        request = make_request(credential.user)

        response = protected_view(request)

        assert response.url == LOGIN_URL
        assert [str(m) for m in request._messages] == ['Your DrChrono session expired, please sign in again.']

    def test_usable_token_is_passed_to_view(self, credential, make_request):
        response = protected_view(make_request(credential.user))
        assert response.status_code == 200
        assert response.content == b'valid-access-token'


# ── Sign-in views ─────────────────────────────────────────────────────────────

AUTHORIZE_URL = reverse('verify_app:authorize')
CALLBACK_TOKEN = {'access_token': 'callback-access', 'refresh_token': 'callback-refresh', 'expires_in': 7200}


class TestConnectPage:
    def test_shows_sign_in_button(self, client, db):
        response = client.get(LOGIN_URL)

        assert response.status_code == 200
        assert f'href="{AUTHORIZE_URL}"' in response.content.decode()

    def test_signed_in_user_goes_to_search(self, auth_client):
        response = auth_client.get(LOGIN_URL)
        assert response.url == SEARCH_URL

    def test_signed_in_user_with_dead_token_sees_sign_in(self, auth_client, credential, drchrono_http):
        expire(credential)
        drchrono_http.return_value = fake_response({}, status=400)

        response = auth_client.get(LOGIN_URL)

        assert response.status_code == 200
        assert b'Sign in with DrChrono' in response.content


class TestAuthorize:
    def test_redirects_to_drchrono_with_saved_state(self, client, db):
        response = client.get(AUTHORIZE_URL)

        query = parse_qs(urlparse(response.url).query)
        assert response.url.startswith('https://app.drchrono.com/o/authorize/?')
        assert query['state'] == [client.session['oauth_state']]
        assert len(client.session['oauth_state']) >= 32


@pytest.fixture
def drchrono_login():
    """DrChrono answers the token exchange and the current-user lookup."""
    def respond(method, url, **kwargs):
        if method == 'POST':
            return fake_response(dict(CALLBACK_TOKEN))
        return fake_response({'id': 7, 'username': 'drjane'})

    with patch('verify.services.requests.request', side_effect=respond) as request:
        yield request


def sign_in(client, **params):
    """Start sign-in, then return from DrChrono to the callback with the saved state."""
    client.get(AUTHORIZE_URL)
    query = {'code': 'abc', 'state': client.session['oauth_state']} | params
    return client.get(CALLBACK_URL, {k: v for k, v in query.items() if v is not None})


class TestOAuthCallback:
    def test_new_user_is_created_and_logged_in(self, client, db, drchrono_login):
        response = sign_in(client)

        assert response.url == SEARCH_URL
        user = User.objects.get(username='drjane')
        assert user.drchrono_cred.access_token == 'callback-access'
        assert user.drchrono_cred.refresh_token == 'callback-refresh'
        assert user.drchrono_cred.expires_at > timezone.now() + timedelta(seconds=7100)
        assert client.session['_auth_user_id'] == str(user.pk)
        assert 'oauth_state' not in client.session
        assert 'Successfully connected as drjane' in message_texts(response)

    def test_code_exchange_request(self, client, db, drchrono_login):
        sign_in(client)

        token_call, user_call = drchrono_login.call_args_list
        assert token_call.kwargs['data'] == {
            'grant_type': 'authorization_code', 'code': 'abc',
            'redirect_uri': 'https://testserver/oauth/callback',
            'client_id': 'test-client-id', 'client_secret': 'test-client-secret',
        }
        assert user_call.kwargs['headers'] == {'Authorization': 'Bearer callback-access'}

    def test_new_user_has_unusable_password(self, client, db, drchrono_login):
        sign_in(client)
        assert not User.objects.get(username='drjane').has_usable_password()

    def test_existing_user_gets_new_tokens(self, client, credential, drchrono_login):
        sign_in(client)

        credential.refresh_from_db()
        assert credential.access_token == 'callback-access'
        assert User.objects.count() == 1

    def test_signed_in_user_with_expired_token_gets_new_tokens(self, auth_client, credential, drchrono_login):
        expire(credential)

        sign_in(auth_client)

        credential.refresh_from_db()
        assert credential.access_token == 'callback-access'
        assert not credential.is_expired

    @pytest.mark.parametrize('params, message', [
        ({'error': 'access_denied', 'code': None}, 'Sign-in was cancelled.'),
        ({'state': 'forged'}, 'Sign-in expired, please try again.'),
        ({'state': None}, 'Sign-in expired, please try again.'),
    ])
    def test_rejected_before_calling_drchrono(self, params, message, client, db, drchrono_login):
        response = sign_in(client, **params)

        assert response.url == LOGIN_URL
        assert message in message_texts(response)
        drchrono_login.assert_not_called()
        assert not User.objects.exists()

    def test_callback_without_starting_sign_in(self, client, db, drchrono_login):
        response = client.get(CALLBACK_URL, {'code': 'abc', 'state': 'anything'})

        assert 'Sign-in expired, please try again.' in message_texts(response)
        drchrono_login.assert_not_called()

    @pytest.mark.parametrize('failing_method', ['POST', 'GET'])
    def test_drchrono_failure(self, failing_method, client, db, drchrono_login):
        respond = drchrono_login.side_effect

        def fail_one(method, url, **kwargs):
            if method == failing_method:
                raise requests.ConnectionError('down')
            return respond(method, url, **kwargs)

        drchrono_login.side_effect = fail_one

        response = sign_in(client)

        assert response.url == LOGIN_URL
        assert "Couldn't sign in to DrChrono, please try again." in message_texts(response)
        assert not User.objects.exists()


class TestCsrfFailure:
    def test_redirects_to_sign_in_with_message(self, credential):
        client = Client(enforce_csrf_checks=True)
        client.force_login(credential.user)

        response = client.post(SEARCH_URL, {'last_name': 'Doe'})

        assert response.status_code == 302
        assert response.url == LOGIN_URL
        assert 'Your session has expired, please sign in again.' in message_texts(response)


class TestCredentialAdmin:
    @pytest.fixture
    def admin_client(self, client, credential):
        client.force_login(User.objects.create_superuser('admin', 'admin@example.test', 'pw'))
        return client

    def test_list_shows_credentials(self, admin_client):
        response = admin_client.get(reverse('admin:verify_drchronocredential_changelist'))

        assert response.status_code == 200
        assert b'drjane' in response.content

    def test_edit_form_hides_tokens(self, admin_client, credential):
        response = admin_client.get(reverse('admin:verify_drchronocredential_change', args=[credential.pk]))

        html = response.content.decode()
        assert response.status_code == 200
        assert 'valid-access-token' not in html and 'valid-refresh-token' not in html
        assert 'name="access_token"' not in html and 'name="refresh_token"' not in html
        assert 'name="scope"' in html
