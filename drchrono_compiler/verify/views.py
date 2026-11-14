import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from . import services
from .exceptions import DrChronoAuthError


def connect_drchrono(request):
    """Sign-in page. Signed-in users with a usable token go straight to search."""
    if request.user.is_authenticated:
        try:
            services.get_access_token(request.user)
            return redirect('search_app:search')
        except DrChronoAuthError:
            pass  # token is gone or can't be refreshed: show the sign-in page
    return render(request, 'verify/connect.html')


def authorize(request):
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    return redirect(services.authorize_url(state))


def oauth_callback(request):
    expected_state = request.session.pop('oauth_state', None)
    if 'error' in request.GET:
        return services.back_to_sign_in(request, 'Sign-in was cancelled.')
    if not expected_state or not secrets.compare_digest(expected_state, request.GET.get('state', '')):
        return services.back_to_sign_in(request, 'Sign-in expired, please try again.')
    try:
        token = services.request_token(grant_type='authorization_code', code=request.GET.get('code', ''),
                                       redirect_uri=settings.DRCHRONO_REDIRECT_URI)
        username = services.fetch_current_user(token['access_token'])['username']
    except (DrChronoAuthError, KeyError):
        return services.back_to_sign_in(request, "Couldn't sign in to DrChrono, please try again.")
    # DrChrono is the only identity provider, so local users never get a usable password.
    user, _ = User.objects.get_or_create(username=username, defaults={'password': make_password(None)})
    services.save_token(user, token)
    login(request, user)
    messages.success(request, f'Successfully connected as {username}')
    return redirect('search_app:search')


def csrf_failure(request, reason=''):
    return services.back_to_sign_in(request, 'Your session has expired, please sign in again.')
