from django.contrib import admin
from django.urls import path, include
from api.django_home import django_home
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', django_home, name='home'),
    path('api/', include('api.urls')),
    path('api/browser/', include('api.browser_automation_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
