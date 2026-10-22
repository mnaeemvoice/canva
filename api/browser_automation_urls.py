from django.urls import path
from .browser_automation import browser_automation_status, browser_sync_canva_designs

urlpatterns = [
    path("status/", browser_automation_status, name="browser-automation-status"),
    path("canva/sync/", browser_sync_canva_designs, name="browser-canva-sync"),
]
