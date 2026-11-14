from django.views.generic import ListView
from django.contrib import messages
from django.utils.decorators import method_decorator

from core.drchrono import eligible_appointments
from verify.services import require_auth

@method_decorator(require_auth, name='dispatch')
class HistoricalAppointmentsView(ListView):
    template_name = 'appts/historical_list.html'
    context_object_name = 'appointments'

    # Verify DrChrono login access
    login_url = 'verify_app:connect_drchrono'
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        patient_id = self.kwargs['patient_id']

        try:
            return eligible_appointments(self.request.drchrono_token, patient_id)

        except Exception as e:
            messages.error(self.request, f"Failed to load appointments: {str(e)}")
            return []

    def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            
            patient_id = self.kwargs['patient_id']
            patient_name = self.kwargs['patient_name']
            context['patient_name'] = patient_name
            context['patient_id'] = patient_id
            context['page_title'] = f"Historical Appointments for {patient_name}"
            
            return context