from datetime import datetime
from unittest.mock import patch

import pytest
from django.urls import reverse

from core.drchrono import DrChronoError
from core.testing import make_appointment, make_patient, message_texts

LIST_URL = reverse('appts_app:historical_list', kwargs={'patient_id': 101})


@pytest.fixture
def drchrono():
    """Patch the two DrChrono calls the list makes."""
    visits = [
        make_appointment(2, datetime(2025, 3, 10, 9, 30), reason='Low back pain'),
        make_appointment(1, datetime(2024, 11, 2, 14, 0), reason=None),
    ]
    with patch('appts.views.drchrono.patient', return_value=make_patient()) as patient, \
            patch('appts.views.drchrono.eligible_appointments', return_value=visits) as appointments:
        yield patient, appointments


class TestAppointmentList:
    def test_anonymous_user_redirected_to_login(self, client, db):
        assert client.get(LIST_URL).url == reverse('verify_app:connect_drchrono')

    def test_url_has_only_the_patient_id(self):
        assert LIST_URL == '/appts/patient/101/'

    def test_lists_visits_with_ticked_checkboxes(self, auth_client, drchrono):
        patient, appointments = drchrono

        html = auth_client.get(LIST_URL).content.decode()

        assert 'Past Appointments for Jane Doe' in html
        assert 'Showing <strong style="color: #134e4a;">2</strong> past appointments' in html
        assert 'Mar 10, 2025 09:30 AM' in html
        assert 'Low back pain' in html and 'No reason provided' in html
        assert html.count('name="selected_appts"') == 2
        assert 'value="2" checked' in html and 'value="1" checked' in html
        assert patient.call_args.args == ('valid-access-token', 101)
        assert appointments.call_args.args == ('valid-access-token', 101)

    def test_form_posts_to_pdf_without_patient_name(self, auth_client, drchrono):
        html = auth_client.get(LIST_URL).content.decode()

        assert f'action="{reverse("pdf_app:generate_selected", kwargs={"patient_id": 101})}"' in html
        assert 'patient_name' not in html

    @pytest.mark.parametrize('status, text', [(None, "isn't responding"), (404, "couldn't find that record")])
    def test_drchrono_error_shows_plain_message(self, status, text, auth_client, drchrono):
        _, appointments = drchrono
        appointments.side_effect = DrChronoError('x', status)

        response = auth_client.get(LIST_URL)

        assert response.status_code == 200
        assert any(text in m for m in message_texts(response))
        assert b'No historical appointments found for this patient.' in response.content

    def test_rejected_token_goes_to_sign_in(self, auth_client, drchrono):
        patient, _ = drchrono
        patient.side_effect = DrChronoError('rejected', 401)

        response = auth_client.get(LIST_URL)

        assert response.url == reverse('verify_app:connect_drchrono')
        assert 'Your DrChrono session expired, please sign in again.' in message_texts(response)

    def test_search_results_link_here_by_id(self, auth_client):
        session = auth_client.session
        session['patient_search'] = {'patients': [make_patient()], 'more': False, 'query': {}}
        session.save()

        html = auth_client.get(reverse('search_app:results')).content.decode()

        assert f'href="{LIST_URL}"' in html
