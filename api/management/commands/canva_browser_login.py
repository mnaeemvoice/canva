"""Open Canva in a visible browser, let the owner sign in, then save state.

Run on a machine that can display the browser, or through an authorized VNC
session: python manage.py canva_browser_login
"""
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Log into Canva manually once and save a Playwright browser state file."

    def handle(self, *args, **options):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CommandError(
                "Playwright is missing. Install it with pip install playwright "
                "and run python -m playwright install chromium."
            ) from exc

        state_dir = Path(os.getenv(
            "CANVA_PLAYWRIGHT_STATE_DIR",
            str(Path(settings.BASE_DIR) / "private" / "browser_states"),
        ))
        state_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(state_dir, 0o700)
        except OSError:
            pass
        state_file = state_dir / "canva-storage-state.json"

        self.stdout.write(self.style.WARNING(
            "A visible Chromium window will open. Sign into your own Canva account. "
            "Complete verification yourself; do not share the session file."
        ))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto("https://www.canva.com/login", wait_until="domcontentloaded")
            self.stdout.write("After signing in, open Your designs. Return here and press Enter.")
            input()
            if "canva.com" not in page.url or "/login" in page.url.lower() or "/signup" in page.url.lower():
                browser.close()
                raise CommandError("Canva login was not detected.")
            context.storage_state(path=str(state_file))
            try:
                os.chmod(state_file, 0o600)
            except OSError:
                pass
            browser.close()

        self.stdout.write(self.style.SUCCESS(
            "Playwright state saved to " + str(state_file) + ". Keep it private and outside Git."
        ))
