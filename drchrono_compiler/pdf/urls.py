from django.urls import path

from . import views

app_name = 'pdf_app'

urlpatterns = [
    path('patient/<int:patient_id>/generate-selected/', views.generate, name='generate_selected'),
]
