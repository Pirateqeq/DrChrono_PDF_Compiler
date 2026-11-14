from django.contrib import messages
from django.shortcuts import render

from core import drchrono
from verify.services import require_auth


@require_auth
def appointment_list(request, patient_id):
    """A patient's eligible visits, each with a checkbox for the PDF and a tag if it has no charges."""
    token = request.drchrono_token
    patient, appointments = None, []
    try:
        patient = drchrono.patient(token, patient_id)
        appointments = drchrono.eligible_appointments(token, patient_id)
        charges = drchrono.by_visit(drchrono.line_items(token, patient=patient_id))
    except drchrono.DrChronoError as e:
        messages.error(request, drchrono.user_message(e))
        appointments = []
    for appt in appointments:  # eligible_appointments returns copies, so marking them is safe
        appt['no_charges'] = not charges.get(str(appt['id']))
    return render(request, 'appts/historical_list.html',
                  {'patient': patient, 'patient_id': patient_id, 'appointments': appointments})
