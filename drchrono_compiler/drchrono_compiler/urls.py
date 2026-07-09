from django.contrib import admin
from django.urls import path, include

app_name = "main_app"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('verify.urls')),
    path('search/', include('search.urls')),
    path('appts/', include('appts.urls')),
    path('pdf/', include('pdf.urls')),
]
