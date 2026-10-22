"""Staff-only remote Canva browser controls for the Django workspace.

This is screenshot-and-input remoting, not an iframe of Canva. The browser is
owned by the Django worker, so deploy with a single worker or move this manager
into a dedicated browser-worker service before scaling.
"""
import base64
import os
import threading
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

_lock = threading.RLock()
_browser = None
_context = None
_page = None
_playwright = None
_last_error = None
_owner_id = None
STATE_DIR = Path(os.getenv(
    "CANVA_PLAYWRIGHT_STATE_DIR",
    str(Path(settings.BASE_DIR) / "private" / "browser_states"),
))
STATE_FILE = STATE_DIR / "canva-storage-state.json"
CANVA_URL = "https://www.canva.com/"


def _status():
    return {
        "running": bool(_browser and _browser.is_connected() and _page),
        "url": _page.url if _page else "",
        "title": _page.title() if _page else "",
        "error": _last_error or "",
    }


@staff_member_required
@csrf_protect
@require_POST
def remote_canva_start(request):
    """Start one browser in this Django worker; user completes login manually."""
    global _browser, _context, _page, _playwright, _last_error, _owner_id
    with _lock:
        if _browser and _browser.is_connected() and _page:
            if _owner_id != request.user.pk:
                return JsonResponse({"success": False, "error": "Remote browser is owned by another staff user."}, status=409)
            return JsonResponse({"success": True, **_status()})
        try:
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=True)
            if STATE_FILE.is_file():
                _context = _browser.new_context(
                    storage_state=str(STATE_FILE), accept_downloads=True,
                    viewport={"width": 1440, "height": 900},
                )
            else:
                _context = _browser.new_context(
                    accept_downloads=True, viewport={"width": 1440, "height": 900},
                )
            _page = _context.new_page()
            _owner_id = request.user.pk
            _page.goto(CANVA_URL, wait_until="domcontentloaded", timeout=60000)
            _last_error = None
            return JsonResponse({"success": True, **_status()})
        except Exception as exc:
            _last_error = str(exc)[:400]
            _cleanup()
            return JsonResponse({
                "success": False, "error": "Could not start the remote Canva browser.",
                "detail": _last_error,
                "hint": "Install Playwright Chromium on the server and check outbound access to canva.com.",
            }, status=503)


def _cleanup():
    global _browser, _context, _page, _playwright, _owner_id
    try:
        if _context:
            _context.close()
    except Exception:
        pass
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _browser = _context = _page = _playwright = None
    _owner_id = None


@staff_member_required
@require_GET
def remote_canva_status(request):
    with _lock:
        if _browser and _owner_id != request.user.pk:
            return JsonResponse({"success": False, "error": "Remote browser is owned by another staff user."}, status=403)
        return JsonResponse({"success": True, **_status()})


@staff_member_required
@require_GET
def remote_canva_screenshot(request):
    """Return a screenshot for the staff-only remote workspace."""
    with _lock:
        if _browser and _owner_id != request.user.pk:
            return JsonResponse({"success": False, "error": "Remote browser is owned by another staff user."}, status=403)
        if not (_browser and _browser.is_connected() and _page):
            return JsonResponse({"success": False, "error": "Start the Canva browser first."}, status=409)
        try:
            png = _page.screenshot(type="jpeg", quality=65)
            return JsonResponse({
                "success": True,
                "image": "data:image/jpeg;base64," + base64.b64encode(png).decode("ascii"),
                "url": _page.url,
                "title": _page.title(),
            })
        except Exception as exc:
            return JsonResponse({"success": False, "error": str(exc)[:300]}, status=502)


@staff_member_required
@csrf_protect
@require_POST
def remote_canva_input(request):
    """Relay basic mouse/keyboard input into the authenticated browser."""
    import json
    global _last_error
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Invalid JSON."}, status=400)
    action = payload.get("action")
    with _lock:
        if _browser and _owner_id != request.user.pk:
            return JsonResponse({"success": False, "error": "Remote browser is owned by another staff user."}, status=403)
        if not (_browser and _browser.is_connected() and _page):
            return JsonResponse({"success": False, "error": "Start the Canva browser first."}, status=409)
        try:
            if action == "click":
                x, y = float(payload.get("x", -1)), float(payload.get("y", -1))
                if not (0 <= x <= 1440 and 0 <= y <= 900):
                    return JsonResponse({"success": False, "error": "Click coordinates out of bounds."}, status=400)
                _page.mouse.click(x, y)
            elif action == "drag":
                coords = [float(payload.get(k, -1)) for k in ("x1", "y1", "x2", "y2")]
                x1, y1, x2, y2 = coords
                if not all(0 <= v <= limit for v, limit in zip(coords, (1440, 900, 1440, 900))):
                    return JsonResponse({"success": False, "error": "Drag coordinates out of bounds."}, status=400)
                _page.mouse.move(x1, y1)
                _page.mouse.down()
                _page.mouse.move(x2, y2, steps=12)
                _page.mouse.up()
            elif action == "wheel":
                dx = max(-1000, min(1000, float(payload.get("delta_x", 0))))
                dy = max(-1000, min(1000, float(payload.get("delta_y", 0))))
                _page.mouse.wheel(dx, dy)
            elif action == "type":
                value = str(payload.get("text", ""))[:2000]
                _page.keyboard.insert_text(value)
            elif action == "key":
                key = str(payload.get("key", ""))
                allowed = {"Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown",
                           "ArrowLeft", "ArrowRight", "Home", "End", "Space"}
                if key not in allowed:
                    return JsonResponse({"success": False, "error": "Key not allowed."}, status=400)
                _page.keyboard.press(key)
            elif action == "navigate":
                url = str(payload.get("url", ""))
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.scheme != "https" or parsed.hostname not in {"canva.com", "www.canva.com"}:
                    return JsonResponse({"success": False, "error": "Only https://www.canva.com pages are allowed."}, status=400)
                _page.goto(url, wait_until="domcontentloaded", timeout=60000)
            elif action == "save_session":
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(STATE_DIR, 0o700)
                except OSError:
                    pass
                _context.storage_state(path=str(STATE_FILE))
                try:
                    os.chmod(STATE_FILE, 0o600)
                except OSError:
                    pass
            elif action == "stop":
                _cleanup()
                return JsonResponse({"success": True, "running": False})
            else:
                return JsonResponse({"success": False, "error": "Unknown action."}, status=400)
            _last_error = None
            return JsonResponse({"success": True, **_status()})
        except Exception as exc:
            _last_error = str(exc)[:400]
            return JsonResponse({"success": False, "error": _last_error}, status=502)
