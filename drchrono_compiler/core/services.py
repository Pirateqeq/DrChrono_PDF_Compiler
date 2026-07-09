def fetch_appointment(requests, headers, appt_id) -> dict:
    url = f"https://app.drchrono.com/api/appointments/{appt_id}?verbose=true"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def fetch_lineitem(requests, headers, appt_id) -> dict:
    url = f"https://app.drchrono.com/api/line_items?appointment={appt_id}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get('results')

def fetch_patient(requests, headers, patient_id) -> dict:
    url = f"https://app.drchrono.com/api/patients/{patient_id}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

from datetime import datetime, timedelta

def get_valid_appointments(requests, headers, patient_id, lookback_days=365*3) -> list[dict]:

    INVALID_APPT_STATUSES = ("Rescheduled", "Cancelled", "No Show")

    since = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%dT00:00:00')
    url = "https://app.drchrono.com/api/appointments"
    params = {
        'patient': patient_id,
        'since': since,
        'verbose': 'true',
        'page_size': 50,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()

    today_iso = datetime.now().date().isoformat()
    valid_appts = []

    for appt in resp.json().get('results', []):
        if appt.get('status') in INVALID_APPT_STATUSES:
            continue

        appt_date_str = appt.get('scheduled_time') or appt.get('date')
        if not appt_date_str or len(appt_date_str) < 10 or appt_date_str[:10] > today_iso:
            continue

        clinical_note = appt.get('clinical_note')
        pdf_url = None
        if isinstance(clinical_note, dict):
            pdf_url = clinical_note.get('pdf')
        elif isinstance(clinical_note, str) and clinical_note.startswith('http'):
            pdf_url = clinical_note
        if not pdf_url:
            continue

        appt['scheduled_time'] = datetime.fromisoformat(appt['scheduled_time'])
        valid_appts.append(appt)

    valid_appts.sort(key=lambda a: a['scheduled_time'], reverse=True)
    return valid_appts