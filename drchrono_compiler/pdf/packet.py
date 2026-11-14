"""The billing PDF: fetch everything once, then assemble it visit by visit, skipping (and listing) what fails."""
from collections import defaultdict
from io import BytesIO

import requests
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from core import drchrono

from . import balance, hcfa


class PacketError(Exception):
    """The PDF can't be built at all; the message says why, in plain words."""


class NoteError(Exception):
    """A visit's clinical note can't be included; the message says why."""


def load(token, patient_id, selected_ids):
    """Everything the PDF needs, fetched once: patient, eligible visits, and their line items by visit."""
    patient = drchrono.patient(token, patient_id)
    appointments = drchrono.eligible_appointments(token, patient_id)
    by_id = {str(appt['id']): appt for appt in appointments}
    # Only this patient's eligible visits: a stale or altered form can't put another visit on the claims.
    if not set(selected_ids) <= by_id.keys():
        raise PacketError('The visit list changed. Reload the page and try again.')
    missing = hcfa.missing_details(patient)
    if missing:
        raise PacketError(f"Can't build claim forms: missing {', '.join(missing)}.")
    line_items = defaultdict(list)
    for item in drchrono.line_items(token, patient=patient_id):
        line_items[item['appointment']].append(item)
    selected = sorted((by_id[appt_id] for appt_id in set(selected_ids)), key=lambda appt: appt['scheduled_time'])
    # The visit list normally carries ICD-10 codes; fetch a visit only if they're absent.
    selected = [appt if 'icd10_codes' in appt
                else appt | {'icd10_codes': drchrono.appointment(token, appt['id']).get('icd10_codes')}
                for appt in selected]
    return {'patient': patient, 'appointments': appointments, 'selected': selected, 'line_items': line_items}


def build(packet):
    """PDF bytes: balance report, then each selected visit's note and claim forms, oldest visit first."""
    skipped = []
    parts = [balance.balance_report(packet['patient'], packet['appointments'], packet['line_items'])]
    for visit in packet['selected']:
        when = f"{visit['scheduled_time']:%b %d, %Y}"
        try:
            parts.append(download_note(visit))
        except NoteError as e:
            skipped.append(f'{when} clinical note: {e}')
        try:
            parts.extend(hcfa.claim_forms(packet['patient'], visit, packet['line_items'][visit['id']]))
        except hcfa.ClaimError as e:
            skipped.append(f'{when} claim form: {e}')
    if skipped:
        parts.insert(0, _not_included_page(skipped))
    writer = PdfWriter()
    for part in parts:
        writer.append(BytesIO(part))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def download_note(visit):
    """The clinical note PDF's bytes (the URL needs no auth header)."""
    url = drchrono.note_pdf_url(visit)
    if not url:
        raise NoteError('no clinical note PDF')
    try:
        resp = drchrono.session.get(url, timeout=15)
        resp.raise_for_status()
        PdfReader(BytesIO(resp.content))  # fail here, not halfway through the merge
    except requests.RequestException as e:
        raise NoteError("couldn't download it") from e
    except PdfReadError as e:
        raise NoteError("the downloaded file isn't a PDF") from e
    return resp.content


def _not_included_page(skipped):
    styles = getSampleStyleSheet()
    lines = [Paragraph('Not included', styles['Heading1']),
             Paragraph('These parts could not be built and are missing from this report:', styles['Normal']),
             Spacer(1, 8)] + [Paragraph(f'&bull; {line}', styles['Normal']) for line in skipped]
    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=(620, 800)).build(lines)
    return buffer.getvalue()
