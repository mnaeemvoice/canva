from django.db import models


class CanvaDesign(models.Model):
    design_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    raw_data = models.JSONField()

    def __str__(self):
        return self.design_id


class CanvaConnection(models.Model):
    access_token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    connected = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
class CanvaDesign(models.Model):
    design_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    raw_data = models.JSONField()

    def __str__(self):
        return self.design_id

    @classmethod
    def save_design(cls, item):
        obj, created = cls.objects.update_or_create(
            design_id=item.get("id"),
            defaults={
                "title": item.get("title"),
                "raw_data": item
            }
        )
        return obj, created
    
    # models.py
class CanvaConnection(models.Model):
    access_token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    connected = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def save_token(cls, access_token, refresh_token=None, expires_at=None):
        # 🔥 overwrite old connection (single source of truth)
        obj, created = cls.objects.update_or_create(
            id=1,  # simple singleton approach
            defaults={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "connected": True
            }
        )
        return obj

    @classmethod
    def get_token(cls):
        obj = cls.objects.first()
        return obj.access_token if obj else None