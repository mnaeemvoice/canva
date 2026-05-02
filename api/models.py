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

    # category for better organization
    category = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="image"
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

    # 🔥 NEW: Binary file storage
    binary_file = models.BinaryField(null=True, blank=True)
    binary_file_name = models.CharField(max_length=255, null=True, blank=True)
    binary_file_type = models.CharField(max_length=50, null=True, blank=True)
    binary_file_size = models.IntegerField(null=True, blank=True)

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


# ===============================
# SOCIAL MEDIA CONNECTIONS (OAuth)
# ===============================
class SocialMediaConnection(models.Model):
    """Store OAuth tokens for various social media platforms"""
    
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('youtube', 'YouTube'),
        ('instagram', 'Instagram'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'TikTok'),
    ]
    
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, unique=True)
    access_token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    token_type = models.CharField(max_length=50, default='Bearer')
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Additional platform-specific data
    user_id = models.CharField(max_length=255, null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    raw_data = models.JSONField(null=True, blank=True)
    
    connected = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.get_platform_display()} Connection"
    
    @classmethod
    def save_token(cls, platform, access_token, refresh_token=None, expires_at=None, user_id=None, username=None, raw_data=None):
        """Save or update token for a platform"""
        obj, created = cls.objects.update_or_create(
            platform=platform,
            defaults={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "user_id": user_id,
                "username": username,
                "raw_data": raw_data,
                "connected": True
            }
        )
        return obj
    
    @classmethod
    def get_token(cls, platform):
        """Get access token for a platform"""
        obj = cls.objects.filter(platform=platform, connected=True).first()
        return obj.access_token if obj else None
    
    @classmethod
    def is_connected(cls, platform):
        """Check if platform is connected"""
        return cls.objects.filter(platform=platform, connected=True).exists()
    
    @classmethod
    def disconnect(cls, platform):
        """Disconnect a platform"""
        obj = cls.objects.filter(platform=platform).first()
        if obj:
            obj.connected = False
            obj.save()


# ===============================
# POSTED CONTENT TRACKING
# ===============================
class PostedContent(models.Model):
    """Track content posted to various platforms"""
    
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('youtube', 'YouTube'),
        ('instagram', 'Instagram'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'TikTok'),
        ('canva', 'Canva'),
    ]
    
    CONTENT_TYPE_CHOICES = [
        ('video', 'Video'),
        ('image', 'Image'),
        ('presentation', 'Presentation'),
        ('document', 'Document'),
    ]
    
    design = models.ForeignKey(CanvaDesign, on_delete=models.CASCADE, null=True, blank=True)
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES)
    content_type = models.CharField(max_length=50, choices=CONTENT_TYPE_CHOICES)
    
    # Original content (binary file)
    content_file = models.BinaryField(null=True, blank=True)
    content_file_name = models.CharField(max_length=255, null=True, blank=True)
    content_file_type = models.CharField(max_length=50, null=True, blank=True)
    
    # Posted content info
    post_id = models.CharField(max_length=255, null=True, blank=True)  # Platform's post ID
    post_url = models.URLField(null=True, blank=True)  # Direct URL to the post
    
    # Canva link (if posted from Canva)
    canva_link = models.URLField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=50, default='pending')  # pending, posted, failed
    error_message = models.TextField(null=True, blank=True)
    
    # Metadata
    raw_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.get_platform_display()} - {self.content_type}"