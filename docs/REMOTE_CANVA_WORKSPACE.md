# Remote Canva workspace inside Django

The `feature/canva-server-browser-workspace` branch adds a staff-only remote
browser panel. A user clicks **Login with Canva**, a Chromium browser opens on
the Django server, and the user's own Canva login/verification is completed
manually. Django then shows refreshed browser screenshots and relays basic
mouse/keyboard actions. Canva itself is loaded normally in the server browser;
the application does not impersonate Canva or bypass its security controls.

## What this is / is not

- It is a remote-browser workspace rendered as screenshots with input relay.
- It is not a Canva iframe, and it does not make Canva's editor DOM part of the
  Django page.
- The existing design-sync/export endpoints remain separate workflows.
- Canva may change its UI, request re-authentication, block automation, or show
  flows this simple remote panel cannot operate. CAPTCHA/2FA must be completed
  by the account owner in the visible remote workspace if available.
- Publishing to social networks still depends on valid platform credentials,
  permissions, public media URLs and successful live testing.

## Local setup

```bash
git fetch origin
git checkout feature/canva-server-browser-workspace
pip install -r requirements.txt
python -m playwright install chromium
python manage.py migrate
python manage.py runserver
```

Sign in to Django as a staff user and open `/api/browser/`. Click **Login with
Canva**. Complete Canva login in the remote panel, then click **Save Canva
session**. The session state is stored in
`private/browser_states/canva-storage-state.json`; keep it private and never
commit or send it to anyone.

## Deployment constraints

The current manager is process-local (one browser per Django worker). Use one
Django worker for this prototype. For production/multiple users, move browser
ownership to a dedicated isolated worker/service, bind sessions to the
authenticated Django user, enforce session expiry and idle shutdown, and use
WebSocket/WebRTC streaming with an authenticated gateway. Do not expose these
endpoints to non-staff users or the public internet without a security review.
Headless Chromium may be challenged by Canva, and this implementation has not
been live-tested against all Canva account/login flows.

## Endpoints

- `POST /api/browser/remote/start/` — launch or reuse the server browser.
- `GET /api/browser/remote/status/` — inspect status.
- `GET /api/browser/remote/screenshot/` — latest JPEG screenshot as data URL.
- `POST /api/browser/remote/input/` — allowed actions: click, type, key,
  navigate (Canva HTTPS only), save_session, stop.

All endpoints require an authenticated Django staff account. POST endpoints
require CSRF protection.
