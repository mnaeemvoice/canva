"""Canva browser automation endpoints.

The account owner performs first login with the management command:
python manage.py canva_browser_login. Browser state is stored outside Git.
"""
import os
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect

from .models import CanvaDesign
from .remote_canva_browser import _get_worker

STATE_DIR = Path(os.getenv(
    "CANVA_PLAYWRIGHT_STATE_DIR",
    str(Path(settings.BASE_DIR) / "private" / "browser_states"),
))
STATE_FILE = STATE_DIR / "canva-storage-state.json"
CANVA_DESIGNS_URL = "https://www.canva.com/your-designs"


def _playwright_available():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


@staff_member_required
@require_GET
def browser_automation_status(request):
    """Report setup status without exposing session data."""
    return JsonResponse({
        "success": True,
        "engine": "playwright",
        "state_saved": STATE_FILE.is_file(),
        "playwright_installed": _playwright_available(),
        "login_command": "python manage.py canva_browser_login",
        "sync_endpoint": "/api/browser/canva/sync/",
        "note": "Never upload the storage-state file to GitHub or share it.",
    })


def _extract_designs(page):
    """Extract design links from Canva's visible Your designs page."""
    return page.locator('a[href*="/design/"]').evaluate_all(r"""anchors => {
      const found = new Map();
      for (const a of anchors) {
        const href = a.href || "";
        const match = href.match(/\/design\/([A-Za-z0-9_-]+)(?:\/|\?|$)/);
        if (!match) continue;
        const id = match[1];
        const title = (a.getAttribute("aria-label") || a.innerText ||
          a.querySelector("img")?.alt || "").trim().slice(0, 255);
        if (!found.has(id)) found.set(id, {id, title, edit_url: href});
      }
      return Array.from(found.values());
    }""")


@staff_member_required
@csrf_protect
@require_POST
def browser_sync_canva_designs(request):
    """Sync design metadata from the same live Selenium browser shown in the dashboard.

    This avoids starting a separate headless browser with a potentially stale
    storage-state file. The user completes Canva login and any verification
    manually in the remote browser first.
    """
    try:
        result = _get_worker().call(
            "input",
            request.user.pk,
            action="sync_designs",
        )
        status = result.pop("status", 200)
        return JsonResponse(result, status=status)
    except TimeoutError:
        return JsonResponse({
            "success": False,
            "error": "Canva sync timed out.",
            "next_step": "Wait for Canva's Your designs page to finish loading and retry.",
        }, status=504)
    except Exception as exc:
        return JsonResponse({
            "success": False,
            "error": "Canva browser sync failed.",
            "detail": str(exc)[:400],
            "next_step": "Open Canva in Selenium, finish any verification manually, open Your designs, and retry.",
        }, status=502)
