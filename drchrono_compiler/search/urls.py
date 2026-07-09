from django.urls import path
from django.shortcuts import render
from .views import PatientSearchView, PatientResultsView

app_name = "search_app"

urlpatterns = [
    path('', PatientSearchView.as_view(), name='search'),
    path('results/', PatientResultsView.as_view(), name='results'),
]