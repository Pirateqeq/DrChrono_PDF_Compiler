from django.contrib import messages
from django.shortcuts import redirect, render

from core.drchrono import DrChronoError, user_message
from verify.services import require_auth

from .forms import PatientSearchForm
from .services import search_patients


@require_auth
def search(request):
    form = PatientSearchForm(request.POST if request.method == 'POST' else None)
    if form.is_valid():
        # The filled-in fields as strings (dates as YYYY-MM-DD): sent to DrChrono and shown on the results page.
        query = {field: str(value) for field, value in form.cleaned_data.items() if value}
        try:
            patients, more = search_patients(request.drchrono_token, query)
            if patients:
                request.session['patient_search'] = {'patients': patients, 'more': more, 'query': query}
                messages.success(request, f'Found {len(patients)} matching patient(s).')
                return redirect('search_app:results')
            messages.info(request, 'No patients found matching your criteria.')
        except DrChronoError as e:
            messages.error(request, user_message(e))
    return render(request, 'search/search.html', {'form': form})


@require_auth
def results(request):
    return render(request, 'search/results.html', request.session.get('patient_search', {}))
