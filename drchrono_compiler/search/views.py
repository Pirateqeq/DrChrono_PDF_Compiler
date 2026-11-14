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
        try:
            patients, more = search_patients(request.drchrono_token, **form.cleaned_data)
        except DrChronoError as e:
            if e.status == 401:
                raise  # require_auth sends the user to sign in
            messages.error(request, user_message(e))
        else:
            if patients:
                query = {field: str(value) for field, value in form.cleaned_data.items() if value}
                request.session['patient_search'] = {'patients': patients, 'more': more, 'query': query}
                messages.success(request, f'Found {len(patients)} matching patient(s).')
                return redirect('search_app:results')
            messages.info(request, 'No patients found matching your criteria.')
    return render(request, 'search/search.html', {'form': form})


@require_auth
def results(request):
    return render(request, 'search/results.html', request.session.get('patient_search', {}))
