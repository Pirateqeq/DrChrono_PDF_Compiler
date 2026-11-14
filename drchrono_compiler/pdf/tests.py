from io import BytesIO
from unittest.mock import patch

import pytest
from django.urls import reverse
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from core.testing import (
    FakeDrChrono,
    fake_response,
    make_appointment,
    make_line_item,
    make_patient,
    make_pdf_bytes,
    message_texts,
)
from pdf.golden import (
    BALANCE_REPORT_GOLDEN,
    CLAIM_FORM_GOLDEN,
    GOLDEN_BALANCE_ITEMS,
    GOLDEN_BALANCE_VISITS,
    GOLDEN_CHARGES,
    GOLDEN_VISIT,
    record_drawing,
)
from pdf.services import (
    fetch_hcfa_data,
    generate_balance_report,
    generate_clinical_notes,
    generate_hcfa_bill,
)

GENERATE_URL = reverse('pdf_app:generate_selected', kwargs={'patient_id': 101})
LIST_URL = reverse('appts_app:historical_list', kwargs={'patient_id': 101})
HCFA_HEIGHT = 800


def pdf_text(data):
    reader = PdfReader(BytesIO(data) if isinstance(data, bytes) else data)
    return [page.extract_text() for page in reader.pages]


def two_visits():
    """Visit 1 (older, two charges, one already paid) and visit 2 (newer, one charge)."""
    return {
        'patient': make_patient(),
        'appointments': [make_appointment(2, '2025-05-20T10:00:00'), make_appointment(1, '2025-03-10T09:30:00')],
        'line_items': {
            1: [make_line_item(1, '99213', '150.00'),
                make_line_item(1, '97140', '40.00', balance_total='0.00')],
            2: [make_line_item(2, '98940', '75.50', service_date='2025-05-20')],
        },
    }


def drchrono_routes(data):
    routes = {
        '/api/patients/101': fake_response(data['patient']),
        '/api/appointments': fake_response({'results': data['appointments']}),
    }
    for appt in data['appointments']:
        appt_id = appt['id']
        routes[f'/api/appointments/{appt_id}?verbose=true'] = fake_response(appt)
        routes[f'/api/line_items?appointment={appt_id}'] = fake_response({'results': data['line_items'][appt_id]})
        routes[appt['clinical_note']['pdf']] = fake_response(content=make_pdf_bytes(f'NOTE-{appt_id}'))
    return routes


@pytest.fixture
def drchrono():
    """Fake DrChrono for everything under pdf/. Edit `.routes` to change a response."""
    fake = FakeDrChrono(drchrono_routes(two_visits()))
    with patch('core.drchrono.requests.get', fake.get), patch('pdf.services.requests', fake):
        yield fake


@pytest.fixture
def drawn():
    """Record every Canvas.drawString call as {(x, y): text}."""
    calls = {}
    original = Canvas.drawString

    def record(self, x, y, text, *args, **kwargs):
        calls[(x, y)] = text
        return original(self, x, y, text, *args, **kwargs)

    with patch.object(Canvas, 'drawString', record):
        yield calls


def hcfa_data(**patient_overrides):
    data = two_visits()
    return fetch_hcfa_data(make_patient(**patient_overrides), make_appointment(1), data['line_items'][1])


# ── fetch_hcfa_data ───────────────────────────────────────────────────────────

# ── Golden output: the overhaul must reproduce today's documents ──────────────

class TestGoldenOutput:
    def test_claim_form_drawing_unchanged(self):
        drawn = record_drawing(lambda: generate_hcfa_bill(None, fetch_hcfa_data(make_patient(), GOLDEN_VISIT, GOLDEN_CHARGES)))
        assert drawn == CLAIM_FORM_GOLDEN

    def test_balance_report_text_unchanged(self, drchrono):
        items = {}
        for item in GOLDEN_BALANCE_ITEMS:
            items.setdefault(item['appointment'], []).append(item)
        drchrono.routes['/api/appointments'] = fake_response({'results': GOLDEN_BALANCE_VISITS, 'next': None})
        for appt_id, appt_items in items.items():
            drchrono.routes[f'/api/line_items?appointment={appt_id}'] = fake_response({'results': appt_items, 'next': None})

        assert pdf_text(generate_balance_report(101, 'tok'))[0] == BALANCE_REPORT_GOLDEN


