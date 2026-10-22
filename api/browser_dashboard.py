from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import CanvaDesign, PostedContent, SocialMediaConnection
from .browser_automation import STATE_FILE, _playwright_available


@staff_member_required
def browser_automation_dashboard(request):
    designs = CanvaDesign.objects.order_by("-last_modified", "-created_at")[:100]
    connected = {
        connection.platform: connection
        for connection in SocialMediaConnection.objects.filter(connected=True)
    }
    platform_options = list(SocialMediaConnection.PLATFORM_CHOICES)
    platform_rows = [
        {
            "key": key,
            "label": label,
            "connected": key in connected,
            "username": connected[key].username if key in connected else "",
        }
        for key, label in platform_options
    ]
    return render(request, "browser_automation/dashboard.html", {
        "designs": designs,
        "state_saved": STATE_FILE.is_file(),
        "playwright_installed": _playwright_available(),
        "connections": connected,
        "platform_options": platform_options,
        "platform_rows": platform_rows,
        "posted_content": PostedContent.objects.order_by("-created_at")[:12],
    })
