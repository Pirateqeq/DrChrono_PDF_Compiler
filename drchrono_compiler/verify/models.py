from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class DrChronoCredential(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='drchrono_cred')
    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255, blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def needs_refresh(self):
        # 5-minute margin so a token can't expire partway through a multi-call PDF build.
        return self.expires_at is None or self.expires_at - timedelta(minutes=5) <= timezone.now()
