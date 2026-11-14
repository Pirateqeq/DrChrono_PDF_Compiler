from io import BytesIO

from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from core.drchrono import DrChronoError, user_message
from verify.services import require_auth

from . import packet


@require_POST
@require_auth
def generate(request, patient_id):
    """Build the billing PDF for the ticked visits and send it as a download."""
    selected_ids = request.POST.getlist('selected_appts')
    if not selected_ids:
        messages.warning(request, 'No appointments were selected for PDF generation.')
        return redirect('appts_app:historical_list', patient_id=patient_id)
    try:
        contents = packet.load(request.drchrono_token, patient_id, selected_ids)
        pdf = packet.build(contents)
    except packet.PacketError as e:
        messages.error(request, str(e))
    except DrChronoError as e:
        messages.error(request, user_message(e))
    else:
        patient = contents['patient']
        # FileResponse quotes and encodes the name, so quotes or accents can't break the header.
        return FileResponse(BytesIO(pdf), as_attachment=True, content_type='application/pdf',
                            filename=f"Patient_{patient['first_name']}_{patient['last_name']}_REPORT.pdf")
    return redirect('appts_app:historical_list', patient_id=patient_id)
