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
from pdf import balance, hcfa, packet

GENERATE_URL = reverse('pdf_app:generate_selected', kwargs={'patient_id': 101})
LIST_URL = reverse('appts_app:historical_list', kwargs={'patient_id': 101})


def pdf_text(data):
    reader = PdfReader(BytesIO(data) if isinstance(data, bytes) else data)
    return [page.extract_text() for page in reader.pages]


def two_visits():
    """Visit 1 (older: one unpaid charge, one paid) and visit 2 (newer: one charge)."""
    return {
        'patient': make_patient(),
        'appointments': [make_appointment(2, '2025-05-20T10:00:00'), make_appointment(1, '2025-03-10T09:30:00')],
        'line_items': [make_line_item(1, '99213', '150.00'), make_line_item(1, '97140', '40.00', balance_total='0.00'),
                       make_line_item(2, '98940', '75.50', service_date='2025-05-20')],
    }


def drchrono_routes(data):
    routes = {
        '/api/patients/101': fake_response(data['patient']),
        '/api/appointments': fake_response({'results': data['appointments'], 'next': None}),
        '/api/line_items?patient=101': fake_response({'results': data['line_items'], 'next': None}),
    }
    for appt in data['appointments']:
        routes[appt['clinical_note']['pdf']] = fake_response(content=make_pdf_bytes(f"NOTE-{appt['id']}"))
    return routes


@pytest.fixture
def drchrono():
    """Fake DrChrono (API and note files) on the shared session. Edit `.routes` to change a response."""
    fake = FakeDrChrono(drchrono_routes(two_visits()))
    with patch('core.drchrono.session.get', fake.get):
        yield fake


def api_calls(fake):
    return [c['url'] for c in fake.calls if c['url'].startswith('https://app.drchrono.com/')]


# ── Golden output: the overhaul must reproduce today's documents ──────────────

class TestGoldenOutput:
    def test_claim_form_drawing_unchanged(self):
        drawn = record_drawing(lambda: hcfa.claim_forms(make_patient(), GOLDEN_VISIT, GOLDEN_CHARGES))
        assert drawn == CLAIM_FORM_GOLDEN

    def test_balance_report_text_unchanged(self):
        report = balance.balance_report(make_patient(), GOLDEN_BALANCE_VISITS, by_visit(GOLDEN_BALANCE_ITEMS))
        assert pdf_text(report)[0] == BALANCE_REPORT_GOLDEN


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

def by_visit(items):
    grouped = {}
    for item in items:
        grouped.setdefault(item['appointment'], []).append(item)
    return grouped


class TestBalanceReport:
    def report_text(self, visits=GOLDEN_BALANCE_VISITS, items=GOLDEN_BALANCE_ITEMS):
        return pdf_text(balance.balance_report(make_patient(), visits, by_visit(items)))[0]

    def test_totals_unpaid_charges_and_skips_paid_ones(self):
        text = self.report_text()

        assert 'Patient: Doe, Jane' in text and 'Provider: Springfield Chiropractic' in text
        assert '$396.00' in text  # 150 + 45 + 60 + 40 + 25.50 + 75.50
        assert '97750' not in text  # balance 0.00

    def test_newest_charges_first(self):
        text = self.report_text()
        assert text.index('May 20, 2025') < text.index('Mar 10, 2025')

    def test_no_balance_due(self):
        text = self.report_text(items=[])

        assert '$0.00' in text
        assert 'No billable transactions found.' in text

    def test_default_provider_name(self, monkeypatch):
        monkeypatch.delenv('PROVIDER_NAME')
        assert 'Provider: Unknown Provider' in self.report_text()

    def test_zero_written_differently_counts_as_paid(self):
        items = [make_line_item(1, '99213', '150.00', balance_total='0')]
        assert 'No billable transactions found.' in self.report_text(items=items)


# ── packet ────────────────────────────────────────────────────────────────────

class TestDownloadNote:
    def test_downloads_the_pdf(self, drchrono):
        assert 'NOTE-1' in pdf_text(packet.download_note(make_appointment(1)))[0]

    @pytest.mark.parametrize('setup, reason', [
        (lambda routes: None, 'no clinical note PDF'),
        (lambda routes: routes.update({'https://files.example.test/note-1.pdf': fake_response(status=404)}),
         "couldn't download it"),
        (lambda routes: routes.update({'https://files.example.test/note-1.pdf': fake_response(content=b'<html>')}),
         "isn't a PDF"),
    ])
    def test_problems_raise_note_error(self, setup, reason, drchrono):
        setup(drchrono.routes)
        visit = make_appointment(1, clinical_note={'pdf': None}) if reason == 'no clinical note PDF' else make_appointment(1)

        with pytest.raises(packet.NoteError, match=reason):
            packet.download_note(visit)


