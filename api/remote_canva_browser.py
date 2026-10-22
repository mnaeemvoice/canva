"""Selenium-backed remote Canva browser for the staff dashboard.

All WebDriver calls run on one worker thread. Canva is controlled through its
normal website UI; this module does not call Canva's API.
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
    "CANVA_SELENIUM_STATE_DIR",
    str(Path(settings.BASE_DIR) / "private" / "browser_states"),
))
PROFILE_DIR = Path(os.getenv("CANVA_SELENIUM_PROFILE_DIR", str(STATE_DIR / "chrome-profile")))
PLAYWRIGHT_STATE_FILE = STATE_DIR / "canva-storage-state.json"
CANVA_URL = "https://www.canva.com/"
VIEWPORT = {"width": 1440, "height": 900}
ALLOWED_KEYS = {
    "Enter": "ENTER", "Tab": "TAB", "Escape": "ESC", "Backspace": "BACKSPACE",
    "Delete": "DELETE", "ArrowUp": "ARROW_UP", "ArrowDown": "ARROW_DOWN",
    "ArrowLeft": "ARROW_LEFT", "ArrowRight": "ARROW_RIGHT", "Home": "HOME",
    "End": "END", "Space": "SPACE",
}


class CanvaBrowserWorker:
    """Own a single Selenium WebDriver and serialize browser actions."""

    def __init__(self):
        self.commands = queue.Queue()
        self.thread = threading.Thread(target=self._run, name="canva-selenium-worker", daemon=True)
        self.thread.start()

    def call(self, command, owner_id=None, **payload):
        future = Future()
        self.commands.put((future, command, owner_id, payload))
        return future.result(timeout=90)

    def _run(self):
        driver = None
        playwright = None
        pw_browser = None
        pw_context = None
        pw_page = None
        playwright_error = ""
        owner_id = None
        last_error = ""
        while True:
            future, command, caller_id, payload = self.commands.get()
            try:
                if command == "start":
                    if driver:
                        if owner_id != caller_id:
                            raise PermissionError("Remote browser is owned by another staff user.")
                    else:
                        from selenium import webdriver
                        from selenium.webdriver.chrome.options import Options
                        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                        try:
                            os.chmod(STATE_DIR, 0o700)
                            os.chmod(PROFILE_DIR, 0o700)
                        except OSError:
                            pass
                        options = Options()
                        options.add_argument(f"--user-data-dir={PROFILE_DIR.resolve()}")
                        options.add_argument(f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}")
                        options.add_argument("--disable-notifications")
                        options.add_argument("--no-first-run")
                        options.add_argument("--no-default-browser-check")
                        headless = os.getenv("CANVA_HEADLESS", "0").strip().lower() in {"1", "true", "yes"}
                        if headless:
                            options.add_argument("--headless=new")
                        driver = webdriver.Chrome(options=options)
                        driver.set_window_size(VIEWPORT["width"], VIEWPORT["height"])
                        owner_id = caller_id
                        driver.get(CANVA_URL)
                        # Attach Playwright to the SAME Chrome started by Selenium.
                        # Selenium remains the visible/manual control layer; Playwright
                        # supplies DOM-aware inspection and storage-state persistence.
                        try:
                            from playwright.sync_api import sync_playwright
                            playwright = sync_playwright().start()
                            debugger_address = driver.capabilities.get("goog:chromeOptions", {}).get("debuggerAddress")
                            if not debugger_address:
                                raise RuntimeError("ChromeDriver did not expose a CDP debugger address.")
                            pw_browser = playwright.chromium.connect_over_cdp("http://" + debugger_address)
                            pw_context = pw_browser.contexts[0] if pw_browser.contexts else None
                            pw_page = pw_context.pages[0] if pw_context and pw_context.pages else None
                            if pw_page is None:
                                raise RuntimeError("Playwright attached, but no Canva tab was found.")
                            playwright_error = ""
                        except Exception as exc:
                            playwright_error = f"{type(exc).__name__}: {exc}"[:300]
                            if playwright:
                                try:
                                    playwright.stop()
                                except Exception:
                                    pass
                            playwright = pw_browser = pw_context = pw_page = None
                    last_error = ""
                    result = self._status(driver, last_error)
                    result["playwright_attached"] = pw_page is not None
                    result["playwright_error"] = playwright_error
                elif command == "status":
                    if driver and owner_id != caller_id:
                        raise PermissionError("Remote browser is owned by another staff user.")
                    result = self._status(driver, last_error)
                    result["playwright_attached"] = pw_page is not None
                    result["playwright_error"] = playwright_error
                elif command == "screenshot":
                    self._check_owner(driver, owner_id, caller_id)
                    image = driver.get_screenshot_as_png()
                    result = {
                        "success": True,
                        "image": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
                        "url": driver.current_url,
                        "title": driver.title,
                        "playwright_attached": pw_page is not None,
                        "playwright_error": playwright_error,
                    }
                elif command == "input":
                    self._check_owner(driver, owner_id, caller_id)
                    kind = str(payload.get("action", ""))
                    if kind == "click":
                        x, y = self._point(payload.get("x"), payload.get("y"))
                        self._click_at(driver, x, y)
                    elif kind == "drag":
                        from selenium.webdriver import ActionChains
                        x1, y1 = self._point(payload.get("x1"), payload.get("y1"))
                        x2, y2 = self._point(payload.get("x2"), payload.get("y2"))
                        target, ox, oy = self._target_offset(driver, x1, y1)
                        ActionChains(driver).move_to_element_with_offset(target, ox, oy).click_and_hold().move_by_offset(
                            x2 - x1, y2 - y1
                        ).release().perform()
                    elif kind == "wheel":
                        dx = max(-1000, min(1000, float(payload.get("delta_x", 0))))
                        dy = max(-1000, min(1000, float(payload.get("delta_y", 0))))
                        driver.execute_script("window.scrollBy(arguments[0], arguments[1]);", dx, dy)
                    elif kind == "type":
                        from selenium.webdriver.common.keys import Keys
                        text = str(payload.get("text", ""))[:2000]
                        driver.switch_to.active_element.send_keys(text)
                    elif kind == "key":
                        from selenium.webdriver.common.keys import Keys
                        key = str(payload.get("key", ""))
                        if key not in ALLOWED_KEYS:
                            raise ValueError("Key not allowed.")
                        driver.switch_to.active_element.send_keys(getattr(Keys, ALLOWED_KEYS[key]))
                    elif kind == "navigate":
                        parsed = urlparse(str(payload.get("url", "")))
                        if parsed.scheme != "https" or parsed.hostname not in {"canva.com", "www.canva.com"}:
                            raise ValueError("Only https://www.canva.com pages are allowed.")
                        driver.get(parsed.geturl())
                    elif kind == "save_session":
                        # Keep Chrome's profile and export Playwright state for other workflows.
                        session_saved = False
                        if pw_context is not None:
                            STATE_DIR.mkdir(parents=True, exist_ok=True)
                            pw_context.storage_state(path=str(PLAYWRIGHT_STATE_FILE))
                            try:
                                os.chmod(STATE_DIR, 0o700)
                                os.chmod(PLAYWRIGHT_STATE_FILE, 0o600)
                            except OSError:
                                pass
                            session_saved = True
                        result = {
                            "success": True,
                            "session_saved": True,
                            "playwright_state_saved": session_saved,
                            "playwright_attached": pw_page is not None,
                            "playwright_error": playwright_error,
                        }
                    elif kind == "stop":
                        if playwright:
                            try:
                                playwright.stop()
                            except Exception:
                                pass
                        playwright = pw_browser = pw_context = pw_page = None
                        driver.quit()
                        driver = None
                        owner_id = None
                        result = {"success": True, "running": False}
                    else:
                        raise ValueError("Unknown action.")
                    last_error = ""
                    if kind not in {"stop", "save_session"}:
                        result = self._status(driver, last_error)
                        result["playwright_attached"] = pw_page is not None
                        result["playwright_error"] = playwright_error
                    elif kind == "save_session":
                        result.update(self._status(driver, last_error))
                else:
                    raise ValueError("Unknown worker command.")
                future.set_result(result)
            except PermissionError as exc:
                future.set_result({"success": False, "error": str(exc), "status": 403})
            except ValueError as exc:
                future.set_result({"success": False, "error": str(exc), "status": 400})
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"[:400]
                future.set_result({"success": False, "error": last_error, "status": 502})

    @staticmethod
    def _point(x, y):
        x, y = float(x), float(y)
        if not (0 <= x <= VIEWPORT["width"] and 0 <= y <= VIEWPORT["height"]):
            raise ValueError("Browser coordinates are out of bounds.")
        return x, y

    @staticmethod
    def _target_offset(driver, x, y):
        from selenium.webdriver.common.by import By
        target = driver.execute_script("return document.elementFromPoint(arguments[0], arguments[1]);", x, y)
        if target is None:
            target = driver.find_element(By.TAG_NAME, "body")
        rect = driver.execute_script(
            "const r=arguments[0].getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height};",
            target,
        )
        return target, x - rect["left"] - rect["width"] / 2, y - rect["top"] - rect["height"] / 2

    @classmethod
    def _click_at(cls, driver, x, y):
        from selenium.webdriver import ActionChains
        target, ox, oy = cls._target_offset(driver, x, y)
        ActionChains(driver).move_to_element_with_offset(target, ox, oy).click().perform()

    @staticmethod
    def _check_owner(driver, owner_id, caller_id):
        if driver and owner_id != caller_id:
            raise PermissionError("Remote browser is owned by another staff user.")
        if driver is None:
            raise ValueError("Start the Canva browser first.")

    @staticmethod
    def _status(driver, error):
        running = driver is not None
        try:
            title = driver.title if running else ""
            url = driver.current_url if running else ""
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
