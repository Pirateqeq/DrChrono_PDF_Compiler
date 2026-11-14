from core import drchrono


def search_patients(token, query):
    """Up to 50 DrChrono matches for `query`, slimmed to what the results page shows, and whether DrChrono has more."""
    data = drchrono.get(token, '/api/patients_summary', page_size=50, **query)
    # Only these fields go into the session, so it never holds DrChrono's full patient record.
    shown = ('id', 'first_name', 'last_name', 'date_of_birth', 'chart_id')
    patients = [{field: patient.get(field) for field in shown} for patient in data['results']]
    return patients, bool(data.get('next'))
