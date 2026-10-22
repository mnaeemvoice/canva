"""Thread-affine Playwright worker for a staff-only remote Canva workspace.

Playwright's synchronous objects must remain on the thread that created them.
This worker serializes browser actions on one dedicated thread and returns
screenshots to the Django dashboard; this is not a native Canva iframe.
"""
import base64
import json
import os
import queue
import threading
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

STATE_DIR = Path(os.getenv(
    "CANVA_PLAYWRIGHT_STATE_DIR",
    str(Path(settings.BASE_DIR) / "private" / "browser_states"),
))
STATE_FILE = STATE_DIR / "canva-storage-state.json"
CANVA_URL = "https://www.canva.com/"
VIEWPORT = {"width": 1440, "height": 900}


class CanvaBrowserWorker:
    """Own all Playwright objects in one thread and serialize commands."""

    def __init__(self):
        self.commands = queue.Queue()
        self.thread = threading.Thread(target=self._run, name="canva-browser-worker", daemon=True)
        self.thread.start()

    def call(self, command, owner_id=None, **payload):
        future = Future()
        self.commands.put((future, command, owner_id, payload))
        return future.result(timeout=90)

    def _run(self):
        playwright = browser = context = page = None
        owner_id = None
        last_error = ""
        while True:
            future, action, caller_id, payload = self.commands.get()
            try:
                if action == "start":
                    if browser and browser.is_connected() and page:
                        if owner_id != caller_id:
                            raise PermissionError("Remote browser is owned by another staff user.")
                        result = self._status(browser, page, last_error)
                    else:
                        from playwright.sync_api import sync_playwright
                        playwright = sync_playwright().start()
                        headless = os.getenv("CANVA_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}
                        browser = playwright.chromium.launch(headless=headless)
                        context_args = {"accept_downloads": True, "viewport": VIEWPORT}
                        if STATE_FILE.is_file():
                            context_args["storage_state"] = str(STATE_FILE)
                        context = browser.new_context(**context_args)
                        page = context.new_page()
                        owner_id = caller_id
                        page.goto(CANVA_URL, wait_until="domcontentloaded", timeout=60000)
                        last_error = ""
                        result = self._status(browser, page, last_error)
                elif action == "status":
                    if browser and owner_id != caller_id:
                        raise PermissionError("Remote browser is owned by another staff user.")
                    result = self._status(browser, page, last_error)
                elif action == "screenshot":
                    self._check_owner(browser, page, owner_id, caller_id)
                    shot = page.screenshot(type="jpeg", quality=60)
                    result = {"success": True, "image": "data:image/jpeg;base64," + base64.b64encode(shot).decode("ascii"),
                              "url": page.url, "title": page.title()}
                elif action == "input":
                    self._check_owner(browser, page, owner_id, caller_id)
                    kind = payload.get("action")
                    if kind == "click":
                        x, y = float(payload.get("x", -1)), float(payload.get("y", -1))
                        if not (0 <= x <= 1440 and 0 <= y <= 900):
                            raise ValueError("Click coordinates out of bounds.")
                        page.mouse.click(x, y)
                    elif kind == "drag":
                        coords = [float(payload.get(k, -1)) for k in ("x1", "y1", "x2", "y2")]
                        if not all(0 <= v <= limit for v, limit in zip(coords, (1440, 900, 1440, 900))):
                            raise ValueError("Drag coordinates out of bounds.")
                        page.mouse.move(coords[0], coords[1])
                        page.mouse.down()
                        page.mouse.move(coords[2], coords[3], steps=12)
                        page.mouse.up()
                    elif kind == "wheel":
                        dx = max(-1000, min(1000, float(payload.get("delta_x", 0))))
                        dy = max(-1000, min(1000, float(payload.get("delta_y", 0))))
                        page.mouse.wheel(dx, dy)
                    elif kind == "type":
                        page.keyboard.insert_text(str(payload.get("text", ""))[:2000])
                    elif kind == "key":
                        key = str(payload.get("key", ""))
                        allowed = {"Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown",
                                   "ArrowLeft", "ArrowRight", "Home", "End", "Space"}
                        if key not in allowed:
                            raise ValueError("Key not allowed.")
                        page.keyboard.press(key)
                    elif kind == "navigate":
                        parsed = urlparse(str(payload.get("url", "")))
                        if parsed.scheme != "https" or parsed.hostname not in {"canva.com", "www.canva.com"}:
                            raise ValueError("Only https://www.canva.com pages are allowed.")
                        page.goto(parsed.geturl(), wait_until="domcontentloaded", timeout=60000)
                    elif kind == "save_session":
                        STATE_DIR.mkdir(parents=True, exist_ok=True)
                        try:
                            os.chmod(STATE_DIR, 0o700)
                        except OSError:
                            pass
                        context.storage_state(path=str(STATE_FILE))
                        try:
                            os.chmod(STATE_FILE, 0o600)
                        except OSError:
                            pass
                    elif kind == "stop":
                        try:
                            if context:
                                context.close()
                        finally:
                            if browser:
                                browser.close()
                            if playwright:
                                playwright.stop()
                        playwright = browser = context = page = None
                        owner_id = None
                        result = {"success": True, "running": False}
                    else:
                        raise ValueError("Unknown action.")
                    last_error = ""
                    if kind != "stop":
                        result = self._status(browser, page, last_error)
                else:
                    raise ValueError("Unknown worker command.")
                future.set_result(result)
            except PermissionError as exc:
                future.set_result({"success": False, "error": str(exc), "status": 403})
            except ValueError as exc:
                future.set_result({"success": False, "error": str(exc), "status": 400})
            except Exception as exc:
                last_error = str(exc)[:400]
                future.set_result({"success": False, "error": last_error, "status": 502})

    @staticmethod
    def _check_owner(browser, page, owner_id, caller_id):
        if browser and owner_id != caller_id:
            raise PermissionError("Remote browser is owned by another staff user.")
        if not (browser and browser.is_connected() and page):
            raise ValueError("Start the Canva browser first.")

    @staticmethod
    def _status(browser, page, error):
        running = bool(browser and browser.is_connected() and page)
        try:
            title = page.title() if running else ""
            url = page.url if running else ""
        except Exception:
            title, url = "", ""
        return {"success": True, "running": running, "url": url, "title": title, "error": error or ""}


_worker = None
_worker_lock = threading.Lock()


def _get_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.thread.is_alive():
            _worker = CanvaBrowserWorker()
        return _worker


def _call(command, request, **payload):
    # Keep the worker command separate from payload['action'] used for mouse/keyboard input.
    result = _get_worker().call(command, request.user.pk, **payload)
    status = result.pop("status", 200)
    return JsonResponse(result, status=status)


@staff_member_required
@csrf_protect
@require_POST
def remote_canva_start(request):
    return _call("start", request)


@staff_member_required
@require_GET
def remote_canva_status(request):
    return _call("status", request)


@staff_member_required
@require_GET
def remote_canva_screenshot(request):
    return _call("screenshot", request)


@staff_member_required
@csrf_protect
@require_POST
def remote_canva_input(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Invalid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"success": False, "error": "JSON body must be an object."}, status=400)
    return _call("input", request, **payload)