class TestLoad:
    def test_fetches_everything_in_three_calls(self, drchrono):
        contents = packet.load('tok', 101, ['2', '1'])

        assert api_calls(drchrono) == ['https://app.drchrono.com/api/patients/101',
                                       'https://app.drchrono.com/api/appointments',
                                       'https://app.drchrono.com/api/line_items']
        assert drchrono.calls[2]['params'] == {'patient': 101}
        assert [v['id'] for v in contents['selected']] == [1, 2]  # oldest first
        assert sorted(contents['line_items']) == [1, 2]

    def test_visit_not_on_the_patients_list_is_rejected(self, drchrono):
        with pytest.raises(packet.PacketError, match='visit list changed'):
            packet.load('tok', 101, ['1', '999'])

    def test_missing_patient_details_block_the_pdf(self, drchrono):
        drchrono.routes['/api/patients/101'] = fake_response(make_patient(zip_code='', city=None))

        with pytest.raises(packet.PacketError, match="Can't build claim forms: missing patient city, patient zip code."):
            packet.load('tok', 101, ['1'])

    def test_fetches_a_visit_only_when_icd_codes_are_absent(self, drchrono):
        visits = two_visits()['appointments']
        del visits[1]['icd10_codes']
        drchrono.routes['/api/appointments'] = fake_response({'results': visits, 'next': None})
        drchrono.routes['/api/appointments/1?verbose=true'] = fake_response(make_appointment(1, icd10_codes=['S13.4']))

        contents = packet.load('tok', 101, ['1', '2'])

        assert contents['selected'][0]['icd10_codes'] == ['S13.4']
        assert len(api_calls(drchrono)) == 4


# ── View ──────────────────────────────────────────────────────────────────────

class TestGenerateView:
    def generate(self, client, selected=('2', '1')):
        return client.post(GENERATE_URL, {'selected_appts': list(selected)})

    def test_anonymous_user_redirected_to_login(self, client, db):
        assert self.generate(client).url == reverse('verify_app:connect_drchrono')

    def test_get_not_allowed(self, auth_client):
        assert auth_client.get(GENERATE_URL).status_code == 405

    def test_downloads_the_pdf_with_three_drchrono_calls(self, auth_client, drchrono):
        response = self.generate(auth_client)

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert response['Content-Disposition'] == 'attachment; filename="Patient_Jane_Doe_REPORT.pdf"'
        assert len(api_calls(drchrono)) == 3
        assert drchrono.calls[0]['headers'] == {'Authorization': 'Bearer valid-access-token'}

    def test_page_order_is_balance_then_each_visit_oldest_first(self, auth_client, drchrono):
        pages = pdf_text(self.generate(auth_client).content)

        assert len(pages) == 5
        assert 'Patient Account Balance' in pages[0]
        assert 'NOTE-1' in pages[1]
        assert '99213' in pages[2] and '98940' not in pages[2]
        assert 'NOTE-2' in pages[3]
        assert '98940' in pages[4]

    def test_failed_note_download_is_skipped_and_listed(self, auth_client, drchrono):
        # Was a known bug: an empty note buffer broke the merge and the whole PDF failed.
        drchrono.routes['https://files.example.test/note-1.pdf'] = fake_response(status=404)

        pages = pdf_text(self.generate(auth_client).content)

        assert 'Not included' in pages[0] and "Mar 10, 2025 clinical note: couldn't download it" in pages[0]
        assert 'Patient Account Balance' in pages[1]
        assert len(pages) == 5  # not included, balance, visit 1 claim, visit 2 note and claim

    def test_visit_without_charges_lists_its_claim(self, auth_client, drchrono):
        data = two_visits()
        drchrono.routes['/api/line_items?patient=101'] = fake_response(
            {'results': [i for i in data['line_items'] if i['appointment'] == 1], 'next': None})

        pages = pdf_text(self.generate(auth_client).content)

        assert 'May 20, 2025 claim form: no charges' in pages[0]

    def test_more_than_six_charges_add_a_claim_form(self, auth_client, drchrono):
        many = [make_line_item(2, str(99200 + n), '10.00', service_date='2025-05-20') for n in range(7)]
        drchrono.routes['/api/line_items?patient=101'] = fake_response({'results': many, 'next': None})

        pages = pdf_text(self.generate(auth_client, selected=['2']).content)

        assert len(pages) == 4  # balance, note, two claim forms

    def test_missing_patient_details_return_to_list(self, auth_client, drchrono):
        drchrono.routes['/api/patients/101'] = fake_response(make_patient(zip_code=''))

        response = self.generate(auth_client)

        assert response.url == LIST_URL
        assert "Can't build claim forms: missing patient zip code." in message_texts(response)

    def test_drchrono_error_returns_to_list_with_plain_message(self, auth_client, drchrono):
        drchrono.routes['/api/appointments'] = fake_response({}, status=503)

        response = self.generate(auth_client)

        assert response.url == LIST_URL
        assert "DrChrono returned an error. Try again in a moment." in message_texts(response)

    def test_rejected_token_goes_to_sign_in(self, auth_client, drchrono):
        drchrono.routes['/api/patients/101'] = fake_response({}, status=401)

        response = self.generate(auth_client)

        assert response.url == reverse('verify_app:connect_drchrono')
        assert 'Your DrChrono session expired, please sign in again.' in message_texts(response)

    def test_no_visits_selected(self, auth_client, drchrono):
        response = self.generate(auth_client, selected=[])

        assert response.url == LIST_URL
        assert 'No appointments were selected for PDF generation.' in message_texts(response)
