from verify.services import get_valid_access_token
from verify.exceptions import DrChronoAuthError
import requests
from django.contrib.auth.decorators import login_required
from verify.services import require_auth

DRCHRONO_BASE = "https://app.drchrono.com/api"

@login_required(login_url='verify:connect_drchrono')
@require_auth
def search_patients(request, search_filters: dict) -> tuple[list[dict], str | None]:
    """
    Returns (list of patient dicts, next_cursor or None)
    Filter ex: {'first_name': 'John', 'last_name': 'Smith', 'page_size': 20}
    """

    try:
        token = get_valid_access_token(request)
    except DrChronoAuthError as e:
        raise
    
    headers = {"Authorization": f"Bearer {token}"}
    allowed = ["first_name", "last_name", "date_of_birth", "chart_id"]
    params = {
        "page_size": min(search_filters.get("page_size", 50), 200),
        **{k: v for k, v in search_filters.items() if k in allowed}
    }

    if 'date_of_birth' in params and params['date_of_birth']:
        if isinstance(params['date_of_birth'], str):
            try:
                from datetime import datetime
                dt = datetime.strptime(params['date_of_birth'], '%m/%d/%Y')
                params['date_of_birth'] = dt.strftime('%Y-%m-%d')
            except:
                pass

    url = f"{DRCHRONO_BASE}/patients_summary"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        patients = data.get("results", [])
        next_cursor = data.get("next")
        return patients, next_cursor
    
    except requests.HTTPError as e:
        status = e.response.status_code
        if status == 401:
            raise DrChronoAuthError("Token issue during patient search")
        elif status == 403:
            raise DrChronoAuthError("Insufficient scopes for patient search")
        else:
            raise ValueError(f'DrChrono returned {status}: {e.response.text}')
    except requests.RequestException as e:
        raise ValueError(f"Network error searching patients: {str(e)}")