from io import BytesIO
from unittest.mock import patch

import pytest
from django.urls import reverse
from pypdf import PdfReader

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
from pdf import hcfa
from pdf.services import generate_balance_report, generate_clinical_notes

GENERATE_URL = reverse('pdf_app:generate_selected', kwargs={'patient_id': 101})
LIST_URL = reverse('appts_app:historical_list', kwargs={'patient_id': 101})


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


# ── Golden output: the overhaul must reproduce today's documents ──────────────

class TestGoldenOutput:
    def test_claim_form_drawing_unchanged(self):
        drawn = record_drawing(lambda: hcfa.claim_forms(make_patient(), GOLDEN_VISIT, GOLDEN_CHARGES))
        assert drawn == CLAIM_FORM_GOLDEN

    def test_balance_report_text_unchanged(self, drchrono):
        items = {}
        for item in GOLDEN_BALANCE_ITEMS:
            items.setdefault(item['appointment'], []).append(item)
        drchrono.routes['/api/appointments'] = fake_response({'results': GOLDEN_BALANCE_VISITS, 'next': None})
        for appt_id, appt_items in items.items():
            drchrono.routes[f'/api/line_items?appointment={appt_id}'] = fake_response({'results': appt_items, 'next': None})

        assert pdf_text(generate_balance_report(101, 'tok'))[0] == BALANCE_REPORT_GOLDEN


# ── hcfa ──────────────────────────────────────────────────────────────────────

def charges(count):
    return [make_line_item(1, str(99200 + n), f'{10 + n}.00') for n in range(count)]


class TestClaimForms:
    def test_one_page_form_on_the_template(self):
        forms = hcfa.claim_forms(make_patient(), GOLDEN_VISIT, GOLDEN_CHARGES)

        assert len(forms) == 1
        pages = pdf_text(forms[0])
        assert len(pages) == 1
        assert 'FORM 1500' in pages[0] and 'Doe, Jane' in pages[0]  # template text plus the overlay

    def test_more_than_six_charges_continue_on_another_form(self):
        drawn = record_drawing(lambda: hcfa.claim_forms(make_patient(), GOLDEN_VISIT, charges(7)))

        codes = sorted(text for x, y, text in drawn if x == hcfa.LINE_X['code'])
        assert codes == [str(99200 + n) for n in range(7)]
        totals = [text for x, y, text in drawn if (x, y) == (390, hcfa.PAGE_HEIGHT - 698)]
        assert sorted(totals) == ['16', '75']  # 10+11+...+15 on the first form, 16 on the second
        assert len(hcfa.claim_forms(make_patient(), GOLDEN_VISIT, charges(7))) == 2

    def test_six_charges_fit_one_form(self):
        assert len(hcfa.claim_forms(make_patient(), GOLDEN_VISIT, charges(6))) == 1

    def test_phone_without_area_code(self):
        # Was a known bug: a phone number that isn't 10 digits raised IndexError.
        drawn = record_drawing(lambda: hcfa.claim_forms(make_patient(cell_phone='555-0123'), GOLDEN_VISIT, GOLDEN_CHARGES))

        assert (162, hcfa.PAGE_HEIGHT - 221, '555-0123') in drawn
        assert not any(x == 134 and y == hcfa.PAGE_HEIGHT - 221 for x, y, _ in drawn)

    @pytest.mark.parametrize('gender, x', [('Female', 360), ('Male', 324)])
    def test_sex_checkbox(self, gender, x):
        drawn = record_drawing(lambda: hcfa.claim_forms(make_patient(gender=gender), GOLDEN_VISIT, GOLDEN_CHARGES))
        assert (x, hcfa.PAGE_HEIGHT - 148, '✓') in drawn

    @pytest.mark.parametrize('visit, items, reason', [
        (GOLDEN_VISIT, [], 'no charges'),
        ({**GOLDEN_VISIT, 'icd10_codes': []}, GOLDEN_CHARGES, 'no ICD-10 diagnosis codes'),
        ({**GOLDEN_VISIT, 'clinical_note': {'pdf': 'https://x/n.pdf'}}, GOLDEN_CHARGES, 'no signature date'),
    ])
    def test_visit_problems_raise_claim_error(self, visit, items, reason):
        with pytest.raises(hcfa.ClaimError, match=reason):
            hcfa.claim_forms(make_patient(), visit, items)

    def test_inputs_unchanged(self):
        patient, visit, items = make_patient(), dict(GOLDEN_VISIT), [dict(c) for c in GOLDEN_CHARGES]

        hcfa.claim_forms(patient, visit, items)

        assert (patient, visit, items) == (make_patient(), GOLDEN_VISIT, GOLDEN_CHARGES)

    def test_no_pypdf_deprecation_warning(self, recwarn):
        hcfa.claim_forms(make_patient(), GOLDEN_VISIT, GOLDEN_CHARGES)
        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]


class TestMissingDetails:
    def test_complete_patient_and_practice(self):
        assert hcfa.missing_details(make_patient()) == []

    def test_lists_everything_missing(self, monkeypatch):
        monkeypatch.delenv('PROVIDER_NPI')

        assert hcfa.missing_details(make_patient(zip_code='', city=None)) == [
            'patient city', 'patient zip code', 'practice setting PROVIDER_NPI']


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
