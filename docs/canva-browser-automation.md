# Canva Playwright browser automation (Django)

This branch adds a native Django staff dashboard and a Playwright workflow that reuses a manually authenticated Canva browser session. It does not use the Canva API for this browser-automation path.

## Setup

1. Install Python dependencies: pip install -r requirements.txt
2. Install Chromium: python -m playwright install chromium
3. Create a Django staff/superuser if needed: python manage.py createsuperuser
4. Run python manage.py canva_browser_login on a machine that can display Chromium (or through a secured VNC/desktop session). Sign in to Canva yourself and complete any verification. The state file is saved under private/browser_states/ by default.
5. Start Django and visit /api/browser/ while signed in as a Django staff user.
6. Click Sync Canva designs to import design metadata. Click Export MP4 on a design to attempt a full MP4 export through Canva's UI.
7. For background discovery, run python manage.py canva_browser_watch --interval 60 under a process supervisor.

Set CANVA_PLAYWRIGHT_STATE_DIR to move session state to a private directory outside the project. Protect this file like a password; never commit it, email it, or expose it to other users. .gitignore excludes the default state folder and common Playwright state files.

## Endpoints

- GET /api/browser/ — Django template dashboard (staff only)
- GET /api/browser/status/ — status (staff only)
- POST /api/browser/canva/sync/ — discover designs and save metadata (staff only)
- POST /api/browser/canva/export/<design_id>/ — attempt UI-based MP4 export (staff only)

## Important limitations

- Canva changes its UI often. The export selectors may need maintenance, and some designs may not offer MP4 export.
- Background watcher syncs metadata. It does not silently export every new design; use the dashboard's MP4 export action to retrieve full animation/video files.
- This branch is a first implementation and has not been tested against a live Canva account in this environment. Test with a non-sensitive design before relying on it.
- For production, serve MEDIA_ROOT securely, use HTTPS, restrict dashboard access, and run the watcher as a supervised worker. Session files and exported assets must not be public by default.
- The original React frontend repository is separate and has not been rewritten by this backend branch; the new automation dashboard itself is native Django templates.
