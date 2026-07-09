from django.urls import path
from . import views

app_name = 'verify_app'

urlpatterns = [
    path('', views.connect_drchrono, name='connect_drchrono'),
    path('oauth/callback', views.oauth_callback, name='oauth_callback'),
]