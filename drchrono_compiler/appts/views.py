from django.contrib import messages
from django.shortcuts import render

from core import drchrono
from verify.services import require_auth


@require_auth
def appointment_list(request, patient_id):
    """A patient's eligible visits, each with a checkbox for the PDF."""
    token = request.drchrono_token
    patient, appointments = None, []
    try:
        patient = drchrono.patient(token, patient_id)
        appointments = drchrono.eligible_appointments(token, patient_id)
    except drchrono.DrChronoError as e:
        if e.status == 401:
            raise  # require_auth sends the user to sign in
        messages.error(request, drchrono.user_message(e))
    return render(request, 'appts/historical_list.html',
                  {'patient': patient, 'patient_id': patient_id, 'appointments': appointments})
