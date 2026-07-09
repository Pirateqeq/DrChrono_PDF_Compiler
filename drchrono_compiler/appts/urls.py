from django.urls import path
from . import views

app_name = 'appts_app'

urlpatterns = [
    path('patient/<int:patient_id>_<str:patient_name>/historical/', views.HistoricalAppointmentsView.as_view(), name='historical_list'),
]