class TestFetchHcfaData:
    def test_maps_patient_and_visit_fields(self):
        data = hcfa_data()

        assert data['first_name'] == 'Jane'
        assert data['last_name'] == 'Doe'
        assert data['dob'] == '1980-04-15'
        assert data['gender'] == 'Female'
        assert (data['address'], data['city'], data['state'], data['zip']) == \
            ('123 Main St', 'Springfield', 'IL', '62701')
        assert data['icd10_codes'] == ['M54.5']
        assert data['signature_date'] == '2025-03-10T12:00:00'

    def test_reads_practice_details_from_env(self):
        data = hcfa_data()

        assert data['provider_npi'] == '1234567890'
        assert data['federal_id'] == '12-3456789'
        assert data['account_number'] == 'ACCT-42'
        assert data['physician_signature'] == 'Dr. Sam Smith'
        assert data['provider_number'] == '217 555-0199'

    def test_formats_phone_number(self):
        assert hcfa_data()['number'] == '217 555 0123'

    def test_collects_line_items_in_order(self):
        data = hcfa_data()

        assert data['code'] == ['99213', '97140']
        assert data['charges'] == ['150.00', '40.00']
        assert data['service_date'] == ['2025-03-10', '2025-03-10']
        assert data['diagnosis_pointer'] == [[1], [1]]

    def test_missing_fields_are_all_listed(self, monkeypatch):
        monkeypatch.delenv('PROVIDER_NPI')

        with pytest.raises(Exception) as exc:
            hcfa_data(zip_code='', city=None)

        errors = exc.value.args[0]
        assert 'Missing Patient Zip' in errors
        assert 'Missing Patient City' in errors
        assert 'Missing Patient Provider Npi' in errors


# ── generate_hcfa_bill ────────────────────────────────────────────────────────

class TestGenerateHcfaBill:
    def test_one_page_with_claim_details(self):
        pages = pdf_text(generate_hcfa_bill(None, hcfa_data()))

        assert len(pages) == 1
        for expected in ['Doe, Jane', '123 Main St', '62701', '555-0123', 'M54.5', '99213', '97140',
                         '1234567890', '12-3456789', 'ACCT-42', 'Signature on File', '03/10/2025',
                         'Dr. Sam Smith', '500 Oak Ave']:
            assert expected in pages[0], expected

    def test_total_charge_is_sum_of_line_items(self, drawn):
        generate_hcfa_bill(None, hcfa_data())

        assert drawn[(390, HCFA_HEIGHT - 698)] == '190'
        assert drawn[(443, HCFA_HEIGHT - 698)] == '00'

    def test_one_service_row_per_line_item(self, drawn):
        generate_hcfa_bill(None, hcfa_data())

        assert drawn[(210, HCFA_HEIGHT - 555)] == '99213'
        assert drawn[(210, HCFA_HEIGHT - 579)] == '97140'
        assert (210, HCFA_HEIGHT - 603) not in drawn

    @pytest.mark.parametrize('gender, x', [('Female', 360), ('Male', 324)])
    def test_sex_checkbox(self, gender, x, drawn):
        generate_hcfa_bill(None, hcfa_data(gender=gender))
        assert drawn[(x, HCFA_HEIGHT - 148)] == '✓'

    def test_phone_without_area_code(self):
        # Known bug: a phone number that isn't exactly 10 digits isn't split into
        # area code and number, and drawing it raises IndexError.
        pages = pdf_text(generate_hcfa_bill(None, hcfa_data(cell_phone='555-0123')))
        assert 'Doe, Jane' in pages[0]


# ── generate_balance_report ───────────────────────────────────────────────────

class TestGenerateBalanceReport:
    def test_totals_unpaid_line_items(self, drchrono):
        text = pdf_text(generate_balance_report(101, 'tok'))[0]

        assert 'Patient Account Balance' in text
        assert 'Provider: Springfield Chiropractic' in text
        assert 'Patient: Doe, Jane' in text
        assert '$225.50' in text
        assert '99213' in text and '98940' in text
        assert '97140' not in text
        assert drchrono.calls[0]['headers'] == {'Authorization': 'Bearer tok'}

    def test_newest_line_items_first(self, drchrono):
        text = pdf_text(generate_balance_report(101, 'tok'))[0]
        assert text.index('May 20, 2025') < text.index('Mar 10, 2025')

    def test_no_balance_due(self, drchrono):
        drchrono.routes['/api/appointments'] = fake_response({'results': []})

        text = pdf_text(generate_balance_report(101, 'tok'))[0]

        assert '$0.00' in text
        assert 'No billable transactions found.' in text

    def test_default_provider_name(self, drchrono, monkeypatch):
        monkeypatch.delenv('PROVIDER_NAME')
        assert 'Provider: Unknown Provider' in pdf_text(generate_balance_report(101, 'tok'))[0]


