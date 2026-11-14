"""HCFA-1500 claim forms: what goes in each box for a visit, and where it is printed on the blank form."""
from decimal import Decimal
from io import BytesIO
from os import getenv
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

TEMPLATE = Path(__file__).parent / 'forms' / 'HCFA.pdf'
PAGE_WIDTH, PAGE_HEIGHT = 620, 800
LINES_PER_FORM = 6  # box 24 has six service lines; more charges go on extra forms

# Positions are (x, y) with y measured down from the top of the page, hand-tuned to forms/HCFA.pdf.
CHECKS = [
    (345, 124),  # box 1: insurance type
    (259, 173),  # box 6: patient is the insured (self)
    (317, 269),  # box 10a: employment, no
    (274, 292),  # box 10b: auto accident, yes
    (317, 316),  # box 10c: other accident, no
    (432, 340),  # box 11d: another health plan, no
    (159, 699),  # box 25: EIN
    (296, 699),  # box 27: accept assignment, yes
]
SEX_CHECKS = {'Male': [(324, 148), (511, 268)], 'Female': [(360, 148), (562, 268)]}  # boxes 3 and 11a
TEXT = {
    'name': [(37, 146), (388, 146)],                       # boxes 2 and 4
    'dob_month': [(247, 147), (407, 268)],                 # boxes 3 and 11a
    'dob_day': [(270, 147), (430, 268)],
    'dob_year': [(290, 147), (450, 268)],
    'address': [(37, 171), (388, 170)],                    # boxes 5 and 7
    'city': [(37, 194), (388, 194)],
    'state': [(211, 194), (555, 194)],
    'zip': [(37, 219), (388, 219)],
    'phone_area': [(134, 221), (493, 220)],
    'phone_number': [(162, 221), (520, 220)],
    'signature': [(72, 385), (430, 385)],                  # boxes 12 and 13
    'signature_date': [(280, 385), (120, 750)],            # box 12 and box 31 dates
    'icd_indicator': [(327, 474)],                         # box 21
    'federal_id': [(37, 698)],                             # box 25
    'account_number': [(190, 698)],                        # box 26
    'total_dollars': [(390, 698)],                         # box 28
    'total_cents': [(443, 698)],
    'physician_signature': [(37, 745)],                    # box 31
    'office': [(190, 720)],                                # box 32
    'provider_address': [(190, 735), (388, 735)],          # boxes 32 and 33
    'provider_city_state': [(190, 745), (388, 745)],
    'provider_phone_area': [(500, 712)],                   # box 33
    'provider_phone_number': [(525, 712)],
    'provider_info': [(388, 720)],
    'provider_npi': [(388, 760)],                          # box 33a
}
# Box 24 columns; line n is printed 24 points below line n-1, starting at y=555.
LINE_X = {'from_month': 32, 'from_day': 53, 'from_year': 74, 'to_month': 95, 'to_day': 116, 'to_year': 139,
          'place': 161, 'code': 210, 'pointer': 355, 'dollars': 387, 'cents': 427, 'units': 455, 'npi': 523}

PATIENT_DETAILS = {'first_name': 'first name', 'last_name': 'last name', 'date_of_birth': 'date of birth',
                   'gender': 'sex', 'address': 'address', 'city': 'city', 'state': 'state', 'zip_code': 'zip code',
                   'cell_phone': 'cell phone'}
PRACTICE_SETTINGS = ('PROVIDER_NPI', 'FEDERAL_TAX_ID', 'PROVIDER_ACCOUNT_NUMBER', 'PHYSICIAN_SIGNATURE',
                     'PROVIDER_OFFICE_NAME', 'PROVIDER_ADDRESS', 'PROVIDER_CITY_STATE', 'PROVIDER_PHONE', 'PROVIDER_INFO')


class ClaimError(Exception):
    """This visit's claim form can't be built; the message says why, in plain words."""


def missing_details(patient):
    """Patient fields and practice settings that every claim needs but are empty."""
    return ([f'patient {label}' for field, label in PATIENT_DETAILS.items() if not patient.get(field)]
            + [f'practice setting {name}' for name in PRACTICE_SETTINGS if not getenv(name)])


