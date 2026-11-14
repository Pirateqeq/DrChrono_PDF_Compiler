from datetime import datetime
from unittest.mock import patch

import pytest
from django.urls import reverse

from core.testing import make_appointment, message_texts

LIST_URL = reverse('appts_app:historical_list', kwargs={'patient_id': 101, 'patient_name': 'Jane Doe'})


@pytest.fixture
def appointments():
    visits = [
        make_appointment(2, datetime(2025, 3, 10, 9, 30), reason='Low back pain'),
        make_appointment(1, datetime(2024, 11, 2, 14, 0), reason=None),
    ]
    with patch('appts.views.eligible_appointments', return_value=visits) as fake:
        yield fake


class TestHistoricalAppointmentsView:
    def test_anonymous_user_redirected_to_login(self, client, db):
        response = client.get(LIST_URL)
        assert response.url == reverse('verify_app:connect_drchrono')

    def test_url_keeps_name_with_spaces(self):
        assert LIST_URL == '/appts/patient/101_Jane%20Doe/historical/'

    def test_lists_visits_with_ticked_checkboxes(self, auth_client, appointments):
        response = auth_client.get(LIST_URL)

        html = response.content.decode()
        assert response.status_code == 200
        assert 'Past Appointments for Jane Doe' in html
        assert 'Showing <strong style="color: #134e4a;">2</strong> past appointments' in html
        assert 'Mar 10, 2025 09:30 AM' in html
        assert 'Low back pain' in html
        assert 'No reason provided' in html
        assert html.count('name="selected_appts"') == 2
        assert 'value="2" checked' in html and 'value="1" checked' in html
        assert appointments.call_args.args == ('valid-access-token', 101)

    def test_form_posts_to_pdf_generation(self, auth_client, appointments):
        html = auth_client.get(LIST_URL).content.decode()

        pdf_url = reverse('pdf_app:generate_selected', kwargs={'patient_id': 101})
        assert f'action="{pdf_url}?patient_name=Jane Doe"' in html
        assert '<input type="hidden" name="patient_name" value="Jane Doe">' in html

    def test_fetch_error_shows_message_and_empty_list(self, auth_client):
        with patch('appts.views.eligible_appointments', side_effect=RuntimeError('timeout')):
            response = auth_client.get(LIST_URL)

        assert response.status_code == 200
        assert 'Failed to load appointments: timeout' in message_texts(response)
        assert b'No historical appointments found for this patient.' in response.content
