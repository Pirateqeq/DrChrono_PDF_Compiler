"""Fake DrChrono data and HTTP responses shared by every app's tests."""

from io import BytesIO
from urllib.parse import urlencode
from unittest.mock import Mock

import requests
from django.contrib.messages import get_messages
from reportlab.pdfgen import canvas

DRCHRONO_HOST = 'https://app.drchrono.com'


def fake_response(json_data=None, status=200, content=b''):
    """A stand-in for requests.Response."""
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.content = content

    def raise_for_status():
        if status >= 400:
            raise requests.HTTPError(f'{status} Error', response=resp)

    resp.raise_for_status.side_effect = raise_for_status
    return resp


class FakeDrChrono:
    """
    Stands in for `requests.get` (patch `core.drchrono.requests.get` with `.get`)
    or for a whole `requests` module (e.g. `pdf.services.requests`, for note downloads).
    Routes are keyed by URL with the DrChrono host stripped. A key with a query
    ('/api/line_items?appointment=1') matches that path with exactly those params;
    a bare path ('/api/appointments') matches any params. Full URLs work for other
    hosts (clinical note files). Unknown URLs fail the test.
    """

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({'url': url, 'headers': headers, 'params': params, 'timeout': timeout})
        path = url.removeprefix(DRCHRONO_HOST)
        query = urlencode(params or {})
        for key in (f'{path}?{query}', path) if query else (path,):
            if key in self.routes:
                return self.routes[key]
        raise AssertionError(f'Unexpected DrChrono request: {url} {params or ""}')


def make_patient(**overrides):
    patient = {
        'id': 101,
        'first_name': 'Jane',
        'last_name': 'Doe',
        'date_of_birth': '1980-04-15',
        'gender': 'Female',
        'address': '123 Main St',
        'city': 'Springfield',
        'state': 'IL',
        'zip_code': '62701',
        'cell_phone': '(217) 555-0123',
        'chart_id': 'DOJA000001',
    }
    patient.update(overrides)
    return patient


def make_appointment(appt_id=1, scheduled_time='2025-03-10T09:30:00', **overrides):
    appt = {
        'id': appt_id,
        'patient': 101,
        'scheduled_time': scheduled_time,
        'status': 'Complete',
        'reason': 'Follow-up',
        'icd10_codes': ['M54.5'],
        'clinical_note': {
            'pdf': f'https://files.example.test/note-{appt_id}.pdf',
            'updated_at': '2025-03-10T12:00:00',
        },
    }
    appt.update(overrides)
    return appt


def make_line_item(appointment=1, code='99213', price='150.00', balance_total=None,
                   service_date='2025-03-10'):
    return {
        'appointment': appointment,
        'code': code,
        'price': price,
        'balance_total': price if balance_total is None else balance_total,
        'service_date': service_date,
        'diagnosis_pointers': [1],
    }


def make_pdf_bytes(text='Clinical note', pages=1):
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    for _ in range(pages):
        c.drawString(72, 720, text)
        c.showPage()
    c.save()
    return buffer.getvalue()


def message_texts(response):
    """Flash messages queued during the request that produced `response`."""
    return [str(m) for m in get_messages(response.wsgi_request)]
