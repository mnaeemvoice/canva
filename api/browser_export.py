"""Export real Canva files through the Canva website UI using Playwright.

No Canva API is used here. Exported files are saved under MEDIA_ROOT/browser_exports.
The visible Selenium browser is not navigated; this endpoint uses a separate
headless Playwright context built from the user's privately saved session.
"""
import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .models import CanvaDesign

STATE_FILE = Path(os.getenv(
    "CANVA_PLAYWRIGHT_STATE_DIR",
    str(Path(settings.BASE_DIR) / "private" / "browser_states"),
)) / "canva-storage-state.json"

EXPORT_FORMATS = {
    "mp4": {"label": "MP4 Video", "ext": "mp4", "mime": "video/mp4", "type": "video", "category": "animation"},
    "png": {"label": "PNG", "ext": "png", "mime": "image/png", "type": "image", "category": "image"},
    "jpg": {"label": "JPG", "ext": "jpg", "mime": "image/jpeg", "type": "image", "category": "image"},
    "pdf": {"label": "PDF Standard", "ext": "pdf", "mime": "application/pdf", "type": "pdf", "category": "document"},
    "pdf_print": {"label": "PDF Print", "ext": "pdf", "mime": "application/pdf", "type": "pdf", "category": "document"},
    "gif": {"label": "GIF", "ext": "gif", "mime": "image/gif", "type": "animation", "category": "animation"},
    "svg": {"label": "SVG", "ext": "svg", "mime": "image/svg+xml", "type": "image", "category": "image"},
}


@staff_member_required
@csrf_protect
@require_POST
def browser_export_design(request, design_id, export_format="mp4"):
    """Export one actual file through Canva's Download UI, never a screenshot."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,255}", design_id or ""):
        return JsonResponse({"success": False, "error": "Invalid design ID."}, status=400)
    fmt = (export_format or request.POST.get("format") or "mp4").lower().strip()
    spec = EXPORT_FORMATS.get(fmt)
    if not spec:
        return JsonResponse({
            "success": False,
            "error": "Unsupported export format.",
            "supported_formats": list(EXPORT_FORMATS),
        }, status=400)
    if not STATE_FILE.is_file():
        return JsonResponse({
            "success": False,
            "error": "Canva session missing. Open Canva in Selenium and click Save Canva session first.",
        }, status=409)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return JsonResponse({"success": False, "error": "Playwright is not installed."}, status=503)

    design = CanvaDesign.objects.filter(design_id=design_id).first()
    if not design:
        return JsonResponse({"success": False, "error": "Sync designs before exporting."}, status=404)

    target_dir = Path(settings.MEDIA_ROOT) / "browser_exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{design_id}_{fmt}.{spec['ext']}"
    browser = context = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(STATE_FILE), accept_downloads=True)
            page = context.new_page()
            page.goto(
                "https://www.canva.com/design/" + design_id + "/edit",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_timeout(2500)
            if "login" in page.url.lower() or "signup" in page.url.lower():
                return JsonResponse({
                    "success": False,
                    "error": "Canva session expired. Sign in again in Selenium and save the session.",
                }, status=409)

            # Use Canva's normal Share -> Download UI.
            page.get_by_role("button", name=re.compile("share", re.I)).first.click(timeout=25000)
            page.get_by_text(re.compile(r"^Download$", re.I)).last.click(timeout=25000)
            page.get_by_text(spec["label"], exact=True).last.click(timeout=20000)
            with page.expect_download(timeout=180000) as download_info:
                page.get_by_role("button", name=re.compile(r"^Download$", re.I)).last.click(timeout=25000)
            download_info.value.save_as(str(target))
    except Exception as exc:
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
        return JsonResponse({
            "success": False,
            "error": f"Canva {spec['label']} export failed. This design may not support the format or Canva's UI may have changed.",
            "detail": str(exc)[:500],
            "format": fmt,
        }, status=502)
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    if not target.is_file() or target.stat().st_size == 0:
        return JsonResponse({"success": False, "error": "Canva did not produce a non-empty export file."}, status=502)

    relative = "browser_exports/" + target.name
    asset_url = request.build_absolute_uri(settings.MEDIA_URL + relative)
    raw = design.raw_data if isinstance(design.raw_data, dict) else {}
    exports = raw.get("browser_exports", {})
    if not isinstance(exports, dict):
        exports = {}
    exports[fmt] = {
        "file": target.name,
        "relative_path": relative,
        "url": asset_url,
        "mime_type": spec["mime"],
        "size_bytes": target.stat().st_size,
        "exported_at": timezone.now().isoformat(),
    }
    raw["browser_exports"] = exports
    raw["export_source"] = "canva_website_ui_playwright"
    raw["last_export_format"] = fmt

    # Preserve every export's file on disk and its metadata in raw_data.
    # The legacy single-file fields point to the latest successful export.
    design.asset_url = asset_url
    design.asset_type = spec["type"]
    design.category = spec["category"]
    design.status = "browser_exported"
    design.binary_file = target.read_bytes()
    design.binary_file_name = target.name
    design.binary_file_type = spec["mime"]
    design.binary_file_size = target.stat().st_size
    design.raw_data = raw
    design.last_modified = timezone.now()
    design.save(update_fields=[
        "asset_url", "asset_type", "category", "status", "binary_file",
        "binary_file_name", "binary_file_type", "binary_file_size",
        "raw_data", "last_modified",
    ])
    return JsonResponse({
        "success": True,
        "design_id": design_id,
        "format": fmt,
        "file": target.name,
        "size_bytes": target.stat().st_size,
        "asset_url": asset_url,
        "publish_ready": fmt == "mp4",
        "message": f"Real {spec['label']} export saved from Canva's website UI.",
    })


# Backwards-compatible import name used by earlier URL configurations.
browser_export_design_mp4 = browser_export_design