def claim_forms(patient, visit, charges):
    """One filled form (PDF bytes) per six charges of the visit."""
    if not charges:
        raise ClaimError('no charges')
    if not visit.get('icd10_codes'):
        raise ClaimError('no ICD-10 diagnosis codes')
    if not (visit.get('clinical_note') or {}).get('updated_at'):
        raise ClaimError('the clinical note has no signature date')
    fields = _visit_fields(patient, visit)
    return [_draw(fields, patient.get('gender'), visit['icd10_codes'], charges[i:i + LINES_PER_FORM])
            for i in range(0, len(charges), LINES_PER_FORM)]


def _phone(raw):
    """(area code, number) for a 10-digit phone; otherwise the number as given, with no area code."""
    digits = ''.join(ch for ch in raw if ch.isdigit())
    return (digits[:3], f'{digits[3:6]}-{digits[6:]}') if len(digits) == 10 else ('', raw)


def _visit_fields(patient, visit):
    dob_year, dob_month, dob_day = patient['date_of_birth'].split('-')
    signed_year, signed_month, signed_day = visit['clinical_note']['updated_at'][:10].split('-')
    phone_area, phone_number = _phone(patient['cell_phone'])
    provider_area, provider_number = _phone(getenv('PROVIDER_PHONE'))
    return {
        'name': f"{patient['last_name']}, {patient['first_name']}",
        'dob_month': dob_month, 'dob_day': dob_day, 'dob_year': dob_year,
        'address': patient['address'], 'city': patient['city'], 'state': patient['state'], 'zip': patient['zip_code'],
        'phone_area': phone_area, 'phone_number': phone_number,
        'signature': 'Signature on File', 'signature_date': f'{signed_month}/{signed_day}/{signed_year}',
        'icd_indicator': '0',  # ICD-10
        'federal_id': getenv('FEDERAL_TAX_ID'), 'account_number': getenv('PROVIDER_ACCOUNT_NUMBER'),
        'physician_signature': getenv('PHYSICIAN_SIGNATURE'), 'office': getenv('PROVIDER_OFFICE_NAME'),
        'provider_address': getenv('PROVIDER_ADDRESS'), 'provider_city_state': getenv('PROVIDER_CITY_STATE'),
        'provider_phone_area': provider_area, 'provider_phone_number': provider_number,
        'provider_info': getenv('PROVIDER_INFO'), 'provider_npi': getenv('PROVIDER_NPI'),
    }


def _line(charge):
    year, month, day = charge['service_date'].split('-')
    dollars, cents = f"{Decimal(charge['price']):.2f}".split('.')
    return {'from_month': month, 'from_day': day, 'from_year': year[2:], 'to_month': month, 'to_day': day,
            'to_year': year[2:], 'place': '11', 'code': charge['code'], 'pointer': 'a', 'dollars': dollars,
            'cents': cents, 'units': '1', 'npi': getenv('PROVIDER_NPI')}


def _draw(fields, sex, icd_codes, charges):
    total_dollars, total_cents = f"{sum(Decimal(c['price']) for c in charges):.2f}".split('.')
    fields = fields | {'total_dollars': total_dollars, 'total_cents': total_cents}
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    for x, y in CHECKS + SEX_CHECKS.get(sex, []):  # drawn before the font change, as on the original forms
        c.drawString(x, PAGE_HEIGHT - y, '✓')
    c.setFont('Courier', 10)
    for field, value in fields.items():
        for x, y in TEXT[field] if value else []:
            c.drawString(x, PAGE_HEIGHT - y, value)
    for i, code in enumerate(icd_codes):  # box 21: four codes per row
        c.drawString(50 + 93 * i - 373 * (i // 4), PAGE_HEIGHT - 484 - 12 * (i // 4), code)
    for row, charge in enumerate(charges):
        for column, value in _line(charge).items():
            c.drawString(LINE_X[column], PAGE_HEIGHT - 555 - 24 * row, value)
    c.save()
    writer = PdfWriter(clone_from=TEMPLATE)  # a fresh copy of the blank form per claim
    writer.pages[0].merge_page(PdfReader(buffer).pages[0])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
