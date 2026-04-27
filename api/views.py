
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

    state = str(uuid.uuid4())
    cache.set(f"canva_verifier_{state}", code_verifier, timeout=600)

    scope = (
        "profile:read "
        "app:read app:write "
        "design:content:read design:content:write "
        "design:meta:read "
        "design:permission:read design:permission:write "
        "folder:read folder:write folder:permission:read folder:permission:write "
        "asset:read asset:write "
        "comment:read comment:write "
        "brandtemplate:content:read brandtemplate:content:write brandtemplate:meta:read "
        "collaboration:event"
    )

    url = (
        "https://www.canva.com/api/oauth/authorize"
        f"?client_id={settings.CLIENT_ID}"
        "&response_type=code"
        "&code_challenge_method=s256"
        f"&code_challenge={code_challenge}"
        f"&redirect_uri={settings.REDIRECT_URI}"
        f"&state={state}"
        f"&scope={scope}"
    )

    return redirect(url)
# ======================
# CALLBACK
# ======================
# CALLBACK (AUTO WEBHOOK FIXED)
# ======================
@api_view(['GET'])
def canva_callback(request):

    import requests

    code = request.GET.get("code")
    state = request.GET.get("state")

    print("\n🔥 CANVA CALLBACK START")

    if not code:
        return Response({"error": "Missing code"})

    # ======================
    # PKCE VERIFY
    # ======================
    code_verifier = cache.get(f"canva_verifier_{state}")

    if not code_verifier:
        return Response({"error": "Code verifier expired"})

    # ======================
    # TOKEN REQUEST
    # ======================
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.CLIENT_ID,
        "client_secret": settings.CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.REDIRECT_URI,
        "code_verifier": code_verifier
    }

    print("🚀 TOKEN REQUEST SENT")

    response = requests.post(
        "https://api.canva.com/rest/v1/oauth/token",
        data=data
    )

    try:
        token_data = response.json()
    except:
        return Response({
            "error": "Invalid token response",
            "raw": response.text
        })

    access_token = token_data.get("access_token")

    if not access_token:
        return Response(token_data)

    # ======================
    # SAVE TOKEN
    # ======================
    conn, _ = CanvaConnection.objects.get_or_create(id=1)
    conn.access_token = access_token
    conn.refresh_token = token_data.get("refresh_token")
    conn.save()

    print("✅ TOKEN SAVED")

    # ======================
    # ⚠️ WEBHOOK NOTE (IMPORTANT FIX)
    # ======================
    print("\n⚠️ WEBHOOK NOTE:")
    print("Canva REST API me /webhooks endpoint available nahi hota.")
    print("Webhook registration MUST be done in Canva Developer Dashboard.")

    print("\n👉 Use this URL in Canva App settings:")
    print(f"{settings.NGROK_URL}/api/canva/webhook/")

    print("\n👉 Events to enable:")
    print([
        "design/exported",
        "design/updated",
        "asset/created"
    ])

    # ======================
    # CLEANUP
    # ======================
    cache.delete(f"canva_verifier_{state}")

    return redirect("/api/canva/dashboard/")

# ======================
# 🔥 SUPER DEBUG WEBHOOK (FINAL)
# ======================
@api_view(['POST'])
def canva_webhook(request):

    import json, os, traceback
    from django.conf import settings

    print("\n🔥 ===== CANVA WEBHOOK HIT =====")

    debug = {
        "method": request.method,
        "content_type": request.content_type,
        "raw_body": None,
        "parsed": None,
        "headers": dict(request.headers),
        "errors": [],
        "status": "unknown"
    }

    # RAW BODY
    try:
        raw = request.body.decode("utf-8")
        debug["raw_body"] = raw
        print("📩 RAW:", raw)
    except Exception as e:
        debug["errors"].append(str(e))

    # JSON PARSE
    try:
        data = json.loads(request.body.decode("utf-8"))
        debug["parsed"] = data
    except Exception as e:
        data = {}
        debug["errors"].append(str(e))

    # EVENT
    event = data.get("event") or data.get("type") or data.get("event_type")

    print("🎯 EVENT:", event)

    if not event:
        print("❌ NO EVENT RECEIVED")

    # DESIGN ID
    design_id = (
        data.get("data", {}).get("design", {}).get("id")
        or data.get("design_id")
        or None
    )

    print("🆔 DESIGN ID:", design_id)

    # SAVE LOG FILE
    try:
        log_dir = os.path.join(settings.MEDIA_ROOT, "canva_logs")
        os.makedirs(log_dir, exist_ok=True)

        with open(os.path.join(log_dir, "webhook.log"), "a") as f:
            f.write(json.dumps(data) + "\n")

    except Exception as e:
        debug["errors"].append(str(e))

    print("📊 DEBUG:", debug)

    return Response({
        "ok": True,
        "debug": debug
    })
