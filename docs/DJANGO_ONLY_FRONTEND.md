# Django-only UI

This feature branch provides the application UI as Django templates. The main dashboard is available at `/api/browser/` and the root URL redirects staff users there. The React app in the separate `canva_frontend` repository is not required for this workflow and is not loaded by Django.

## Workflow

1. Install Python requirements and Chromium for Playwright.
2. Create a Django staff/superuser account.
3. Run `python manage.py canva_browser_login` on the machine that owns the Canva account and complete login manually.
4. Run the Django server and open `/`; it redirects to the Django dashboard.
5. Sync design metadata, export a design as MP4, then use the dashboard's publish form.

The Canva browser-state file is a credential and must remain private/outside Git. Browser export depends on Canva's changing UI and must be tested against the account and design type.

## Social publishing

The dashboard uses the existing server-side social publishing endpoint and saved platform tokens. Every social platform requires its own valid account/token and may require an eligible account type, review, scopes, and media format. The old posting implementation contains placeholder behavior for some platforms; this branch must not be treated as production-ready publishing for those platforms until their platform-specific API flows are implemented and verified. Never report a placeholder response as a successful live post.
