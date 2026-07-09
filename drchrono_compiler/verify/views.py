from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.conf import settings
import requests
from requests_oauthlib import OAuth2Session
from .models import DrChronoCredential
from django.utils import timezone
from datetime import timedelta

# Contains authentication views (functions called via urls [check urls.py])

# Starting point for authorization connect_drchrono -> oauth_callback.
def connect_drchrono(request):
    oauth = OAuth2Session(
        settings.DRCHRONO_CLIENT_ID,
        redirect_uri=settings.DRCHRONO_REDIRECT_URI,
        scope=settings.DRCHRONO_SCOPES.split()
    )
    authorization_url, csrf_state = oauth.authorization_url(settings.DRCHRONO_AUTH_URL)
    request.session['oauth_state'] = csrf_state
    return redirect(authorization_url)

def oauth_callback(request):
    oauth = OAuth2Session(
        settings.DRCHRONO_CLIENT_ID,
        redirect_uri=settings.DRCHRONO_REDIRECT_URI,
        state=request.session.get('oauth_state')
    )
    
    try:    
        token = oauth.fetch_token(
            settings.DRCHRONO_TOKEN_URL,
            client_secret=settings.DRCHRONO_CLIENT_SECRET,
            authorization_response=request.build_absolute_uri()
        )
    except Exception as e:
        messages.error(request, "Unable to fetch token")
        return redirect('verify_app:connect_drchrono')
    
    access_token = token['access_token']
    refresh_token = token.get('refresh_token')
    expires_in = token.get('expires_in', 3600)

    headers = {'Authorization': f"Bearer {access_token}"}
    user_resp = requests.get('https://app.drchrono.com/api/users/current', headers=headers, timeout=10)
    if user_resp.status_code != 200:
        messages.error(request, "Could not fetch user information from DrChrono")
        return redirect('verify_app:connect_drchrono')
    
    user_data = user_resp.json()
    username = user_data.get('username', '')

    if request.user.is_authenticated and request.user.username == username:
        return redirect('search_app:search')

    user, created = User.objects.get_or_create(username=username,)

    if created:
        user.set_unusable_password()

    credential, cred_created = DrChronoCredential.objects.update_or_create(
        user=user,
        defaults={
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': timezone.now() + timedelta(seconds=expires_in),
            'scope': ' '.join(settings.DRCHRONO_SCOPES.split()),
        }
    )

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.pop('oauth_state', None)
    messages.success(request, f'Successfully connected as {username}')
    return redirect('search_app:search')

def csrf_failure(request, reason=''):
    messages.error(request, "Your session has expired please relogin")
    return redirect("verify_app:connect_drchrono")