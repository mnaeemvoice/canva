from django.db import models


# ===============================
# CANVA DESIGN MODEL
# ===============================
from django.db import models

from django.db import models

class CanvaDesign(models.Model):

    design_id = models.CharField(max_length=255, unique=True)

    title = models.CharField(max_length=255, null=True, blank=True)

    # main asset url (image/pdf/video/svg)
    asset_url = models.URLField(null=True, blank=True)

    # asset type
    asset_type = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # 🔥 status field (important for tracking)
    status = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="synced"
    )

    # full Canva API response
    raw_data = models.JSONField(null=True, blank=True)

    # 🔥 NEW: Track last modified time from Canva
    last_modified = models.DateTimeField(null=True, blank=True)

    # 🔥 NEW: Track if preview is ready for display
    preview_ready = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or self.design_id

# ===============================
# CANVA CONNECTION (TOKEN)
# ===============================
class CanvaConnection(models.Model):
    access_token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    connected = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Canva Connection"

    # 🔥 SAVE TOKEN (singleton)
    @classmethod
    def save_token(cls, access_token, refresh_token=None, expires_at=None):
        obj, created = cls.objects.update_or_create(
            id=1,  # singleton pattern
            defaults={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "connected": True
            }
        )
        return obj

    # 🔥 GET TOKEN
    @classmethod
    def get_token(cls):
        obj = cls.objects.first()
        return obj.access_token if obj else None

    # 🔥 CHECK TOKEN EXIST
    @classmethod
    def is_connected(cls):
        return cls.objects.filter(connected=True).exists()