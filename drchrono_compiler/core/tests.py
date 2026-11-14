from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
import requests

from core import drchrono
from core.drchrono import DrChronoError
from core.testing import FakeDrChrono, fake_response, make_appointment, make_line_item, make_patient


def days_ago(n):
    return (datetime.now() - timedelta(days=n)).replace(microsecond=0).isoformat()


@pytest.fixture
def api():
    """FakeDrChrono standing in for requests.get; add routes per test."""
    fake = FakeDrChrono({})
    with patch('core.drchrono.requests.get', fake.get):
        yield fake


def page(results, next_url=None):
    return fake_response({'previous': None, 'results': results, 'next': next_url})


# ── get / get_all ─────────────────────────────────────────────────────────────

class TestGet:
    def test_builds_url_header_params_and_timeout(self, api):
        api.routes['/api/patients/101'] = fake_response(make_patient())

        assert drchrono.get('tok', '/api/patients/101', verbose='true') == make_patient()
        call = api.calls[0]
        assert call['url'] == 'https://app.drchrono.com/api/patients/101'
        assert call['headers'] == {'Authorization': 'Bearer tok'}
        assert call['params'] == {'verbose': 'true'}
        assert call['timeout'] == 10

    def test_full_url_used_as_is(self, api):
        api.routes['/api/line_items?cursor=abc'] = page([])

        drchrono.get('tok', 'https://app.drchrono.com/api/line_items?cursor=abc')

        assert api.calls[0]['url'] == 'https://app.drchrono.com/api/line_items?cursor=abc'
        assert api.calls[0]['params'] == {}

    @pytest.mark.parametrize('status', [401, 404, 429, 500])
    def test_http_error_carries_status(self, status, api):
        api.routes['/api/patients/101'] = fake_response({}, status=status)

        with pytest.raises(DrChronoError) as exc:
            drchrono.get('tok', '/api/patients/101')
        assert exc.value.status == status

    def test_network_error_has_no_status(self):
        with patch('core.drchrono.requests.get', side_effect=requests.ConnectionError('down')):
            with pytest.raises(DrChronoError) as exc:
                drchrono.get('tok', '/api/patients/101')
        assert exc.value.status is None


class TestGetAll:
    def test_follows_next_links(self, api):
        api.routes['/api/line_items'] = page([1, 2], 'https://app.drchrono.com/api/line_items?cursor=p2')
        api.routes['/api/line_items?cursor=p2'] = page([3], 'https://app.drchrono.com/api/line_items?cursor=p3')
        api.routes['/api/line_items?cursor=p3'] = page([4])

        assert drchrono.get_all('tok', '/api/line_items', patient=101) == [1, 2, 3, 4]
        assert [c['params'] for c in api.calls] == [{'patient': 101}, {}, {}]


# ── Endpoint helpers ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_patient(self, api):
        api.routes['/api/patients/101'] = fake_response(make_patient())
        assert drchrono.patient('tok', 101) == make_patient()

    def test_appointment_is_verbose(self, api):
        api.routes['/api/appointments/5'] = fake_response(make_appointment(5))

        assert drchrono.appointment('tok', 5) == make_appointment(5)
        assert api.calls[0]['params'] == {'verbose': 'true'}

    @pytest.mark.parametrize('filters', [{'appointment': 5}, {'patient': 101}])
    def test_line_items_filters_and_pages(self, filters, api):
        api.routes['/api/line_items'] = page([make_line_item(5)], 'https://app.drchrono.com/api/line_items?cursor=2')
        api.routes['/api/line_items?cursor=2'] = page([make_line_item(6)])

        assert drchrono.line_items('tok', **filters) == [make_line_item(5), make_line_item(6)]
        assert api.calls[0]['params'] == filters


# ── eligible_appointments ─────────────────────────────────────────────────────

def eligible_ids(api, visits):
    api.routes['/api/appointments'] = page(visits)
    return [a['id'] for a in drchrono.eligible_appointments('tok', 101)]


class TestEligibleAppointments:
    def test_request_parameters(self, api):
        eligible_ids(api, [])

        three_years_ago = (date.today() - timedelta(days=365 * 3)).isoformat()
        assert api.calls[0]['params'] == {
            'patient': 101, 'verbose': 'true', 'exclude_membership': 'true',
            'occurred_since': f'{three_years_ago}T00:00:00', 'page_size': 25,
        }

    def test_includes_every_page(self, api):
        api.routes['/api/appointments'] = page(
            [make_appointment(1, days_ago(30))], 'https://app.drchrono.com/api/appointments?cursor=2')
        api.routes['/api/appointments?cursor=2'] = page([make_appointment(2, days_ago(2))])

        assert [a['id'] for a in drchrono.eligible_appointments('tok', 101)] == [2, 1]

    @pytest.mark.parametrize('status', ['Rescheduled', 'Cancelled', 'No Show'])
    def test_drops_skipped_statuses(self, status, api):
        assert eligible_ids(api, [make_appointment(1, days_ago(5), status=status)]) == []

    def test_keeps_attended_past_visits(self, api):
        assert eligible_ids(api, [make_appointment(1, days_ago(5), status='Complete')]) == [1]

    def test_drops_future_visits(self, api):
        future = (datetime.now() + timedelta(days=5)).replace(microsecond=0).isoformat()
        assert eligible_ids(api, [make_appointment(1, future)]) == []

    def test_drops_visits_without_a_date(self, api):
        assert eligible_ids(api, [make_appointment(1, None)]) == []

    def test_falls_back_to_date_field(self, api):
        appt = make_appointment(1, days_ago(5))
        appt['date'] = appt.pop('scheduled_time')[:10]

        api.routes['/api/appointments'] = page([appt])

        result = drchrono.eligible_appointments('tok', 101)

        assert [a['id'] for a in result] == [1]
        assert result[0]['scheduled_time'] == datetime.fromisoformat(appt['date'])

    @pytest.mark.parametrize('note, kept', [
        ({'pdf': 'https://files.example.test/n.pdf'}, True),
        ('https://files.example.test/n.pdf', True),
        ({'pdf': None}, False),
        ('not-a-url', False),
        (None, False),
    ])
    def test_requires_a_clinical_note_pdf(self, note, kept, api):
        assert eligible_ids(api, [make_appointment(1, days_ago(5), clinical_note=note)]) == ([1] if kept else [])

    def test_newest_first_with_parsed_times_and_api_data_unchanged(self, api):
        visits = [make_appointment(1, days_ago(30)), make_appointment(2, days_ago(2)), make_appointment(3, days_ago(10))]
        api.routes['/api/appointments'] = page(visits)

        result = drchrono.eligible_appointments('tok', 101)

        assert [a['id'] for a in result] == [2, 3, 1]
        assert all(isinstance(a['scheduled_time'], datetime) for a in result)
        assert all(isinstance(v['scheduled_time'], str) for v in visits)
