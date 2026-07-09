from django.views.generic import FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin

from verify.exceptions import DrChronoAuthError
from .forms import PatientSearchForm
from .services import search_patients  # from earlier sketch
from verify.services import require_auth

@method_decorator(require_auth, name='dispatch')
class PatientSearchView(LoginRequiredMixin, FormView):
    template_name = 'search/search.html'
    form_class = PatientSearchForm
    success_url = reverse_lazy('search_app:results')

    # Verify DrChrono login access
    login_url = 'verify_app:connect_drchrono'
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Search Patients"
        return context
    
    def form_valid(self, form):
        """
        On valid form perform API search, store results in session, redirect to results
        """

        filters = form.cleaned_data
        # Normalize for API (expects YYYY-MM-DD for DOB)
        if filters.get('date_of_birth'):
            filters['date_of_birth'] = filters['date_of_birth'].isoformat()
        
        try:
            patients, next_cursor = search_patients(self.request, filters)

            if not patients:
                messages.info(self.request, "No patients found matching your criteria.")
                return self.form_invalid(form)

            self.request.session['patient_search_results'] = patients
            self.request.session['patient_search_filters'] = filters
            self.request.session['patient_next_cursor'] = next_cursor

            messages.success(self.request, f"Found {len(patients)} matching patient(s).")
            return redirect('search_app:results')
        
        except DrChronoAuthError as e:
            messages.error(self.request, f"Authentication issue: {str(e)}. Please try again.")
            return self.form_invalid(form)
        
        except ValueError as e:
            messages.error(self.request, "An error occurred while searching patients. Please try again or contact support.")
            return self.form_invalid(form)
        
        except Exception as e:
            messages.error(self.request, "An unexpected error occurred. Please try again later.")
            return self.form_invalid(form)
        
    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

from django.views import View
from django.shortcuts import render

@method_decorator(require_auth, name='dispatch')
class PatientResultsView(View):
    # Verify DrChrono login access
    login_url = 'verify_app:connect_drchrono'
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request):
        patients = request.session.get('patient_search_results', [])
        filters = request.session.get('patient_search_filters', {})
        next_cursor = request.session.get('patient_next_cursor')

        context = {
            'patients': patients,
            'filters': filters,
            'next_cursor': next_cursor,
            'page_title': 'Search Results',
            'result_count': len(patients),
        }

        return render(request, 'search/results.html', context)
    