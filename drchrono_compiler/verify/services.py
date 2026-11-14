from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone

from core.drchrono import DRCHRONO

from .exceptions import DrChronoAuthError
from .models import DrChronoCredential



def authorize_url(state):
    params = {'response_type': 'code', 'client_id': settings.DRCHRONO_CLIENT_ID,
              'redirect_uri': settings.DRCHRONO_REDIRECT_URI, 'scope': settings.DRCHRONO_SCOPES, 'state': state}
    return f'{DRCHRONO}/o/authorize/?{urlencode(params)}'


def _call(method, path, **kwargs):
    try:
        resp = requests.request(method, DRCHRONO + path, timeout=10, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise DrChronoAuthError(f'DrChrono request failed: {e}') from e


def _client_post(path, data):
    client = {'client_id': settings.DRCHRONO_CLIENT_ID, 'client_secret': settings.DRCHRONO_CLIENT_SECRET}
    return _call('POST', path, data=data | client)


def request_token(**data):
    """Code exchange or refresh at /o/token/."""
    return _client_post('/o/token/', data)


def fetch_current_user(access_token):
    return _call('GET', '/api/users/current', headers={'Authorization': f'Bearer {access_token}'})


def save_token(user, token):
    """The only place tokens are written. Keeps the old refresh token if DrChrono sends none."""
    cred = DrChronoCredential.objects.filter(user=user).first() or DrChronoCredential(user=user)
    cred.access_token = token['access_token']
    cred.refresh_token = token.get('refresh_token') or cred.refresh_token
    cred.expires_at = timezone.now() + timedelta(seconds=token['expires_in'])
    cred.scope = token.get('scope', cred.scope)
    cred.save()
    return cred


def get_access_token(user):
    cred = DrChronoCredential.objects.filter(user=user).first()
    if cred is None:
        raise DrChronoAuthError('Not connected to DrChrono')
    if not cred.needs_refresh:
        return cred.access_token
    with transaction.atomic():
        # Lock so two requests can't both spend the same refresh token.
        cred = DrChronoCredential.objects.select_for_update().get(pk=cred.pk)
        if not cred.needs_refresh:  # another request refreshed it while we waited
            return cred.access_token
        token = request_token(grant_type='refresh_token', refresh_token=cred.refresh_token)
        return save_token(user, token).access_token


def require_auth(view):
    """Run the view with request.drchrono_token set, or send the user to sign in."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('verify_app:connect_drchrono')
        try:
            request.drchrono_token = get_access_token(request.user)
        except DrChronoAuthError:
            return back_to_sign_in(request, 'Your DrChrono session expired, please sign in again.')
        return view(request, *args, **kwargs)
    return wrapper


def sign_out(request):
    """Revoke the app's DrChrono access, delete the stored tokens and end the session."""
    cred = DrChronoCredential.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    if cred:
        try:
            # Revoking the refresh token also revokes the access token issued with it.
            _client_post('/o/revoke_token/', {'token': cred.refresh_token or cred.access_token})
        except DrChronoAuthError:
            pass  # best effort (an empty-body success also lands here); the tokens are deleted below either way
        cred.delete()
    logout(request)


def back_to_sign_in(request, message):
    messages.error(request, message)
    return redirect('verify_app:connect_drchrono')
