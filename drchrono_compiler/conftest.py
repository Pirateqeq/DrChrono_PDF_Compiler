from datetime import timedelta

import pytest
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory
from django.utils import timezone

from verify.models import DrChronoCredential

PROVIDER_ENV = {
    'PROVIDER_NAME': 'Springfield Chiropractic',
    'PROVIDER_NPI': '1234567890',
    'FEDERAL_TAX_ID': '12-3456789',
    'PROVIDER_ACCOUNT_NUMBER': 'ACCT-42',
    'PHYSICIAN_SIGNATURE': 'Dr. Sam Smith',
    'PROVIDER_OFFICE_NAME': 'Springfield Chiropractic',
    'PROVIDER_ADDRESS': '500 Oak Ave',
    'PROVIDER_CITY_STATE': 'Springfield, IL 62701',
    'PROVIDER_PHONE': '217 555-0199',
    'PROVIDER_INFO': 'Springfield Chiropractic',
}


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail any test that reaches the real network instead of a mock."""
    def refuse(*args, **kwargs):
        raise RuntimeError('Unmocked HTTP request in a test')
    monkeypatch.setattr(requests.sessions.Session, 'request', refuse)


@pytest.fixture(autouse=True)
def provider_env(monkeypatch):
    for key, value in PROVIDER_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def user(db):
    user = User.objects.create(username='drjane')
    user.set_unusable_password()
    user.save()
    return user


@pytest.fixture
def credential(user):
    return DrChronoCredential.objects.create(
        user=user,
        access_token='valid-access-token',
        refresh_token='valid-refresh-token',
        expires_at=timezone.now() + timedelta(hours=1),
        scope=settings.DRCHRONO_SCOPES,
    )


@pytest.fixture
def auth_client(client, credential):
    client.force_login(credential.user)
    return client


@pytest.fixture
def make_request(db):
    """Build a request with a session and message storage, for calling helpers directly."""
    def build(user=None, path='/'):
        request = RequestFactory().get(path)
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        if user is not None:
            request.user = user
        return request
    return build
