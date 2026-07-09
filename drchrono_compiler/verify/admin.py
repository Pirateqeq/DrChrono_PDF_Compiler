from django.contrib import admin
from .models import DrChronoCredential

# Register your models here.
@admin.register(DrChronoCredential)
class DrChronoCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'is_expired')
    readonly_fields = ('created_at', 'updated_at')