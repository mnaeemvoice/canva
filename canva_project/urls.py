from django.contrib import admin
from django.urls import path, include
from api.views import home
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # HOME
    path('', home),

    # API ROUTES
    path('api/', include('api.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)