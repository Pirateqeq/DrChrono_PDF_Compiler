"""DrChrono API client: every DrChrono data call except sign-in goes through here."""
from datetime import date, datetime, timedelta

import requests

DRCHRONO = 'https://app.drchrono.com'


class DrChronoError(Exception):
    """A DrChrono request failed. `status` is the HTTP status code, or None for network/JSON errors."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def get(token, path_or_url, **params):
    """One GET; takes an API path or a full `next` page URL (which already carries its query)."""
    url = path_or_url if path_or_url.startswith('https://') else DRCHRONO + path_or_url
    try:
        resp = requests.get(url, headers={'Authorization': f'Bearer {token}'}, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise DrChronoError(f'DrChrono request failed: {e}', getattr(e.response, 'status_code', None)) from e


def get_all(token, path, **params):
    """Every result of a list endpoint, following DrChrono's `next` page links."""
    page = get(token, path, **params)
    results = page['results']
    while page.get('next'):
        page = get(token, page['next'])
        results += page['results']
    return results


def patient(token, patient_id):
    return get(token, f'/api/patients/{patient_id}')


def appointment(token, appt_id):
    return get(token, f'/api/appointments/{appt_id}', verbose='true')


def line_items(token, **filters):
    """Billing line items, filtered by `appointment=` or `patient=`."""
    return get_all(token, '/api/line_items', **filters)


def eligible_appointments(token, patient_id):
    """Past, attended visits from the last 3 years that have a clinical note PDF, newest first."""
    today = date.today()
    visits = get_all(token, '/api/appointments', patient=patient_id, verbose='true', exclude_membership='true',
                     occurred_since=f'{today - timedelta(days=365 * 3)}T00:00:00', page_size=25)
    eligible = []
    for appt in visits:
        scheduled = appt.get('scheduled_time') or appt.get('date')
        note = appt.get('clinical_note')
        pdf_url = note.get('pdf') if isinstance(note, dict) else note
        attended = appt.get('status') not in ('Rescheduled', 'Cancelled', 'No Show')
        in_past = bool(scheduled) and scheduled[:10] <= today.isoformat()
        has_note = str(pdf_url).startswith('http')
        if attended and in_past and has_note:
            # A copy, so DrChrono's data isn't changed; the list template formats the parsed datetime.
            eligible.append({**appt, 'scheduled_time': datetime.fromisoformat(scheduled)})
    return sorted(eligible, key=lambda a: a['scheduled_time'], reverse=True)
