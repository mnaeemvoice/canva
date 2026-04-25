
import os
import hashlib
import base64
import requests
import jwt
from django.conf import settings
from django.shortcuts import render, redirect
from django.core.cache import cache

from rest_framework.decorators import api_view
from rest_framework.response import Response
import uuid
from .models import CanvaConnection, CanvaDesign
# ======================
# HOME
# ======================
def home(request):
    return render(request, "index.html")


# ======================
# PKCE HELPERS
# ======================
def generate_code_verifier():
    return base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8').rstrip('=')


def generate_code_challenge(verifier):
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode('utf-8').rstrip('=')


# ======================
# LOGIN (CANVA AUTH)
# ======================
@api_view(['GET'])
def canva_login(request):
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    state = str(uuid.uuid4())  # 🔥 unique state generate

    # 🔥 store verifier with state
    cache.set(f"canva_verifier_{state}", code_verifier, timeout=600)

    url = (
        "https://www.canva.com/api/oauth/authorize"
        f"?client_id={settings.CLIENT_ID}"
        "&response_type=code"
        "&code_challenge_method=s256"
        f"&code_challenge={code_challenge}"
        f"&redirect_uri={settings.REDIRECT_URI}"
        f"&state={state}"
        "&scope=design:content:read design:meta:read"
    )

    return redirect(url)
# ======================
# CALLBACK
# ======================
@api_view(['GET'])
def canva_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code:
        return Response({"error": "Missing authorization code"})

    if not state:
        return Response({"error": "Missing state parameter"})

    # ✅ get verifier
    code_verifier = cache.get(f"canva_verifier_{state}")

    if not code_verifier:
        return Response({
            "error": "Code verifier not found (cache expired or invalid state)"
        })

    # 🔐 exchange token
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.CLIENT_ID,
        "client_secret": settings.CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.REDIRECT_URI,
        "code_verifier": code_verifier
    }

    response = requests.post(
        "https://api.canva.com/rest/v1/oauth/token",
        data=data
    )

    try:
        token_data = response.json()
    except Exception:
        return Response({
            "error": "Invalid response from Canva",
            "response_text": response.text
        })

    if "access_token" not in token_data:
        return Response({
            "error": "Token not received",
            "canva_response": token_data
        })

    # ✅ save session
    request.session["access_token"] = token_data["access_token"]
    request.session["canva_connected"] = True
    print("🎉 access_token saved")
    # 🧹 clear cache
    cache.delete(f"canva_verifier_{state}")
    CanvaConnection.save_token(
    access_token=token_data["access_token"],
    refresh_token=token_data.get("refresh_token"),
    expires_at=None
)

    # 🚀 FINAL REDIRECT TO CANVA PAGE
    return redirect("/api/canva/dashboard/")
    
                         

# ======================
# PROFILE
# ======================
@api_view(['POST']) # Changed from GET to POST
def canva_profile(request):
    # Get access token from request body (for frontend POST) or session
    access_token = request.data.get("access_token") or request.session.get("access_token")

    if not access_token:
        return Response({"error": "User not logged in or session expired"})

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(
        "https://api.canva.com/rest/v1/oauth/profile",
        headers=headers
    )

    return Response(response.json() if response.ok else {
        "error": response.text,
        "status_code": response.status_code
    })
# ======================
# DESIGNS
# ======================
@api_view(['POST']) # Changed from GET to POST
def canva_designs(request):
    # Get access token from request body (for frontend POST) or session
    access_token = request.data.get("access_token") or request.session.get("access_token")

    if not access_token:
        return Response({"error": "User not logged in or session expired"})

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(
        "https://api.canva.com/rest/v1/oauth/designs",
        headers=headers
    )

    return Response(response.json() if response.ok else {
        "error": response.text,
        "status_code": response.status_code
    })


