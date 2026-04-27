from django.contrib import admin
from django.urls import path, include
from api.views import home
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # HOME
    path('', home, name='home'),

    # API ROUTES
    path('api/', include('api.urls')),
]

# ======================
# MEDIA FILES (DEV ONLY SAFE)
# ======================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)