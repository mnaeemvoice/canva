"""Save an authenticated Canva browser session for sync and MP4 export.

Run: python manage.py canva_browser_login
Sign in to your own Canva account manually. The storage-state file contains
session credentials and must never be committed or shared.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.browser_automation import CANVA_DESIGNS_URL, STATE_FILE


class Command(BaseCommand):
    help = "Open Chromium for manual Canva sign-in and save the private browser session."

    def handle(self, *args, **options):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CommandError(
                "Playwright is missing. Install it with "
                "./venv/bin/python -m pip install playwright"
            ) from exc

        state_path = Path(STATE_FILE)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            state_path.parent.chmod(0o700)
        except OSError:
            pass

        self.stdout.write(self.style.WARNING(
            "A browser will open. Sign in to Canva manually and complete any verification. "
            "Do not share or commit the saved browser session."
        ))

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(
                    CANVA_DESIGNS_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                input(
                    "\nAfter you finish signing in and can see your Canva designs, "
                    "return here and press ENTER to save the session..."
                )
                if "canva.com" not in page.url.lower() or any(
                    marker in page.url.lower() for marker in ("/login", "/signup")
                ):
                    raise CommandError(
                        "Canva login was not detected. Sign in and open Your designs before saving."
                    )
                context.storage_state(path=str(state_path))
                try:
                    state_path.chmod(0o600)
                except OSError:
                    pass
                self.stdout.write(self.style.SUCCESS(
                    f"Canva session saved privately to {state_path}"
                ))
            finally:
                context.close()
                browser.close()
