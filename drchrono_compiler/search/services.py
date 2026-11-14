from django.contrib.auth.decorators import login_required

from core import drchrono
from verify.exceptions import DrChronoAuthError
from verify.services import require_auth

@login_required(login_url='verify:connect_drchrono')
@require_auth
def search_patients(request, search_filters: dict) -> tuple[list[dict], str | None]:
    """
    Returns (list of patient dicts, next_cursor or None)
    Filter ex: {'first_name': 'John', 'last_name': 'Smith', 'page_size': 20}
    """

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

    try:
        data = drchrono.get(request.drchrono_token, '/api/patients_summary', **params)
    except drchrono.DrChronoError as e:
        status = e.status
        if status is None:
            raise  # network or unreadable reply: the view shows its generic error, as before
        if status == 401:
            raise DrChronoAuthError("Authentication error during patient search")
        elif status == 403:
            raise DrChronoAuthError("Unsufficent permissions for patient search")
        elif 400 <= status < 500:
            raise RuntimeError(f"client error")
        elif 500 <= status < 600:
            raise RuntimeError(f"server error")
        else:
            raise RuntimeError(f"unknown")
    return data.get("results", []), data.get("next")