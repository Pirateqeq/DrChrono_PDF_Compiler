"""Golden output captured from the pre-overhaul pdf code (Nov 2026), used by pdf/tests.py.

The claim form and balance report must keep producing exactly this for a normal visit. To
regenerate after an intentional layout change, record `record_drawing(...)` for GOLDEN_VISIT /
GOLDEN_CHARGES and the balance report's page text, and replace the two constants.
"""
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas

from core.testing import make_appointment, make_line_item

GOLDEN_VISIT = make_appointment(1, '2025-03-10T09:30:00', icd10_codes=['M54.5', 'M99.03'])
GOLDEN_CHARGES = [make_line_item(1, code, price) for code, price in [
    ('99213', '150.00'), ('97140', '45.00'), ('98940', '60.00'), ('97110', '40.00'), ('97012', '25.50')]]
# Balance report input: visit 1 with the charges above plus a paid-off one, visit 2 with one charge.
GOLDEN_BALANCE_VISITS = [make_appointment(2, '2025-05-20T10:00:00'), make_appointment(1, '2025-03-10T09:30:00')]
GOLDEN_BALANCE_ITEMS = GOLDEN_CHARGES + [make_line_item(1, '97750', '30.00', balance_total='0.00'),
                                         make_line_item(2, '98940', '75.50', service_date='2025-05-20')]


def record_drawing(build):
    """Every Canvas.drawString call made while `build()` runs, as sorted (x, y, text) tuples."""
    calls = []
    original = Canvas.drawString

    def record(self, x, y, text, *args, **kwargs):
        calls.append((x, y, text))
        return original(self, x, y, text, *args, **kwargs)

    with patch.object(Canvas, 'drawString', record):
        build()
    return sorted(calls)


CLAIM_FORM_GOLDEN = [(32, 149, '03'),
 (32, 173, '03'),
 (32, 197, '03'),
 (32, 221, '03'),
 (32, 245, '03'),
 (37, 55, 'Dr. Sam Smith'),
 (37, 102, '12-3456789'),
 (37, 581, '62701'),
 (37, 606, 'Springfield'),
 (37, 629, '123 Main St'),
 (37, 654, 'Doe, Jane'),
 (50, 316, 'M54.5'),
 (53, 149, '10'),
 (53, 173, '10'),
 (53, 197, '10'),
 (53, 221, '10'),
 (53, 245, '10'),
 (72, 415, 'Signature on File'),
 (74, 149, '25'),
 (74, 173, '25'),
 (74, 197, '25'),
 (74, 221, '25'),
 (74, 245, '25'),
 (95, 149, '03'),
 (95, 173, '03'),
 (95, 197, '03'),
 (95, 221, '03'),
 (95, 245, '03'),
 (116, 149, '10'),
 (116, 173, '10'),
 (116, 197, '10'),
 (116, 221, '10'),
 (116, 245, '10'),
 (120, 50, '03/10/2025'),
 (134, 579, '217'),
 (139, 149, '25'),
 (139, 173, '25'),
 (139, 197, '25'),
 (139, 221, '25'),
 (139, 245, '25'),
 (143, 316, 'M99.03'),
 (159, 101, '✓'),
 (161, 149, '11'),
 (161, 173, '11'),
 (161, 197, '11'),
 (161, 221, '11'),
 (161, 245, '11'),
 (162, 579, '555-0123'),
 (190, 55, 'Springfield, IL 62701'),
 (190, 65, '500 Oak Ave'),
 (190, 80, 'Springfield Chiropractic'),
 (190, 102, 'ACCT-42'),
 (210, 149, '97012'),
 (210, 173, '97110'),
 (210, 197, '98940'),
 (210, 221, '97140'),
 (210, 245, '99213'),
 (211, 606, 'IL'),
 (247, 653, '04'),
 (259, 627, '✓'),
 (270, 653, '15'),
 (274, 508, '✓'),
 (280, 415, '03/10/2025'),
 (290, 653, '1980'),
 (296, 101, '✓'),
 (317, 484, '✓'),
 (317, 531, '✓'),
 (327, 326, '0'),
 (345, 676, '✓'),
 (355, 149, 'a'),
 (355, 173, 'a'),
 (355, 197, 'a'),
 (355, 221, 'a'),
 (355, 245, 'a'),
 (360, 652, '✓'),
 (387, 149, '25'),
 (387, 173, '40'),
 (387, 197, '60'),
 (387, 221, '45'),
 (387, 245, '150'),
 (388, 40, '1234567890'),
 (388, 55, 'Springfield, IL 62701'),
 (388, 65, '500 Oak Ave'),
 (388, 80, 'Springfield Chiropractic'),
 (388, 581, '62701'),
 (388, 606, 'Springfield'),
 (388, 630, '123 Main St'),
 (388, 654, 'Doe, Jane'),
 (390, 102, '320'),
 (407, 532, '04'),
 (427, 149, '50'),
 (427, 173, '00'),
 (427, 197, '00'),
 (427, 221, '00'),
 (427, 245, '00'),
 (430, 415, 'Signature on File'),
 (430, 532, '15'),
 (432, 460, '✓'),
 (443, 102, '50'),
 (450, 532, '1980'),
 (455, 149, '1'),
 (455, 173, '1'),
 (455, 197, '1'),
 (455, 221, '1'),
 (455, 245, '1'),
 (493, 580, '217'),
 (500, 88, '217'),
 (520, 580, '555-0123'),
 (523, 149, '1234567890'),
 (523, 173, '1234567890'),
 (523, 197, '1234567890'),
 (523, 221, '1234567890'),
 (523, 245, '1234567890'),
 (525, 88, '555-0199'),
 (555, 606, 'IL'),
 (562, 532, '✓')]
BALANCE_REPORT_GOLDEN = 'Patient Account Balance\nProvider: Springfield Chiropractic\nPatient: Doe, Jane\nAccount Balance:\n$396.00\nPayment History:\nDate\nDebit\nAuto Accident Claim\nDescription\nMay 20, 2025\n$75.50\nAuto Accident Claim\nAppointment [2] 05/20/25 Doe, Jane: Follow-up Code\n98940\nMar 10, 2025\n$150.00\nAuto Accident Claim\nAppointment [1] 03/10/25 Doe, Jane: Follow-up Code\n99213\nMar 10, 2025\n$45.00\nAuto Accident Claim\nAppointment [1] 03/10/25 Doe, Jane: Follow-up Code\n97140\nMar 10, 2025\n$60.00\nAuto Accident Claim\nAppointment [1] 03/10/25 Doe, Jane: Follow-up Code\n98940\nMar 10, 2025\n$40.00\nAuto Accident Claim\nAppointment [1] 03/10/25 Doe, Jane: Follow-up Code\n97110\nMar 10, 2025\n$25.50\nAuto Accident Claim\nAppointment [1] 03/10/25 Doe, Jane: Follow-up Code\n97012\n'
