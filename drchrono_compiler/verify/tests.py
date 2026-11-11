from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.testing import fake_response, message_texts
from verify.exceptions import DrChronoAuthError
from verify.models import DrChronoCredential
from verify.services import get_valid_access_token, refresh_token, require_auth

LOGIN_URL = reverse('verify_app:connect_drchrono')
SEARCH_URL = reverse('search_app:search')
CALLBACK_URL = reverse('verify_app:oauth_callback')


def expire(cred):
    cred.expires_at = timezone.now() - timedelta(minutes=1)
    cred.save()
    return cred


# ── Model ─────────────────────────────────────────────────────────────────────

class TestCredentialExpiry:
    def test_missing_expiry_counts_as_expired(self, credential):
        credential.expires_at = None
        assert credential.is_expired

    def test_past_expiry_is_expired(self, credential):
        assert expire(credential).is_expired

    def test_future_expiry_is_valid(self, credential):
        assert not credential.is_expired


# ── refresh_token ─────────────────────────────────────────────────────────────

class TestRefreshToken:
    @patch('verify.services.requests.post')
    def test_success_saves_new_token_and_expiry(self, post, credential):
        post.return_value = fake_response({
            'access_token': 'new-access', 'refresh_token': 'new-refresh',
            'expires_in': 7200, 'scope': 'patients:read',
        })

        refresh_token(credential)

        credential.refresh_from_db()
        assert credential.access_token == 'new-access'
        assert credential.refresh_token == 'new-refresh'
        assert credential.scope == 'patients:read'
        assert credential.expires_at > timezone.now() + timedelta(seconds=7100)
        sent = post.call_args.kwargs['data']
        assert sent['grant_type'] == 'refresh_token'
        assert sent['refresh_token'] == 'valid-refresh-token'
        assert sent['client_id'] == 'test-client-id'

    @patch('verify.services.requests.post')
    def test_keeps_old_refresh_token_when_none_returned(self, post, credential):
        post.return_value = fake_response({'access_token': 'new-access', 'expires_in': 3600})

        refresh_token(credential)

        credential.refresh_from_db()
        assert credential.refresh_token == 'valid-refresh-token'

    def test_no_refresh_token_raises(self, credential):
        credential.refresh_token = None
        with pytest.raises(DrChronoAuthError):
            refresh_token(credential)

    @pytest.mark.parametrize('status', [400, 401, 500])
    @patch('verify.services.requests.post')
    def test_rejected_refresh_raises(self, post, status, credential):
        post.return_value = fake_response({}, status=status)
        with pytest.raises(DrChronoAuthError):
            refresh_token(credential)

    @patch('verify.services.requests.post', side_effect=requests.ConnectionError('down'))
    def test_network_error_raises(self, post, credential):
        with pytest.raises(DrChronoAuthError):
            refresh_token(credential)


# ── get_valid_access_token ────────────────────────────────────────────────────

class TestGetValidAccessToken:
    @patch('verify.services.requests.post')
    def test_valid_token_returned_without_refresh(self, post, credential, make_request):
        assert get_valid_access_token(make_request(credential.user)) == 'valid-access-token'
        post.assert_not_called()

    @patch('verify.services.requests.post')
    def test_expired_token_is_refreshed(self, post, credential, make_request):
        expire(credential)
        post.return_value = fake_response({'access_token': 'fresh', 'expires_in': 3600})

        assert get_valid_access_token(make_request(credential.user)) == 'fresh'

    def test_user_without_credential_raises(self, user, make_request):
        with pytest.raises(DrChronoAuthError):
            get_valid_access_token(make_request(user))


# ── require_auth ──────────────────────────────────────────────────────────────

@require_auth
def protected_view(request):
    return HttpResponse(request.drchrono_token)


class TestRequireAuth:
    def test_anonymous_user_redirected_to_login(self, make_request):
        from django.contrib.auth.models import AnonymousUser
        response = protected_view(make_request(AnonymousUser()))
        assert response.status_code == 302
        assert response.url == LOGIN_URL

    @patch('verify.services.requests.post')
    def test_failed_refresh_redirects_to_login(self, post, credential, make_request):
        expire(credential)
        post.return_value = fake_response({}, status=401)

        response = protected_view(make_request(credential.user))

        assert response.status_code == 302
        assert response.url == LOGIN_URL

    def test_valid_token_is_passed_to_view(self, credential, make_request):
        response = protected_view(make_request(credential.user))
        assert response.status_code == 200
        assert response.content == b'valid-access-token'


