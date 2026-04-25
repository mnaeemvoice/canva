from django.urls import path
from .views import (
    canva_login,
    canva_callback,
    canva_profile,
    canva_designs,
    canva_webhook,
    canva_dashboard,
    list_saved_canva_designs,
    open_canva,
    register_webhook,   # 🔥 ADD
    canva_monitor       # 🔥 ADD
)

urlpatterns = [
    path('canva/login/', canva_login),
    path('canva/callback/', canva_callback),

    path("canva/open/", open_canva),

    path('canva/profile/', canva_profile),
    path('canva/designs/', canva_designs),

    path('canva/webhook/', canva_webhook),

    path('canva/dashboard/', canva_dashboard),
    path('canva/saved-designs/', list_saved_canva_designs),

    # 🔥 NEW URLS
    path('canva/register-webhook/', register_webhook),
    path('canva/monitor/', canva_monitor),
]