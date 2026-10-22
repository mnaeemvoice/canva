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


@staff_member_required
@csrf_protect
@require_POST
def browser_export_design_mp4(request, design_id):
    """Attempt a true MP4 download from Canva's editor; never substitute a thumbnail."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,255}", design_id or ""):
        return JsonResponse({"success": False, "error": "Invalid design ID."}, status=400)
    if not STATE_FILE.is_file():
        return JsonResponse({"success": False, "error": "Canva session missing; run canva_browser_login first."}, status=409)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return JsonResponse({"success": False, "error": "Playwright is not installed."}, status=503)

    design = CanvaDesign.objects.filter(design_id=design_id).first()
    if not design:
        return JsonResponse({"success": False, "error": "Sync designs before exporting."}, status=404)

    target_dir = Path(settings.MEDIA_ROOT) / "browser_exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (design_id + ".mp4")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(STATE_FILE), accept_downloads=True)
            page = context.new_page()
            page.goto("https://www.canva.com/design/" + design_id + "/edit",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            if "login" in page.url.lower():
                browser.close()
                return JsonResponse({"success": False, "error": "Session expired; sign in again."}, status=409)

            page.get_by_role("button", name=re.compile("share", re.I)).first.click(timeout=20000)
            page.get_by_text(re.compile(r"^Download$", re.I)).last.click(timeout=20000)
            page.get_by_text(re.compile(r"MP4 Video", re.I)).first.click(timeout=15000)
            page.wait_for_timeout(500)
            with page.expect_download(timeout=180000) as download_info:
                page.get_by_role("button", name=re.compile(r"^Download$", re.I)).last.click(timeout=20000)
            download_info.value.save_as(str(target))
            context.close()
            browser.close()

        if not target.is_file() or target.stat().st_size < 1024:
            return JsonResponse({"success": False, "error": "Canva did not produce a valid MP4 file."}, status=502)

        relative = "browser_exports/" + target.name
        design.asset_url = request.build_absolute_uri(settings.MEDIA_URL + relative)
        design.asset_type = "video"
        design.category = "animation"
        design.status = "browser_exported"
        design.binary_file_name = target.name
        design.binary_file_type = "video/mp4"
        design.binary_file_size = target.stat().st_size
        design.last_modified = timezone.now()
        design.save(update_fields=[
            "asset_url", "asset_type", "category", "status", "binary_file_name",
            "binary_file_type", "binary_file_size", "last_modified",
        ])
        return JsonResponse({
            "success": True, "design_id": design_id, "file": target.name,
            "size_bytes": target.stat().st_size, "asset_url": design.asset_url,
        })
    except Exception as exc:
        return JsonResponse({
            "success": False,
            "error": "Canva MP4 export failed. The editor UI may have changed or this design may not support video export.",
            "detail": str(exc)[:500],
        }, status=502)
