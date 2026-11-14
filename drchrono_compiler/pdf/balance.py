"""The balance report: the patient's unpaid charges across all eligible visits, newest first."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from os import getenv

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TABLE_STYLE = TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.white),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 11),
    ('WORDWRAP', (3, 0), (3, -1), True),
    ('ALIGN', (0, 1), (2, -1), 'CENTER'),  # date, debit, claim type
    ('ALIGN', (3, 1), (3, -1), 'LEFT'),    # description
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 1), (-1, -1), 10),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ('LEFTPADDING', (0, 0), (-1, -1), 8),
])


def balance_report(patient, appointments, line_items):
    """PDF bytes. `line_items` maps each visit ID to that visit's line items."""
    name = f"{patient.get('last_name')}, {patient.get('first_name')}"
    unpaid = [(item, appt) for appt in appointments for item in line_items.get(appt['id'], [])
              if Decimal(item['balance_total']) != 0]
    unpaid.sort(key=lambda pair: pair[0]['service_date'], reverse=True)
    total = sum((Decimal(item['balance_total']) for item, _ in unpaid), Decimal('0.00'))
    rows = [_row(item, appt, name) for item, appt in unpaid] or [['—', '—', '—', 'No billable transactions found.']]

    styles = getSampleStyleSheet()  # a fresh sheet per call, so this only affects this report
    styles['Normal'].fontSize, styles['Normal'].leading = 9, 11
    elements = [
        Paragraph('Patient Account Balance', styles['Heading1']), Spacer(1, 12),
        Paragraph(f"Provider: {getenv('PROVIDER_NAME', 'Unknown Provider')}", styles['Normal']), Spacer(1, 8),
        Paragraph(f'Patient: {name}', styles['Normal']), Spacer(1, 8),
        Paragraph('Account Balance:', styles['Heading2']), Paragraph(f'${total:,.2f}', styles['Normal']), Spacer(1, 12),
        Paragraph('Payment History:', styles['Heading2']), Spacer(1, 16),
        Table([['Date', 'Debit', 'Auto Accident Claim', 'Description']] + rows, colWidths=[96, 96, 128, 256],
              style=TABLE_STYLE),
        Spacer(1, 36),
    ]
    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=(620, 800), leftMargin=18, rightMargin=18, topMargin=36,
                      bottomMargin=36).build(elements)
    return buffer.getvalue()


def _row(item, appt, name):
    served = date.fromisoformat(item['service_date'])
    description = Paragraph(f"Appointment [{item['appointment']}] {served:%m/%d/%y} {name}: "
                            f"{appt.get('reason', '---')} Code {item.get('code', '—')}")
    return [f'{served:%b %d, %Y}', f"${Decimal(item['balance_total']):,.2f}", 'Auto Accident Claim', description]
