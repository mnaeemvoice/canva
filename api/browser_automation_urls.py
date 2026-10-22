from django.urls import path
from .browser_automation import browser_automation_status, browser_sync_canva_designs
from .browser_dashboard import browser_automation_dashboard
from .browser_export import browser_export_design_mp4

urlpatterns = [
    path("", browser_automation_dashboard, name="browser-automation-dashboard"),
    path("status/", browser_automation_status, name="browser-automation-status"),
    path("canva/sync/", browser_sync_canva_designs, name="browser-canva-sync"),
    path("canva/export/<str:design_id>/", browser_export_design_mp4, name="browser-canva-export"),
]
