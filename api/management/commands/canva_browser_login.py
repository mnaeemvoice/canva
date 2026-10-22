"""Open Canva in Selenium's visible Chrome and keep its profile for future sessions.

Run: python manage.py canva_browser_login
Complete login and verification yourself. The Chrome profile contains sensitive
authentication data and must never be committed or shared.
"""
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Open Canva in Chrome for manual sign-in using a persistent Selenium profile."

    def handle(self, *args, **options):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError as exc:
            raise CommandError("Selenium is missing. Install requirements.txt first.") from exc

        state_dir = Path(os.getenv(
            "CANVA_SELENIUM_STATE_DIR",
            str(Path(settings.BASE_DIR) / "private" / "browser_states"),
        ))
        profile_dir = Path(os.getenv("CANVA_SELENIUM_PROFILE_DIR", str(state_dir / "chrome-profile")))
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(state_dir, 0o700)
            os.chmod(profile_dir, 0o700)
        except OSError:
            pass

        options = Options()
        options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
        options.add_argument("--window-size=1440,900")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-first-run")
        if os.getenv("CANVA_HEADLESS", "0").strip().lower() in {"1", "true", "yes"}:
            options.add_argument("--headless=new")

        driver = None
        try:
            self.stdout.write(self.style.WARNING(
                "Chrome will open. Sign into Canva manually and complete any verification yourself. "
                "Do not share or commit the Chrome profile."
            ))
            driver = webdriver.Chrome(options=options)
            driver.get("https://www.canva.com/login")
            input("After login, return to this terminal and press Enter to close Chrome: ")
            if "canva.com" not in driver.current_url:
                raise CommandError("Canva login was not detected.")
        except KeyboardInterrupt:
            self.stdout.write("\nLogin setup cancelled.")
        finally:
            if driver:
                driver.quit()

        self.stdout.write(self.style.SUCCESS(
            f"Persistent Selenium Chrome profile is stored privately at: {profile_dir}"
        ))
