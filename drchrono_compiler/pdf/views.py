from django.views import View
from django.http import HttpResponse
from django.contrib import messages
from django.shortcuts import redirect
from verify.services import require_auth, get_valid_access_token
from django.utils.decorators import method_decorator
from pypdf import PdfWriter

from core.services import (
    fetch_appointment,
    fetch_lineitem,
    fetch_patient,
)

from .services import (
    generate_balance_report,
    generate_clinical_notes,
    fetch_hcfa_data,
    generate_hcfa_bill,
)
from io import BytesIO
import requests

@method_decorator(require_auth, name='dispatch')
class GenerateSelectedPDFView(View):

    # Verify DrChrono login access
    login_url = 'verify_app:connect_drchrono'
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, patient_id):
        PRINT_ERRORS = False
        selected_ids = request.POST.getlist('selected_appts')
        if not selected_ids:
            messages.warning(request, "No appointments were selected for PDF generation.")
            return redirect('appts:historical_list', patient_id=patient_id)

        try:
            selected_ids = list(reversed(selected_ids))
            token = get_valid_access_token(request)
            headers = {"Authorization": f"Bearer {token}"}

            merger = PdfWriter()

            balance_buffer = generate_balance_report(patient_id, token)
            merger.append(balance_buffer)

            # Pull appointment JSONs and key them into -> selected_appts{ APPT_ID : APPT_JSON }. Note - Later seperate pull into service file to include exception checks.
            # If appointment JSON is pulled properly key line_item into -> line_items{ APPT_ID : LINE_ITEM_JSON}. Note - Later seperate pull into service file to include exception checks.
            line_items = {}
            selected_appts = {}
            for appt_id in selected_ids:
                selected_appts[appt_id] = fetch_appointment(requests, headers, appt_id)
                line_items[appt_id] = fetch_lineitem(requests, headers, appt_id)

            # Pull patient JSON. Note - Later seperate pull into service file to include exception checks.
            patient_json = {}
            patient_json = fetch_patient(requests, headers, patient_id)
        

            # Pull doctor JSON. Note - Later seperate pull into service file to include exception checks (Implement Later).
            for appt_id in selected_appts:
                if PRINT_ERRORS: print("Printing Clinical Notes")
                merger.append(generate_clinical_notes(request, selected_appts[appt_id]))
                
                if PRINT_ERRORS: print("Fetching Patient Data")
                hcfa_data = fetch_hcfa_data(patient_json, selected_appts[appt_id], line_items[appt_id])

                if PRINT_ERRORS: print("Printing HCFA Bill")
                merger.append(generate_hcfa_bill(request, hcfa_data))

            output = BytesIO()
            merger.write(output)
            merger.close()
            output.seek(0)

            response = HttpResponse(content_type='application/pdf')
            filename = f"Patient_{patient_json.get('first_name')}_{patient_json.get('last_name')}_REPORT.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.write(output.read())

            return response

        except Exception as e:
            patient_name = request.POST.get("patient_name")
            messages.error(request, f"PDF generation failed.")
            for er in e.args:
                messages.error(request, str(er))
            return redirect('appts_app:historical_list', patient_id=patient_id, patient_name=patient_name)