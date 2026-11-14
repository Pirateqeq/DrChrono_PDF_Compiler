from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from core.drchrono import DrChronoError
from core.testing import FakeDrChrono, fake_response, make_patient, message_texts
from search.forms import PatientSearchForm
from search.services import search_patients

SEARCH_URL = reverse('search_app:search')
RESULTS_URL = reverse('search_app:results')
LOGIN_URL = reverse('verify_app:connect_drchrono')
# make_patient() as the session stores it: only the fields the results page shows.
JANE = {'id': 101, 'first_name': 'Jane', 'last_name': 'Doe', 'date_of_birth': '1980-04-15', 'chart_id': 'DOJA000001'}


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
def api():
    fake = FakeDrChrono({'/api/patients_summary': fake_response({'results': [make_patient()], 'next': None})})
    with patch('core.drchrono.session.get', fake.get):
        yield fake


class TestSearchPatients:
    def test_sends_query_with_page_size(self, api):
        search_patients('tok', {'last_name': 'Doe', 'date_of_birth': '1980-04-15'})

        call = api.calls[0]
        assert call['url'] == 'https://app.drchrono.com/api/patients_summary'
        assert call['headers'] == {'Authorization': 'Bearer tok'}
        assert call['params'] == {'page_size': 50, 'last_name': 'Doe', 'date_of_birth': '1980-04-15'}

    def test_slims_records_to_shown_fields(self, api):
        api.routes['/api/patients_summary'] = fake_response(
            {'results': [make_patient(ssn='000-00-0000', address='1 Main St')], 'next': None})

        patients, more = search_patients('tok', {'last_name': 'Doe'})

        assert patients == [JANE]
        assert more is False

    def test_more_when_drchrono_has_another_page(self, api):
        api.routes['/api/patients_summary'] = fake_response(
            {'results': [make_patient()], 'next': 'https://app.drchrono.com/api/patients_summary?cursor=2'})

        assert search_patients('tok', {'last_name': 'Doe'})[1] is True

    def test_errors_propagate(self, api):
        api.routes['/api/patients_summary'] = fake_response({}, status=500)
        with pytest.raises(DrChronoError):
            search_patients('tok', {'last_name': 'Doe'})


# ── Views ─────────────────────────────────────────────────────────────────────

class TestSearchView:
    def test_anonymous_user_redirected_to_login(self, client, db):
        assert client.get(SEARCH_URL).url == LOGIN_URL

    def test_form_renders(self, auth_client):
        response = auth_client.get(SEARCH_URL)

        assert response.status_code == 200
        assert b'Enter a first name, last name or date of birth.' in response.content

    def test_successful_search_stores_slim_results_and_redirects(self, auth_client, api):
        response = auth_client.post(SEARCH_URL, {'last_name': 'Doe', 'date_of_birth': '04/15/1980'})

        assert response.url == RESULTS_URL
        assert auth_client.session['patient_search'] == {
            'patients': [JANE],
            'more': False,
            'query': {'last_name': 'Doe', 'date_of_birth': '1980-04-15'},
        }
        assert api.calls[0]['headers'] == {'Authorization': 'Bearer valid-access-token'}
        assert 'Found 1 matching patient(s).' in message_texts(response)

    def test_invalid_form_shows_error_without_calling_drchrono(self, auth_client, api):
        response = auth_client.post(SEARCH_URL, {})

        assert response.status_code == 200
        assert b'Please provide at least one of' in response.content
        assert api.calls == []

    def test_no_matches(self, auth_client, api):
        api.routes['/api/patients_summary'] = fake_response({'results': [], 'next': None})

        response = auth_client.post(SEARCH_URL, {'last_name': 'Nobody'})

        assert response.status_code == 200
        assert 'No patients found matching your criteria.' in message_texts(response)
        assert 'patient_search' not in auth_client.session

    @pytest.mark.parametrize('status, text', [(403, "doesn't have permission"), (500, 'returned an error')])
    def test_drchrono_error_shows_plain_message(self, status, text, auth_client, api):
        api.routes['/api/patients_summary'] = fake_response({}, status=status)

        response = auth_client.post(SEARCH_URL, {'last_name': 'Doe'})

        assert response.status_code == 200
        assert any(text in m for m in message_texts(response))

    def test_rejected_token_goes_to_sign_in(self, auth_client, api):
        api.routes['/api/patients_summary'] = fake_response({}, status=401)

        response = auth_client.post(SEARCH_URL, {'last_name': 'Doe'})

        assert response.url == LOGIN_URL
        assert 'Your DrChrono session expired, please sign in again.' in message_texts(response)


class TestResultsView:
    def store(self, client, patients, more=False):
        session = client.session
        session['patient_search'] = {'patients': patients, 'more': more, 'query': {'last_name': 'doe'}}
        session.save()

    def test_anonymous_user_redirected_to_login(self, client, db):
        assert client.get(RESULTS_URL).url == LOGIN_URL

    def test_lists_patients(self, auth_client):
        self.store(auth_client, [JANE])

        html = auth_client.get(RESULTS_URL).content.decode()

        assert 'Doe, Jane' in html and '1980-04-15' in html and 'DOJA000001' in html
        assert 'href="/appts/patient/101/"' in html
        assert '"Doe"' in html
        assert 'more than 50 matches' not in html

    def test_more_notice(self, auth_client):
        self.store(auth_client, [make_patient()], more=True)
        assert b'DrChrono found more than 50 matches.' in auth_client.get(RESULTS_URL).content

    def test_empty_session_shows_notice(self, auth_client):
        assert b'No search results available in this session.' in auth_client.get(RESULTS_URL).content
