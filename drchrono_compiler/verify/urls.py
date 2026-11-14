from django.urls import path

from . import views

app_name = 'verify_app'

urlpatterns = [
    path('', views.connect_drchrono, name='connect_drchrono'),
    path('authorize/', views.authorize, name='authorize'),
    path('oauth/callback', views.oauth_callback, name='oauth_callback'),
    path('logout/', views.sign_out, name='sign_out'),
]
