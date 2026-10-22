# Canva Playwright automation — Django-only application

This branch puts the application interface in Django templates. The React app in the separate `canva_frontend` repository is not needed for this workflow. The browser-sync/export workflow does not call the Canva API: you sign into Canva in a visible browser once, and Playwright reuses the private saved session.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python manage.py migrate
python manage.py createsuperuser
python manage.py canva_browser_login
python manage.py runserver
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`. Run `canva_browser_login` on the computer with a visible browser. Sign in and complete Canva's verification yourself, navigate to Your designs, then press Enter in the terminal. Keep the generated `private/browser_states/canva-storage-state.json` secret.

Open `http://127.0.0.1:8000/`, sign in with a Django staff account, and use the dashboard to sync designs and export an MP4. Exported files are saved under `media/browser_exports/` and the bytes are stored in the design record so the publishing workflow can access them.

## Social publishing

The dashboard lets you store a platform access token and publish exported media. Use official authorization flows to obtain tokens; do not enter platform passwords. Facebook video/photo publishing and YouTube resumable video upload use their platform APIs. Instagram Graph publishing requires an eligible professional account, its account ID, required permissions, and a publicly reachable HTTPS media URL. LinkedIn and TikTok currently return an explicit “not implemented” error rather than creating fake success records. Platform eligibility, scopes, app review, upload limits, and token expiration still apply.

The social publishing APIs are separate from Canva API usage. No account password is collected by this dashboard.

## Background sync and endpoints

- `GET /` — Django-native staff dashboard
- `GET /api/browser/status/` — setup status (staff only)
- `POST /api/browser/canva/sync/` — discover Canva designs and save metadata (staff only)
- `POST /api/browser/canva/export/<design_id>/` — attempt MP4 export through Canva's UI (staff only)
- `POST /api/social/unified-post/` — publish an exported design using its saved media bytes and a connected platform token

Run `python manage.py canva_browser_watch --interval 60` under a process supervisor for background metadata discovery. The watcher does not automatically export every new design.

## Important limitations and security

- Canva UI selectors can change. Export has not been tested against a live Canva account in this environment; test with a non-sensitive design first.
- Canva can require extra export time, account entitlements, or different download options for some designs. If a design does not offer MP4, the export fails rather than substituting a thumbnail.
- Instagram requires a publicly reachable media URL; localhost URLs will not work for publishing.
- The dashboard is staff-only. Do not make browser session state or exported media publicly readable in production. Use HTTPS, a secure production database, environment-based Django secrets, restricted hosts, and private media delivery.