# ── Login views ───────────────────────────────────────────────────────────────

class TestConnectDrChrono:
    def test_redirects_to_drchrono_authorize_with_state(self, client, db):
        response = client.get(LOGIN_URL)

        assert response.status_code == 302
        url = urlparse(response.url)
        query = parse_qs(url.query)
        assert f'{url.scheme}://{url.netloc}{url.path}' == 'https://app.drchrono.com/o/authorize/'
        assert query['client_id'] == ['test-client-id']
        assert query['redirect_uri'] == ['https://testserver/oauth/callback']
        assert 'patients:read' in query['scope'][0]
        assert query['state'] == [client.session['oauth_state']]


TOKEN = {'access_token': 'callback-access', 'refresh_token': 'callback-refresh', 'expires_in': 7200}


@pytest.fixture
def drchrono_login():
    """Patch the token exchange and user lookup that oauth_callback performs."""
    with patch('verify.views.OAuth2Session') as session_cls, \
            patch('verify.views.requests.get') as get:
        session_cls.return_value.fetch_token.return_value = dict(TOKEN)
        get.return_value = fake_response({'username': 'drjane'})
        yield session_cls.return_value, get


class TestOAuthCallback:
    def test_new_user_is_created_and_logged_in(self, client, db, drchrono_login):
        response = client.get(CALLBACK_URL, {'code': 'abc', 'state': 'xyz'})

        assert response.status_code == 302
        assert response.url == SEARCH_URL
        user = User.objects.get(username='drjane')
        assert user.drchrono_cred.access_token == 'callback-access'
        assert user.drchrono_cred.refresh_token == 'callback-refresh'
        assert user.drchrono_cred.expires_at > timezone.now() + timedelta(seconds=7100)
        assert client.session['_auth_user_id'] == str(user.pk)
        assert 'Successfully connected as drjane' in message_texts(response)

    def test_new_user_has_unusable_password(self, client, db, drchrono_login):
        # Known bug: set_unusable_password() runs after the user is saved and is never
        # saved itself, so the stored password is '' rather than marked unusable.
        client.get(CALLBACK_URL, {'code': 'abc', 'state': 'xyz'})

        assert not User.objects.get(username='drjane').has_usable_password()

    def test_existing_user_gets_new_tokens(self, client, credential, drchrono_login):
        client.get(CALLBACK_URL, {'code': 'abc', 'state': 'xyz'})

        credential.refresh_from_db()
        assert credential.access_token == 'callback-access'
        assert User.objects.count() == 1

    def test_signed_in_user_with_expired_token_gets_new_tokens(self, auth_client, credential, drchrono_login):
        # Known bug: the callback returns early for an already signed-in user and drops
        # the new tokens, so a user whose refresh failed loops back to DrChrono sign-in.
        expire(credential)

        auth_client.get(CALLBACK_URL, {'code': 'abc', 'state': 'xyz'})

        credential.refresh_from_db()
        assert credential.access_token == 'callback-access'
        assert not credential.is_expired

    def test_token_exchange_failure(self, client, db, drchrono_login):
        session, _ = drchrono_login
        session.fetch_token.side_effect = Exception('invalid_grant')

        response = client.get(CALLBACK_URL, {'code': 'bad'})

        assert response.url == LOGIN_URL
        assert 'Unable to fetch token' in message_texts(response)
        assert not User.objects.exists()

    def test_user_lookup_failure(self, client, db, drchrono_login):
        _, get = drchrono_login
        get.return_value = fake_response({}, status=500)

        response = client.get(CALLBACK_URL, {'code': 'abc'})

        assert response.url == LOGIN_URL
        assert 'Could not fetch user information from DrChrono' in message_texts(response)
        assert not User.objects.exists()


class TestCsrfFailure:
    def test_redirects_to_login_with_message(self, credential):
        client = Client(enforce_csrf_checks=True)
        client.force_login(credential.user)

        response = client.post(SEARCH_URL, {'last_name': 'Doe'})

        assert response.status_code == 302
        assert response.url == LOGIN_URL
        assert 'Your session has expired please relogin' in message_texts(response)


class TestCredentialAdmin:
    def test_admin_list_shows_credentials(self, client, credential):
        admin = User.objects.create_superuser('admin', 'admin@example.test', 'pw')
        client.force_login(admin)

        response = client.get(reverse('admin:verify_drchronocredential_changelist'))

        assert response.status_code == 200
        assert b'drjane' in response.content
