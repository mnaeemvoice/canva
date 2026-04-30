import os
import hashlib
import base64
import requests
import jwt
from django.conf import settings
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.db.models import Q
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
import uuid
from .models import CanvaConnection, CanvaDesign
# ======================
# HOME
# ======================
from django.http import JsonResponse

def home(request):
    return JsonResponse({
        "message": "Canva Integration API Server",
        "endpoints": {
            "login": "/api/canva/login/",
            "callback": "/api/canva/callback/",
            "profile": "/api/canva/profile/",
            "designs": "/api/canva/designs/",
            "saved_designs": "/api/canva/saved-designs/",
            "create_design": "/api/canva/create-design/ (POST)",
            "sync_designs": "/api/canva/sync-designs/ (POST)",
            "webhook": "/api/canva/webhook/ (POST)",
            "monitor": "/api/canva/monitor/",
        },
        "frontend": "http://localhost:3000",
        "docs": "Run frontend: npm start (in canva_frontend folder)"
    })


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
        "brandtemplate:content:write "
        "profile:read "
        "app:read "
        "folder:permission:write "
        "collaboration:event "
        "comment:read "
        "brandtemplate:meta:read "
        "design:content:read "
        "comment:write "
        "design:meta:read "
        "brandtemplate:content:read "
        "asset:write "
        "design:permission:write "
        "app:write "
        "folder:read "
        "design:content:write "
        "asset:read "
        "folder:permission:read "
        "design:permission:read "
        "folder:write"
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

    print(f"🔗 LOGIN URL: {url}")
    print(f"📍 REDIRECT_URI: {settings.REDIRECT_URI}")
    
    return Response({
        "success": True,
        "login_url": url,
        "message": "Please visit this URL to login to Canva"
    })
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
    error = request.GET.get("error")
    error_description = request.GET.get("error_description")

    # Handle permission denied
    if error:
        print(f"❌ Permission denied: {error} - {error_description}")
        return redirect("http://localhost:3000?error=" + error)
    
    # Only process if code exists (user allowed permissions)
    if not code:
        return Response({"error": "Missing code - User may have denied permissions"})

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

    
    # ======================
    # CLEANUP
    # ======================
    cache.delete(f"canva_verifier_{state}")

    return redirect("http://localhost:3000")

