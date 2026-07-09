from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# User credential class
class DrChronoCredential(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='drchrono_cred')
    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255, blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_expired(self):
        if not self.expires_at:
            return True
        return timezone.now() >= self.expires_at
