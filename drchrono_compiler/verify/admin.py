from django.contrib import admin

from .models import DrChronoCredential


@admin.register(DrChronoCredential)
class DrChronoCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'needs_refresh')
    readonly_fields = ('created_at', 'updated_at')
    exclude = ('access_token', 'refresh_token')  # live DrChrono credentials; never shown or edited here
