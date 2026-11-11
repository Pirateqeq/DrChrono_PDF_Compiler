from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import requests

from core.services import fetch_appointment, fetch_lineitem, fetch_patient, get_valid_appointments
from core.testing import fake_response, make_appointment, make_line_item, make_patient

HEADERS = {'Authorization': 'Bearer t'}


def fake_requests(json_data=None, status=200):
    module = Mock()
    module.get.return_value = fake_response(json_data, status=status)
    return module


def days_ago(n):
    return (datetime.now() - timedelta(days=n)).replace(microsecond=0).isoformat()


# ── Fetch helpers ─────────────────────────────────────────────────────────────

class TestFetchHelpers:
    def test_fetch_appointment(self):
        api = fake_requests(make_appointment(5))

        assert fetch_appointment(api, HEADERS, 5) == make_appointment(5)
        api.get.assert_called_once_with(
            'https://app.drchrono.com/api/appointments/5?verbose=true', headers=HEADERS, timeout=10)

    def test_fetch_lineitem_returns_results_list(self):
        items = [make_line_item(5)]
        api = fake_requests({'results': items, 'next': None})

        assert fetch_lineitem(api, HEADERS, 5) == items
        api.get.assert_called_once_with(
            'https://app.drchrono.com/api/line_items?appointment=5', headers=HEADERS, timeout=10)

    def test_fetch_patient(self):
        api = fake_requests(make_patient())

        assert fetch_patient(api, HEADERS, 101) == make_patient()
        api.get.assert_called_once_with(
            'https://app.drchrono.com/api/patients/101', headers=HEADERS, timeout=10)

    @pytest.mark.parametrize('call', [
        lambda api: fetch_appointment(api, HEADERS, 5),
        lambda api: fetch_lineitem(api, HEADERS, 5),
        lambda api: fetch_patient(api, HEADERS, 101),
    ])
    def test_http_errors_raise(self, call):
        with pytest.raises(requests.HTTPError):
            call(fake_requests({}, status=500))


# ── get_valid_appointments ────────────────────────────────────────────────────

def valid_ids(appointments):
    api = fake_requests({'results': appointments})
    return [a['id'] for a in get_valid_appointments(api, HEADERS, 101)]


class TestGetValidAppointments:
    def test_request_parameters(self):
        api = fake_requests({'results': []})

        get_valid_appointments(api, HEADERS, 101)

        assert api.get.call_args.args[0] == 'https://app.drchrono.com/api/appointments'
        params = api.get.call_args.kwargs['params']
        assert params['patient'] == 101
        assert params['verbose'] == 'true'
        assert params['page_size'] == 50
        three_years_ago = (datetime.now() - timedelta(days=365 * 3)).strftime('%Y-%m-%d')
        assert params['since'] == f'{three_years_ago}T00:00:00'

    @pytest.mark.parametrize('status', ['Rescheduled', 'Cancelled', 'No Show'])
    def test_drops_invalid_statuses(self, status):
        assert valid_ids([make_appointment(1, days_ago(5), status=status)]) == []

    def test_keeps_attended_past_visits(self):
        assert valid_ids([make_appointment(1, days_ago(5), status='Complete')]) == [1]

    def test_drops_future_visits(self):
        future = (datetime.now() + timedelta(days=5)).replace(microsecond=0).isoformat()
        assert valid_ids([make_appointment(1, future)]) == []

    def test_drops_visits_without_a_date(self):
        assert valid_ids([make_appointment(1, None)]) == []

    @pytest.mark.parametrize('note, kept', [
        ({'pdf': 'https://files.example.test/n.pdf'}, True),
        ('https://files.example.test/n.pdf', True),
        ({'pdf': None}, False),
        ('not-a-url', False),
        (None, False),
    ])
    def test_requires_a_clinical_note_pdf(self, note, kept):
        ids = valid_ids([make_appointment(1, days_ago(5), clinical_note=note)])
        assert ids == ([1] if kept else [])

    def test_sorted_newest_first_with_datetimes(self):
        api = fake_requests({'results': [
            make_appointment(1, days_ago(30)),
            make_appointment(2, days_ago(2)),
            make_appointment(3, days_ago(10)),
        ]})

        result = get_valid_appointments(api, HEADERS, 101)

        assert [a['id'] for a in result] == [2, 3, 1]
        assert all(isinstance(a['scheduled_time'], datetime) for a in result)

    def test_falls_back_to_date_field(self):
        # Known bug: the filter accepts `date` when `scheduled_time` is missing, but the
        # code then reads appt['scheduled_time'] directly and raises KeyError.
        appt = make_appointment(1, days_ago(5))
        appt['date'] = appt.pop('scheduled_time')[:10]

        assert valid_ids([appt]) == [1]

    def test_http_error_raises(self):
        with pytest.raises(requests.HTTPError):
            get_valid_appointments(fake_requests({}, status=503), HEADERS, 101)
