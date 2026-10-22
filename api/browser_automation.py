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
    """Reuse the saved session to discover designs and persist metadata."""
    if not STATE_FILE.is_file():
        return JsonResponse({
            "success": False,
            "error": "Canva browser session is not configured.",
            "next_step": "Run python manage.py canva_browser_login on a machine with a visible browser and sign into Canva.",
        }, status=409)
    if not _playwright_available():
        return JsonResponse({
            "success": False,
            "error": "Playwright is not installed.",
            "next_step": "Install requirements and run python -m playwright install chromium.",
        }, status=503)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(STATE_FILE), accept_downloads=True)
            page = context.new_page()
            page.goto(CANVA_DESIGNS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)

            current_url = page.url
            if "login" in current_url.lower() or "signup" in current_url.lower():
                browser.close()
                return JsonResponse({
                    "success": False,
                    "session_expired": True,
                    "error": "Canva requires login again.",
                    "next_step": "Run python manage.py canva_browser_login and sign in again.",
                }, status=409)

            designs = _extract_designs(page)
            created = updated = 0
            for item in designs:
                design_id = item.get("id")
                if not design_id:
                    continue
                title = item.get("title") or "Canva design " + design_id
                obj, was_created = CanvaDesign.objects.update_or_create(
                    design_id=design_id,
                    defaults={
                        "title": title,
                        "category": "unknown",
                        "asset_type": "unknown",
                        "status": "browser_discovered",
                        "raw_data": {
                            "source": "playwright_browser",
                            "edit_url": item.get("edit_url"),
                            "discovered_at": timezone.now().isoformat(),
                            "export_note": "Metadata sync is complete; use the dashboard MP4 export action to retrieve the full file.",
                        },
                        "last_modified": timezone.now(),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            context.close()
            browser.close()
        return JsonResponse({
            "success": True,
            "found": len(designs),
            "created": created,
            "updated": updated,
            "designs": designs[:100],
            "message": "Design metadata synced. Use the dashboard Export MP4 action to retrieve a complete video file where Canva offers MP4 export.",
        })
    except Exception as exc:
        return JsonResponse({
            "success": False,
            "error": "Canva browser sync failed.",
            "detail": str(exc)[:500],
            "next_step": "Check the saved session and whether Canva's design page loaded successfully.",
        }, status=502)
