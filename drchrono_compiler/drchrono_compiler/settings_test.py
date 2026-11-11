"""Settings for the test suite. Never used in production."""

from .settings import *  # noqa: F401,F403

SECRET_KEY = 'test-secret-key'
DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Production forces HTTPS; the test client speaks plain HTTP.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

DRCHRONO_CLIENT_ID = 'test-client-id'
DRCHRONO_CLIENT_SECRET = 'test-client-secret'
DRCHRONO_REDIRECT_URI = 'https://testserver/oauth/callback'
DRCHRONO_SCOPES = 'user:read patients:read calendar:read clinical:read billing:read'