# ======================
# WEBHOOK
# ======================
@api_view(['POST'])
def canva_webhook(request):

    import json, uuid, os
    from django.conf import settings
    from rest_framework.response import Response
    from .models import CanvaDesign

    print("\n🔥 CANVA WEBHOOK HIT")

    try:
        data = json.loads(request.body.decode("utf-8"))
    except:
        data = request.data or {}

    # ⚡ FAST ACK FIRST (IMPORTANT)
    response_data = {
        "status": "received"
    }

    # ================= EVENT =================
    event_type = (
        data.get("event")
        or data.get("event_type")
        or data.get("type")
        or ""
    ).lower()

    # ================= DESIGN ID =================
    design_id = (
        data.get("data", {}).get("design", {}).get("id")
        or data.get("design_id")
        or str(uuid.uuid4())
    )

    # ================= LOG ONLY =================
    log_dir = os.path.join(settings.MEDIA_ROOT, "canva_logs")
    os.makedirs(log_dir, exist_ok=True)

    with open(os.path.join(log_dir, "events.log"), "a") as f:
        f.write(json.dumps(data) + "\n")

    # ================= DB SAVE =================
    CanvaDesign.objects.update_or_create(
        design_id=design_id,
        defaults={
            "status": event_type,
            "raw_data": json.dumps(data)
        }
    )

    print("✅ EVENT STORED:", event_type)

    # ⚡ RETURN IMMEDIATELY (CRITICAL)
    return Response(response_data)
# ======================
# DASHBOARD
# ======================
@api_view(['GET']) # A dashboard page will typically be a GET request
def canva_dashboard(request):
    # This view will display saved designs
    return render(request, "canva_dashboard.html")

# ======================
# SAVED DESIGNS API
# ======================
@api_view(['GET'])
def list_saved_canva_designs(request):
    save_dir = os.path.join(settings.MEDIA_ROOT, "canva")
    if not os.path.exists(save_dir):
        return Response({"designs": []})

    design_files = []
    for filename in os.listdir(save_dir):
        if filename.endswith(".png"): # Assuming designs are saved as PNG
            design_id = filename.replace(".png", "")
            # Assuming MEDIA_URL is configured in settings.py to serve these files
            # For example, MEDIA_URL = '/media/'
            design_url = f"/media/canva/{filename}" # Construct URL for the frontend
            design_files.append({"id": design_id, "url": design_url})

    return Response({"designs": design_files})


import requests
from django.shortcuts import redirect
from .models import CanvaConnection

import requests
from django.shortcuts import redirect
from .models import CanvaConnection
import jwt


def open_canva(request):

    conn = CanvaConnection.objects.first()

    if not conn or not conn.access_token:
        print("❌ No access token found")
        return redirect("/")

    token = conn.access_token

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # =============================
    # 🔍 1. PRINT TOKEN SCOPES
    # =============================
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        print("\n========== TOKEN DEBUG ==========")
        print("SUBJECT:", decoded.get("sub"))
        print("SCOPES:", decoded.get("scopes"))
        print("ROLE:", decoded.get("roles"))
        print("=================================\n")

    except Exception as e:
        print("Token decode error:", str(e))

    # =============================
    # 🔥 2. CREATE DESIGN CALL
    # =============================
    try:
        response = requests.post(
            "https://api.canva.com/rest/v1/designs",
            headers=headers,
            json={"title": "My Design from Django"},
            timeout=10
        )

        print("\n========== CANVA API RESPONSE ==========")
        print("STATUS:", response.status_code)
        print("HEADERS:", dict(response.headers))
        print("TEXT:", response.text)
        print("========================================\n")

        # Try JSON parsing safely
        try:
            data = response.json()
        except Exception:
            print("❌ Response is not JSON")
            return redirect("/")

        # =============================
        # 🧠 CHECK MISSING SCOPES
        # =============================
        if response.status_code == 403:
            print("❌ PERMISSION ERROR DETECTED")

            if "missing_scope" in response.text:
                print("👉 Missing scopes detected in response")
                print("👉 Fix in Canva Dashboard and re-login user")

            return redirect("/")

        # =============================
        # 🧾 HANDLE DESIGN ID
        # =============================
        design_id = data.get("id")

        if design_id:
            print("✅ Design created:", design_id)
            return redirect(f"https://www.canva.com/design/{design_id}")

        # =============================
        # 🧾 HANDLE JOB FLOW
        # =============================
        job_id = data.get("job", {}).get("id")

        if job_id:
            print("⏳ Job created:", job_id)
            return redirect("/api/canva/dashboard/")

        print("⚠️ Unexpected response format")

    except Exception as e:
        print("🔥 ERROR:", str(e))

    return redirect("/")
