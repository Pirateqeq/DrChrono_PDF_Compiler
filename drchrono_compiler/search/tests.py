from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from core.testing import fake_response, make_patient, message_texts
from search.forms import PatientSearchForm
from search.services import search_patients
from verify.exceptions import DrChronoAuthError

SEARCH_URL = reverse('search_app:search')
RESULTS_URL = reverse('search_app:results')
LOGIN_URL = reverse('verify_app:connect_drchrono')


# ── Form ──────────────────────────────────────────────────────────────────────

class TestPatientSearchForm:
    def test_all_fields_empty_is_rejected(self):
        form = PatientSearchForm(data={})
        assert not form.is_valid()
        assert 'Please provide at least one of' in form.non_field_errors()[0]

    @pytest.mark.parametrize('data', [
        {'first_name': 'Jane'},
        {'last_name': 'Doe'},
        {'date_of_birth': '1980-04-15'},
    ])
    def test_any_single_field_is_enough(self, data):
        assert PatientSearchForm(data=data).is_valid()

    @pytest.mark.parametrize('value', ['1980-04-15', '04/15/1980'])
    def test_date_of_birth_formats(self, value):
        form = PatientSearchForm(data={'date_of_birth': value})
        assert form.is_valid()
        assert form.cleaned_data['date_of_birth'] == date(1980, 4, 15)

    def test_invalid_date_is_rejected(self):
        form = PatientSearchForm(data={'date_of_birth': '15/04/1980'})
        assert not form.is_valid()
        assert 'date_of_birth' in form.errors


# ── search_patients ───────────────────────────────────────────────────────────

@pytest.fixture
def api_get():
    with patch('core.drchrono.requests.get') as get:
        get.return_value = fake_response({'results': [make_patient()], 'next': 'cursor-2'})
        yield get


class TestSearchPatients:
    def test_returns_patients_and_next_cursor(self, api_get, credential, make_request):
        patients, next_cursor = search_patients(make_request(credential.user), {'last_name': 'Doe'})

        assert patients == [make_patient()]
        assert next_cursor == 'cursor-2'
        assert api_get.call_args.args[0] == 'https://app.drchrono.com/api/patients_summary'
        assert api_get.call_args.kwargs['headers'] == {'Authorization': 'Bearer valid-access-token'}
        assert api_get.call_args.kwargs['timeout'] == 10

    def test_only_allowed_filters_are_sent(self, api_get, credential, make_request):
        filters = {'first_name': 'Jane', 'last_name': 'Doe', 'chart_id': 'X1', 'ssn': '000-00-0000'}

        search_patients(make_request(credential.user), filters)

        params = api_get.call_args.kwargs['params']
        assert params == {'page_size': 50, 'first_name': 'Jane', 'last_name': 'Doe', 'chart_id': 'X1'}

    @pytest.mark.parametrize('requested, sent', [(20, 20), (500, 200)])
    def test_page_size_is_capped(self, requested, sent, api_get, credential, make_request):
        search_patients(make_request(credential.user), {'last_name': 'Doe', 'page_size': requested})
        assert api_get.call_args.kwargs['params']['page_size'] == sent

    def test_us_date_of_birth_is_converted(self, api_get, credential, make_request):
        search_patients(make_request(credential.user), {'date_of_birth': '04/15/1980'})
        assert api_get.call_args.kwargs['params']['date_of_birth'] == '1980-04-15'

    @pytest.mark.parametrize('status, error, text', [
        (401, DrChronoAuthError, 'Authentication error'),
        (403, DrChronoAuthError, 'permissions'),
        (404, RuntimeError, 'client error'),
        (500, RuntimeError, 'server error'),
    ])
    def test_http_errors(self, status, error, text, api_get, credential, make_request):
        api_get.return_value = fake_response({}, status=status)
        with pytest.raises(error, match=text):
            search_patients(make_request(credential.user), {'last_name': 'Doe'})


# ── Views ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def search_api():
    with patch('search.views.search_patients') as fake:
        fake.return_value = ([make_patient()], None)
        yield fake


class TestPatientSearchView:
    def test_anonymous_user_redirected_to_login(self, client, db):
        response = client.get(SEARCH_URL)
        assert response.status_code == 302
        assert response.url == LOGIN_URL

    def test_form_renders(self, auth_client):
        response = auth_client.get(SEARCH_URL)
        assert response.status_code == 200
        assert b'Search for a Patient' in response.content

    def test_successful_search_stores_results_and_redirects(self, auth_client, search_api):
        response = auth_client.post(SEARCH_URL, {'last_name': 'Doe', 'date_of_birth': '04/15/1980'})

        assert response.status_code == 302
        assert response.url == RESULTS_URL
        session = auth_client.session
        assert session['patient_search_results'] == [make_patient()]
        assert session['patient_search_filters']['date_of_birth'] == '1980-04-15'
        assert session['patient_next_cursor'] is None
        assert 'Found 1 matching patient(s).' in message_texts(response)

    def test_invalid_form_shows_error(self, auth_client, search_api):
        response = auth_client.post(SEARCH_URL, {})
        assert response.status_code == 200
        assert b'Please provide at least one of' in response.content
        search_api.assert_not_called()

    @pytest.mark.parametrize('result, message', [
        (([], None), 'No patients found matching your criteria.'),
        (DrChronoAuthError('Token rejected'), 'Authentication issue: Token rejected. Please try again.'),
        (RuntimeError('server error'), 'A server error occurred while searching patients. '),
        (ValueError('boom'), 'An unexpected error occurred. Please try again later.'),
    ])
    def test_problems_rerender_form_with_message(self, result, message, auth_client, search_api):
        if isinstance(result, Exception):
            search_api.side_effect = result
        else:
            search_api.return_value = result

        response = auth_client.post(SEARCH_URL, {'last_name': 'Doe'})

        assert response.status_code == 200
        assert message in message_texts(response)
        assert 'patient_search_results' not in auth_client.session


class TestPatientResultsView:
    def store_results(self, client, patients):
        session = client.session
        session['patient_search_results'] = patients
        session['patient_search_filters'] = {'last_name': 'doe'}
        session.save()

    def test_anonymous_user_redirected_to_login(self, client, db):
        response = client.get(RESULTS_URL)
        assert response.url == LOGIN_URL

    def test_lists_patients_with_link_to_appointments(self, auth_client):
        self.store_results(auth_client, [make_patient()])

        response = auth_client.get(RESULTS_URL)

        html = response.content.decode()
        assert 'Doe, Jane' in html
        assert '1980-04-15' in html
        assert 'DOJA000001' in html
        assert reverse('appts_app:historical_list',
                       kwargs={'patient_id': 101, 'patient_name': 'Jane Doe'}) in html
        assert 'Many results returned' not in html

    def test_empty_session_shows_notice(self, auth_client):
        response = auth_client.get(RESULTS_URL)
        assert b'No search results available in this session.' in response.content

    def test_many_results_show_warning(self, auth_client):
        self.store_results(auth_client, [make_patient(id=i) for i in range(31)])

        response = auth_client.get(RESULTS_URL)

        assert b'Many results returned' in response.content
