from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from .models import CanvaDesign
from .browser_automation import STATE_FILE, _playwright_available


@staff_member_required
def browser_automation_dashboard(request):
    return render(request, "browser_automation/dashboard.html", {
        "designs": CanvaDesign.objects.order_by("-last_modified", "-created_at")[:100],
        "state_saved": STATE_FILE.is_file(),
        "playwright_installed": _playwright_available(),
    })