@api_view(['GET'])
def canva_monitor(request):

    import requests
    import httpx
    import time
    import logging

    from .models import CanvaConnection, CanvaDesign

    logger = logging.getLogger(__name__)

    results = {
        "token_status": None,
        "api_test": None,
        "webhooks": None,
        "webhook_active": False,
        "saved_designs": 0,
        "latency": {},
        "errors": []
    }

    # ================= TOKEN CHECK =================
    try:
        conn = CanvaConnection.objects.first()

        if not conn or not conn.access_token:
            return Response({"error": "❌ No Canva token found"})

        token = conn.access_token
        headers = {"Authorization": f"Bearer {token}"}

        results["token_status"] = "FOUND"

    except Exception as e:
        results["errors"].append(f"TOKEN ERROR: {str(e)}")
        logger.error(e)
        return Response(results)

    # ================= 1. REQUESTS API TEST =================
    try:
        start = time.time()

        r = requests.get(
            "https://api.canva.com/rest/v1/users/me",
            headers=headers,
            timeout=10
        )

        results["api_test"] = r.status_code
        results["latency"]["requests_users_me"] = round(time.time() - start, 3)

        results["token_status"] = "VALID" if r.ok else "INVALID"

    except Exception as e:
        results["errors"].append(f"REQUESTS ERROR: {str(e)}")
        logger.error(e)

    # ================= 2. HTTPX FALLBACK TEST =================
    try:
        start = time.time()

        with httpx.Client(timeout=10) as client:
            r2 = client.get(
                "https://api.canva.com/rest/v1/users/me",
                headers=headers
            )

        results["latency"]["httpx_users_me"] = round(time.time() - start, 3)
        results["api_test_httpx"] = r2.status_code

    except Exception as e:
        results["errors"].append(f"HTTPX ERROR: {str(e)}")
        logger.error(e)

    # ================= 3. WEBHOOK LIST =================
    try:
        start = time.time()

        w = requests.get(
            "https://api.canva.com/rest/v1/webhooks",
            headers=headers,
            timeout=10
        )

        results["latency"]["webhooks"] = round(time.time() - start, 3)

        if w.ok:
            data = w.json()
            results["webhooks"] = data

            if isinstance(data, list) and len(data) > 0:
                results["webhook_active"] = True
            else:
                results["webhook_active"] = False
        else:
            results["errors"].append(f"WEBHOOK API ERROR: {w.text}")

    except Exception as e:
        results["errors"].append(f"WEBHOOK ERROR: {str(e)}")
        logger.error(e)

    # ================= 4. DB CHECK =================
    try:
        results["saved_designs"] = CanvaDesign.objects.count()

    except Exception as e:
        results["errors"].append(f"DB ERROR: {str(e)}")
        logger.error(e)

    # ================= FINAL LOG =================
    logger.info(f"CANVA MONITOR RUN: {results}")

    return Response(results)
@api_view(['GET'])
def register_webhook(request):

    import requests
    from django.conf import settings
    from .models import CanvaConnection

    conn = CanvaConnection.objects.first()

    if not conn or not conn.access_token:
        return Response({"error": "❌ No Canva connection found"})

    webhook_url = f"{settings.NGROK_URL}/api/canva/webhook/"

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # =========================
    # 🔍 STEP 1: CHECK EXISTING WEBHOOKS
    # =========================
    try:
        existing_res = requests.get(
            "https://api.canva.com/rest/v1/webhooks",
            headers=headers
        )

        if existing_res.ok:
            existing_hooks = existing_res.json()

            for hook in existing_hooks:
                if hook.get("url") == webhook_url:
                    return Response({
                        "status": "already_exists",
                        "message": "✅ Webhook already registered",
                        "webhook": hook
                    })

    except Exception as e:
        return Response({
            "error": f"❌ Failed to check existing webhooks: {str(e)}"
        })

    # =========================
    # 🚀 STEP 2: REGISTER NEW WEBHOOK
    # =========================
    data = {
        "url": webhook_url,
        "events": ["design.exported"]
    }

    try:
        res = requests.post(
            "https://api.canva.com/rest/v1/webhooks",
            json=data,
            headers=headers
        )

        if res.ok:
            return Response({
                "status": "created",
                "message": "🎉 Webhook registered successfully",
                "data": res.json()
            })
        else:
            return Response({
                "status": "failed",
                "error": res.text,
                "status_code": res.status_code
            })

    except Exception as e:
        return Response({
            "error": f"❌ Webhook registration failed: {str(e)}"
        })