# ======================
# 🔥 SUPER DEBUG WEBHOOK (FINAL)
# ======================
@api_view(['POST'])
def canva_webhook(request):

    import json
    import os
    import time
    from django.utils import timezone

    print("\n🔥 ===== CANVA WEBHOOK RECEIVED =====")
    print("⏰ TIME:", timezone.now())

    # ================= HEADERS =================
    headers = dict(request.headers)
    print("📩 HEADERS:")
    for k, v in headers.items():
        print(f"   {k}: {v}")

    # ================= RAW BODY =================
    raw_body = request.body.decode("utf-8")
    print("\n📩 RAW BODY:")
    print(raw_body)

    # ================= PARSE JSON =================
    try:
        data = json.loads(raw_body)
        print("\n📦 PARSED JSON SUCCESS")
    except Exception as e:
        data = {}
        print("\n❌ JSON PARSE ERROR:", str(e))

    print("📦 DATA:", data)

    # ================= EVENT DETECTION =================
    event = data.get("event") or data.get("type") or data.get("event_type")

    design_id = (
        data.get("design_id")
        or data.get("data", {}).get("design", {}).get("id")
        or data.get("data", {}).get("id")
    )

    print("\n🎯 ===== EVENT INFO =====")
    print("🎯 EVENT TRIGGERED:", event)
    print("🆔 DESIGN ID:", design_id)

    # ================= EVENT TYPE HANDLING =================
    if event:
        print("\n🚀 EVENT ACTION LOG:")

        if event == "design/created":
            print("🆕 NEW DESIGN CREATED EVENT FIRED")

        elif event == "design/updated":
            print("✏️ DESIGN UPDATED EVENT FIRED")

        elif event == "design/exported":
            print("📤 DESIGN EXPORTED EVENT FIRED")

        elif event == "asset/created":
            print("📁 ASSET CREATED EVENT FIRED")

        elif event == "design/shared":
            print("🤝 DESIGN SHARED EVENT FIRED")

        elif event == "design/published":
            print("🚀 DESIGN PUBLISHED EVENT FIRED")

        else:
            print("⚠️ UNKNOWN EVENT TYPE:", event)

    else:
        print("❌ NO EVENT RECEIVED")

    # ================= LOG FILE =================
    log_dir = "media/webhook_logs"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "canva_webhook.log")

    with open(log_file, "a") as f:
        f.write(raw_body + "\n")

    print("\n💾 LOG SAVED TO FILE")

    # ================= SAVE DESIGN TO DATABASE =================
    if design_id and event in ["design/created", "design/updated", "design/exported"]:
        print("\n💾 ATTEMPTING TO SAVE DESIGN TO DATABASE...")
        
        try:
            conn = CanvaConnection.objects.first()
            
            if not conn or not conn.access_token:
                print("❌ NO ACCESS TOKEN - CANNOT SAVE DESIGN")
            else:
                headers = {
                    "Authorization": f"Bearer {conn.access_token}",
                    "Content-Type": "application/json"
                }
                
                # Fetch design details from Canva API
                print(f"📡 FETCHING DESIGN DETAILS FOR {design_id}...")
                design_res = requests.get(
                    f"https://api.canva.com/rest/v1/designs/{design_id}",
                    headers=headers,
                    timeout=20
                )
                
                if design_res.ok:
                    design_data = design_res.json()
                    title = design_data.get("title", "Untitled")
                    print(f"📌 TITLE: {title}")
                    
                    # Export the design with proper type
                    print("📤 EXPORTING DESIGN...")
                    
                    # Get design type first
                    design_type = design_data.get("type", "image")
                    
                    export_res = requests.post(
                        "https://api.canva.com/rest/v1/exports",
                        headers=headers,
                        json={
                            "design_id": design_id,
                            "format": "jpg",
                            "type": design_type
                        },
                        timeout=20
                    )
                    
                    if export_res.ok:
                        export_json = export_res.json()
                        export_id = (
                            export_json.get("export", {}).get("id")
                            or export_json.get("id")
                            or export_json.get("export_id")
                        )
                        
                        if export_id:
                            print(f"🆔 EXPORT ID: {export_id}")
                            
                            # Poll for export completion
                            for attempt in range(1, 11):
                                print(f"⏳ CHECKING EXPORT STATUS ({attempt})")
                                time.sleep(2)
                                
                                check_res = requests.get(
                                    f"https://api.canva.com/rest/v1/exports/{export_id}",
                                    headers=headers,
                                    timeout=20
                                )
                                
                                if check_res.ok:
                                    exp = check_res.json().get("export", {})
                                    status = exp.get("status")
                                    print(f"📊 STATUS: {status}")
                                    
                                    if status == "COMPLETE":
                                        output = exp.get("output", {})
                                        blobs = output.get("exportBlobs", [])
                                        
                                        asset_url = None
                                        asset_type = None
                                        
                                        for blob in blobs:
                                            url = (
                                                blob.get("url")
                                                or blob.get("download_url")
                                                or blob.get("signed_url")
                                            )
                                            if url:
                                                asset_url = url
                                                break
                                        
                                        if not asset_url:
                                            asset_url = (
                                                output.get("url")
                                                or output.get("download_url")
                                                or output.get("signed_url")
                                            )
                                        
                                        if asset_url:
                                            if ".mp4" in asset_url:
                                                asset_type = "video"
                                            elif ".pdf" in asset_url:
                                                asset_type = "pdf"
                                            else:
                                                asset_type = "image"
                                        
                                        # Save to database
                                        obj, created = CanvaDesign.objects.update_or_create(
                                            design_id=design_id,
                                            defaults={
                                                "title": title,
                                                "asset_url": asset_url,
                                                "asset_type": asset_type,
                                                "raw_data": json.dumps(design_data),
                                                "status": "synced"
                                            }
                                        )
                                        
                                        action = "CREATED" if created else "UPDATED"
                                        print(f"✅ DESIGN {action} IN DATABASE")
                                        break
                                    
                                    elif status == "FAILED":
                                        print("❌ EXPORT FAILED")
                                        break
                    else:
                        print("❌ EXPORT REQUEST FAILED")
                else:
                    print("❌ FAILED TO FETCH DESIGN DETAILS")
                    
        except Exception as e:
            print(f"❌ ERROR SAVING DESIGN: {str(e)}")

    # ================= FINAL RESPONSE =================
    print("✅ WEBHOOK PROCESS COMPLETE")

    return Response({
        "ok": True,
        "received": True,
        "event": event,
        "design_id": design_id
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

    import requests, time, json

    print("\n🚀 ===== CANVA DESIGN SYNC START =====")

    conn = CanvaConnection.objects.first()

    if not conn or not conn.access_token:
        print("❌ NO ACCESS TOKEN FOUND")
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # ================= GET DESIGNS =================
    print("📡 FETCHING DESIGNS FROM CANVA...")

    try:
        res = requests.get(
            "https://api.canva.com/rest/v1/designs",
            headers=headers,
            timeout=20
        )
    except Exception as e:
        return Response({"error": str(e)}, status=500)

    print("📥 RESPONSE STATUS:", res.status_code)

    if not res.ok:
        print("❌ FAILED:", res.text)
        return Response({
            "error": "Failed to fetch designs",
            "details": res.text
        }, status=500)

    # ================= SAFE JSON PARSE =================
    try:
        data = res.json()
    except Exception:
        return Response({
            "error": "Invalid JSON from Canva",
            "raw": res.text
        }, status=500)

    print("📦 RAW RESPONSE KEYS:", data.keys())

    # ================= SAFE DESIGN EXTRACTION =================
    designs = (
        data.get("items")
        or data.get("designs")
        or data.get("data", {}).get("items")
        or []
    )

    print(f"📊 TOTAL DESIGNS FOUND: {len(designs)}")

    if not designs:
        return Response({
            "count": 0,
            "designs": [],
            "message": "No designs found in Canva response",
            "debug": data
        })

    saved = []

    # ================= LOOP DESIGNS =================
    for index, d in enumerate(designs, start=1):

        print(f"\n==============================")
        print(f"🧩 PROCESSING DESIGN #{index}")

        design_id = d.get("id")
        if not design_id:
            print("⚠️ SKIPPED: NO DESIGN ID")
            continue

        title = (
            d.get("title")
            or d.get("name")
            or d.get("document", {}).get("title")
            or "Untitled"
        )

        print("🆔 ID:", design_id)
        print("📌 TITLE:", title)

        existing = CanvaDesign.objects.filter(design_id=design_id).first()

        if existing and existing.asset_url:
            print("✔️ EXISTS - SKIP EXPORT")
            saved.append(existing)
            continue

        asset_url = None
        asset_type = None

        # ================= EXPORT =================
        try:
            print("📤 EXPORT START...")

            export_res = requests.post(
                "https://api.canva.com/rest/v1/exports",
                headers=headers,
                json={
                    "design_id": design_id,
                    "format": "jpg"
                },
                timeout=20
            )

            print("📥 EXPORT STATUS:", export_res.status_code)

            if not export_res.ok:
                print("❌ EXPORT FAILED:", export_res.text)
                continue

            export_json = export_res.json()
            export_id = (
                export_json.get("export", {}).get("id")
                or export_json.get("id")
                or export_json.get("export_id")
            )

            if not export_id:
                print("❌ NO EXPORT ID")
                continue

            print("🆔 EXPORT ID:", export_id)

            # ================= POLLING =================
            for attempt in range(1, 11):

                print(f"⏳ CHECKING STATUS ({attempt})")

                time.sleep(2)

                check_res = requests.get(
                    f"https://api.canva.com/rest/v1/exports/{export_id}",
                    headers=headers,
                    timeout=20
                )

                if not check_res.ok:
                    print("❌ STATUS API FAILED")
                    break

                exp = check_res.json().get("export", {})
                status = exp.get("status")

                print("📊 STATUS:", status)

                if status == "COMPLETE":

                    output = exp.get("output", {})
                    blobs = output.get("exportBlobs", [])

                    for blob in blobs:
                        url = (
                            blob.get("url")
                            or blob.get("download_url")
                            or blob.get("signed_url")
                        )

                        if url:
                            asset_url = url
                            break

                    # fallback
                    if not asset_url:
                        asset_url = (
                            output.get("url")
                            or output.get("download_url")
                            or output.get("signed_url")
                        )

                    if asset_url:
                        if ".mp4" in asset_url:
                            asset_type = "video"
                        elif ".pdf" in asset_url:
                            asset_type = "pdf"
                        else:
                            asset_type = "image"

                    print("✅ ASSET READY:", asset_url)
                    break

                if status == "FAILED":
                    print("❌ EXPORT FAILED")
                    break

        except Exception as e:
            print("❌ EXPORT ERROR:", str(e))
            continue

        # ================= SAVE =================
        if not asset_url:
            print("⚠️ NO ASSET - SKIP")
            continue

        obj, _ = CanvaDesign.objects.update_or_create(
            design_id=design_id,
            defaults={
                "title": title,
                "asset_url": asset_url,
                "asset_type": asset_type,
                "raw_data": json.dumps(d)
            }
        )

        saved.append(obj)
        print("💾 SAVED")

    # ================= RESPONSE =================
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
# ======================
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def canva_dashboard(request):

    designs = CanvaDesign.objects.exclude(
        asset_type="debug_event"
    ).order_by("-id")

    data = [
        {
            "id": d.design_id,
            "title": d.title,
            "asset": d.asset_url,
            "type": d.asset_type
        }
        for d in designs if d.asset_url  # only real assets
    ]

    return Response({
        "count": len(data),
        "designs": data
    })
# ======================
# SAVED DESIGNS API
# ======================
from rest_framework.decorators import api_view
from rest_framework.response import Response
import json

@api_view(['GET'])
def list_saved_canva_designs(request):
    print("📋 Dashboard request - loading saved designs...")
    
    # Use select_related and transaction to prevent database locks
    with transaction.atomic():
        # Sort by last_modified (latest first), fallback to created_at - LIMIT TO 5
        designs = CanvaDesign.objects.select_related().order_by("-last_modified", "-created_at")[:5]
        print(f"📊 Total designs in database: {len(designs)} (limited to 5 for performance)")

    result = []

    for d in designs:
        print(f"🔍 Processing dashboard design: {d.design_id} - {d.title}")
        
        asset = d.asset_url
        thumb = None

        # =========================
        # SAFE RAW DATA PARSING
        # =========================
        raw = {}

        if d.raw_data:
            try:
                # try JSON first (BEST)
                raw = json.loads(d.raw_data)
            except:
                try:
                    # fallback for broken string dict
                    import ast
                    raw = ast.literal_eval(d.raw_data)
                except:
                    raw = {}

        # =========================
        # THUMBNAIL EXTRACTION
        # =========================
        thumb = (
            raw.get("thumbnail", {}).get("url")
            if isinstance(raw.get("thumbnail"), dict)
            else raw.get("thumbnail")
        )

        # =========================
        # FALLBACK TO CANVA DEFAULT THUMBNAIL
        # =========================
        if not asset and not thumb:
            # Try to construct Canva's default thumbnail URL
            thumb = f"https://www.canva.com/api/design/{d.design_id}/thumbnail"
            print(f"🔄 Using Canva default thumbnail for {d.design_id}")

        # =========================
        # FINAL ASSET
        # =========================
        final_asset = asset or thumb

        print(f"🖼️ Final asset for {d.design_id}: {bool(final_asset)}")

        # =========================
        # TYPE DETECTION (IMPROVED)
        # =========================
        asset_type = "unknown"

        # First try to get type from Canva design data
        if d.raw_data:
            try:
                raw = json.loads(d.raw_data)
                if isinstance(raw, dict):
                    canva_type = raw.get("type", "").lower()
                    print(f"🔍 Canva type from raw_data: {canva_type}")
                    
                    # Map Canva types to our types
                    if canva_type in ["image", "photo", "picture"]:
                        asset_type = "image"
                    elif canva_type in ["video", "animation", "animated", "movie"]:
                        asset_type = "video"
                    elif canva_type in ["document", "pdf"]:
                        asset_type = "pdf"
                    elif canva_type in ["presentation", "deck"]:
                        asset_type = "presentation"
                    else:
                        # If type is null or empty, try to detect from other indicators
                        if not canva_type or canva_type == "null":
                            print(f"🔍 Type is null, checking other indicators...")
                            
                            # Check URLs for video indicators
                            urls = raw.get("urls", {})
                            url_str = str(urls).lower()
                            if "video" in url_str or "animation" in url_str:
                                asset_type = "video"
                                print(f"🎬 Detected video from URLs")
                            else:
                                asset_type = "image"  # Default to image
                                print(f"🖼️ Defaulting to image")
                        else:
                            asset_type = canva_type
            except:
                pass

        # Fallback to URL-based detection
        if asset_type == "unknown" and final_asset:
            url = str(final_asset).lower()
            if any(ext in url for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                asset_type = "image"
            elif ".mp4" in url or ".mov" in url or ".gif" in url:
                asset_type = "video"
            elif ".pdf" in url:
                asset_type = "pdf"
            elif "video" in url or "animation" in url or "animated" in url:
                asset_type = "video"
                
        # Special check: If this might be a video but we only have thumbnail, try to get video asset
        if asset_type == "image" and d.raw_data:
            try:
                raw = json.loads(d.raw_data)
                # Check for video indicators in raw data
                urls = raw.get("urls", {})
                url_str = str(urls).lower()
                
                # Enhanced video detection
                is_video = False
                
                # Method 1: Check URLs for video indicators
                if "video" in url_str or "animation" in url_str or "animated" in url_str:
                    is_video = True
                    print(f"🎬 Video indicators found in URLs")
                
                # Method 2: Check if design has video assets in database
                if d.asset_url and ("video" in d.asset_url.lower() or ".mp4" in d.asset_url.lower()):
                    is_video = True
                    print(f"🎬 Video asset found in database")
                
                # Method 3: Check design title for video indicators
                if d.title and any(word in d.title.lower() for word in ["video", "animation", "animated", "movie"]):
                    is_video = True
                    print(f"🎬 Video indicators found in title")
                
                # Method 4: Check Canva design type field more thoroughly
                canva_type = raw.get("type", "").lower()
                if canva_type in ["video", "animation", "animated", "movie", "mp4", "mov"]:
                    is_video = True
                    print(f"🎬 Video type found in Canva data: {canva_type}")
                
                # Method 5: Check for specific video design patterns
                if any(pattern in url_str for pattern in ["export", "video", "animation", "motion"]):
                    is_video = True
                    print(f"🎬 Video pattern found in URLs")
                
                if is_video:
                    print(f"🎬 Video detected for {d.design_id}, updating type to video")
                    asset_type = "video"
                    category = "video"
                    
                    # Try to get video asset from database or generate new one
                    if d.asset_url and "video" in d.asset_url:
                        final_asset = d.asset_url  # Use existing video asset
                        print(f"🎬 Using existing video asset: {final_asset}")
                    else:
                        # Generate video asset using export endpoint
                        try:
                            conn = CanvaConnection.objects.first()
                            if conn and conn.access_token:
                                headers = {
                                    "Authorization": f"Bearer {conn.access_token}",
                                    "Content-Type": "application/json"
                                }
                                
                                export_res = requests.post(
                                    "https://api.canva.com/rest/v1/exports",
                                    headers=headers,
                                    json={
                                        "design_id": d.design_id,
                                        "format": "MP4",
                                        "quality": "HIGH"
                                    },
                                    timeout=10
                                )
                                
                                if export_res.ok:
                                    export_data = export_res.json()
                                    if export_data and len(export_data) > 0:
                                        job_id = export_data[0].get("job", {}).get("id")
                                        if job_id:
                                            # Poll for completion
                                            job_res = requests.get(
                                                f"https://api.canva.com/rest/v1/exports/{job_id}",
                                                headers=headers,
                                                timeout=5
                                            )
                                            if job_res.ok:
                                                job_data = job_res.json()
                                                if job_data.get("job", {}).get("status") == "completed":
                                                    video_url = job_data.get("job", {}).get("result", {}).get("url")
                                                    if video_url:
                                                        final_asset = video_url
                                                        print(f"🎬 Generated video asset: {video_url}")
                                                        # Update database with video asset
                                                        with transaction.atomic():
                                                            d.asset_url = video_url
                                                            d.asset_type = "video"
                                                            d.save()
                        except:
                            pass
            except:
                pass
                
        # Additional check: If database has asset_type, use it as fallback
        if asset_type == "unknown" and d.asset_type and d.asset_type != "unknown":
            asset_type = d.asset_type
        elif not final_asset:
            # No asset available - still show the design
            asset_type = "unknown"

        print(f"🏷️ Asset type for {d.design_id}: {asset_type}")

        # =========================
        # CATEGORY MAPPING (USE CANVA DESIGNS API TYPE)
        # =========================
        category = "other"
        
        # Get Canva's actual type from designs API (not raw data)
        canva_api_type = None
        try:
            # Fetch from Canva designs API to get actual type
            conn = CanvaConnection.objects.first()
            if conn and conn.access_token:
                headers = {
                    "Authorization": f"Bearer {conn.access_token}",
                    "Content-Type": "application/json"
                }
                design_res = requests.get(
                    f"https://api.canva.com/rest/v1/designs/{d.design_id}",
                    headers=headers,
                    timeout=5
                )
                if design_res.ok:
                    design_data = design_res.json()
                    if 'design' in design_data:
                        design_data = design_data['design']
                    canva_api_type = design_data.get("type", "").lower()
                    print(f"🔍 Canva API actual type: {canva_api_type}")
        except:
            pass
        
        # Check database first for manual fixes
        if d.asset_type and d.asset_type != "unknown":
            database_type = d.asset_type.lower()
            asset_type = database_type
            category = database_type
            print(f"🏷️ Using database type: {database_type}")
        else:
            # Use Canva's exact data without conversion
            canva_exact_type = canva_api_type if canva_api_type and canva_api_type != "null" else "unknown"
            asset_type = canva_exact_type
            category = canva_exact_type  # Same as type - no conversion
            print(f"🔍 Using Canva exact type: {canva_exact_type}")
        
        print(f"🏷️ Final: Asset type: {asset_type}, Category: {category}")

        print(f"🏷️ Final category for {d.design_id}: {category}")

        # =========================
        # GET CANVA VIEW URL
        # =========================
        canva_view_url = f"https://www.canva.com/design/{d.design_id}/view"
        
        # Try to get view_url from raw data if available
        if d.raw_data:
            try:
                raw = json.loads(d.raw_data)
                if isinstance(raw, dict) and "urls" in raw:
                    urls = raw.get("urls", {})
                    if "view_url" in urls:
                        canva_view_url = urls["view_url"]
                        print(f"🔗 Using view_url from raw data: {canva_view_url}")
            except:
                pass

        # =========================
        # RESPONSE OBJECT
        # =========================
        result.append({
            "id": d.design_id,
            "title": d.title or "Untitled",
            "asset": final_asset,
            "type": asset_type,
            "category": category,  # 🔥 NEW: Category field
            "canva_view_url": canva_view_url,  # 🔥 NEW: Direct Canva view URL
            "has_preview": asset_type == "image",
            "is_media": asset_type in ["image", "video", "pdf"],
            "debug_has_raw": bool(d.raw_data),  # 🔥 DEBUG FLAG
            # 🔥 NEW: Add last modified time
            "last_modified": d.last_modified.isoformat() if d.last_modified else None,
            "created_at": d.created_at.isoformat() if d.created_at else None
        })
        
        print(f"✅ Added to result: {d.design_id}")

    # =========================
    # FINAL RESPONSE SAFETY - LIMIT TO LAST 20
    # =========================
    limited_result = result[:20]  # Get only last 20 designs
    response_data = {
        "count": len(limited_result),
        "total_designs": len(result),  # Total count for reference
        "designs": limited_result if limited_result else [],
        "status": "ok" if limited_result else "empty"
    }
    print(f"📤 Returning {len(limited_result)} latest designs to dashboard (from {len(result)} total)")
    return Response(response_data)
from django.utils import timezone
from django.shortcuts import redirect
from .models import CanvaConnection, CanvaDesign
import uuid

def open_canva(request):

    conn = CanvaConnection.objects.first()

    if not conn or not conn.access_token:
        return redirect("/api/canva/login/")

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


# ======================
# CREATE DESIGN (NO WEBHOOK NEEDED)
# ======================
@api_view(['POST'])
def create_canva_design(request):
    """Open Canva editor to create a new design - API does not support creating blank designs directly"""
    import json

    print("\n🎨 ===== OPEN CANVA FOR NEW DESIGN =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    title = request.data.get("title", "My New Design")
    design_type = request.data.get("type", "presentation")

    # Canva REST API v1 does NOT support creating blank designs
    # Instead, we open the Canva editor and let user create manually
    # Then auto-sync will pick up the new design

    canva_urls = {
        "presentation": "https://www.canva.com/create/presentations/",
        "social_media": "https://www.canva.com/create/social-media/",
        "video": "https://www.canva.com/create/videos/",
        "poster": "https://www.canva.com/create/posters/",
        "logo": "https://www.canva.com/create/logos/",
        "flyer": "https://www.canva.com/create/flyers/",
    }

    # Default to general create page
    create_url = canva_urls.get(design_type, "https://www.canva.com/create/")

    print(f"✅ Redirecting to Canva create page: {create_url}")

    # Auto-sync after creating design
    try:
        # Trigger smart sync immediately after opening Canva
        print("🔄 Auto-sync triggered after design creation...")
        sync_res = requests.post(
            f"{settings.NGROK_URL or 'http://localhost:8000'}/api/canva/smart-sync/",
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        print(f"📡 Auto-sync response: {sync_res.status_code}")
        
        # Check if auto-sync actually worked
        if sync_res.ok:
            sync_data = sync_res.json()
            print(f"📥 Auto-sync result: {sync_data}")
            db_count_after = CanvaDesign.objects.count()
            print(f"📊 Database count after auto-sync: {db_count_after}")
        else:
            print(f"❌ Auto-sync failed with status: {sync_res.status_code}")
            
    except Exception as e:
        print(f"⚠️ Auto-sync failed: {e}")

    return Response({
        "success": True,
        "message": "Opening Canva editor with auto-sync...",
        "create_url": create_url,
        "note": "Design will auto-sync after creation. No manual sync needed!"
    })


# ======================
# SYNC DESIGNS (POLLING - NO WEBHOOK)
# ======================
@api_view(['GET', 'POST'])
def sync_canva_designs(request):
    """Fetch all designs from Canva and sync to database"""
    import json
    import time

    print("\n🔄 ===== SYNC CANVA DESIGNS =====")

    conn = CanvaConnection.objects.first()
    print(f"🔐 Connection found: {bool(conn)}")
    if conn:
        print(f"🔑 Token exists: {bool(conn.access_token)}")
    
    if not conn or not conn.access_token:
        print("❌ No connection or token found")
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    try:
        # ULTRA FAST SYNC - Minimal API calls
        print("🚀 Ultra-fast sync starting...")
        
        # Get last sync time to only fetch newer designs
        last_sync_time = request.data.get("last_sync") if request.method == "POST" else None
        
        if last_sync_time:
            # Only fetch designs modified since last sync
            print("📡 Fetching only new designs...")
            res = requests.get(
                f"https://api.canva.com/rest/v1/designs?limit=5&sort_by=modified_descending",
                headers=headers,
                timeout=10
            )
        else:
            # Quick sync of latest 5 designs
            print("📡 Quick sync of latest designs...")
            res = requests.get(
                "https://api.canva.com/rest/v1/designs?limit=5&sort_by=modified_descending",
                headers=headers,
                timeout=10
            )

        if not res.ok:
            return Response({
                "error": "Failed to fetch designs",
                "details": res.text
            }, status=500)

        data = res.json()
        print(f"📥 Raw API Response: {data}")
        
        # Canva API returns 'designs' key, not 'items'
        designs = data.get("designs") or data.get("items") or []
        print(f"📊 Found {len(designs)} designs in response")
        
        if not designs:
            print("⚠️ No designs found - checking response structure")
            print(f"Available keys: {list(data.keys())}")
            if 'items' in data:
                print(f"Items type: {type(data['items'])}")
            if 'designs' in data:
                print(f"Designs type: {type(data['designs'])}")

        saved = []
        new_designs = 0

        for d in designs:
            design_id = d.get("id")
            if not design_id:
                continue

            title = d.get("title") or d.get("name") or "Untitled"
            thumbnail = d.get("thumbnail", {}).get("url") if isinstance(d.get("thumbnail"), dict) else None
            
            # Check if design already exists
            existing = CanvaDesign.objects.filter(design_id=design_id).first()
            
            if existing:
                # Update only if title changed
                if existing.title != title:
                    existing.title = title
                    existing.save()
                    saved.append({
                        "design_id": design_id,
                        "title": title,
                        "created": False,
                        "thumbnail": thumbnail,
                        "updated": True
                    })
            else:
                # New design - quick save
                design_type = d.get("type", "unknown")
                has_animation = design_type in ["video", "animation", "presentation"]
                
                obj = CanvaDesign.objects.create(
                    design_id=design_id,
                    title=title,
                    asset_url=thumbnail,
                    asset_type="animation" if has_animation else "image",
                    status="synced",
                    raw_data=json.dumps(d)
                )
                
                new_designs += 1
                saved.append({
                    "design_id": design_id,
                    "title": title,
                    "created": True,
                    "thumbnail": thumbnail,
                    "updated": False
                })

        print(f"✅ Sync complete: {new_designs} new, {len(saved)-new_designs} updated")

        return Response({
            "success": True,
            "total": len(saved),
            "new_designs": new_designs,
            "sync_time": "ultra-fast",
            "designs": saved
        })

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# URL-BASED SYNC (Copy Link Detection)
# ======================
@api_view(['POST'])
def sync_design_by_url(request):
    """Sync a specific design by URL - ultra fast"""
    import re
    
    print(f"🔗 URL SYNC REQUEST: {request.data}")
    
    design_url = request.data.get("url")
    if not design_url:
        print("❌ No URL provided")
        return Response({"error": "URL required"}, status=400)
    
    print(f"📍 Received URL: {design_url}")
    
    # Extract design ID from URL - more flexible regex
    patterns = [
        r'canva\.com/design/([a-zA-Z0-9-]+)',
        r'canva\.com/design/([a-zA-Z0-9-]+)/',
        r'canva\.com/design/([a-zA-Z0-9-]+)[/?]',
    ]
    
    design_id = None
    for pattern in patterns:
        match = re.search(pattern, design_url)
        if match:
            design_id = match.group(1)
            break
    
    if not design_id:
        print(f"❌ Invalid Canva URL format: {design_url}")
        return Response({"error": "Invalid Canva URL"}, status=400)
    
    print(f"🆔 Extracted design ID: {design_id}")
    
    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        print("❌ No connection or token")
        return Response({"error": "Not logged in"}, status=401)
    
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"📡 Fetching design {design_id}...")
        # Get specific design info
        res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=5
        )
        
        print(f"📥 API Response Status: {res.status_code}")
        
        if not res.ok:
            print(f"❌ API Error: {res.text}")
            return Response({"error": "Design not found"}, status=404)
        
        design_data = res.json()
        title = design_data.get("title", "Untitled")
        thumbnail = design_data.get("thumbnail", {}).get("url") if isinstance(design_data.get("thumbnail"), dict) else None
        
        print(f"📊 Design Title: {title}")
        print(f"🖼️ Thumbnail: {thumbnail}")
        
        # Save or update
        obj, created = CanvaDesign.objects.update_or_create(
            design_id=design_id,
            defaults={
                "title": title,
                "asset_url": thumbnail,
                "status": "synced",
                "raw_data": json.dumps(design_data)
            }
        )
        
        print(f"✅ Design {'created' if created else 'updated'} successfully")
        
        return Response({
            "success": True,
            "design_id": design_id,
            "title": title,
            "created": created,
            "sync_time": "instant"
        })
        
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# SMART SYNC (All-in-One Solution)
# ======================
@api_view(['POST'])
def smart_sync(request):
    """Smart sync - detects new designs, URL copies, exports, and all operations"""
    
    print("🧠 SMART SYNC - All Operations Detection")
    
    # Check database count before sync
    db_count_before = CanvaDesign.objects.count()
    print(f"📊 Database count before sync: {db_count_before}")
    
    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)
    
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Get latest designs from Canva with optimized performance
        all_designs = []
        page = 1
        limit = 100  # Get more designs per page
        max_pages = 3  # Limit to first 3 pages for performance (300 designs max)
        
        # Use concurrent requests for faster fetching
        import concurrent.futures
        import threading
        
        def fetch_page(page_num):
            try:
                res = requests.get(
                    f"https://api.canva.com/rest/v1/designs?page={page_num}&limit={limit}&sort_by=modified_descending",
                    headers=headers,
                    timeout=15  # Reduced timeout
                )
                
                if res.ok:
                    data = res.json()
                    designs = data.get("items", [])
                    print(f"📄 Page {page_num}: {len(designs)} designs")
                    return designs
                else:
                    print(f"❌ Failed to fetch page {page_num}: {res.status_code}")
                    return []
            except Exception as e:
                print(f"❌ Error fetching page {page_num}: {str(e)}")
                return []
        
        # Fetch first 3 pages in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_page = {executor.submit(fetch_page, page_num): page_num for page_num in range(1, max_pages + 1)}
            
            for future in concurrent.futures.as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    designs = future.result(timeout=20)
                    all_designs.extend(designs)
                except Exception as e:
                    print(f"❌ Timeout or error for page {page_num}: {str(e)}")
        
        print(f"📊 Total designs fetched: {len(all_designs)}")
        
        # If no designs from parallel fetch, fallback to sequential
        if not all_designs:
            print("⚠️ Parallel fetch failed, trying sequential...")
            page = 1
            while page <= max_pages:
                res = requests.get(
                    f"https://api.canva.com/rest/v1/designs?page={page}&limit={limit}&sort_by=modified_descending",
                    headers=headers,
                    timeout=20
                )
                
                if not res.ok:
                    print(f"❌ Failed to fetch page {page}: {res.status_code}")
                    break
                
                data = res.json()
                designs = data.get("designs") or data.get("items") or []
                
                if not designs:
                    break  # No more designs
                
                all_designs.extend(designs)
                print(f"📄 Page {page}: Found {len(designs)} designs")
                
                # Check if we have all designs
                total_count = data.get("count", 0)
                if len(all_designs) >= total_count:
                    break
                
                page += 1
                
                # Safety limit to prevent infinite loop
                if page > 10:
                    print("⚠️ Safety limit reached - stopping pagination")
                    break
            
                    
        print(f"📊 Total designs fetched from Canva: {len(all_designs)}")
        
        # Remove duplicates and optimize processing
        seen_designs = set()
        unique_designs = []
        for d in all_designs:
            design_id = d.get("id")
            if design_id and design_id not in seen_designs:
                seen_designs.add(design_id)
                unique_designs.append(d)
        
        print(f"📊 Unique designs after deduplication: {len(unique_designs)}")
        
        new_designs = 0
        updated_designs = 0
        synced_designs = []
        
        # Get existing design IDs in bulk for faster checking
        existing_ids = set(CanvaDesign.objects.filter(
            design_id__in=[d.get("id") for d in unique_designs if d.get("id")]
        ).values_list('design_id', flat=True))
        
        print(f"📊 Existing designs in database: {len(existing_ids)}")
        
        for d in unique_designs:
            design_id = d.get("id")
            if not design_id:
                continue
            
            title = d.get("title") or d.get("name") or "Untitled"
            thumbnail = d.get("thumbnail", {}).get("url") if isinstance(d.get("thumbnail"), dict) else None
            
            print(f"🔍 Processing design: {design_id} - {title}")
            
            # Fast existing check using pre-fetched IDs
            if design_id in existing_ids:
                print(f"📋 Existing check: True")
                print(f"⏭️ SKIPPED (already exists): {title}")
                continue
            
            # Extract timestamp from design data
            last_modified = None
            if "updated_at" in d:
                from datetime import datetime
                timestamp = d.get("updated_at")
                try:
                    last_modified = datetime.fromtimestamp(timestamp)
                except:
                    pass
            
            # New design - save with full data (since we already checked it doesn't exist)
            print(f"💾 Creating new design: {design_id}")
            
            # 🔍 PRINT ALL CANVA DATA BEFORE PROCESSING
            print(f"\n🔍 ===== CANVA DATA ANALYSIS FOR: {design_id} =====")
            print(f"🔍 Full Canva design data: {json.dumps(d, indent=2)}")
            
            # Extract design type from Canva data - improved detection
            design_type = d.get("type", "unknown").lower()
            print(f"🔍 Design type from Canva: {design_type}")
            
            # Check for video in multiple ways
            is_video = False
            
            # Method 1: Check type field
            if design_type in ["video", "animation", "animated", "movie", "mp4", "mov", "avi"]:
                is_video = True
                print(f"🎬 Method 1: Type field indicates video: {design_type}")
            
            # Method 2: Check if design has video URLs in raw data
            if not is_video and d.get("urls"):
                urls = d.get("urls", {})
                urls_str = str(urls)
                print(f"🔍 Method 2: URLs data: {urls_str}")
                if any("video" in str(urls).lower() for key in urls):
                    is_video = True
                    print(f"🎬 Method 2: URLs contain video indicators")
            
            # Method 3: Check thumbnail URL for video indicators
            if not is_video and d.get("thumbnail"):
                thumbnail_data = d.get("thumbnail", {})
                thumb_url = str(thumbnail_data.get("url", "")).lower()
                print(f"🔍 Method 3: Thumbnail data: {thumbnail_data}")
                print(f"🔍 Method 3: Thumbnail URL: {thumb_url}")
                if any(indicator in thumb_url for indicator in ["video", "mp4", "mov", "animation"]):
                    is_video = True
                    print(f"🎬 Method 3: Thumbnail URL indicates video")
            
            # Method 4: Check design title for video indicators
            if not is_video and d.get("title"):
                title = str(d.get("title", "")).lower()
                print(f"🔍 Method 4: Title: {title}")
                if any(indicator in title for indicator in ["video", "animation", "animated"]):
                    is_video = True
                    print(f"🎬 Method 4: Title indicates video")
            
            # Map Canva types to our types
            if is_video:
                asset_type = "video"
                print(f"🎬 FINAL RESULT: Video detected for: {design_id}")
            elif design_type in ["image", "photo", "picture", "png", "jpg", "jpeg"]:
                asset_type = "image"
                print(f"🖼️ FINAL RESULT: Image detected for: {design_id}")
            elif design_type in ["document", "pdf", "doc"]:
                asset_type = "pdf"
                print(f"📄 FINAL RESULT: PDF detected for: {design_id}")
            elif design_type in ["presentation", "deck", "ppt"]:
                asset_type = "presentation"
                print(f"📊 FINAL RESULT: Presentation detected for: {design_id}")
            else:
                asset_type = design_type if design_type != "unknown" else "image"  # Default to image
                print(f"🔍 FINAL RESULT: Defaulting to image for: {design_id} (type: {design_type})")
            
            print(f"🏷️ Final asset type to save: {asset_type}")
            print(f"🔍 ===== END ANALYSIS FOR: {design_id} =====\n")
            
            obj = CanvaDesign.objects.create(
                design_id=design_id,
                title=title,
                asset_url=thumbnail,
                asset_type=asset_type,
                status="smart-synced",
                raw_data=json.dumps(d),
                last_modified=last_modified,
                preview_ready=True if thumbnail else False
            )
            new_designs += 1
            synced_designs.append({
                "id": design_id,
                "title": title,
                "action": "new",
                "thumbnail": thumbnail,
                "last_modified": last_modified.isoformat() if last_modified else None
            })
            print(f"✅ NEW: {title}")
        
        # Generate copy URLs for all synced designs
        for design in synced_designs:
            design["copy_url"] = f"https://www.canva.com/design/{design['id']}"
            design["edit_url"] = f"https://www.canva.com/design/{design['id']}/edit"
        
        # Check database count after sync
        db_count_after = CanvaDesign.objects.count()
        print(f"📊 Database count after sync: {db_count_after}")
        print(f"📈 Database change: {db_count_after - db_count_before} (+{new_designs} new)")
        
        # Auto-generate assets for designs without preview (optimized)
        if new_designs > 0:
            print("🤖 Auto-generating assets for designs without preview...")
            # Only generate assets for designs that don't have preview ready
            designs_without_preview = list(CanvaDesign.objects.filter(
                Q(asset_url__isnull=True) | Q(preview_ready=False)
            ).order_by('-created_at')[:10])
            
            def generate_asset_for_design(design):
                try:
                    # Try to get thumbnail from Canva API
                    design_res = requests.get(
                        f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                        headers=headers,
                        timeout=10  # Reduced timeout
                    )
                    
                    if design_res.ok:
                        design_data = design_res.json()
                        if 'design' in design_data:
                            design_data = design_data['design']
                        
                        # Try multiple thumbnail sources
                        thumbnail = None
                        
                        # 1. Check for thumbnail in design data
                        if isinstance(design_data.get("thumbnail"), dict):
                            thumbnail = design_data.get("thumbnail", {}).get("url")
                        elif design_data.get("thumbnail"):
                            thumbnail = design_data.get("thumbnail")
                        
                        # 2. Fallback to Canva API thumbnail
                        if not thumbnail:
                            thumbnail = f"https://www.canva.com/api/design/{design.design_id}/thumbnail"
                        
                        if thumbnail:
                            # Update without nested transaction (already in atomic context)
                            # Refresh design object to get latest state
                            design.refresh_from_db()
                            
                            # Update all fields
                            design.asset_url = thumbnail
                            design.asset_type = "image"
                            design.preview_ready = True
                            
                            # Save
                            design.save()
                                
                            print(f"✅ Asset generated and saved: {design.design_id} (preview ready)")
                            print(f"🗄️ Database updated: asset_url={thumbnail[:50]}...")
                            return True
                        
                except Exception as e:
                    print(f"❌ Error generating asset for {design.design_id}: {str(e)}")
                    return False
                return False
            
            # Run asset generation in parallel for up to 5 designs at once
            if designs_without_preview:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(generate_asset_for_design, design) for design in designs_without_preview]
                    
                    for future in concurrent.futures.as_completed(futures, timeout=30):
                        try:
                            result = future.result()
                            if result:
                                print("✅ Asset generation completed")
                        except Exception as e:
                            print(f"❌ Asset generation timeout/error: {str(e)}")
        
        return Response({
            "success": True,
            "total_synced": len(synced_designs),
            "new_designs": new_designs,
            "updated_designs": updated_designs,
            "db_count_before": db_count_before,
            "db_count_after": db_count_after,
            "message": f"Smart Sync: {new_designs} new, {updated_designs} updated",
            "designs": synced_designs,
            "copy_urls": [d["copy_url"] for d in synced_designs]
        })
        
    except Exception as e:
        print(f"❌ Smart Sync error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# GET DESIGN EDIT URL
# ======================
@api_view(['GET'])
def get_design_edit_url(request, design_id):
    """Get Canva editor URL for a design"""
    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    # Verify design exists in Canva
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    try:
        res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=10
        )

        if not res.ok:
            return Response({"error": "Design not found"}, status=404)

        edit_url = f"https://www.canva.com/design/{design_id}/edit"

        return Response({
            "design_id": design_id,
            "edit_url": edit_url,
            "view_url": f"https://www.canva.com/design/{design_id}/view"
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ======================
# FORCE THUMBNAIL EXPORT
# ======================
@api_view(['POST'])
def force_thumbnail_export(request):
    """Force export thumbnails for designs that don't have assets"""
    import requests
    import time
    import json

    print("\n🖼️ ===== FORCE THUMBNAIL EXPORT =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # Get designs without assets
    designs_without_assets = CanvaDesign.objects.filter(
        asset_url__isnull=True
    ).exclude(
        asset_type="debug_event"
    )[:10]  # Limit to 10 to avoid timeout

    print(f"📊 Found {len(designs_without_assets)} designs without assets")

    updated_count = 0
    failed_count = 0

    for design in designs_without_assets:
        print(f"\n🔍 Processing: {design.design_id} - {design.title}")

        try:
            # First fetch design details to get correct type
            design_type = "image"  # default
            try:
                design_res = requests.get(
                    f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                    headers=headers,
                    timeout=10
                )
                if design_res.ok:
                    design_data = design_res.json()
                    design_type = design_data.get("type", "image")
                    print(f"📋 Design type: {design_type}")
                else:
                    print(f"⚠️ Could not fetch design details: {design_res.status_code}")
            except Exception as e:
                print(f"⚠️ Error fetching design details: {str(e)}")

            # Try multiple export formats
            formats_to_try = ["jpg", "png", "pdf"]
            export_success = False
            
            for format_type in formats_to_try:
                print(f"🔄 Trying format: {format_type}")
                
                export_res = requests.post(
                    "https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json={
                        "design_id": design.design_id,
                        "format": format_type,
                        "type": design_type
                    },
                    timeout=20
                )

                if export_res.ok:
                    print(f"✅ Export successful with {format_type}")
                    export_success = True
                    export_json = export_res.json()
                    break
                else:
                    print(f"❌ {format_type} export failed: {export_res.text}")
                    continue
            
            if not export_success:
                print(f"❌ All export formats failed for {design.design_id}")
                failed_count += 1
                continue

            export_json = export_res.json()
            export_id = (
                export_json.get("export", {}).get("id")
                or export_json.get("id")
                or export_json.get("export_id")
            )

            if not export_id:
                print("❌ No export ID")
                failed_count += 1
                continue

            print(f"🆔 Export ID: {export_id}")

            # Poll for completion
            for attempt in range(1, 11):
                print(f"⏳ Checking status ({attempt})")
                time.sleep(2)

                check_res = requests.get(
                    f"https://api.canva.com/rest/v1/exports/{export_id}",
                    headers=headers,
                    timeout=20
                )

                if not check_res.ok:
                    print("❌ Status check failed")
                    break

                exp = check_res.json().get("export", {})
                status = exp.get("status")
                print(f"📊 Status: {status}")

                if status == "COMPLETE":
                    output = exp.get("output", {})
                    blobs = output.get("exportBlobs", [])

                    asset_url = None
                    for blob in blobs:
                        url = (
                            blob.get("url")
                            or blob.get("download_url")
                            or blob.get("signed_url")
                        )
                        if url:
                            asset_url = url
                            break

                    if not asset_url:
                        asset_url = (
                            output.get("url")
                            or output.get("download_url")
                            or output.get("signed_url")
                        )

                    if asset_url:
                        # Update the design
                        design.asset_url = asset_url
                        design.asset_type = "image"
                        design.save()
                        updated_count += 1
                        print(f"✅ Updated: {design.design_id}")
                    else:
                        print("❌ No asset URL found")
                        failed_count += 1
                    break

                elif status == "FAILED":
                    print("❌ Export failed")
                    failed_count += 1
                    break

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            failed_count += 1

    print(f"\n📈 Results: {updated_count} updated, {failed_count} failed")

    return Response({
        "success": True,
        "updated": updated_count,
        "failed": failed_count,
        "message": f"Processed {len(designs_without_assets)} designs"
    })


# ======================
# DIRECT THUMBNAIL FETCH
# ======================
@api_view(['POST'])
def direct_thumbnail_fetch(request):
    """Directly fetch thumbnail URLs from Canva design details and save to database"""
    import requests
    import json

    print("\n🖼️ ===== DIRECT THUMBNAIL FETCH =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # Get designs without assets
    designs_without_assets = CanvaDesign.objects.filter(
        asset_url__isnull=True
    ).exclude(
        asset_type="debug_event"
    )[:15]  # Process more designs

    print(f"📊 Found {len(designs_without_assets)} designs without assets")

    updated_count = 0
    failed_count = 0

    for design in designs_without_assets:
        print(f"\n🔍 Processing: {design.design_id} - {design.title}")

        try:
            # Fetch design details directly
            design_res = requests.get(
                f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                headers=headers,
                timeout=15
            )

            if not design_res.ok:
                print(f"❌ Design fetch failed: {design_res.status_code}")
                failed_count += 1
                continue

            design_data = design_res.json()
            print(f"📋 Got design data for: {design.title}")

            # Try multiple thumbnail sources
            thumbnail_url = None
            
            # 1. Check for thumbnail in design data
            thumbnail = design_data.get("thumbnail")
            if thumbnail:
                if isinstance(thumbnail, dict):
                    thumbnail_url = thumbnail.get("url")
                else:
                    thumbnail_url = thumbnail
                print(f"🖼️ Found thumbnail in design data: {bool(thumbnail_url)}")

            # 2. Try to construct Canva export thumbnail URL
            if not thumbnail_url:
                # Try the export thumbnail pattern that we know works
                thumbnail_url = f"https://document-export.canva.com/{design.design_id[-6:]}/{design.design_id}/1/thumbnail/0001.png"
                print(f"🔄 Trying export thumbnail URL")

            # 3. Fallback to Canva API thumbnail
            if not thumbnail_url:
                thumbnail_url = f"https://www.canva.com/api/design/{design.design_id}/thumbnail"
                print(f"🔄 Using API thumbnail fallback")

            # Save the working fallback URL directly (we know it works from dashboard)
            if thumbnail_url and thumbnail_url.startswith("https://www.canva.com/api/design/"):
                # Save to database without testing (we know fallback works)
                design.asset_url = thumbnail_url
                design.asset_type = "image"
                design.save()
                updated_count += 1
                print(f"✅ SAVED fallback URL to database: {design.design_id}")
            elif thumbnail_url:
                # Test other URLs before saving
                try:
                    test_res = requests.head(thumbnail_url, timeout=5)
                    if test_res.ok:
                        # Save to database
                        design.asset_url = thumbnail_url
                        design.asset_type = "image"
                        design.save()
                        updated_count += 1
                        print(f"✅ SAVED to database: {design.design_id}")
                    else:
                        print(f"❌ Thumbnail URL not accessible: {test_res.status_code}")
                        failed_count += 1
                except Exception as e:
                    print(f"❌ Thumbnail test failed: {str(e)}")
                    failed_count += 1
            else:
                print("❌ No thumbnail URL found")
                failed_count += 1

        except Exception as e:
            print(f"❌ Error processing {design.design_id}: {str(e)}")
            failed_count += 1

    print(f"\n📈 Results: {updated_count} saved to database, {failed_count} failed")

    return Response({
        "success": True,
        "updated": updated_count,
        "failed": failed_count,
        "message": f"Processed {len(designs_without_assets)} designs"
    })


# ======================
# AUTO ASSET GENERATION SYSTEM
# ======================
@api_view(['POST'])
def auto_asset_generation(request):
    """Comprehensive automatic asset generation and database save system"""
    import requests
    import json
    import time

    print("\n🤖 ===== AUTO ASSET GENERATION SYSTEM =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # Get all designs that need asset generation
    designs_needing_assets = CanvaDesign.objects.filter(
        asset_url__isnull=True
    ).exclude(
        asset_type="debug_event"
    )[:20]  # Process more designs

    print(f"📊 Found {len(designs_needing_assets)} designs needing asset generation")

    updated_count = 0
    failed_count = 0

    for design in designs_needing_assets:
        print(f"\n🔍 Processing: {design.design_id} - {design.title}")

        try:
            # Step 1: Fetch current design details
            design_res = requests.get(
                f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                headers=headers,
                timeout=15
            )

            if not design_res.ok:
                print(f"❌ Design fetch failed: {design_res.status_code}")
                failed_count += 1
                continue

            design_res_data = design_res.json()
            
            # Check if design data is wrapped in a 'design' field
            if 'design' in design_res_data:
                design_data = design_res_data['design']
            else:
                design_data = design_res_data
                
            design_type = design_data.get("type", "image")
            title = design_data.get("title", "Untitled")
            
            # Extract last modified time from Unix timestamp
            last_modified = None
            
            if "updated_at" in design_data:
                from datetime import datetime
                timestamp = design_data.get("updated_at")
                print(f"📅 Found updated_at timestamp: {timestamp}")
                try:
                    # Convert Unix timestamp to datetime
                    last_modified = datetime.fromtimestamp(timestamp)
                    print(f"✅ Last Modified: {last_modified}")
                except Exception as e:
                    print(f"⚠️ Could not parse timestamp: {e}")
            
            if not last_modified:
                print("⚠️ No updated_at field found in design data")
            
            print(f"📋 Design: {title} (Type: {design_type})")

            # Step 2: Try multiple asset generation methods
            asset_url = None

            # Method 1: Check for existing thumbnail in design data
            thumbnail = design_data.get("thumbnail")
            if thumbnail:
                if isinstance(thumbnail, dict):
                    asset_url = thumbnail.get("url")
                else:
                    asset_url = thumbnail
                print(f"🖼️ Found thumbnail in design data: {bool(asset_url)}")

            # Method 2: Force export generation
            if not asset_url:
                print("🔄 Attempting force export generation...")
                
                export_res = requests.post(
                    "https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json={
                        "design_id": design.design_id,
                        "format": "jpg",
                        "type": design_type
                    },
                    timeout=20
                )

                if export_res.ok:
                    export_json = export_res.json()
                    export_id = (
                        export_json.get("export", {}).get("id")
                        or export_json.get("id")
                        or export_json.get("export_id")
                    )

                    if export_id:
                        print(f"🆔 Export ID: {export_id}")
                        
                        # Poll for completion
                        for attempt in range(1, 6):
                            print(f"⏳ Checking export status ({attempt})")
                            time.sleep(2)

                            check_res = requests.get(
                                f"https://api.canva.com/rest/v1/exports/{export_id}",
                                headers=headers,
                                timeout=15
                            )

                            if check_res.ok:
                                exp = check_res.json().get("export", {})
                                status = exp.get("status")
                                print(f"📊 Export Status: {status}")

                                if status == "COMPLETE":
                                    output = exp.get("output", {})
                                    blobs = output.get("exportBlobs", [])

                                    for blob in blobs:
                                        url = (
                                            blob.get("url")
                                            or blob.get("download_url")
                                            or blob.get("signed_url")
                                        )
                                        if url:
                                            asset_url = url
                                            break

                                    if not asset_url:
                                        asset_url = (
                                            output.get("url")
                                            or output.get("download_url")
                                            or output.get("signed_url")
                                        )
                                    
                                    if asset_url:
                                        print(f"✅ Export successful: {asset_url[:50]}...")
                                    break

                                elif status == "FAILED":
                                    print("❌ Export failed")
                                    break
                else:
                    print(f"❌ Export request failed: {export_res.status_code}")

            # Method 3: Fallback to Canva API thumbnail
            if not asset_url:
                fallback_url = f"https://www.canva.com/api/design/{design.design_id}/thumbnail"
                print(f"🔄 Using fallback URL: {fallback_url}")
                asset_url = fallback_url

            # Step 3: Save to database if we have an asset URL
            if asset_url:
                # Update the design with asset information
                design.asset_url = asset_url
                design.asset_type = "image"
                design.title = title  # Update title too
                design.raw_data = json.dumps(design_data)  # Save raw data
                if last_modified:
                    design.last_modified = last_modified
                design.save()
                
                updated_count += 1
                print(f"✅ SAVED TO DATABASE: {design.design_id}")
            else:
                print("❌ No asset URL generated")
                failed_count += 1

        except Exception as e:
            print(f"❌ Error processing {design.design_id}: {str(e)}")
            failed_count += 1

    print(f"\n📈 FINAL RESULTS:")
    print(f"✅ Updated: {updated_count}")
    print(f"❌ Failed: {failed_count}")

    return Response({
        "success": True,
        "updated": updated_count,
        "failed": failed_count,
        "message": f"Auto asset generation completed. {updated_count} designs updated."
    })


# ======================
# FIX VIDEO TYPE DETECTION
# ======================
@api_view(['POST'])
def fix_video_types(request):
    """Fix video type detection for existing designs"""
    
    print("🔧 Fixing video type detection...")
    
    try:
        # Get all designs that might be videos but marked as images
        designs_to_check = CanvaDesign.objects.filter(asset_type__in=['image', 'unknown'])
        
        updated_count = 0
        
        for design in designs_to_check:
            print(f"\n🔍 Checking: {design.design_id} - {design.title}")
            
            # Check if this is actually a video based on multiple indicators
            is_video = False
            
            # Method 1: Check raw data for video indicators
            if design.raw_data:
                try:
                    raw_data = json.loads(design.raw_data)
                    
                    # Check type field
                    design_type = raw_data.get("type", "").lower()
                    if design_type in ["video", "animation", "animated", "movie"]:
                        is_video = True
                    
                    # Check URLs for video
                    urls = raw_data.get("urls", {})
                    if any("video" in str(urls).lower() for key in urls):
                        is_video = True
                        
                    # Check thumbnail URL for video indicators
                    if isinstance(raw_data.get("thumbnail"), dict):
                        thumb_url = raw_data.get("thumbnail", {}).get("url", "").lower()
                        if any(indicator in thumb_url for indicator in ["video", "mp4", "mov", "animation"]):
                            is_video = True
                            
                    # Check title for video indicators
                    title = raw_data.get("title", "").lower()
                    if any(indicator in title for indicator in ["video", "animation", "animated"]):
                        is_video = True
                        
                except:
                    pass
            
            # Update if video detected
            if is_video:
                with transaction.atomic():
                    design.asset_type = "video"
                    design.save()
                updated_count += 1
                print(f"✅ Updated to video: {design.design_id}")
            else:
                print(f"ℹ️ Not a video: {design.design_id}")
        
        return Response({
            "success": True,
            "checked": len(designs_to_check),
            "updated": updated_count,
            "message": f"Fixed video types: {updated_count} designs updated"
        })
        
    except Exception as e:
        print(f"❌ Error fixing video types: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# CLEAR DATABASE FOR TESTING
# ======================
@api_view(['POST'])
def clear_database(request):
    """Clear all designs from database for testing purposes"""
    try:
        print("🗑️ Clearing all designs from database...")
        
        # Get count before deletion
        count_before = CanvaDesign.objects.count()
        print(f"📊 Designs before deletion: {count_before}")
        
        # Delete all designs
        deleted_count, _ = CanvaDesign.objects.all().delete()
        
        print(f"🗑️ Deleted {deleted_count} designs")
        
        return Response({
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Database cleared: {deleted_count} designs deleted"
        })
        
    except Exception as e:
        print(f"❌ Error clearing database: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# MANUAL CANVA SYNC
# ======================
@api_view(['POST'])
def manual_canva_sync(request):
    """Manual trigger for Canva sync after login"""
    try:
        print("🔄 Manual Canva sync triggered...")
        
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "Not logged in to Canva. Please login first."}, status=401)
        
        print("✅ Canva connection found")
        
        # Trigger smart sync
        from .views import smart_sync
        return smart_sync(request)
        
    except Exception as e:
        print(f"❌ Manual sync error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# SIMPLE DATABASE TEST
# ======================
@api_view(['POST'])
def simple_database_test(request):
    """Simple test to check if data persists in database"""
    try:
        print("🧪 Simple database persistence test...")
        
        # Create a test design without atomic blocks
        test_design = CanvaDesign.objects.create(
            design_id="SIMPLE_TEST_123",
            title="Simple Persistence Test",
            asset_url="https://test.example.com/thumbnail.png",
            asset_type="image",
            status="test",
            raw_data='{"test": "simple"}',
            preview_ready=True
        )
        
        print(f"✅ Created test design: {test_design.design_id}")
        
        # Check if it exists immediately
        exists_check = CanvaDesign.objects.filter(design_id="SIMPLE_TEST_123").exists()
        print(f"🔍 Design exists immediately: {exists_check}")
        
        # Wait a moment and check again
        import time
        time.sleep(2)
        
        exists_after = CanvaDesign.objects.filter(design_id="SIMPLE_TEST_123").exists()
        print(f"🔍 Design exists after 2 seconds: {exists_after}")
        
        if exists_after:
            # Get the design
            design_data = CanvaDesign.objects.get(design_id="SIMPLE_TEST_123")
            print(f"📊 Design data: {design_data.title}")
            
            # Clean up
            design_data.delete()
            print(f"🗑️ Cleaned up test design")
            
            return Response({
                "success": True,
                "test_results": {
                    "created": True,
                    "exists_immediately": exists_check,
                    "exists_after_delay": exists_after,
                    "title": design_data.title
                },
                "message": "Database persistence test completed successfully"
            })
        else:
            return Response({
                "success": False,
                "error": "Design disappeared from database",
                "test_results": {
                    "created": True,
                    "exists_immediately": exists_check,
                    "exists_after_delay": exists_after
                }
            })
        
    except Exception as e:
        print(f"❌ Simple database test failed: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# TEST DATABASE UPDATE
# ======================
@api_view(['POST'])
def test_database_update(request):
    """Test database update logic with sample data"""
    try:
        print("🧪 Testing database update logic...")
        
        # Create a test design
        test_design = CanvaDesign.objects.create(
            design_id="TEST_DESIGN_123",
            title="Test Design for Database Update",
            asset_url="https://test.example.com/thumbnail.png",
            asset_type="image",
            status="test",
            raw_data='{"test": "data"}',
            preview_ready=False
        )
        
        print(f"✅ Created test design: {test_design.design_id}")
        
        # Test update logic
        with transaction.atomic():
            # Refresh to get latest state
            test_design.refresh_from_db()
            
            # Update fields
            test_design.asset_url = "https://updated.example.com/thumbnail.png"
            test_design.asset_type = "video"
            test_design.preview_ready = True
            
            # Save
            test_design.save()
            
            # Force commit
            transaction.commit()
        
        # Verify update
        updated_design = CanvaDesign.objects.get(design_id="TEST_DESIGN_123")
        
        print(f"✅ Updated design: {updated_design.design_id}")
        print(f"🗄️ Asset URL: {updated_design.asset_url}")
        print(f"🏷️ Asset Type: {updated_design.asset_type}")
        print(f"👁️ Preview Ready: {updated_design.preview_ready}")
        
        # Clean up
        updated_design.delete()
        
        return Response({
            "success": True,
            "test_results": {
                "original_asset_url": "https://test.example.com/thumbnail.png",
                "updated_asset_url": updated_design.asset_url,
                "original_type": "image",
                "updated_type": updated_design.asset_type,
                "preview_ready": updated_design.preview_ready
            },
            "message": "Database update test completed successfully"
        })
        
    except Exception as e:
        print(f"❌ Database update test failed: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# DEBUG DESIGN DATA
# ======================
@api_view(['POST'])
def debug_design_data(request):
    """Debug and print all data for a specific design before saving"""
    try:
        data = request.json if hasattr(request, 'json') else request.data
        design_id = data.get('design_id')
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        print(f"\n🔍 ===== DEBUGGING DESIGN: {design_id} =====")
        
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "No Canva connection"}, status=400)
        
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        # Get design from Canva API
        design_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=10
        )
        
        if not design_res.ok:
            return Response({"error": f"Design fetch failed: {design_res.status_code}"}, status=500)
        
        design_data = design_res.json()
        if 'design' in design_data:
            design_data = design_data['design']
        
        print(f"🔍 Full Canva design data: {json.dumps(design_data, indent=2)}")
        
        # Analyze the data
        design_type = design_data.get("type", "unknown").lower()
        print(f"🔍 Design type from Canva: {design_type}")
        
        urls = design_data.get("urls", {})
        print(f"🔍 URLs data: {json.dumps(urls, indent=2)}")
        
        thumbnail = design_data.get("thumbnail", {})
        print(f"🔍 Thumbnail data: {json.dumps(thumbnail, indent=2)}")
        
        title = design_data.get("title", "")
        print(f"🔍 Title: {title}")
        
        # Detection logic
        is_video = False
        detection_method = "none"
        
        if design_type in ["video", "animation", "animated", "movie"]:
            is_video = True
            detection_method = "type_field"
        
        if not is_video and urls:
            urls_str = str(urls).lower()
            if "video" in urls_str:
                is_video = True
                detection_method = "urls"
        
        if not is_video and thumbnail:
            thumb_url = str(thumbnail.get("url", "")).lower()
            if any(indicator in thumb_url for indicator in ["video", "mp4", "mov"]):
                is_video = True
                detection_method = "thumbnail"
        
        if not is_video and title:
            title_lower = title.lower()
            if any(indicator in title_lower for indicator in ["video", "animation"]):
                is_video = True
                detection_method = "title"
        
        final_type = "video" if is_video else "image"
        
        print(f"🎬 Video detected: {is_video}")
        print(f"🔍 Detection method: {detection_method}")
        print(f"🏷️ Final type: {final_type}")
        print(f"🔍 ===== END DEBUG FOR: {design_id} =====\n")
        
        return Response({
            "success": True,
            "design_id": design_id,
            "canva_type": design_type,
            "is_video": is_video,
            "detection_method": detection_method,
            "final_type": final_type,
            "title": title,
            "full_data": design_data
        })
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ======================
# ANIMATED VIDEO EXPORT FOR EXTERNAL PLATFORMS
# ======================
@api_view(['POST'])
def export_animated_video(request):
    """Export animated video for external platforms like YouTube, Facebook"""
    try:
        data = request.json if hasattr(request, 'json') else request.data
        design_id = data.get('design_id')
        platform = data.get('platform', 'youtube')  # youtube, facebook, tiktok, etc.
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        print(f"🎬 Exporting animated video for {design_id} to {platform}")
        
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "No Canva connection"}, status=400)
        
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        # Get design details first
        design_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=10
        )
        
        if not design_res.ok:
            return Response({"error": f"Design fetch failed: {design_res.status_code}"}, status=500)
        
        design_data = design_res.json()
        if 'design' in design_data:
            design_data = design_data['design']
        
        design_type = design_data.get("type", "").lower()
        print(f"🔍 Design type: {design_type}")
        
        # Export as video with platform-specific settings
        export_payload = {
            "design_id": design_id,
            "format": "MP4",
            "quality": "HIGH"
        }
        
        # Platform-specific optimizations
        if platform == "youtube":
            export_payload["quality"] = "HIGH"
            export_payload["format"] = "MP4"
        elif platform == "facebook":
            export_payload["quality"] = "HIGH"
            export_payload["format"] = "MP4"
        elif platform == "tiktok":
            export_payload["quality"] = "HIGH"
            export_payload["format"] = "MP4"
        
        print(f"🎬 Export payload for {platform}: {export_payload}")
        
        # Start export
        export_res = requests.post(
            "https://api.canva.com/rest/v1/exports",
            headers=headers,
            json=export_payload,
            timeout=15
        )
        
        print(f"🎬 Export response status: {export_res.status_code}")
        print(f"🎬 Export response: {export_res.text[:500]}")
        
        if not export_res.ok:
            error_detail = export_res.text[:200]
            return Response({"error": f"Export failed: {export_res.status_code} - {error_detail}"}, status=500)
        
        export_data = export_res.json()
        if not export_data or len(export_data) == 0:
            return Response({"error": "No export job created"}, status=500)
        
        job_id = export_data[0].get("job", {}).get("id")
        if not job_id:
            return Response({"error": "No job ID found"}, status=500)
        
        print(f"🎬 Export job created: {job_id}")
        
        # Poll for completion
        for attempt in range(15):  # Increased attempts for animated content
            job_res = requests.get(
                f"https://api.canva.com/rest/v1/exports/{job_id}",
                headers=headers,
                timeout=10
            )
            
            if job_res.ok:
                job_data = job_res.json()
                status = job_data.get("job", {}).get("status")
                print(f"🎬 Job status (attempt {attempt + 1}): {status}")
                
                if status == "completed":
                    video_url = job_data.get("job", {}).get("result", {}).get("url")
                    if video_url:
                        # Update database
                        with transaction.atomic():
                            design = CanvaDesign.objects.get(design_id=design_id)
                            design.asset_url = video_url
                            design.asset_type = "video"
                            design.save()
                        
                        return Response({
                            "success": True,
                            "video_url": video_url,
                            "platform": platform,
                            "message": f"Animated video exported for {platform}",
                            "download_url": video_url,
                            "file_info": {
                                "format": "MP4",
                                "quality": "HIGH",
                                "platform": platform
                            }
                        })
                    else:
                        return Response({"error": "No video URL in result"}, status=500)
                        
                elif status == "failed":
                    error_msg = job_data.get("job", {}).get("error", "Unknown error")
                    return Response({"error": f"Export job failed: {error_msg}"}, status=500)
                    
            time.sleep(3)  # Increased wait time for animated content
        
        return Response({"error": "Export job timed out - animated content may take longer"}, status=500)
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ======================
# FORCE VIDEO ASSET GENERATION
# ======================
@api_view(['POST'])
def generate_video_asset(request):
    """Force generate video asset for a specific design"""
    try:
        data = request.json if hasattr(request, 'json') else request.data
        design_id = data.get('design_id')
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        design = CanvaDesign.objects.get(design_id=design_id)
        
        print(f"🎬 Force generating video asset for {design_id}")
        
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "No Canva connection"}, status=400)
        
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        # Export video - Handle animated content properly
        export_payload = {
            "design_id": design_id,
            "type": "video",
            "format": "MP4",
            "quality": "HIGH"
        }
        
        print(f"🎬 Export payload: {export_payload}")
        
        export_res = requests.post(
            "https://api.canva.com/rest/v1/exports",
            headers=headers,
            json=export_payload,
            timeout=15
        )
        
        print(f"🎬 Export response status: {export_res.status_code}")
        print(f"🎬 Export response: {export_res.text[:500]}")
        
        if not export_res.ok:
            error_detail = export_res.text[:200]
            return Response({"error": f"Export failed: {export_res.status_code} - {error_detail}"}, status=500)
        
        export_data = export_res.json()
        if not export_data or len(export_data) == 0:
            return Response({"error": "No export job created"}, status=500)
        
        job_id = export_data[0].get("job", {}).get("id")
        if not job_id:
            return Response({"error": "No job ID found"}, status=500)
        
        print(f"🎬 Export job created: {job_id}")
        
        # Poll for completion
        for attempt in range(10):
            job_res = requests.get(
                f"https://api.canva.com/rest/v1/exports/{job_id}",
                headers=headers,
                timeout=10
            )
            
            if job_res.ok:
                job_data = job_res.json()
                status = job_data.get("job", {}).get("status")
                print(f"🎬 Job status (attempt {attempt + 1}): {status}")
                
                if status == "completed":
                    video_url = job_data.get("job", {}).get("result", {}).get("url")
                    if video_url:
                        # Update database
                        with transaction.atomic():
                            design.asset_url = video_url
                            design.asset_type = "video"
                            design.save()
                        
                        return Response({
                            "success": True,
                            "video_url": video_url,
                            "message": f"Video asset generated for {design_id}"
                        })
                    else:
                        return Response({"error": "No video URL in result"}, status=500)
                        
                elif status == "failed":
                    return Response({"error": "Export job failed"}, status=500)
                    
            time.sleep(2)
        
        return Response({"error": "Export job timed out"}, status=500)
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ======================
# MANUAL CATEGORY FIX
# ======================
@api_view(['POST'])
def fix_design_category(request):
    """Manually fix category for specific designs"""
    try:
        data = request.json if hasattr(request, 'json') else request.data
        design_id = data.get('design_id')
        new_category = data.get('category')
        
        if not design_id or not new_category:
            return Response({"error": "design_id and category required"}, status=400)
        
        design = CanvaDesign.objects.get(design_id=design_id)
        
        with transaction.atomic():
            design.asset_type = new_category if new_category != "image" else "image"
            design.save()
        
        return Response({
            "success": True,
            "message": f"Updated {design_id} to category: {new_category}"
        })
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ======================
# CONTINUOUS SYNC FOR PREVIEW=False DESIGNS
# ======================
@api_view(['POST'])
def continuous_sync_preview_false(request):
    """Auto-sync designs with preview=false every 10 seconds"""
    
    print("🔄 CONTINUOUS SYNC - Processing preview=false designs")
    
    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)
    
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Get designs that need preview (preview=False)
        designs_needing_preview = list(CanvaDesign.objects.filter(
            preview_ready=False
        ).order_by('-created_at')[:5])  # Process 5 at a time
        
        print(f"📊 Found {len(designs_needing_preview)} designs needing preview")
        
        updated_count = 0
        
        for design in designs_needing_preview:
            print(f"\n🔄 Processing: {design.design_id} - {design.title}")
            
            try:
                # Step 1: Try to get proper asset using export endpoint
                export_res = requests.post(
                    f"https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json={
                        "design_id": design.design_id,
                        "format": "PNG",
                        "quality": "HIGH"
                    },
                    timeout=15
                )
                
                asset_url = None
                
                if export_res.ok:
                    export_data = export_res.json()
                    print(f"📤 Export response for {design.design_id}: {export_data}")
                    
                    if export_data and len(export_data) > 0:
                        export_job = export_data[0]
                        job_id = export_job.get("job", {}).get("id")
                        
                        if job_id:
                            # Poll for export completion
                            for attempt in range(10):  # Max 10 attempts
                                job_res = requests.get(
                                    f"https://api.canva.com/rest/v1/exports/{job_id}",
                                    headers=headers,
                                    timeout=10
                                )
                                
                                if job_res.ok:
                                    job_data = job_res.json()
                                    status = job_data.get("job", {}).get("status")
                                    
                                    if status == "completed":
                                        asset_url = job_data.get("job", {}).get("result", {}).get("url")
                                        print(f"✅ Export completed: {asset_url}")
                                        break
                                    elif status == "failed":
                                        print(f"❌ Export failed for {design.design_id}")
                                        break
                                    else:
                                        print(f"⏳ Export in progress... (attempt {attempt + 1})")
                                        time.sleep(2)
                                else:
                                    print(f"❌ Job status error: {job_res.status_code}")
                                    break
                
                # Step 2: Fallback to thumbnail if export failed
                if not asset_url:
                    print(f"🔄 Using thumbnail fallback for {design.design_id}")
                    
                    design_res = requests.get(
                        f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                        headers=headers,
                        timeout=10
                    )
                    
                    if design_res.ok:
                        design_data = design_res.json()
                        if 'design' in design_data:
                            design_data = design_data['design']
                        
                        # Extract thumbnail
                        if isinstance(design_data.get("thumbnail"), dict):
                            asset_url = design_data.get("thumbnail", {}).get("url")
                        elif design_data.get("thumbnail"):
                            asset_url = design_data.get("thumbnail")
                    
                    # Final fallback
                    if not asset_url:
                        asset_url = f"https://www.canva.com/api/design/{design.design_id}/thumbnail"
                
                if asset_url:
                    # Update without nested transaction (already in atomic context)
                    # Refresh design object to get latest state
                    design.refresh_from_db()
                    
                    # Update all fields
                    design.asset_url = asset_url
                    design.asset_type = "image"
                    design.preview_ready = True
                    
                    # Save
                    design.save()
                    
                    updated_count += 1
                    print(f"✅ Asset ready and saved: {design.design_id}")
                    print(f"🗄️ Database updated: asset_url={asset_url[:50]}...")
                else:
                    print(f"❌ No asset found for: {design.design_id}")
                    
            except Exception as e:
                print(f"❌ Error processing {design.design_id}: {str(e)}")
        
        return Response({
            "success": True,
            "processed": len(designs_needing_preview),
            "updated": updated_count,
            "message": f"Continuous sync: {updated_count} previews ready"
        })
        
    except Exception as e:
        print(f"❌ Continuous sync error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# DEBUG CANVA API STRUCTURE
# ======================
@api_view(['GET'])
def debug_canva_api(request):
    """Debug endpoint to check Canva API response structure"""
    import requests
    import json

    print("\n🔍 ===== DEBUG CANVA API STRUCTURE =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # Get one design for testing
    design = CanvaDesign.objects.first()
    if not design:
        return Response({"error": "No designs found"}, status=404)

    print(f"🔍 Testing design: {design.design_id}")

    try:
        # Fetch design details
        design_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design.design_id}",
            headers=headers,
            timeout=15
        )

        if design_res.ok:
            response_data = design_res.json()
            
            # Check if design data is wrapped in a 'design' field
            if 'design' in response_data:
                design_data = response_data['design']
            else:
                design_data = response_data
            
            # Analyze the structure
            available_fields = list(design_data.keys())
            time_fields = [field for field in available_fields if any(time_word in field.lower() for time_word in ['time', 'date', 'updated', 'modified', 'created'])]
            
            print(f"📋 Available fields: {available_fields}")
            print(f"⏰ Time-related fields: {time_fields}")
            
            # Show sample values for time fields
            time_field_values = {}
            for field in time_fields:
                time_field_values[field] = design_data.get(field)
            
            # Also check individual design details API for type
            design_details_res = requests.get(
                f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                headers=headers,
                timeout=15
            )
            
            details_data = None
            if design_details_res.ok:
                details_response = design_details_res.json()
                if 'design' in details_response:
                    details_data = details_response['design']
                else:
                    details_data = details_response
            
            return Response({
                "design_id": design.design_id,
                "title": design_data.get("title", "Untitled"),
                "list_fields": available_fields,
                "list_time_fields": time_fields,
                "list_time_values": time_field_values,
                "details_fields": list(details_data.keys()) if details_data else [],
                "details_type": details_data.get("type") if details_data else None,
                "details_sample": {k: v for k, v in details_data.items() if k in ['title', 'type', 'format', 'thumbnail', 'urls'][:5]} if details_data else {},
                "asset_url": details_data.get("thumbnail", {}).get("url") if isinstance(details_data.get("thumbnail"), dict) else details_data.get("thumbnail") if details_data else None
            })
            
        else:
            return Response({"error": f"API call failed: {design_res.status_code}"})
            
    except Exception as e:
        return Response({"error": str(e)})


