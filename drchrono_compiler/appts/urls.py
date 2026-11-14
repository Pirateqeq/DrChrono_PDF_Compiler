from django.urls import path

from . import views

app_name = 'appts_app'

urlpatterns = [
    path('patient/<int:patient_id>/', views.appointment_list, name='historical_list'),
]