# ── generate_clinical_notes ───────────────────────────────────────────────────

class TestGenerateClinicalNotes:
    def test_downloads_note(self, drchrono, make_request):
        note = generate_clinical_notes(make_request(), make_appointment(1))
        assert 'NOTE-1' in pdf_text(note)[0]

    def test_missing_note_link_warns(self, drchrono, make_request):
        request = make_request()

        note = generate_clinical_notes(request, make_appointment(1, clinical_note={'pdf': None}))

        assert note.getvalue() == b''
        assert [str(m) for m in request._messages] == [
            'No clinical note PDF found for appointment 1 – skipped.']

    def test_failed_download_warns(self, drchrono, make_request):
        drchrono.routes['https://files.example.test/note-1.pdf'] = fake_response(status=404)
        request = make_request()

        note = generate_clinical_notes(request, make_appointment(1))

        assert note.getvalue() == b''
        assert [str(m) for m in request._messages] == ['Failed to download clinical note for 1']


# ── GenerateSelectedPDFView ───────────────────────────────────────────────────

class TestGenerateSelectedPDFView:
    def generate(self, client, selected=('2', '1')):
        return client.post(GENERATE_URL, {'selected_appts': list(selected)})

    def test_anonymous_user_redirected_to_login(self, client, db):
        response = self.generate(client)
        assert response.url == reverse('verify_app:connect_drchrono')

    def test_get_not_allowed(self, auth_client):
        assert auth_client.get(GENERATE_URL).status_code == 405

    def test_downloads_merged_pdf(self, auth_client, drchrono):
        response = self.generate(auth_client)

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert response['Content-Disposition'] == 'attachment; filename="Patient_Jane_Doe_REPORT.pdf"'

    def test_page_order_is_balance_then_each_visit_oldest_first(self, auth_client, drchrono):
        pages = pdf_text(self.generate(auth_client).content)

        assert len(pages) == 5
        assert 'Patient Account Balance' in pages[0]
        assert 'NOTE-1' in pages[1]
        assert '99213' in pages[2] and '98940' not in pages[2]
        assert 'NOTE-2' in pages[3]
        assert '98940' in pages[4]

    def test_single_visit(self, auth_client, drchrono):
        pages = pdf_text(self.generate(auth_client, selected=['2']).content)

        assert len(pages) == 3
        assert 'NOTE-2' in pages[1]

    def test_missing_patient_data_returns_to_list(self, auth_client, drchrono):
        drchrono.routes['/api/patients/101'] = fake_response(make_patient(zip_code=''))

        response = self.generate(auth_client)

        assert response.status_code == 302
        assert response.url == LIST_URL
        messages = message_texts(response)
        assert 'PDF generation failed.' in messages
        assert any('Missing Patient Zip' in m for m in messages)

    def test_drchrono_error_returns_to_list(self, auth_client, drchrono):
        drchrono.routes['/api/appointments/1?verbose=true'] = fake_response({}, status=500)

        response = self.generate(auth_client)

        assert response.url == LIST_URL
        assert 'PDF generation failed.' in message_texts(response)

    def test_failed_note_download_is_skipped(self, auth_client, drchrono):
        # Known bug: generate_clinical_notes returns an empty buffer to skip the note,
        # but appending an empty buffer makes pypdf raise, so the whole PDF fails.
        drchrono.routes['https://files.example.test/note-1.pdf'] = fake_response(status=404)

        response = self.generate(auth_client)

        assert response.status_code == 200
        assert len(pdf_text(response.content)) == 4
        assert 'Failed to download clinical note for 1' in message_texts(response)

    def test_no_visits_selected(self, auth_client, drchrono):
        response = self.generate(auth_client, selected=[])

        assert response.status_code == 302
        assert response.url == LIST_URL
        assert 'No appointments were selected for PDF generation.' in message_texts(response)
