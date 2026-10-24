from django.urls import path
from .browser_automation import browser_automation_status, browser_sync_canva_designs
from .browser_dashboard import browser_automation_dashboard
from .browser_export import browser_export_design_mp4
from .remote_canva_browser import (remote_canva_start, remote_canva_status, remote_canva_screenshot, remote_canva_input)

urlpatterns = [
    path("", browser_automation_dashboard, name="browser-automation-dashboard"),
    path("status/", browser_automation_status, name="browser-automation-status"),
    path("canva/sync/", browser_sync_canva_designs, name="browser-canva-sync"),
    path("canva/export/<str:design_id>/", browser_export_design_mp4, name="browser-canva-export"),
    path("remote/start/", remote_canva_start, name="remote-canva-start"),
    path("remote/status/", remote_canva_status, name="remote-canva-status"),
    path("remote/screenshot/", remote_canva_screenshot, name="remote-canva-screenshot"),
    path("remote/input/", remote_canva_input, name="remote-canva-input"),
]