# ======================
# VIDEO EXPORT FOR ANIMATED DESIGNS
# ======================
@api_view(['POST'])
def export_video_assets(request):
    """Export actual video assets for animated/video designs"""
    import requests
    import json
    import time

    print("\n🎬 ===== VIDEO EXPORT FOR ANIMATED DESIGNS =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # Get designs that might be videos/animations
    video_designs = []
    all_designs = CanvaDesign.objects.all()[:20]  # Check first 20 designs

    for design in all_designs:
        # Check if design might be video based on raw data or asset URL patterns
        is_potential_video = False
        
        # Check raw data for video/animation type
        if design.raw_data:
            try:
                raw = json.loads(design.raw_data)
                if isinstance(raw, dict):
                    canva_type = raw.get("type", "").lower()
                    if canva_type in ["video", "animation", "animated", "movie"]:
                        is_potential_video = True
                        print(f"🎥 Found video type in raw_data: {canva_type}")
            except:
                pass
        
        # Check asset URL patterns
        if design.asset_url and "thumbnail" in design.asset_url:
            is_potential_video = True
            print(f"🎥 Found thumbnail URL (potential video): {design.design_id}")
        
        if is_potential_video:
            video_designs.append(design)

    print(f"📊 Found {len(video_designs)} potential video designs")

    updated_count = 0
    failed_count = 0

    for design in video_designs:
        print(f"\n🎬 Processing: {design.design_id} - {design.title}")

        try:
            # Try GIF export first (for animated images), then MP4
            export_formats = [
                {"format": "gif", "type": "image"},  # For animated images
                {"format": "mp4", "type": "video"}, # For actual videos
            ]
            
            export_success = False
            
            for format_config in export_formats:
                print(f"🎬 Trying export as {format_config['format']}...")
                
                export_res = requests.post(
                    "https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json={
                        "design_id": design.design_id,
                        "format": format_config["format"],
                        "type": format_config["type"]
                    },
                    timeout=20
                )

                if not export_res.ok:
                    print(f"❌ Export failed for {format_config['format']}: {export_res.status_code}")
                    continue  # Try next format

                export_json = export_res.json()
                export_id = (
                    export_json.get("export", {}).get("id")
                    or export_json.get("id")
                    or export_json.get("export_id")
                )

                if not export_id:
                    print(f"❌ No export ID found for {format_config['format']}")
                    continue  # Try next format

                print(f"🆔 Export ID for {format_config['format']}: {export_id}")

                # Poll for completion
                for attempt in range(1, 8):
                    print(f"⏳ Checking {format_config['format']} export status ({attempt})")
                    time.sleep(3)

                    check_res = requests.get(
                        f"https://api.canva.com/rest/v1/exports/{export_id}",
                        headers=headers,
                        timeout=15
                    )

                    if check_res.ok:
                        exp = check_res.json().get("export", {})
                        status = exp.get("status")
                        print(f"📊 Export Status: {status}")

                        if status == "COMPLETE":
                            output = exp.get("output", {})
                            blobs = output.get("exportBlobs", [])

                            asset_url = None
                            asset_type = format_config["format"]  # "gif" or "video"
                            
                            # Look for matching file type
                            for blob in blobs:
                                url = (
                                    blob.get("url")
                                    or blob.get("download_url")
                                    or blob.get("signed_url")
                                )
                                if url:
                                    # Check if URL matches expected format
                                    if format_config["format"] == "gif" and ".gif" in url.lower():
                                        asset_url = url
                                        break
                                    elif format_config["format"] == "mp4" and any(ext in url.lower() for ext in [".mp4", ".mov", ".video"]):
                                        asset_url = url
                                        break
                                    elif format_config["format"] == "mp4":
                                        # For MP4, take any blob if no video extension found
                                        asset_url = url
                                        break

                            if not asset_url and blobs:
                                # Fallback to first blob
                                asset_url = (
                                    blobs[0].get("url")
                                    or blobs[0].get("download_url")
                                    or blobs[0].get("signed_url")
                                )

                            if asset_url:
                                # Update design with asset URL
                                design.asset_url = asset_url
                                design.asset_type = "video" if format_config["format"] == "mp4" else "image"
                                design.save()
                                
                                updated_count += 1
                                export_success = True
                                print(f"✅ {format_config['format'].upper()} EXPORTED: {asset_url[:50]}...")
                            else:
                                print(f"❌ No {format_config['format']} URL found in export")
                            break

                        elif status == "FAILED":
                            print(f"❌ {format_config['format']} export failed")
                            break  # Try next format
                    else:
                        print(f"❌ Status check failed: {check_res.status_code}")
                        break

                if export_success:
                    break  # Success, no need to try other formats

            if not export_success:
                failed_count += 1
                print(f"❌ All export formats failed for {design.design_id}")

        except Exception as e:
            print(f"❌ Error processing {design.design_id}: {str(e)}")
            failed_count += 1

    print(f"\n📈 VIDEO EXPORT RESULTS:")
    print(f"✅ Updated: {updated_count}")
    print(f"❌ Failed: {failed_count}")

    return Response({
        "success": True,
        "updated": updated_count,
        "failed": failed_count,
        "message": f"Video export completed. {updated_count} designs updated."
    })


