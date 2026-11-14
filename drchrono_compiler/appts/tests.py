from datetime import datetime
from unittest.mock import patch

import pytest
from django.urls import reverse

from core.drchrono import DrChronoAuthError, DrChronoError
from core.testing import make_appointment, make_line_item, make_patient, message_texts

LIST_URL = reverse('appts_app:historical_list', kwargs={'patient_id': 101})


@pytest.fixture
def drchrono():
    """Patch the three DrChrono calls the list makes. Both visits have charges."""
    # As DrChrono sends them: a visit's id is text, a line item's appointment is a number.
    visits = [
        make_appointment('2', datetime(2025, 3, 10, 9, 30), reason='Low back pain'),
        make_appointment('1', datetime(2024, 11, 2, 14, 0), reason=None),
    ]
    with patch('appts.views.drchrono.patient', return_value=make_patient()) as patient, \
            patch('appts.views.drchrono.eligible_appointments', return_value=visits) as appointments, \
            patch('appts.views.drchrono.line_items', return_value=[make_line_item(1), make_line_item(2)]) as items:
        yield patient, appointments, items


class TestAppointmentList:
    def test_anonymous_user_redirected_to_login(self, client, db):
        assert client.get(LIST_URL).url == reverse('verify_app:connect_drchrono')

    def test_url_has_only_the_patient_id(self):
        assert LIST_URL == '/appts/patient/101/'

    def test_lists_visits_with_ticked_checkboxes(self, auth_client, drchrono):
        patient, appointments, items = drchrono

        html = auth_client.get(LIST_URL).content.decode()

        assert 'Past Appointments for Jane Doe' in html
        assert 'Showing <strong style="color: #134e4a;">2</strong> past appointments' in html
        assert 'Mar 10, 2025 09:30 AM' in html
        assert 'Low back pain' in html and 'No reason provided' in html
        assert html.count('name="selected_appts"') == 2
        assert 'value="2" checked' in html and 'value="1" checked' in html
        assert patient.call_args.args == ('valid-access-token', 101)
        assert appointments.call_args.args == ('valid-access-token', 101)
        assert items.call_args.kwargs == {'patient': 101}
        assert 'No charges' not in html

    def test_visit_without_charges_is_tagged(self, auth_client, drchrono):
        _, _, items = drchrono
        items.return_value = [make_line_item(1)]

        html = auth_client.get(LIST_URL).content.decode()

        assert html.count('>No charges</span>') == 1
        assert html.index('Mar 10, 2025') < html.index('>No charges</span>') < html.index('Nov 02, 2024')

    def test_form_posts_to_pdf_without_patient_name(self, auth_client, drchrono):
        html = auth_client.get(LIST_URL).content.decode()

        assert f'action="{reverse("pdf_app:generate_selected", kwargs={"patient_id": 101})}"' in html
        assert 'patient_name' not in html

    @pytest.mark.parametrize('status, text', [(None, "isn't responding"), (404, "couldn't find that record")])
    def test_drchrono_error_shows_plain_message(self, status, text, auth_client, drchrono):
        _, _, items = drchrono
        items.side_effect = DrChronoError('x', status)

        response = auth_client.get(LIST_URL)

        assert response.status_code == 200
        assert any(text in m for m in message_texts(response))
        assert b'No historical appointments found for this patient.' in response.content

    def test_rejected_token_goes_to_sign_in(self, auth_client, drchrono):
        patient, _, _ = drchrono
        patient.side_effect = DrChronoAuthError('rejected')

        response = auth_client.get(LIST_URL)

        assert response.url == reverse('verify_app:connect_drchrono')
        assert 'Your DrChrono session expired, please sign in again.' in message_texts(response)
