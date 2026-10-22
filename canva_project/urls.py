from django.contrib import admin
from django.urls import path, include
from api.django_home import django_home
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Send staff users to the Django-native Canva workspace.
    path("", django_home, name="home"),

    # IMPORTANT: put this before the general /api/ include.
    # api.urls also defines "browser/", so this order ensures
    # /api/browser/ resolves to the dashboard instead of the status JSON endpoint.
    path("api/browser/", include("api.browser_automation_urls")),

    # Existing Canva and social API endpoints.
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