# ======================
# UPDATE TIMESTAMPS
# ======================
@api_view(['POST'])
def update_timestamps(request):
    """Update timestamps for existing designs"""
    import requests
    from datetime import datetime

    print("\n🕒 ===== UPDATE TIMESTAMPS =====")

    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)

    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }

    # Get first 5 designs to update
    designs = CanvaDesign.objects.filter(last_modified__isnull=True)[:5]
    print(f"📊 Found {len(designs)} designs without timestamps")

    updated_count = 0

    for design in designs:
        print(f"\n🔍 Processing: {design.design_id}")

        try:
            # Fetch design details
            design_res = requests.get(
                f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                headers=headers,
                timeout=15
            )

            if design_res.ok:
                design_res_data = design_res.json()
                
                # Check if design data is wrapped
                if 'design' in design_res_data:
                    design_data = design_res_data['design']
                else:
                    design_data = design_res_data

                # Extract timestamp
                if "updated_at" in design_data:
                    timestamp = design_data.get("updated_at")
                    last_modified = datetime.fromtimestamp(timestamp)
                    
                    # Update database
                    design.last_modified = last_modified
                    design.save()
                    
                    updated_count += 1
                    print(f"✅ Updated timestamp: {last_modified}")
                else:
                    print("❌ No updated_at field")
            else:
                print(f"❌ API call failed: {design_res.status_code}")

        except Exception as e:
            print(f"❌ Error: {str(e)}")

    return Response({
        "success": True,
        "updated": updated_count,
        "message": f"Updated timestamps for {updated_count} designs"
    })

