from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import CanvaDesign, PostedContent, SocialMediaConnection


@staff_member_required
def browser_automation_dashboard(request):
    designs = CanvaDesign.objects.order_by("-last_modified", "-created_at")[:100]
    connections = {
        connection.platform: connection
        for connection in SocialMediaConnection.objects.filter(connected=True)
    }
    posted_content = PostedContent.objects.order_by("-created_at")[:12]
    return render(request, "browser_automation/dashboard.html", {
        "designs": designs,
        "state_saved": __import__("api.browser_automation", fromlist=["STATE_FILE"]).STATE_FILE.is_file(),
        "playwright_installed": __import__("api.browser_automation", fromlist=["_playwright_available"])._playwright_available(),
        "connections": connections,
        "posted_content": posted_content,
    })
