import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .models import DrChronoCredential
from .exceptions import DrChronoAuthError

def refresh_token(cred: DrChronoCredential) -> DrChronoCredential:
    """
    Attempt to refresh token using stored refresh token.
    Returns updated credential object on success; raises exception on failure.
    """
    if not cred.refresh_token:
        raise DrChronoAuthError("No refresh token available - full re-auth required")

    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': cred.refresh_token,
        'client_id': settings.DRCHRONO_CLIENT_ID,
        'client_secret': settings.DRCHRONO_CLIENT_SECRET,
    }

    try:
        resp = requests.post(settings.DRCHRONO_TOKEN_URL, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        #Update user credential
        cred.access_token = data['access_token']
        cred.refresh_token = data.get('refresh_token', cred.refresh_token)
        cred.expires_at = timezone.now() + timedelta(seconds=data['expires_in'])
        cred.scope = data.get('scope', cred.scope)
        cred.save()

        return cred
    except requests.HTTPError as e:
        if e.response.status_code in (400, 401):
            # Refresh needed
            raise DrChronoAuthError('scope', cred.scope)
        raise DrChronoAuthError(f"Refresh failed: {e}")
    except requests.RequestException as e:
        raise DrChronoAuthError(f"Network error during refresh: {e}")

def get_valid_access_token(request) -> str:
    """
    Returns valid bearer token or raises auth error
    Intended for other apps/views
    """
    
    try:
        cred = request.user.drchrono_cred
        if not cred.is_expired:
            return cred.access_token
        refreshed_cred = refresh_token(cred)
        return refreshed_cred.access_token
    except DrChronoCredential.DoesNotExist:
        raise DrChronoAuthError("No DrChrono credentials found for this user")

# Decorator for views that need API acess
from functools import wraps
from django.shortcuts import redirect
def require_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('verify_app:connect_drchrono')
    
        try:
            token = get_valid_access_token(request)
            request.drchrono_token = token
        except DrChronoAuthError as e:
            # Restart Oauth flow
            return redirect('verify_app:connect_drchrono')
        
        return view_func(request, *args, **kwargs)
    return wrapper