# ======================
# PROFILE
# ======================
@api_view(['GET'])
def canva_profile(request):

    # 🔐 Token from session (best practice)
    access_token = request.session.get("access_token")

    if not access_token:
        return Response({
            "error": "User not logged in or session expired"
        }, status=401)

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.get(
            "https://api.canva.com/rest/v1/users/me",
            headers=headers,
            timeout=10
        )

        if response.ok:
            return Response(response.json())

        return Response({
            "error": response.text,
            "status_code": response.status_code
        }, status=response.status_code)

    except Exception as e:
        return Response({
            "error": str(e)
        }, status=500)
# ======================
# DESIGNS
# ======================
@api_view(['GET'])
def canva_designs(request):

    import requests, time

    access_token = request.session.get("access_token")

    if not access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # ================= GET DESIGNS =================
    response = requests.get(
        "https://api.canva.com/rest/v1/designs",
        headers=headers,
        timeout=20
    )

    try:
        data = response.json()
    except:
        return Response({"error": response.text}, status=500)

    designs = data.get("items") or data.get("designs") or []

    saved = []

    # ================= LOOP =================
    for d in designs:

        design_id = d.get("id")
        if not design_id:
            continue

        title = (
            d.get("title")
            or d.get("name")
            or f"Design {design_id[:6]}"
        )

        asset_url = None
        asset_type = "unknown"

        # ================= FORCE EXPORT =================
        try:
            export_res = requests.post(
                "https://api.canva.com/rest/v1/exports",
                headers=headers,
                json={
                    "design_id": design_id,
                    "format": "png"   # 👈 ALWAYS GET IMAGE
                },
                timeout=20
            )

            export_data = export_res.json()

            job_id = export_data.get("job", {}).get("id")

            if job_id:

                # wait for processing
                time.sleep(2)

                result = requests.get(
                    f"https://api.canva.com/rest/v1/exports/{job_id}",
                    headers=headers
                )

                result_data = result.json()

                urls = result_data.get("export", {}).get("urls", [])

                if urls:
                    asset_url = urls[0]
                    asset_type = "image"

        except Exception as e:
            print("EXPORT ERROR:", e)

        # ================= SAVE =================
        obj, _ = CanvaDesign.objects.update_or_create(
            design_id=design_id,
            defaults={
                "title": title,
                "asset_url": asset_url,
                "asset_type": asset_type,
                "raw_data": str(d)
            }
        )

        saved.append(obj)

    return Response({
        "count": len(saved),
        "designs": [
            {
                "id": s.design_id,
                "title": s.title,
                "asset": s.asset_url,
                "type": s.asset_type
            }
            for s in saved
        ]
    })
@api_view(['GET'])
def register_webhook(request):

    conn = CanvaConnection.objects.first()

    if not conn or not conn.access_token:
        return Response({"error": "No token found"})

    webhook_url = f"{settings.NGROK_URL}/api/canva/webhook/"

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    print("\n🔥 REGISTERING WEBHOOK")
    print("URL:", webhook_url)
    print("SCOPE TOKEN EXISTS:", bool(conn.access_token))

    data = {
        "url": webhook_url,
        "events": [
            "design.exported",
            "design.updated",
            "asset.created"
        ]
    }

    res = requests.post(
        "https://api.canva.com/rest/v1/webhooks",
        json=data,
        headers=headers
    )

    print("📡 RESPONSE STATUS:", res.status_code)
    print("📡 RESPONSE TEXT:", res.text)

    return Response({
        "status": res.status_code,
        "data": res.json() if res.headers.get("content-type") == "application/json" else res.text
    })
# ======================
def canva_dashboard(request):
    designs = CanvaDesign.objects.all().order_by("-id")

    cleaned_designs = []

    for d in designs:
        cleaned_designs.append({
            "id": d.design_id,
            "title": d.title or "Untitled Design",

            # ✅ correct field
            "thumbnail": d.asset_url
        })

    return render(request, "canva_dashboard.html", {
        "designs": cleaned_designs
    })
# ======================
# SAVED DESIGNS API
# ======================
@api_view(['GET'])
def list_saved_canva_designs(request):

    designs = CanvaDesign.objects.all().order_by("-id")

    result = []

    for d in designs:
        result.append({
            "id": d.design_id,
            "title": d.title or "Untitled",
            "asset": d.asset_url or None
        })

    return Response({
        "count": len(result),
        "designs": result
    })
from django.utils import timezone
from django.shortcuts import redirect
from .models import CanvaConnection, CanvaDesign
import uuid

def open_canva(request):

    conn = CanvaConnection.objects.first()

    if not conn or not conn.access_token:
        return redirect("/")

    print("🚀 Opening Canva Dashboard")

    # =========================
    # 🔥 MANUAL EVENT LOG (SIMULATED WEBHOOK)
    # =========================
    design_id = str(uuid.uuid4())

    CanvaDesign.objects.create(
        design_id=design_id,
        status="app_open_trigger",
        raw_data={
            "event": "app_opened",
            "source": "open_canva",
            "timestamp": str(timezone.now())
        }
    )

    print("📡 MANUAL EVENT STORED:", design_id)

    # =========================
    # REDIRECT TO CANVA
    # =========================
    return redirect("https://www.canva.com/")
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
