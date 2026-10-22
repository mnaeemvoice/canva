"""Continuously discover new Canva designs using a saved Playwright session.

Run as a separate supervised worker:
python manage.py canva_browser_watch --interval 60
"""
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.browser_automation import STATE_FILE, _extract_designs
from api.models import CanvaDesign


class Command(BaseCommand):
    help = "Poll Canva Your designs in the background and save new design metadata."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, **options):
        interval = max(20, options["interval"])
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CommandError("Install Playwright and run python -m playwright install chromium.") from exc

        if not STATE_FILE.is_file():
            raise CommandError("Canva session is missing. Run python manage.py canva_browser_login first.")

        self.stdout.write(self.style.SUCCESS(
            "Canva watcher started. It syncs metadata; MP4 export remains available in the Django dashboard."
        ))
        while True:
            browser = None
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(storage_state=str(STATE_FILE))
                    page = context.new_page()
                    page.goto("https://www.canva.com/your-designs", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2500)
                    if "login" in page.url.lower() or "signup" in page.url.lower():
                        raise RuntimeError("Canva session expired; rerun canva_browser_login.")
                    items = _extract_designs(page)
                    created = 0
                    for item in items:
                        design_id = item.get("id")
                        if not design_id:
                            continue
                        _, is_new = CanvaDesign.objects.update_or_create(
                            design_id=design_id,
                            defaults={
                                "title": item.get("title") or "Canva design " + design_id,
                                "category": "unknown",
                                "asset_type": "unknown",
                                "status": "browser_discovered",
                                "raw_data": {
                                    "source": "playwright_background_watcher",
                                    "edit_url": item.get("edit_url"),
                                    "last_seen": timezone.now().isoformat(),
                                },
                                "last_modified": timezone.now(),
                            },
                        )
                        created += int(is_new)
                    self.stdout.write(
                        f"{timezone.now().isoformat()}: found {len(items)} design links; {created} new records."
                    )
                    context.close()
                    browser.close()
            except KeyboardInterrupt:
                if browser:
                    browser.close()
                self.stdout.write("Canva watcher stopped.")
                break
            except Exception as exc:
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                self.stderr.write(self.style.ERROR("Canva watcher error: " + str(exc)[:300]))
            time.sleep(interval)
