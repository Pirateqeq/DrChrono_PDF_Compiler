"""The billing PDF: fetch everything once, then assemble it visit by visit; all or nothing."""
from collections import defaultdict
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from core import drchrono

from . import balance, hcfa


class PacketError(Exception):
    """No PDF is generated. Each argument is one line of the notice shown to the user."""


class NoteError(Exception):
    """A visit's clinical note can't be included; the message says why."""


def load(token, patient_id, selected_ids):
    """Everything the PDF needs, fetched once: patient, eligible visits, and their line items by visit."""
    patient = drchrono.patient(token, patient_id)
    appointments = drchrono.eligible_appointments(token, patient_id)
    by_id = {str(appt['id']): appt for appt in appointments}
    ids = set(selected_ids)
    # Only this patient's eligible visits: a stale or altered form can't put another visit on the claims.
    if not ids <= by_id.keys():
        raise PacketError('The visit list changed. Reload the page and try again.')
    missing = hcfa.missing_details(patient)
    if missing:
        raise PacketError(f"Can't build claim forms: missing {', '.join(missing)}.")
    line_items = by_visit(drchrono.line_items(token, patient=patient_id))
    # The visit list normally carries ICD-10 codes; fetch a visit only if they're absent.
    selected = sorted((by_id[i] if 'icd10_codes' in by_id[i]
                       else by_id[i] | {'icd10_codes': drchrono.appointment(token, i).get('icd10_codes')}
                       for i in ids), key=lambda appt: appt['scheduled_time'])
    return {'patient': patient, 'appointments': appointments, 'selected': selected, 'line_items': line_items}


def by_visit(line_items):
    """Line items grouped by visit ID as text (missing visits give an empty list).

    DrChrono sends a visit's own `id` as text but a line item's `appointment` as a number, so both
    sides are compared as text: look visits up with `str(visit['id'])`.
    """
    grouped = defaultdict(list)
    for item in line_items:
        grouped[str(item['appointment'])].append(item)
    return grouped


def build(packet):
    """PDF bytes: balance report, then each selected visit's note and claim forms, oldest visit first.

    All or nothing: if any note or claim can't be built, PacketError lists every problem at once,
    so they can all be fixed before trying again.
    """
    problems = []
    parts = [balance.balance_report(packet['patient'], packet['appointments'], packet['line_items'])]
    for visit in packet['selected']:
        when = f"{visit['scheduled_time']:%b %d, %Y}"
        try:
            parts.append(download_note(visit))
        except NoteError as e:
            problems.append(f'{when} clinical note: {e}')
        try:
            parts.extend(hcfa.claim_forms(packet['patient'], visit, packet['line_items'][str(visit['id'])]))
        except hcfa.ClaimError as e:
            problems.append(f'{when} claim form: {e}')
    if problems:
        raise PacketError("The PDF wasn't generated because these parts couldn't be built:", *problems)
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
        content = drchrono.download(url)
        PdfReader(BytesIO(content))  # fail here, not halfway through the merge
    except drchrono.DrChronoError as e:
        raise NoteError("couldn't download it") from e
    except PdfReadError as e:
        raise NoteError("the downloaded file isn't a PDF") from e
    return content
