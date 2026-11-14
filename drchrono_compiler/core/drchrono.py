"""DrChrono API client: every DrChrono data call except sign-in goes through here."""
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

import requests

DRCHRONO = 'https://app.drchrono.com'
# One connection pool per worker process: every request after the first skips the TCP/TLS setup
# (about 0.1-0.4 s each). Gunicorn's sync workers handle one request at a time, so sharing it is safe.
session = requests.Session()


class DrChronoAuthError(Exception):
    """DrChrono rejected or can't issue a token; the user must sign in again (require_auth handles it).

    Deliberately not a DrChronoError, so a view's `except DrChronoError` can't swallow it.
    """


class DrChronoError(Exception):
    """A DrChrono request failed. `status` is the HTTP status code, or None for network/JSON errors."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def get(token, path, **params):
    """One GET to a DrChrono API path (which may carry its own query string, like a `next` link)."""
    try:
        resp = session.get(DRCHRONO + path, headers={'Authorization': f'Bearer {token}'}, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        status = getattr(e.response, 'status_code', None)
        if status == 401:
            raise DrChronoAuthError('DrChrono rejected the access token') from e
        raise DrChronoError(f'DrChrono request failed: {e}', status) from e


def user_message(error):
    """Plain-English text for a DrChronoError, for the page that hit it."""
    return {
        None: "DrChrono isn't responding. Try again in a moment.",
        403: "Your DrChrono account doesn't have permission to see this.",
        404: "DrChrono couldn't find that record.",
        429: "DrChrono's hourly request limit was reached. Try again after the top of the hour.",
    }.get(error.status, 'DrChrono returned an error. Try again in a moment.')


def get_all(token, path, **params):
    """Every result of a list endpoint, following DrChrono's `next` page links."""
    page = get(token, path, **params)
    results = page['results']
    while page.get('next'):
        # `next` is a full URL; reuse only its path and query so the token is only ever sent to DrChrono.
        next_url = urlsplit(page['next'])
        page = get(token, f'{next_url.path}?{next_url.query}')
        results += page['results']
    return results


def patient(token, patient_id):
    return get(token, f'/api/patients/{patient_id}')


def appointment(token, appt_id):
    return get(token, f'/api/appointments/{appt_id}', verbose='true')


def line_items(token, **filters):
    """Billing line items, filtered by `appointment=` or `patient=`."""
    return get_all(token, '/api/line_items', **filters)


def note_pdf_url(appt):
    """The clinical note PDF's URL; DrChrono gives either {'pdf': url} or the URL itself."""
    note = appt.get('clinical_note')
    url = note.get('pdf') if isinstance(note, dict) else note
    return url if str(url).startswith('http') else None


def eligible_appointments(token, patient_id):
    """Past, attended visits from the last 3 years that have a clinical note PDF, newest first."""
    today = date.today()
    visits = get_all(token, '/api/appointments', patient=patient_id, verbose='true', exclude_membership='true',
                     occurred_since=f'{today - timedelta(days=365 * 3)}T00:00:00', page_size=25)
    eligible = []
    for appt in visits:
        scheduled = appt.get('scheduled_time') or appt.get('date')
        attended = appt.get('status') not in ('Rescheduled', 'Cancelled', 'No Show')
        in_past = bool(scheduled) and scheduled[:10] <= today.isoformat()
        has_note = note_pdf_url(appt) is not None
        if attended and in_past and has_note:
            # A copy, so DrChrono's data isn't changed; the list template formats the parsed datetime.
            eligible.append({**appt, 'scheduled_time': datetime.fromisoformat(scheduled)})
    return sorted(eligible, key=lambda a: a['scheduled_time'], reverse=True)
