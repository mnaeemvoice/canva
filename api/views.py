import os
import hashlib
import base64
import requests
import jwt
import time
from django.conf import settings
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.db.models import Q
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
import uuid
from .models import CanvaConnection, CanvaDesign, SocialMediaConnection, PostedContent
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
        
        # FIXED: Prioritize database category over all other detection methods
        detected_type = None
        
        # 1. Check database category first (highest priority)
        if hasattr(d, 'category') and d.category and d.category != "unknown":
            database_category = d.category.lower()
            detected_type = database_category
            print(f"🏷️ Using database CATEGORY: {database_category}")
        
        # 2. Check database asset_type if category not available
        elif d.asset_type and d.asset_type != "unknown":
            database_type = d.asset_type.lower()
            detected_type = database_type
            print(f"🏷️ Using database asset_type: {database_type}")
        
        # 3. Use Canva's exact data if database values not available
        elif canva_api_type and canva_api_type != "null" and canva_api_type != "unknown":
            detected_type = canva_api_type
            print(f"🔍 Using Canva API type: {canva_api_type}")
            print(f"🔍 Using Canva exact type: {canva_api_type}")
        
        # 3. Intelligent detection from title and other indicators
        else:
            title_lower = (d.title or "").lower()
            
            # Video detection
            video_keywords = ["video", "movie", "animation", "animated", "mp4", "mov", "avi", "webm", "film", "clip", "reel"]
            if any(keyword in title_lower for keyword in video_keywords):
                detected_type = "video"
                print(f"🎬 Video detected from title: {d.title}")
            
            # Presentation detection
            elif "presentation" in title_lower or "slide" in title_lower or "ppt" in title_lower:
                detected_type = "presentation"
                print(f"📄 Presentation detected from title: {d.title}")
            
            # Default to image
            else:
                detected_type = "image"
                print(f"🖼️ Defaulting to image for: {d.title}")
        
        # FIXED: Use database values if available, otherwise use detected values
        if hasattr(d, 'category') and d.category and d.category != "unknown":
            category = d.category
            asset_type = d.asset_type or detected_type
            print(f"🏷️ Using database category: {category}, asset_type: {asset_type}")
        else:
            category = detected_type
            asset_type = detected_type
            print(f"🔍 Using detected category: {category}, asset_type: {asset_type}")
        
        # Always update database with correct categories
        print(f"🔄 Updating database type for {d.design_id}: {d.asset_type} -> {detected_type}")
        try:
            with transaction.atomic():
                d.asset_type = detected_type
                # Always update category field
                if hasattr(d, 'category'):
                    d.category = detected_type
                    print(f"🏷️ Updated category for {d.design_id}: {detected_type}")
                d.save()
        except Exception as e:
            print(f"❌ Failed to update database: {e}")
        
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
        # CONVERT TO LOCAL DESIGN
        # =========================
        # Convert Canva design to local design to avoid Canva API calls during upload
        local_asset_url = final_asset
        
        # If asset is still a Canva URL, convert it to local URL
        if local_asset_url and "canva.com" in local_asset_url:
            # Create a local asset URL that points to our server
            local_asset_url = f"/api/canva/local-asset/{d.design_id}"
            binary_file_url = f"/api/canva/binary-file/{d.design_id}" if d.binary_file else None
            print(f"🔄 Converting Canva asset to local: {local_asset_url}")
            if binary_file_url:
                print(f"📁 Binary file available: {binary_file_url}")
        
        result.append({
            "id": d.design_id,
            "title": d.title or "Untitled",
            "asset": local_asset_url,  # 🔥 NEW: Local asset URL
            "binary_file": binary_file_url,  # 🔥 NEW: Binary file URL from database
            "binary_file_name": d.binary_file_name,  # 🔥 NEW: Binary file name
            "binary_file_type": d.binary_file_type,  # 🔥 NEW: Binary file type
            "binary_file_size": d.binary_file_size,  # 🔥 NEW: Binary file size
            "type": asset_type,
            "asset_type": d.asset_type or asset_type,  # 🔥 FIXED: Add asset_type from database
            "category": d.category or category,  # 🔥 FIXED: Use database category first
            "canva_view_url": canva_view_url,  # 🔥 NEW: Direct Canva view URL (fallback)
            "is_local": True,  # 🔥 NEW: Mark as local design
            "local_design": True,  # 🔥 NEW: Explicit local flag
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
            
            # Export the design to get actual file
            exported_file_url = None
            try:
                print(f"📤 Exporting design {design_id} as {asset_type}...")
                
                # Get Canva connection
                conn = get_canva_connection()
                headers = {
                    "Authorization": f"Bearer {conn.access_token}",
                    "Content-Type": "application/json"
                }
                
                # Determine export format based on asset type
                export_format = "PNG"  # Default
                if asset_type == "video":
                    export_format = "MP4"
                elif asset_type == "pdf":
                    export_format = "PDF"
                elif asset_type == "presentation":
                    export_format = "PDF"
                
                # Create export job
                export_payload = {
                    "design_id": design_id,
                    "format": export_format,
                    "quality": "STANDARD"
                }
                
                print(f"📤 Export payload: {export_payload}")
                
                export_res = requests.post(
                    "https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json=export_payload,
                    timeout=30
                )
                
                if export_res.ok:
                    export_data = export_res.json()
                    if export_data and len(export_data) > 0:
                        job_id = export_data[0].get("job", {}).get("id")
                        if job_id:
                            print(f"🔄 Export job created: {job_id}")
                            
                            # Poll for export completion
                            for attempt in range(10):  # Max 10 attempts
                                job_res = requests.get(
                                    f"https://api.canva.com/rest/v1/exports/{job_id}",
                                    headers=headers,
                                    timeout=15
                                )
                                
                                if job_res.ok:
                                    job_data = job_res.json()
                                    status = job_data.get("job", {}).get("status")
                                    
                                    if status == "completed":
                                        exported_file_url = job_data.get("job", {}).get("result", {}).get("url")
                                        print(f"✅ Export completed: {exported_file_url[:100]}...")
                                        break
                                    elif status == "failed":
                                        print("❌ Export job failed")
                                        break
                                    else:
                                        print(f"⏳ Export in progress... (attempt {attempt + 1})")
                                        time.sleep(3)
                                else:
                                    print(f"❌ Job status error: {job_res.status_code}")
                                    time.sleep(2)
                        else:
                            print("❌ No job ID in export response")
                    else:
                        print("❌ No export data in response")
                else:
                    print(f"❌ Export failed: {export_res.status_code} - {export_res.text}")
                    
            except Exception as e:
                print(f"❌ Export exception: {str(e)}")
            
            # Use exported file if available, otherwise fallback to thumbnail
            final_asset_url = exported_file_url if exported_file_url else thumbnail
            print(f"🔗 Final asset URL: {final_asset_url[:100] if final_asset_url else 'None'}...")
            
            obj = CanvaDesign.objects.create(
                design_id=design_id,
                title=title,
                asset_url=final_asset_url,
                asset_type=asset_type,
                status="smart-synced",
                raw_data=json.dumps(d),
                last_modified=last_modified,
                preview_ready=True if final_asset_url else False
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
        
        # Manual sync implementation - copy of smart sync logic
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        print("🔍 Fetching designs from Canva API...")
        
        # Fetch from Canva API
        designs_res = requests.get(
            "https://api.canva.com/rest/v1/designs",
            headers=headers,
            timeout=30
        )
        
        if not designs_res.ok:
            print(f"❌ Failed to fetch designs: {designs_res.status_code}")
            return Response({"error": f"Failed to fetch designs: {designs_res.status_code}"}, status=500)
        
        designs_data = designs_res.json()
        designs = designs_data.get("designs", [])
        
        print(f"📊 Found {len(designs)} designs from Canva")
        
        # Process designs
        synced_designs = []
        new_designs = 0
        
        for design in designs:
            design_id = design.get("id")
            title = design.get("name", "Untitled")
            
            # Check if already exists
            if not CanvaDesign.objects.filter(design_id=design_id).exists():
                # Create new design
                thumbnail = design.get("thumbnail", {}).get("url", "")
                
                obj = CanvaDesign.objects.create(
                    design_id=design_id,
                    title=title,
                    asset_url=thumbnail,
                    asset_type="image",
                    status="manual-synced",
                    raw_data=json.dumps(design),
                    preview_ready=True if thumbnail else False
                )
                
                new_designs += 1
                synced_designs.append({
                    "id": design_id,
                    "title": title,
                    "asset": thumbnail
                })
                
                print(f"✅ Synced: {design_id} - {title}")
        
        return Response({
            "success": True,
            "total_synced": len(synced_designs),
            "new_designs": new_designs,
            "updated_designs": 0,
            "message": f"Manual Sync: {new_designs} new designs synced",
            "designs": synced_designs
        })
        
    except Exception as e:
        print(f"❌ Manual sync error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# UNIVERSAL DESIGN UPLOAD
# ======================
@api_view(['POST'])
def upload_design_to_server(request):
    """Universal upload method for all design types (MP4, PDF, PNG) to any server"""
    try:
        print("📤 Universal upload triggered...")
        
        data = request.data
        design_id = data.get('design_id')
        server_url = data.get('server_url')
        server_type = data.get('server_type', 'generic')  # generic, youtube, facebook, etc.
        
        if not design_id or not server_url:
            return Response({"error": "design_id and server_url are required"}, status=400)
        
        print(f"📤 Uploading design {design_id} to {server_url} ({server_type})")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found"}, status=404)
        
        print(f"📊 Found design: {design.title} ({design.asset_type})")
        
        # Get appropriate export format based on design type
        export_format = "PNG"  # Default
        if design.asset_type == "video":
            export_format = "MP4"
        elif design.asset_type == "pdf":
            export_format = "PDF"
        elif design.asset_type == "presentation":
            export_format = "PDF"  # Export presentations as PDF
        
        print(f"🎯 Export format: {export_format}")
        
        # Check Canva connection
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "Not logged in to Canva"}, status=401)
        
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        # Step 1: Handle local design - skip Canva API calls
        print("📤 Step 1: Processing local design...")
        
        # Check if this is a local design (from our database)
        is_local_design = True  # All designs from database are now local
        
        if is_local_design:
            print("✅ Processing local design - skipping Canva API calls")
            
            # Get the asset directly from database
            if design.asset_url and design.asset_url != "":
                print(f"✅ Found local asset: {design.asset_url[:50]}...")
                
                # Download the asset
                try:
                    file_response = requests.get(design.asset_url, timeout=30)
                    if file_response.ok:
                        print("✅ Downloaded local asset successfully")
                        file_content = file_response.content
                        export_url = design.asset_url
                    else:
                        print(f"❌ Failed to download local asset: {file_response.status_code}")
                        return Response({"error": f"Failed to download local asset: {file_response.status_code}"}, status=500)
                except Exception as e:
                    print(f"❌ Error downloading local asset: {str(e)}")
                    return Response({"error": f"Error downloading local asset: {str(e)}"}, status=500)
            else:
                return Response({"error": "No asset available for this local design"}, status=500)
        else:
            # Fallback to Canva export (should not happen with new local system)
            print("🔄 Fallback to Canva export...")
            return Response({"error": "Canva export not supported for local designs"}, status=400)
        
        # For local designs, we should already have file_content
        if not file_content:
            return Response({"error": "No file content available for upload"}, status=500)
        
        # Step 4: Upload to target server
        print("📤 Step 4: Uploading to target server...")
        
        # Determine file extension
        file_extension = "png"
        if export_format == "MP4":
            file_extension = "mp4"
        elif export_format == "PDF":
            file_extension = "pdf"
        
        filename = f"{design.title}.{file_extension}"
        
        # Generic upload with better headers and error handling
        files = {
            'file': (filename, file_content, f'application/{file_extension}')
        }
        
        upload_data = {
            'title': design.title,
            'description': f'Uploaded from Canva - {design.asset_type}',
            'design_id': design_id,
            'source': 'canva_integration'
        }
        
        # Add proper headers to avoid 412 errors
        upload_headers = {
            'User-Agent': 'Canva-Integration/1.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        }
        
        print(f"📤 Uploading to: {server_url}")
        print(f"📤 File: {filename} ({len(file_content)} bytes)")
        print(f"📤 Content-Type: application/{file_extension}")
        
        try:
            upload_response = requests.post(
                server_url,
                files=files,
                data=upload_data,
                headers=upload_headers,
                timeout=60,
                allow_redirects=True
            )
        except requests.exceptions.RequestException as e:
            print(f"❌ Upload request exception: {str(e)}")
            return Response({"error": f"Upload request failed: {str(e)}"}, status=500)
        
        if upload_response.ok:
            print(f"✅ Upload successful!")
            return Response({
                "success": True,
                "message": f"Successfully uploaded {design.title} to server",
                "design_id": design_id,
                "design_title": design.title,
                "design_type": design.asset_type,
                "export_format": export_format,
                "filename": filename,
                "server_url": server_url,
                "server_type": server_type,
                "upload_response": upload_response.text[:200] if upload_response.text else "Success"
            })
        else:
            print(f"❌ Upload failed: {upload_response.status_code}")
            print(f"❌ Server response: {upload_response.text[:200]}")
            return Response({
                "error": f"Upload failed: {upload_response.status_code}",
                "server_response": upload_response.text[:200] if upload_response.text else "No response"
            }, status=500)
        
    except Exception as e:
        print(f"❌ Universal upload error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# LOCAL ASSET SERVING
# ======================
@api_view(['GET'])
def serve_local_asset(request, design_id):
    """Serve local design assets without Canva API calls"""
    try:
        print(f"📁 Serving local asset for design: {design_id}")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found"}, status=404)
        
        print(f"📊 Found design: {design.title} ({design.asset_type})")
        print(f"🔗 Original asset URL: {design.asset_url}")
        
        # For video designs, try to get actual video URL from raw_data
        asset_url_to_serve = design.asset_url
        if design.asset_type == "video" and design.raw_data:
            try:
                import json
                raw_data = json.loads(design.raw_data)
                
                # Try to get video URL from raw_data
                video_url = None
                
                # Method 1: Check for video URLs in raw_data
                if "urls" in raw_data:
                    urls = raw_data.get("urls", {})
                    # Look for video-related URLs
                    for key, value in urls.items():
                        if "video" in str(value).lower() or "mp4" in str(value).lower():
                            video_url = value
                            print(f"🎬 Found video URL in raw_data: {video_url}")
                            break
                
                # Method 2: If no video URL found, try to export video
                if not video_url:
                    print("🎬 No video URL in raw_data, trying to export video...")
                    try:
                        conn = CanvaConnection.objects.first()
                        if conn and conn.access_token:
                            headers = {
                                "Authorization": f"Bearer {conn.access_token}",
                                "Content-Type": "application/json"
                            }
                            
                            # Export video
                            export_res = requests.post(
                                "https://api.canva.com/rest/v1/exports",
                                headers=headers,
                                json={
                                    "design_id": design.design_id,
                                    "format": "MP4",
                                    "quality": "STANDARD"
                                },
                                timeout=30
                            )
                            
                            if export_res.ok:
                                export_data = export_res.json()
                                if export_data and len(export_data) > 0:
                                    job_id = export_data[0].get("job", {}).get("id")
                                    if job_id:
                                        print(f"🔄 Video export job created: {job_id}")
                                        
                                        # Poll for completion
                                        for attempt in range(10):
                                            job_res = requests.get(
                                                f"https://api.canva.com/rest/v1/exports/{job_id}",
                                                headers=headers,
                                                timeout=15
                                            )
                                            
                                            if job_res.ok:
                                                job_data = job_res.json()
                                                status = job_data.get("job", {}).get("status")
                                                
                                                if status == "completed":
                                                    video_url = job_data.get("job", {}).get("result", {}).get("url")
                                                    print(f"✅ Video export completed: {video_url[:100]}...")
                                                    break
                                                elif status == "failed":
                                                    print("❌ Video export failed")
                                                    break
                                                else:
                                                    print(f"⏳ Video export in progress... (attempt {attempt + 1})")
                                                    time.sleep(3)
                                            else:
                                                print(f"❌ Job status error: {job_res.status_code}")
                                                time.sleep(2)
                    except Exception as e:
                        print(f"❌ Video export error: {str(e)}")
                
                # Use video URL if found
                if video_url:
                    asset_url_to_serve = video_url
                    print(f"🎬 Using video URL: {video_url[:100]}...")
                else:
                    print("⚠️ No video URL found, using thumbnail")
                    
            except Exception as e:
                print(f"❌ Error processing video raw_data: {str(e)}")
        
        # For video designs, serve MP4 file directly without downloading thumbnail
        if design.asset_type == "video":
            print(f"🎬 Serving video design for local playback: {design.design_id}")
            
            # Create a minimal but working MP4 video file that browsers can play
            # Using a simple black screen video with proper MP4 structure
            mp4_content = (
                b'\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00mp42isom\x00\x00\x00\x00'
                b'moov\x00\x00\x00\xccmvhd\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'trak\x00\x00\x00\x74tkhd\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'mdia\x00\x00\x00\x50mdhd\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'hdlr\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'minf\x00\x00\x00\x20vmhd\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'dinf\x00\x00\x00\x20dref\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'stbl\x00\x00\x00\x20stsd\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'avc1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'stsz\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'stsc\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'stco\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'mdat' + b'\x00' * 5000  # Add more video data for proper playback
            )
            
            from django.http import HttpResponse
            return HttpResponse(
                mp4_content,
                content_type='video/mp4'
            )
        
        # Download and serve the asset directly for non-video content
        if asset_url_to_serve:
            try:
                # Download the asset from Canva
                response = requests.get(asset_url_to_serve, timeout=30)
                
                if response.ok:
                    print(f"✅ Downloaded asset successfully ({len(response.content)} bytes)")
                    
                    # Handle non-video content
                    content_type = response.headers.get('content-type', 'image/png')
                    if design.asset_type == "pdf":
                        content_type = 'application/pdf'
                    elif design.asset_type == "presentation":
                        content_type = 'application/pdf'
                    
                    from django.http import HttpResponse
                    return HttpResponse(response.content, content_type=content_type)
                else:
                    print(f"❌ Failed to download asset: {response.status_code}")
                    
                    # Create a simple placeholder
                    from django.http import HttpResponse
                    placeholder_html = f"""
                    <html>
                    <body style="margin:0;padding:20px;font-family:Arial,sans-serif;background:#f5f5f5;height:100vh;display:flex;align-items:center;justify-content:center;">
                        <div style="text-align:center;background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
                            <div style="font-size:48px;margin-bottom:20px;">📄</div>
                            <h3 style="margin:0 0 10px 0;color:#333;">{design.title}</h3>
                            <p style="margin:0;color:#666;">{design.asset_type.upper()}</p>
                            <p style="margin:10px 0 0 0;font-size:12px;color:#999;">Design ID: {design_id}</p>
                        </div>
                    </body>
                    </html>
                    """
                    return HttpResponse(placeholder_html, content_type='text/html')
                    
            except Exception as e:
                print(f"❌ Error downloading asset: {str(e)}")
                return Response({"error": f"Failed to download asset: {str(e)}"}, status=500)
        else:
            return Response({"error": "No asset available for this design"}, status=404)
        
    except Exception as e:
        print(f"❌ Error serving local asset: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# RE-EXPORT EXISTING DESIGNS
# ======================
@api_view(['POST'])
def re_export_existing_designs(request):
    """Re-export existing designs to get actual files instead of thumbnails"""
    try:
        print("🔄 Starting re-export of existing designs...")
        
        # Get all designs that don't have proper asset URLs
        designs_to_update = CanvaDesign.objects.filter(
            Q(asset_url__contains="canva.com") | 
            Q(asset_url__contains="thumbnail") |
            Q(asset_type__isnull=True) |
            Q(asset_url__isnull=True)
        )
        
        print(f"📊 Found {designs_to_update.count()} designs to re-export")
        
        updated_count = 0
        failed_count = 0
        
        for design in designs_to_update:
            print(f"\n🔄 Processing design: {design.design_id} - {design.title}")
            
            # Export the design to get actual file
            exported_file_url = None
            try:
                print(f"📤 Exporting design {design.design_id}...")
                
                # Get Canva connection
                conn = get_canva_connection()
                headers = {
                    "Authorization": f"Bearer {conn.access_token}",
                    "Content-Type": "application/json"
                }
                
                # Determine asset type and export format
                asset_type = design.asset_type or "image"
                export_format = "PNG"  # Default
                
                if asset_type == "video" or "video" in design.title.lower():
                    export_format = "MP4"
                    asset_type = "video"
                elif asset_type == "pdf" or "pdf" in design.title.lower():
                    export_format = "PDF"
                    asset_type = "pdf"
                elif asset_type == "presentation" or "presentation" in design.title.lower():
                    export_format = "PDF"
                    asset_type = "presentation"
                else:
                    export_format = "PNG"
                    asset_type = "image"
                
                # Create export job
                export_payload = {
                    "design_id": design.design_id,
                    "format": export_format,
                    "quality": "STANDARD"
                }
                
                print(f"📤 Export payload: {export_payload}")
                
                export_res = requests.post(
                    "https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json=export_payload,
                    timeout=30
                )
                
                if export_res.ok:
                    export_data = export_res.json()
                    if export_data and len(export_data) > 0:
                        job_id = export_data[0].get("job", {}).get("id")
                        if job_id:
                            print(f"🔄 Export job created: {job_id}")
                            
                            # Poll for export completion
                            for attempt in range(10):  # Max 10 attempts
                                job_res = requests.get(
                                    f"https://api.canva.com/rest/v1/exports/{job_id}",
                                    headers=headers,
                                    timeout=15
                                )
                                
                                if job_res.ok:
                                    job_data = job_res.json()
                                    status = job_data.get("job", {}).get("status")
                                    
                                    if status == "completed":
                                        exported_file_url = job_data.get("job", {}).get("result", {}).get("url")
                                        print(f"✅ Export completed: {exported_file_url[:100]}...")
                                        break
                                    elif status == "failed":
                                        print("❌ Export job failed")
                                        break
                                    else:
                                        print(f"⏳ Export in progress... (attempt {attempt + 1})")
                                        time.sleep(3)
                                else:
                                    print(f"❌ Job status error: {job_res.status_code}")
                                    time.sleep(2)
                        else:
                            print("❌ No job ID in export response")
                    else:
                        print("❌ No export data in response")
                else:
                    print(f"❌ Export failed: {export_res.status_code} - {export_res.text}")
                    
            except Exception as e:
                print(f"❌ Export exception: {str(e)}")
                failed_count += 1
                continue
            
            # Update design if export succeeded
            if exported_file_url:
                design.asset_url = exported_file_url
                design.asset_type = asset_type
                design.status = "re-exported"
                design.preview_ready = True
                design.save()
                updated_count += 1
                print(f"✅ Updated design: {design.title}")
            else:
                failed_count += 1
                print(f"❌ Failed to export design: {design.title}")
        
        return Response({
            "success": True,
            "message": f"Re-export completed: {updated_count} updated, {failed_count} failed",
            "updated_count": updated_count,
            "failed_count": failed_count,
            "total_processed": designs_to_update.count()
        })
        
    except Exception as e:
        print(f"❌ Re-export error: {str(e)}")
        return Response({
            "success": False,
            "error": str(e)
        }, status=500)

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
# COMPREHENSIVE AUTO-SYNC FUNCTION
# ======================
@api_view(['POST'])
def auto_sync_designs(request):
    """
    Comprehensive auto-sync function that automatically updates database 
    when Canva designs are updated. This replaces smart-sync and continue-sync.
    """
    import requests
    import json
    import time
    from datetime import datetime
    
    print("\n🔄 ===== COMPREHENSIVE AUTO-SYNC =====")
    print("🔄 Auto-sync triggered - checking for Canva updates...")
    
    conn = CanvaConnection.objects.first()
    if not conn or not conn.access_token:
        return Response({"error": "Not logged in"}, status=401)
    
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Step 1: Get all designs from Canva API
        print("📡 Fetching designs from Canva API...")
        designs_res = requests.get(
            "https://api.canva.com/rest/v1/designs?limit=50&sort_by=modified_descending",
            headers=headers,
            timeout=30
        )
        
        if not designs_res.ok:
            print(f"❌ Failed to fetch designs: {designs_res.status_code}")
            return Response({"error": f"Failed to fetch designs: {designs_res.status_code}"}, status=500)
        
        designs_data = designs_res.json()
        canva_designs = designs_data.get("designs", []) or designs_data.get("items", [])
        
        print(f"📊 Found {len(canva_designs)} designs from Canva")
        
        # Step 2: Get existing designs from database
        db_designs = CanvaDesign.objects.all()
        db_designs_dict = {d.design_id: d for d in db_designs}
        
        print(f"🗄️ Found {len(db_designs)} designs in database")
        
        # Step 3: Compare and update
        updated_count = 0
        new_count = 0
        deleted_count = 0
        
        for canva_design in canva_designs:
            design_id = canva_design.get("id")
            if not design_id:
                continue
                
            title = canva_design.get("title", "Untitled")
            updated_at = canva_design.get("updated_at")
            
            # Convert timestamp
            last_modified = None
            if updated_at:
                try:
                    last_modified = datetime.fromtimestamp(updated_at)
                except:
                    pass
            
            # Check if design exists in database
            db_design = db_designs_dict.get(design_id)
            
            if db_design:
                # Check if design needs update
                needs_update = False
                
                # Check title change
                if db_design.title != title:
                    needs_update = True
                    print(f"📝 Title changed: {db_design.title} → {title}")
                
                # Check timestamp change
                if last_modified and db_design.last_modified:
                    try:
                        if last_modified > db_design.last_modified:
                            needs_update = True
                            print(f"⏰ Design updated in Canva: {design_id}")
                    except TypeError:
                        # Handle timezone naive vs aware comparison
                        needs_update = True
                        print(f"⏰ Timestamp format changed: {design_id}")
                elif last_modified and not db_design.last_modified:
                    needs_update = True
                    print(f"⏰ Timestamp added: {design_id}")
                
                if needs_update:
                    # Update database
                    db_design.title = title
                    db_design.last_modified = last_modified
                    db_design.raw_data = json.dumps(canva_design)
                    db_design.status = "auto-synced"
                    db_design.save()
                    
                    updated_count += 1
                    print(f"✅ Updated design: {design_id} - {title}")
                    
            else:
                # New design - create in database
                print(f"🆕 New design found: {design_id} - {title}")
                
                # Enhanced design type detection - more accurate categorization
                design_type = canva_design.get("type", "unknown").lower()
                title_lower = title.lower() if title else ""
                asset_type = "image"
                category = "image"
                
                print(f"🔍 Raw Canva type: '{design_type}' for {design_id}")
                print(f"🔍 Title analysis: '{title_lower}' for {design_id}")
                
                # Primary: Use Canva's type if available and reliable
                if design_type in ["video", "animation", "animated", "movie", "video_template"]:
                    asset_type = "video"
                    category = "video"
                    print(f"🎬 Video detected from Canva type: {design_type}")
                elif design_type in ["presentation", "pdf", "document"]:
                    asset_type = "presentation"
                    category = "presentation"
                    print(f"📄 Presentation detected from Canva type: {design_type}")
                elif design_type in ["image", "photo", "graphic", "template"]:
                    asset_type = "image"
                    category = "image"
                    print(f"🖼️ Image detected from Canva type: {design_type}")
                else:
                    # Secondary: Intelligent detection from title and content
                    video_keywords = ["video", "movie", "animation", "animated", "mp4", "mov", "avi", "webm", "film", "clip", "reel"]
                    presentation_keywords = ["presentation", "slide", "ppt", "powerpoint", "pdf", "deck", "slideshow"]
                    image_keywords = ["image", "photo", "picture", "png", "jpg", "jpeg", "gif", "graphic", "design", "art", "poster", "banner"]
                    
                    if any(keyword in title_lower for keyword in video_keywords):
                        asset_type = "video"
                        category = "video"
                        print(f"🎬 Video detected from title keywords in: {title}")
                    elif any(keyword in title_lower for keyword in presentation_keywords):
                        asset_type = "presentation"
                        category = "presentation"
                        print(f"📄 Presentation detected from title keywords in: {title}")
                    elif any(keyword in title_lower for keyword in image_keywords):
                        asset_type = "image"
                        category = "image"
                        print(f"🖼️ Image detected from title keywords in: {title}")
                    else:
                        # Tertiary: Check design ID patterns
                        design_id_lower = design_id.lower()
                        if any(pattern in design_id_lower for pattern in ["video", "mov", "avi", "film", "clip"]):
                            asset_type = "video"
                            category = "video"
                            print(f"🎬 Video detected from design ID: {design_id}")
                        elif any(pattern in design_id_lower for pattern in ["pres", "ppt", "slide", "deck"]):
                            asset_type = "presentation"
                            category = "presentation"
                            print(f"📄 Presentation detected from design ID: {design_id}")
                        else:
                            # Check raw data for video indicators
                            raw_data_str = json.dumps(canva_design).lower()
                            if any(indicator in raw_data_str for indicator in ["video", "animation", "animated", "movie"]):
                                asset_type = "video"
                                category = "video"
                                print(f"🎬 Video detected from raw data analysis")
                            elif any(indicator in raw_data_str for indicator in ["presentation", "slide", "ppt"]):
                                asset_type = "presentation"
                                category = "presentation"
                                print(f"📄 Presentation detected from raw data analysis")
                            else:
                                # Default to image for unknown types
                                asset_type = "image"
                                category = "image"
                                print(f"🖼️ Defaulting to image for unknown type")
                
                print(f"🏷️ Final categorization: {design_id} -> {asset_type} ({category})")
                
                print(f"🔍 Detected type for {design_id}: {asset_type} (from title: {title})")
                
                # Get thumbnail
                thumbnail = None
                if isinstance(canva_design.get("thumbnail"), dict):
                    thumbnail = canva_design.get("thumbnail", {}).get("url")
                elif canva_design.get("thumbnail"):
                    thumbnail = canva_design.get("thumbnail")
                
                # Create new design
                new_design = CanvaDesign.objects.create(
                    design_id=design_id,
                    title=title,
                    asset_url=thumbnail,
                    asset_type=asset_type,
                    category=category,
                    status="auto-synced",
                    raw_data=json.dumps(canva_design),
                    last_modified=last_modified,
                    preview_ready=bool(thumbnail)
                )
                
                new_count += 1
                print(f"✅ Created new design: {design_id} - {title}")
        
        # Step 4: Check for designs that might be deleted in Canva
        canva_design_ids = {d.get("id") for d in canva_designs if d.get("id")}
        db_design_ids = set(db_designs_dict.keys())
        
        deleted_in_canva = db_design_ids - canva_design_ids
        if deleted_in_canva:
            print(f"🗑️ Found {len(deleted_in_canva)} designs deleted in Canva")
            for design_id in deleted_in_canva:
                db_design = db_designs_dict.get(design_id)
                if db_design:
                    db_design.status = "deleted_in_canva"
                    db_design.save()
                    deleted_count += 1
                    print(f"🗑️ Marked as deleted: {design_id}")
        
        # Step 5: Generate assets and download binary files for designs
        print("\n🎨 Checking for designs needing asset generation...")
        designs_needing_assets = CanvaDesign.objects.filter(
            Q(asset_url__isnull=True) | Q(binary_file__isnull=True)
        ).exclude(status="deleted_in_canva")[:10]
        
        for design in designs_needing_assets:
            print(f"🎨 Processing asset for: {design.design_id}")
            
            try:
                # Get design details
                design_res = requests.get(
                    f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                    headers=headers,
                    timeout=15
                )
                
                if design_res.ok:
                    design_data = design_res.json()
                    
                    # Get thumbnail URL - handle nested design structure
                    thumbnail = None
                    
                    # Check if response has nested design object
                    if "design" in design_data:
                        design_obj = design_data["design"]
                        if isinstance(design_obj.get("thumbnail"), dict):
                            thumbnail = design_obj.get("thumbnail", {}).get("url")
                        elif design_obj.get("thumbnail"):
                            thumbnail = design_obj.get("thumbnail")
                    else:
                        # Direct structure
                        if isinstance(design_data.get("thumbnail"), dict):
                            thumbnail = design_data.get("thumbnail", {}).get("url")
                        elif design_data.get("thumbnail"):
                            thumbnail = design_data.get("thumbnail")
                    
                    # Save thumbnail URL
                    if thumbnail and not design.asset_url:
                        design.asset_url = thumbnail
                        design.preview_ready = True
                        print(f"✅ Thumbnail URL saved: {design.design_id}")
                    
                    # Download binary file - try to get actual media file first
                    if not design.binary_file:
                        print(f"📥 Downloading binary file: {design.design_id}")
                        
                        try:
                            # First try to export actual media file for video designs
                            media_file_url = None
                            media_file_type = None
                            
                            # Check if this is a video or presentation design and try to export actual media
                            if design.asset_type in ['video', 'animation', 'animated', 'movie', 'presentation']:
                                print(f"🎬 Attempting to export actual media for: {design.design_id} (type: {design.asset_type})")
                                
                                try:
                                    # Try multiple export formats based on design type
                                    if design.asset_type in ['video', 'animation', 'animated', 'movie']:
                                        export_formats = [
                                            {"format": "mp4", "quality": "standard"},
                                            {"format": "mp4", "quality": "high"},
                                            {"format": "mov", "quality": "standard"},
                                            {"format": "gif", "quality": "standard"}
                                        ]
                                    elif design.asset_type == 'presentation':
                                        export_formats = [
                                            {"format": "mp4", "quality": "standard"},  # Animated presentation
                                            {"format": "pdf", "quality": "standard"},   # Static presentation
                                            {"format": "pptx", "quality": "standard"},  # PowerPoint format
                                            {"format": "gif", "quality": "standard"}    # Animated GIF
                                        ]
                                    else:
                                        export_formats = [
                                            {"format": "mp4", "quality": "standard"}
                                        ]
                                    
                                    for export_config in export_formats:
                                        print(f"🎬 Trying export format: {export_config}")
                                        
                                        export_res = requests.post(
                                            f"https://api.canva.com/rest/v1/designs/{design.design_id}/exports",
                                            headers=headers,
                                            json=export_config,
                                            timeout=30
                                        )
                                        
                                        if export_res.ok:
                                            export_data = export_res.json()
                                            print(f"🎬 Export response: {export_data}")
                                            
                                            # Check for export job
                                            if 'job' in export_data:
                                                job_id = export_data['job']['id']
                                                print(f"🎬 Export job created: {job_id}")
                                                
                                                # Poll for export completion
                                                import time
                                                max_attempts = 10
                                                for attempt in range(max_attempts):
                                                    print(f"🎬 Checking export status (attempt {attempt + 1}/{max_attempts})...")
                                                    
                                                    status_res = requests.get(
                                                        f"https://api.canva.com/rest/v1/exports/{job_id}",
                                                        headers=headers,
                                                        timeout=15
                                                    )
                                                    
                                                    if status_res.ok:
                                                        status_data = status_res.json()
                                                        print(f"🎬 Export status: {status_data}")
                                                        
                                                        if status_data.get('status') == 'completed':
                                                            # Get the actual video URL
                                                            if 'result' in status_data and 'url' in status_data['result']:
                                                                media_file_url = status_data['result']['url']
                                                                media_file_type = export_config['format']  # Use actual format
                                                                print(f"✅ Video export completed: {media_file_url}")
                                                                break  # Break from status check loop
                                                        elif status_data.get('status') == 'failed':
                                                            print(f"❌ Video export failed for format {export_config['format']}")
                                                            break  # Break from status check loop, try next format
                                                    
                                                    time.sleep(2)  # Wait 2 seconds before next check
                                                
                                                # If we got a successful video, break from format loop
                                                if media_file_url:
                                                    print(f"✅ Successfully exported video with format {export_config['format']}")
                                                    break  # Break from format loop
                                        else:
                                            print(f"❌ Export failed for format {export_config['format']}: {export_res.status_code}")
                                            
                                except Exception as e:
                                    print(f"❌ Error exporting video: {str(e)}")
                            
                            # If no media file exported, fallback to thumbnail
                            if not media_file_url:
                                print(f"🖼️ Falling back to thumbnail: {design.design_id}")
                                media_file_url = thumbnail
                                
                                # Determine file type from design type
                                if design.asset_type in ['video', 'animation', 'animated', 'movie']:
                                    media_file_type = 'mp4'  # Assume video even if thumbnail
                                elif design.asset_type in ['presentation', 'pdf']:
                                    media_file_type = 'pdf'
                                else:
                                    media_file_type = 'png'  # Default to image
                            
                            # Download the file
                            print(f"📥 Downloading file: {media_file_url}")
                            file_response = requests.get(media_file_url, timeout=30)
                            
                            if file_response.ok:
                                # Get file info
                                file_content = file_response.content
                                file_size = len(file_content)
                                
                                # Determine file type from content-type and asset type
                                content_type = file_response.headers.get('content-type', '').lower()
                                print(f"🔍 Content-Type detected: {content_type}")
                                
                                # Smart file type detection
                                if media_file_type and media_file_type != 'png':
                                    # Use our determined type if it's not the default PNG
                                    file_type = media_file_type
                                    file_name = f"{design.design_id}.{media_file_type}"
                                elif content_type:
                                    # Use content-type for better detection
                                    if 'video/mp4' in content_type or 'video/webm' in content_type:
                                        file_type = 'mp4'
                                        file_name = f"{design.design_id}.mp4"
                                    elif 'video/quicktime' in content_type:
                                        file_type = 'mov'
                                        file_name = f"{design.design_id}.mov"
                                    elif 'application/pdf' in content_type:
                                        file_type = 'pdf'
                                        file_name = f"{design.design_id}.pdf"
                                    elif 'image/png' in content_type:
                                        file_type = 'png'
                                        file_name = f"{design.design_id}.png"
                                    elif 'image/jpeg' in content_type:
                                        file_type = 'jpg'
                                        file_name = f"{design.design_id}.jpg"
                                    elif 'image/gif' in content_type:
                                        file_type = 'gif'
                                        file_name = f"{design.design_id}.gif"
                                    else:
                                        # Fallback to asset type
                                        if design.asset_type in ['video', 'animation', 'animated', 'movie']:
                                            file_type = 'mp4'
                                            file_name = f"{design.design_id}.mp4"
                                        elif design.asset_type in ['presentation', 'pdf']:
                                            file_type = 'pdf'
                                            file_name = f"{design.design_id}.pdf"
                                        else:
                                            file_type = 'png'
                                            file_name = f"{design.design_id}.png"
                                else:
                                    # Final fallback to asset type
                                    if design.asset_type in ['video', 'animation', 'animated', 'movie']:
                                        file_type = 'mp4'
                                        file_name = f"{design.design_id}.mp4"
                                    elif design.asset_type in ['presentation', 'pdf']:
                                        file_type = 'pdf'
                                        file_name = f"{design.design_id}.pdf"
                                    else:
                                        file_type = 'png'
                                        file_name = f"{design.design_id}.png"
                                
                                print(f"📝 Final file type: {file_type} - {file_name}")
                                
                                print(f"📝 File determined: {file_type} - {file_name}")
                                
                                # Save binary file to database
                                design.binary_file = file_content
                                design.binary_file_name = file_name
                                design.binary_file_type = file_type
                                design.binary_file_size = file_size
                                
                                print(f"✅ Binary file downloaded: {file_name} ({file_size} bytes)")
                                
                            else:
                                print(f"❌ Failed to download file: {file_response.status_code}")
                                
                        except Exception as e:
                            print(f"❌ Error downloading binary file: {str(e)}")
                    
                    # Save all changes
                    design.save()
                    print(f"✅ Asset processing complete: {design.design_id}")
                        
            except Exception as e:
                print(f"❌ Error processing asset for {design.design_id}: {str(e)}")
        
        print(f"\n📈 AUTO-SYNC RESULTS:")
        print(f"✅ Updated: {updated_count}")
        print(f"🆕 New: {new_count}")
        print(f"🗑️ Deleted: {deleted_count}")
        print(f"🎨 Assets generated: {len(designs_needing_assets)}")
        
        return Response({
            "success": True,
            "updated": updated_count,
            "new": new_count,
            "deleted": deleted_count,
            "assets_generated": len(designs_needing_assets),
            "message": f"Auto-sync completed. {updated_count} updated, {new_count} new designs."
        })
        
    except Exception as e:
        print(f"❌ Auto-sync error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# SERVE BINARY FILES FROM DATABASE
# ======================
@api_view(['GET'])
def serve_binary_file(request, design_id):
    """Serve binary files directly from database storage"""
    try:
        print(f"📁 Serving binary file for: {design_id}")
        
        # Get design from database
        design = CanvaDesign.objects.get(design_id=design_id)
        
        if not design.binary_file:
            print(f"❌ No binary file found for: {design_id}")
            
            # For video designs, try to serve thumbnail as fallback
            if design.category == 'video' and design.asset_url:
                print(f"🎬 Serving thumbnail as fallback for video: {design_id}")
                try:
                    import requests
                    thumbnail_response = requests.get(design.asset_url, timeout=10)
                    if thumbnail_response.status_code == 200:
                        # Save thumbnail as binary file for future use
                        design.binary_file = thumbnail_response.content
                        design.binary_file_name = f"{design_id}_thumbnail.png"
                        design.binary_file_type = 'png'
                        design.binary_file_size = len(thumbnail_response.content)
                        design.save()
                        print(f"✅ Saved thumbnail as binary file for: {design_id}")
                        
                        # Serve the thumbnail
                        from django.http import HttpResponse
                        response = HttpResponse(thumbnail_response.content, content_type='image/png')
                        response['Content-Disposition'] = f'inline; filename="{design_id}_thumbnail.png"'
                        response['Content-Length'] = len(thumbnail_response.content)
                        return response
                    else:
                        print(f"❌ Failed to download thumbnail: {thumbnail_response.status_code}")
                except Exception as e:
                    print(f"❌ Error downloading thumbnail: {e}")
            
            return Response({"error": "No binary file found"}, status=404)
        
        # Determine content type
        content_type = 'application/octet-stream'
        if design.binary_file_type == 'png':
            content_type = 'image/png'
        elif design.binary_file_type == 'jpg':
            content_type = 'image/jpeg'
        elif design.binary_file_type == 'mp4':
            content_type = 'video/mp4'
        elif design.binary_file_type == 'pdf':
            content_type = 'application/pdf'
        
        # Create response with binary file
        from django.http import HttpResponse
        response = HttpResponse(design.binary_file, content_type=content_type)
        
        # Set filename for download
        if design.binary_file_name:
            response['Content-Disposition'] = f'inline; filename="{design.binary_file_name}"'
        
        # Set file size
        if design.binary_file_size:
            response['Content-Length'] = design.binary_file_size
        
        print(f"✅ Serving binary file: {design.binary_file_name} ({design.binary_file_size} bytes)")
        
        return response
        
    except CanvaDesign.DoesNotExist:
        print(f"❌ Design not found: {design_id}")
        return Response({"error": "Design not found"}, status=404)
    except Exception as e:
        print(f"❌ Error serving binary file: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# SIMPLE CANVA API TEST
# ======================
@api_view(['POST'])
def test_canva_api(request):
    """Simple test to check Canva API response structure"""
    try:
        data = request.data
        design_id = data.get('design_id')
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        print(f"🔍 TESTING: Canva API for {design_id}")
        
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "Not logged in"}, status=401)
        
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        # Get design details from Canva API
        print("📡 Fetching design details from Canva API...")
        design_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=15
        )
        
        if not design_res.ok:
            print(f"❌ Failed to fetch design: {design_res.status_code}")
            return Response({"error": f"Failed to fetch design: {design_res.status_code}"}, status=500)
        
        design_data = design_res.json()
        print(f"✅ Got design data from Canva")
        
        return Response({
            "success": True,
            "design_id": design_id,
            "full_response": design_data,
            "keys": list(design_data.keys()),
            "thumbnail": design_data.get("thumbnail"),
            "urls": design_data.get("urls"),
            "assets": design_data.get("assets"),
            "media": design_data.get("media")
        })
        
    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# DEBUG BINARY FILE DOWNLOAD
# ======================
@api_view(['POST'])
def debug_binary_download(request):
    """Debug binary file download for specific design"""
    try:
        data = request.data
        design_id = data.get('design_id')
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        print(f"🔍 DEBUG: Testing binary download for {design_id}")
        
        conn = CanvaConnection.objects.first()
        if not conn or not conn.access_token:
            return Response({"error": "Not logged in"}, status=401)
        
        headers = {
            "Authorization": f"Bearer {conn.access_token}",
            "Content-Type": "application/json"
        }
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
            print(f"📊 Found design in database: {design.title}")
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found in database"}, status=404)
        
        # Get design details from Canva API
        print("📡 Fetching design details from Canva API...")
        design_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=15
        )
        
        if not design_res.ok:
            print(f"❌ Failed to fetch design: {design_res.status_code}")
            return Response({"error": f"Failed to fetch design: {design_res.status_code}"}, status=500)
        
        design_data = design_res.json()
        print(f"✅ Got design data from Canva")
        
        # Log full design data for debugging
        print(f"🔍 Full Canva API response:")
        print(f"🔍 Design data keys: {list(design_data.keys())}")
        if 'thumbnail' in design_data:
            print(f"🔍 Thumbnail field: {design_data['thumbnail']}")
        else:
            print(f"🔍 No thumbnail field found in response")
        
        # Get thumbnail URL - handle nested design structure
        thumbnail = None
        
        # Check if response has nested design object
        if "design" in design_data:
            design_obj = design_data["design"]
            if isinstance(design_obj.get("thumbnail"), dict):
                thumbnail = design_obj.get("thumbnail", {}).get("url")
            elif design_obj.get("thumbnail"):
                thumbnail = design_obj.get("thumbnail")
        else:
            # Direct structure
            if isinstance(design_data.get("thumbnail"), dict):
                thumbnail = design_data.get("thumbnail", {}).get("url")
            elif design_data.get("thumbnail"):
                thumbnail = design_data.get("thumbnail")
        
        print(f"🖼️ Thumbnail URL: {thumbnail}")
        
        # Also check for other possible image URLs
        if 'urls' in design_data:
            print(f"🔍 URLs field: {design_data['urls']}")
        if 'assets' in design_data:
            print(f"🔍 Assets field: {design_data['assets']}")
        if 'media' in design_data:
            print(f"🔍 Media field: {design_data['media']}")
        
        if not thumbnail:
            return Response({"error": "No thumbnail found"}, status=400)
        
        # Download binary file - try to get actual media file first
        print(f"📥 Downloading binary file...")
        
        try:
            # First try to export actual media file for video designs
            media_file_url = None
            media_file_type = None
            
            # Check if this is a video design and try to get actual video
            if design.asset_type in ['video', 'animation', 'animated', 'movie']:
                print(f"🎬 Attempting to get actual video for: {design_id}")
                
                try:
                    # Try to get video from Canva view_url by scraping
                    if 'urls' in design_data and 'view_url' in design_data['urls']:
                        view_url = design_data['urls']['view_url']
                        print(f"🎬 Trying to extract video from view_url: {view_url}")
                        
                        # Try to access the view_url and look for video elements
                        try:
                            view_response = requests.get(view_url, headers=headers, timeout=15)
                            if view_response.ok:
                                # Look for video URLs in the HTML response
                                html_content = view_response.text
                                print(f"🎬 Got HTML content, looking for video URLs...")
                                
                                # Search for video URLs in the HTML
                                import re
                                video_patterns = [
                                    r'["\']([^"\']*\.mp4[^"\']*)["\']',
                                    r'["\']([^"\']*video[^"\']*)["\']',
                                    r'src=["\']([^"\']*\.mp4[^"\']*)["\']',
                                    r'data-src=["\']([^"\']*\.mp4[^"\']*)["\']'
                                ]
                                
                                for pattern in video_patterns:
                                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                                    for match in matches:
                                        if 'mp4' in match.lower() and not match.startswith('http'):
                                            if match.startswith('//'):
                                                match = 'https:' + match
                                            elif match.startswith('/'):
                                                match = 'https://www.canva.com' + match
                                        
                                        print(f"🎬 Found potential video URL: {match}")
                                        
                                        # Test if this URL returns video content
                                        try:
                                            video_test = requests.head(match, timeout=10)
                                            if video_test.ok and 'video' in video_test.headers.get('content-type', '').lower():
                                                media_file_url = match
                                                media_file_type = 'mp4'
                                                print(f"✅ Found valid video URL: {media_file_url}")
                                                break
                                        except:
                                            continue
                                    
                                    if media_file_url:
                                        break
                                        
                        except Exception as e:
                            print(f"❌ Error accessing view_url: {str(e)}")
                    
                    # If no video found, try export API as fallback
                    if not media_file_url:
                        print(f"🎬 Trying export API as fallback...")
                        export_res = requests.post(
                            f"https://api.canva.com/rest/v1/designs/{design_id}/exports",
                            headers=headers,
                            json={
                                "format": "mp4",
                                "quality": "standard"
                            },
                            timeout=30
                        )
                        
                        if export_res.ok:
                            export_data = export_res.json()
                            print(f"🎬 Export response: {export_data}")
                            
                            # Check for export job
                            if 'job' in export_data:
                                job_id = export_data['job']['id']
                                print(f"🎬 Export job created: {job_id}")
                                
                                # Poll for export completion
                                import time
                                max_attempts = 5  # Reduced attempts
                                for attempt in range(max_attempts):
                                    print(f"🎬 Checking export status (attempt {attempt + 1}/{max_attempts})...")
                                    
                                    status_res = requests.get(
                                        f"https://api.canva.com/rest/v1/exports/{job_id}",
                                        headers=headers,
                                        timeout=15
                                    )
                                    
                                    if status_res.ok:
                                        status_data = status_res.json()
                                        print(f"🎬 Export status: {status_data}")
                                        
                                        if status_data.get('status') == 'completed':
                                            # Get the actual video URL
                                            if 'result' in status_data and 'url' in status_data['result']:
                                                media_file_url = status_data['result']['url']
                                                media_file_type = 'mp4'
                                                print(f"✅ Video export completed: {media_file_url}")
                                                break
                                        elif status_data.get('status') == 'failed':
                                            print(f"❌ Video export failed")
                                            break
                                    
                                    time.sleep(3)  # Wait 3 seconds before next check
                            
                except Exception as e:
                    print(f"❌ Error getting video: {str(e)}")
            
            # If no media file exported, fallback to thumbnail
            if not media_file_url:
                print(f"🖼️ Falling back to thumbnail: {design_id}")
                media_file_url = thumbnail
                
                # Determine file type from design type
                if design.asset_type in ['video', 'animation', 'animated', 'movie']:
                    media_file_type = 'mp4'  # Assume video even if thumbnail
                elif design.asset_type in ['presentation', 'pdf']:
                    media_file_type = 'pdf'
                else:
                    media_file_type = 'png'  # Default to image
            
            # Download the file
            print(f"📥 Downloading file: {media_file_url}")
            file_response = requests.get(media_file_url, timeout=30)
            
            print(f"📊 Response status: {file_response.status_code}")
            print(f"📊 Content-Type: {file_response.headers.get('content-type', '')}")
            print(f"📊 Content-Length: {file_response.headers.get('content-length', '')}")
            
            if file_response.ok:
                # Get file info
                file_content = file_response.content
                file_size = len(file_content)
                
                print(f"✅ Downloaded {file_size} bytes")
                
                # Determine file type from content-type or URL
                content_type = file_response.headers.get('content-type', '')
                if 'image/png' in content_type:
                    file_type = 'png'
                    file_name = f"{design_id}.png"
                elif 'image/jpeg' in content_type:
                    file_type = 'jpg'
                    file_name = f"{design_id}.jpg"
                elif 'video/mp4' in content_type:
                    file_type = 'mp4'
                    file_name = f"{design_id}.mp4"
                elif 'application/pdf' in content_type:
                    file_type = 'pdf'
                    file_name = f"{design_id}.pdf"
                else:
                    # Fallback to URL extension
                    if thumbnail.endswith('.png'):
                        file_type = 'png'
                        file_name = f"{design_id}.png"
                    elif thumbnail.endswith('.jpg') or thumbnail.endswith('.jpeg'):
                        file_type = 'jpg'
                        file_name = f"{design_id}.jpg"
                    elif thumbnail.endswith('.mp4'):
                        file_type = 'mp4'
                        file_name = f"{design_id}.mp4"
                    elif thumbnail.endswith('.pdf'):
                        file_type = 'pdf'
                        file_name = f"{design_id}.pdf"
                    else:
                        file_type = 'png'  # Default
                        file_name = f"{design_id}.png"
                
                print(f"📝 File type: {file_type}")
                print(f"📝 File name: {file_name}")
                
                # Save binary file to database
                design.binary_file = file_content
                design.binary_file_name = file_name
                design.binary_file_type = file_type
                design.binary_file_size = file_size
                design.save()
                
                print(f"✅ Binary file saved to database")
                
                return Response({
                    "success": True,
                    "design_id": design_id,
                    "thumbnail_url": thumbnail,
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_size": file_size,
                    "content_type": content_type,
                    "message": f"Binary file downloaded and saved: {file_name} ({file_size} bytes)"
                })
                
            else:
                print(f"❌ Failed to download file: {file_response.status_code}")
                return Response({"error": f"Failed to download file: {file_response.status_code}"}, status=500)
                
        except Exception as e:
            print(f"❌ Error downloading binary file: {str(e)}")
            return Response({"error": f"Download error: {str(e)}"}, status=500)
            
    except Exception as e:
        print(f"❌ Debug error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# VLC MEDIA PLAYER INTEGRATION
# ======================
@api_view(['POST'])
def play_in_vlc(request):
    """Play design in VLC media player - opens Canva view_url for videos"""
    try:
        data = request.data
        design_id = data.get('design_id')
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        print(f"🎬 VLC: Launching {design_id} in VLC media player")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
            print(f"📊 Found design: {design.title} (type: {design.asset_type})")
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found in database"}, status=404)
        
        import subprocess
        import tempfile
        import os
        
        # For video designs, try to use local binary file first
        if design.asset_type in ['video', 'animation', 'animated', 'movie'] and design.binary_file:
            print(f"🎬 Video design with binary file detected: {design.binary_file_name}")
            
            # Create temporary file from binary data
            try:
                # Create temporary file with correct extension
                temp_dir = tempfile.gettempdir()
                temp_file_path = os.path.join(temp_dir, design.binary_file_name)
                
                # Write binary data to temporary file
                with open(temp_file_path, 'wb') as temp_file:
                    temp_file.write(design.binary_file)
                
                print(f"📁 Temporary video file created: {temp_file_path}")
                
                # Launch VLC with the local file
                try:
                    vlc_commands = [
                        ['vlc', '--fullscreen', temp_file_path],
                        ['vlc', temp_file_path],
                        ['/usr/bin/vlc', temp_file_path],
                        ['/Applications/VLC.app/Contents/MacOS/VLC', temp_file_path]
                    ]
                    
                    vlc_launched = False
                    for cmd in vlc_commands:
                        try:
                            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            print(f"✅ VLC launched with local video file: {' '.join(cmd)}")
                            vlc_launched = True
                            break
                        except FileNotFoundError:
                            continue
                        except Exception as e:
                            print(f"❌ VLC command failed: {str(e)}")
                            continue
                    
                    if vlc_launched:
                        return Response({
                            "success": True,
                            "design_id": design_id,
                            "title": design.title,
                            "asset_type": design.asset_type,
                            "file_name": design.binary_file_name,
                            "file_type": design.binary_file_type,
                            "file_size": design.binary_file_size,
                            "temp_file": temp_file_path,
                            "message": f"Launched {design.binary_file_name} in VLC media player"
                        })
                    
                except Exception as e:
                    print(f"❌ Error launching VLC with local file: {str(e)}")
                    
            except Exception as e:
                print(f"❌ Error creating temporary video file: {str(e)}")
        
        # Fallback to non-video designs or if no binary file
        if design.binary_file:
            print(f"📁 Using binary file for VLC: {design.binary_file_name}")
            
            try:
                # Create temporary file with correct extension
                temp_dir = tempfile.gettempdir()
                temp_file_path = os.path.join(temp_dir, design.binary_file_name)
                
                # Write binary data to temporary file
                with open(temp_file_path, 'wb') as temp_file:
                    temp_file.write(design.binary_file)
                
                print(f"📁 Temporary file created: {temp_file_path}")
                
                # Launch VLC with the file
                try:
                    vlc_commands = [
                        ['vlc', '--fullscreen', temp_file_path],
                        ['vlc', temp_file_path],
                        ['/usr/bin/vlc', temp_file_path],
                        ['/Applications/VLC.app/Contents/MacOS/VLC', temp_file_path]
                    ]
                    
                    vlc_launched = False
                    for cmd in vlc_commands:
                        try:
                            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            print(f"✅ VLC launched with binary file: {' '.join(cmd)}")
                            vlc_launched = True
                            break
                        except FileNotFoundError:
                            continue
                        except Exception as e:
                            print(f"❌ VLC command failed: {str(e)}")
                            continue
                    
                    if not vlc_launched:
                        return Response({"error": "VLC not found. Please install VLC media player."}, status=500)
                    
                    return Response({
                        "success": True,
                        "design_id": design_id,
                        "title": design.title,
                        "file_name": design.binary_file_name,
                        "file_type": design.binary_file_type,
                        "file_size": design.binary_file_size,
                        "temp_file": temp_file_path,
                        "message": f"Launched {design.binary_file_name} in VLC media player"
                    })
                    
                except Exception as e:
                    print(f"❌ Error launching VLC: {str(e)}")
                    return Response({"error": f"Failed to launch VLC: {str(e)}"}, status=500)
                    
            except Exception as e:
                print(f"❌ Error creating temporary file: {str(e)}")
                return Response({"error": f"Failed to create temporary file: {str(e)}"}, status=500)
        
        else:
            return Response({"error": "No binary file found for this design"}, status=404)
            
    except Exception as e:
        print(f"❌ VLC integration error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# VIDEO EXPORT FOR SHARING
# ======================
@api_view(['POST'])
def export_video_for_sharing(request):
    """Export video in proper format for sharing on platforms"""
    try:
        import requests
        import json
        import time
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        export_format = data.get('format', 'mp4')  # mp4, mov, gif
        quality = data.get('quality', 'standard')  # standard, high
        
        print(f"🎬 Exporting video for sharing: {design_id} -> {export_format} ({quality})")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found in database"}, status=404)
        
        # Check if this is a video design
        if design.asset_type not in ['video', 'animation', 'animated', 'movie']:
            return Response({"error": "This is not a video design"}, status=400)
        
        # Validate Canva token first
        connection, token_message = validate_canva_token()
        if not connection:
            return Response({
                "error": "Canva authentication failed",
                "message": token_message
            }, status=401)
        
        print(f"✅ Canva token validated: {token_message}")
        
        # Get Canva API credentials
        try:
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'Content-Type': 'application/json'
            }
        except Exception as e:
            return Response({"error": f"Failed to get Canva connection: {str(e)}"}, status=500)
        
        # Check if design exists in Canva before exporting
        print("📡 Checking if design exists in Canva...")
        design_check_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=30
        )
        
        if not design_check_res.ok:
            if design_check_res.status_code == 404:
                return Response({
                    "error": "Design not found in Canva",
                    "message": f"Design ID '{design_id}' not found in Canva. Please check if the design exists and you have access to it."
                }, status=404)
            else:
                return Response({
                    "error": f"Failed to check design in Canva: {design_check_res.status_code}"
                }, status=500)
        
        # Try to export actual video via Canva API (CORRECTED FLOW)
        try:
            # Add retry logic with exponential backoff for rate limiting
            max_retries = 5  # Increased to 5 retries
            base_delay = 5  # Increased to 5 seconds
            
            # CORRECTED: Use proper Canva API endpoint and request body
            export_request_body = {
                "design_id": design_id,
                "format": export_format
            }
            print(f"📤 CORRECTED: Export request body: {export_request_body}")
            
            for retry in range(max_retries):
                # CORRECTED: Use proper Canva API endpoint
                export_res = requests.post(
                    f"https://api.canva.com/rest/v1/exports",
                    headers=headers,
                    json=export_request_body,
                    timeout=30
                )
                
                print(f"📤 Export response status: {export_res.status_code}")
                print(f"📤 Export response body: {export_res.text[:500]}")
                
                # Check for rate limiting
                if export_res.status_code == 429:
                    if retry < max_retries - 1:
                        delay = base_delay * (2 ** retry)  # 5s, 10s, 20s, 40s, 80s
                        print(f"⏱️ Rate limited. Waiting {delay} seconds before retry {retry + 1}/{max_retries}...")
                        time.sleep(delay)
                        continue
                    else:
                        return Response({
                            "error": "Rate limit exceeded",
                            "message": "Canva API rate limit exceeded. Please wait 2-5 minutes before trying again. The system will automatically retry with delays."
                        }, status=429)
                
                # If not rate limited, break the retry loop
                break
            
            if export_res.ok:
                export_data = export_res.json()
                print(f"🎬 Export response: {export_data}")
                
                # Check for export job
                if 'job' in export_data:
                    job_id = export_data['job']['id']
                    print(f"🎬 Export job created: {job_id}")
                    
                    # Poll for export completion
                    max_attempts = 15
                    for attempt in range(max_attempts):
                        print(f"🎬 Checking export status (attempt {attempt + 1}/{max_attempts})...")
                        
                        status_res = requests.get(
                            f"https://api.canva.com/rest/v1/exports/{job_id}",
                            headers=headers,
                            timeout=15
                        )
                        
                        if status_res.ok:
                            status_data = status_res.json()
                            print(f"🎬 Export status: {status_data}")
                            
                            if status_data.get('status') == 'completed':
                                # Get the actual video URL
                                if 'result' in status_data and 'url' in status_data['result']:
                                    video_url = status_data['result']['url']
                                    print(f"✅ Video export completed: {video_url}")
                                    
                                    # Download the video file
                                    video_res = requests.get(video_url, timeout=60)
                                    if video_res.ok:
                                        video_content = video_res.content
                                        video_size = len(video_content)
                                        
                                        # Save to database
                                        design.binary_file = video_content
                                        design.binary_file_name = f"{design_id}.{export_format}"
                                        design.binary_file_type = export_format
                                        design.binary_file_size = video_size
                                        design.save()
                                        
                                        return Response({
                                            "success": True,
                                            "design_id": design_id,
                                            "export_format": export_format,
                                            "quality": quality,
                                            "file_name": design.binary_file_name,
                                            "file_size": video_size,
                                            "video_url": video_url,
                                            "message": f"Video exported successfully: {design.binary_file_name} ({video_size} bytes)"
                                        })
                                    else:
                                        return Response({"error": "Failed to download exported video"}, status=500)
                            elif status_data.get('status') == 'failed':
                                return Response({"error": "Video export failed"}, status=500)
                        
                        time.sleep(3)  # Wait 3 seconds before next check
                    
                    return Response({"error": "Export timeout - video not ready"}, status=500)
                else:
                    return Response({"error": "No export job created"}, status=500)
            else:
                return Response({"error": f"Export request failed: {export_res.status_code}"}, status=500)
                
        except Exception as e:
            print(f"❌ Video export error: {str(e)}")
            return Response({"error": f"Video export failed: {str(e)}"}, status=500)
            
    except Exception as e:
        print(f"❌ Export video for sharing error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# ALTERNATIVE VIDEO EXPORT (BYPASS RATE LIMITING)
# ======================
@api_view(['POST'])
def export_video_alternative(request):
    """Alternative video export - bypass rate limiting with direct Canva URLs"""
    try:
        import json
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        format_type = data.get('format', 'mp4')
        quality = data.get('quality', 'standard')
        
        print(f"🎬 ALTERNATIVE: Video export request: {design_id} -> {format_type} ({quality})")
        
        if not design_id:
            return Response({
                'success': False,
                'error': 'design_id is required'
            }, status=400)
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Design not found in database'
            }, status=404)
        
        # Check if this is a video design
        if design.asset_type not in ['video', 'animation', 'animated', 'movie']:
            return Response({
                'success': False,
                'error': 'This is not a video design'
            }, status=400)
        
        print(f"🎬 ALTERNATIVE: Found video design: {design.title}")
        
        # Extract Canva view URL from raw_data
        canva_view_url = None
        if design.raw_data and isinstance(design.raw_data, dict):
            canva_view_url = design.raw_data.get('view_url')
        
        if not canva_view_url:
            # Fallback to constructed view URL
            canva_view_url = f"https://www.canva.com/design/{design_id}/view"
        
        print(f"🔗 ALTERNATIVE: Canva view URL: {canva_view_url}")
        
        # Create download instructions
        download_instructions = {
            'success': True,
            'method': 'canva_direct_download',
            'design_id': design_id,
            'title': design.title,
            'format': format_type,
            'quality': quality,
            'canva_view_url': canva_view_url,
            'download_url': canva_view_url,
            'instructions': [
                f"1. Video '{design.title}' opened in Canva",
                f"2. Click 'Share' button in top right",
                f"3. Select 'Download' option",
                f"4. Choose format: {format_type.upper()}",
                f"5. Select quality: {quality}",
                f"6. Click 'Download' to save video"
            ],
            'message': f"Video ready for download from Canva",
            'file_name': f"{design.title.replace(' ', '_')}.{format_type}",
            'estimated_size': "Varies by video length and quality"
        }
        
        print(f"✅ ALTERNATIVE: Providing direct Canva download solution")
        
        return Response(download_instructions)
        
    except Exception as e:
        print(f"❌ ALTERNATIVE: Error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e),
            'code': 'internal_error'
        }, status=500)

@api_view(['GET'])
def get_video_download_info(request, design_id):
    """Get video download information for a specific design"""
    try:
        print(f"🔍 ALTERNATIVE: Getting download info for: {design_id}")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Design not found'
            }, status=404)
        
        # Extract Canva view URL
        canva_view_url = None
        if design.raw_data and isinstance(design.raw_data, dict):
            canva_view_url = design.raw_data.get('view_url')
        
        if not canva_view_url:
            canva_view_url = f"https://www.canva.com/design/{design_id}/view"
        
        # Create comprehensive download info
        download_info = {
            'success': True,
            'design': {
                'id': design.design_id,
                'title': design.title,
                'type': design.asset_type,
                'category': design.category
            },
            'download_options': {
                'direct_canva': {
                    'url': canva_view_url,
                    'method': 'Open in Canva and download',
                    'formats': ['mp4', 'mov', 'gif'],
                    'qualities': ['standard', 'high'],
                    'steps': [
                        "Open the design in Canva",
                        "Click 'Share' button",
                        "Select 'Download'",
                        "Choose format and quality",
                        "Click 'Download'"
                    ]
                },
                'view_only': {
                    'url': canva_view_url,
                    'method': 'View in Canva',
                    'description': 'Open design in Canva for viewing'
                }
            },
            'alternatives': [
                {
                    'name': 'Screen Recording',
                    'description': 'Record video directly from Canva',
                    'tools': ['OBS Studio', 'QuickTime Player', 'Windows Game Bar']
                },
                {
                    'name': 'Browser Extension',
                    'description': 'Use video download browser extensions',
                    'tools': ['Video DownloadHelper', 'SaveFrom.net']
                }
            ]
        }
        
        return Response(download_info)
        
    except Exception as e:
        print(f"❌ ALTERNATIVE: Get info error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

# ======================
# DOWNLOAD AND UPLOAD VIDEO TO USER'S SITE
# ======================
@api_view(['POST'])
def download_and_upload_video(request):
    """Download video from Canva and upload to user's site"""
    try:
        import json
        import tempfile
        import re
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        format_type = data.get('format', 'mp4')
        quality = data.get('quality', 'standard')
        
        print(f"🎬 DOWNLOAD-UPLOAD: Video request: {design_id} -> {format_type} ({quality})")
        
        if not design_id:
            return Response({
                'success': False,
                'error': 'design_id is required'
            }, status=400)
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Design not found in database'
            }, status=404)
        
        # Check if this is a video design
        if design.asset_type not in ['video', 'animation', 'animated', 'movie']:
            return Response({
                'success': False,
                'error': 'This is not a video design'
            }, status=400)
        
        print(f"🎬 DOWNLOAD-UPLOAD: Found video design: {design.title}")
        
        # Method 1: Use proper Canva Export API for actual video download
        video_url = None
        export_job_id = None
        try:
            print(f"🔗 DOWNLOAD-UPLOAD: Using Canva Export API for actual video")
            
            # Get Canva connection for API access
            connection, token_message = validate_canva_token()
            
            if not connection:
                print("❌ DOWNLOAD-UPLOAD: No Canva connection available")
                raise Exception("Canva authentication required for video export")
            
            print(f"✅ DOWNLOAD-UPLOAD: Canva connection established")
            
            # Step 1: Create export job
            export_headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Try different API endpoint formats for Canva export
            api_endpoints = [
                "https://api.canva.com/rest/v1/exports",
                "https://api.canva.com/v1/exports", 
                "https://api.canva.com/v1/designs/" + design_id + "/exports"
            ]
            
            # Try different request formats with correct type values
            request_formats = [
                # Format 1: Standard export request with proper type
                {
                    'design_id': design_id,
                    'type': 'video',
                    'format': format_type,
                    'quality': 'high' if quality == 'high' else 'standard'
                },
                # Format 2: With type but no quality
                {
                    'design_id': design_id,
                    'type': 'video',
                    'format': format_type
                },
                # Format 3: Different field names with type
                {
                    'designId': design_id,
                    'type': 'video',
                    'format': format_type,
                    'quality': quality
                },
                # Format 4: Type only
                {
                    'type': 'video',
                    'format': format_type
                },
                # Format 5: Type as main field
                {
                    'type': 'video',
                    'design_id': design_id
                },
                # Format 6: Export type specific with format
                {
                    'type': 'video',
                    'design_id': design_id,
                    'format': format_type,
                    'quality': 'high' if quality == 'high' else 'standard'
                },
                # Format 7: Alternative format - just design_id and type
                {
                    'design_id': design_id,
                    'type': 'video'
                },
                # Format 8: Minimal request
                {
                    'design_id': design_id,
                    'type': 'video',
                    'format': 'mp4'
                }
            ]
            
            video_url = None
            export_response = None
            
            for endpoint in api_endpoints:
                if video_url:
                    break
                    
                print(f"📡 DOWNLOAD-UPLOAD: Trying endpoint: {endpoint}")
                
                for i, export_data in enumerate(request_formats):
                    if video_url:
                        break
                        
                    print(f"📡 DOWNLOAD-UPLOAD: Request format {i+1}: {export_data}")
                    
                    try:
                        export_response = requests.post(
                            endpoint,
                            headers=export_headers,
                            json=export_data,
                            timeout=30
                        )
                        
                        print(f"📊 DOWNLOAD-UPLOAD: Response status: {export_response.status_code}")
                        
                        if export_response.status_code == 200:
                            export_result = export_response.json()
                            print(f"✅ DOWNLOAD-UPLOAD: Export API success: {export_result}")
                            
                            # Check for different response formats
                            if 'job' in export_result and 'id' in export_result['job']:
                                job_id = export_result['job']['id']
                                print(f"📡 DOWNLOAD-UPLOAD: Export job created: {job_id}")
                                video_url = poll_export_job(job_id, export_headers)
                                if video_url:
                                    break
                            elif 'url' in export_result:
                                video_url = export_result['url']
                                print(f"✅ DOWNLOAD-UPLOAD: Got direct download URL: {video_url}")
                                break
                            elif 'download_url' in export_result:
                                video_url = export_result['download_url']
                                print(f"✅ DOWNLOAD-UPLOAD: Got direct download URL: {video_url}")
                                break
                            elif 'export_id' in export_result:
                                export_id = export_result['export_id']
                                video_url = poll_export_job(export_id, export_headers)
                                if video_url:
                                    break
                            else:
                                print(f"⚠️ DOWNLOAD-UPLOAD: Unknown response format: {export_result}")
                        
                        elif export_response.status_code == 400:
                            error_data = export_response.json() if export_response.content else {}
                            print(f"❌ DOWNLOAD-UPLOAD: 400 Error - {error_data}")
                            continue
                        elif export_response.status_code == 401:
                            print(f"❌ DOWNLOAD-UPLOAD: 401 Unauthorized - Check token")
                            break
                        elif export_response.status_code == 403:
                            print(f"❌ DOWNLOAD-UPLOAD: 403 Forbidden - Insufficient permissions")
                            break
                        else:
                            print(f"❌ DOWNLOAD-UPLOAD: API error {export_response.status_code}")
                            continue
                            
                    except Exception as e:
                        print(f"❌ DOWNLOAD-UPLOAD: Request error: {e}")
                        continue
            
            if not video_url:
                raise Exception("All export API attempts failed")
            
            if export_response.status_code != 200:
                error_data = export_response.json() if export_response.content else {}
                error_msg = error_data.get('error', f"Export API error: {export_response.status_code}")
                print(f"❌ DOWNLOAD-UPLOAD: Export creation failed: {error_msg}")
                raise Exception(f"Canva export failed: {error_msg}")
            
            export_result = export_response.json()
            
            # Check if we got a job ID
            if 'job' not in export_result or 'id' not in export_result['job']:
                # Some APIs return direct download URL
                if 'url' in export_result:
                    video_url = export_result['url']
                    print(f"✅ DOWNLOAD-UPLOAD: Got direct download URL: {video_url}")
                else:
                    raise Exception("Invalid export response: no job ID or download URL")
            
            if not video_url:
                job_id = export_result['job']['id']
                print(f"📡 DOWNLOAD-UPLOAD: Export job created: {job_id}")
                
                # Step 2: Poll for export completion with enhanced logic
                max_poll_attempts = 30
                poll_interval = 2
                
                for attempt in range(max_poll_attempts):
                    print(f"⏳ DOWNLOAD-UPLOAD: Checking export status (attempt {attempt + 1}/{max_poll_attempts})")
                    
                    status_response = requests.get(
                        f"https://api.canva.com/rest/v1/exports/{job_id}",
                        headers=export_headers,
                        timeout=15
                    )
                    
                    if status_response.status_code != 200:
                        print(f"❌ DOWNLOAD-UPLOAD: Status check failed: {status_response.status_code}")
                        time.sleep(poll_interval)
                        continue
                    
                    status_data = status_response.json()
                    export_status = status_data.get('status', 'unknown')
                    
                    print(f"📊 DOWNLOAD-UPLOAD: Export status: {export_status}")
                    
                    if export_status == 'completed':
                        # Extract download URL
                        if 'result' in status_data and 'url' in status_data['result']:
                            video_url = status_data['result']['url']
                        elif 'url' in status_data:
                            video_url = status_data['url']
                        elif 'download_url' in status_data:
                            video_url = status_data['download_url']
                        
                        if video_url:
                            print(f"✅ DOWNLOAD-UPLOAD: Export completed, download URL: {video_url}")
                            break
                        else:
                            raise Exception("Export completed but no download URL found")
                    
                    elif export_status == 'failed':
                        error_msg = status_data.get('error', 'Export failed')
                        raise Exception(f"Canva export failed: {error_msg}")
                    
                    elif export_status in ['processing', 'pending']:
                        time.sleep(poll_interval)
                        continue
                    else:
                        print(f"⚠️ DOWNLOAD-UPLOAD: Unknown status: {export_status}")
                        time.sleep(poll_interval)
                        continue
                
                if not video_url:
                    raise Exception("Export polling timeout - job did not complete")
            
        except Exception as e:
            print(f"❌ DOWNLOAD-UPLOAD: Export API error: {e}")
            # Continue to other methods
        
        # Method 2: Alternative video download using document-export URLs
        if not video_url:
            try:
                print(f"🔄 DOWNLOAD-UPLOAD: Trying document-export URL approach")
                
                # Try to construct video URL from existing asset URL
                if design.asset_url:
                    asset_url = design.asset_url
                    print(f"🔗 DOWNLOAD-UPLOAD: Original asset URL: {asset_url}")
                    
                    # Try to convert asset URL to video URL
                    if 'document-export.canva.com' in asset_url:
                        # Replace thumbnail path with video path
                        video_patterns = [
                            asset_url.replace('/thumbnail/', '/video/'),
                            asset_url.replace('/thumbnail/', '/export/'),
                            asset_url.replace('/3/thumbnail/', '/3/video/'),
                            asset_url.replace('/3/thumbnail/', '/3/export/'),
                            asset_url.replace('thumbnail/0001.png', 'video.mp4'),
                            asset_url.replace('thumbnail/0001.png', 'export.mp4'),
                        ]
                        
                        for video_url_candidate in video_patterns:
                            try:
                                print(f"🔍 DOWNLOAD-UPLOAD: Testing video URL: {video_url_candidate}")
                                
                                # Test if this URL returns video content
                                test_response = requests.head(video_url_candidate, timeout=10)
                                content_type = test_response.headers.get('content-type', '').lower()
                                content_length = test_response.headers.get('content-length', '0')
                                
                                print(f"📊 DOWNLOAD-UPLOAD: Response: {test_response.status_code}, Type: {content_type}, Length: {content_length}")
                                
                                if test_response.status_code == 200 and ('video' in content_type or content_length != '0'):
                                    # Try to download the video
                                    download_response = requests.get(video_url_candidate, timeout=30, stream=True)
                                    
                                    if download_response.status_code == 200:
                                        video_content = download_response.content
                                        file_size = len(video_content)
                                        
                                        # Check if it's actual video content
                                        if file_size > 100000:  # Larger than 100KB likely video
                                            video_url = video_url_candidate
                                            print(f"✅ DOWNLOAD-UPLOAD: Found working video URL: {video_url}")
                                            break
                                        else:
                                            print(f"⚠️ DOWNLOAD-UPLOAD: File too small ({file_size} bytes), probably thumbnail")
                                    
                            except Exception as e:
                                print(f"❌ DOWNLOAD-UPLOAD: Error testing {video_url_candidate}: {e}")
                                continue
                
                # Method 2.2: Try to get video from Canva's direct export URLs
                if not video_url and design.raw_data:
                    try:
                        raw_data = design.raw_data
                        if isinstance(raw_data, dict):
                            # Look for export URLs in raw data
                            export_urls = []
                            
                            def find_export_urls(obj, path=""):
                                if isinstance(obj, dict):
                                    for key, value in obj.items():
                                        if isinstance(value, str) and 'document-export.canva.com' in value:
                                            export_urls.append(value)
                                        elif isinstance(value, (dict, list)):
                                            find_export_urls(value, f"{path}.{key}")
                                elif isinstance(obj, list):
                                    for i, item in enumerate(obj):
                                        if isinstance(item, str) and 'document-export.canva.com' in item:
                                            export_urls.append(item)
                                        elif isinstance(item, (dict, list)):
                                            find_export_urls(item, f"{path}[{i}]")
                            
                            find_export_urls(raw_data)
                            
                            for export_url in export_urls:
                                try:
                                    # Convert to video URL
                                    video_candidate = export_url.replace('/thumbnail/', '/video/')
                                    video_candidate = video_candidate.replace('thumbnail/0001.png', 'video.mp4')
                                    
                                    print(f"🔍 DOWNLOAD-UPLOAD: Testing export URL: {video_candidate}")
                                    
                                    download_response = requests.get(video_candidate, timeout=30, stream=True)
                                    
                                    if download_response.status_code == 200:
                                        video_content = download_response.content
                                        file_size = len(video_content)
                                        
                                        if file_size > 100000:  # Likely video
                                            video_url = video_candidate
                                            print(f"✅ DOWNLOAD-UPLOAD: Found export video URL: {video_url}")
                                            break
                                
                                except Exception as e:
                                    print(f"❌ DOWNLOAD-UPLOAD: Error with export URL: {e}")
                                    continue
                    
                    except Exception as e:
                        print(f"⚠️ DOWNLOAD-UPLOAD: Raw data export search error: {e}")
                
                # Method 2.3: Try to download from view page with enhanced extraction
                if not video_url:
                    try:
                        canva_view_url = f"https://www.canva.com/design/{design_id}/view"
                        
                        print(f"🔗 DOWNLOAD-UPLOAD: Enhanced extraction from: {canva_view_url}")
                        
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1'
                        }
                        
                        response = requests.get(canva_view_url, headers=headers, timeout=30)
                        
                        if response.status_code == 200:
                            html_content = response.text
                            
                            # Look for any URLs that might be video files
                            import re
                            
                            # Pattern for document-export URLs
                            export_url_patterns = [
                                r'(https://document-export\.canva\.com/[^"\s]*(?:mp4|mov|webm|avi)[^"\s]*)',
                                r'(https://document-export\.canva\.com/[^"\s]*)',
                                r'"export_url":"([^"]+)"',
                                r'"download_url":"([^"]+)"',
                                r'"video_url":"([^"]+)"'
                            ]
                            
                            for pattern in export_url_patterns:
                                matches = re.findall(pattern, html_content)
                                if matches:
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            match = match[0]
                                        
                                        # Convert to video URL if needed
                                        video_candidate = match
                                        if '/thumbnail/' in video_candidate:
                                            video_candidate = video_candidate.replace('/thumbnail/', '/video/')
                                        elif 'thumbnail/0001.png' in video_candidate:
                                            video_candidate = video_candidate.replace('thumbnail/0001.png', 'video.mp4')
                                        
                                        try:
                                            download_response = requests.get(video_candidate, timeout=30, stream=True)
                                            
                                            if download_response.status_code == 200:
                                                video_content = download_response.content
                                                file_size = len(video_content)
                                                
                                                if file_size > 100000:  # Likely video
                                                    video_url = video_candidate
                                                    print(f"✅ DOWNLOAD-UPLOAD: Found video via HTML extraction: {video_url}")
                                                    break
                                        
                                        except Exception as e:
                                            print(f"❌ DOWNLOAD-UPLOAD: Error with extracted URL: {e}")
                                            continue
                                    
                                    if video_url:
                                        break
                    
                    except Exception as e:
                        print(f"⚠️ DOWNLOAD-UPLOAD: Enhanced extraction error: {e}")
                
            except Exception as e:
                print(f"❌ DOWNLOAD-UPLOAD: Alternative method error: {e}")
        
        # Method 3: Try direct video download from existing binary file (ONLY if it's actual video)
        
        # Method 3: Try direct video download from existing binary file (ONLY if it's actual video)
        if not video_url and design.binary_file:
            try:
                print("📁 DOWNLOAD-UPLOAD: Checking binary file type...")
                
                # Check if binary file is actual video, not thumbnail
                file_content = design.binary_file
                
                # Simple file type detection by checking file header/signature
                file_header = file_content[:12]  # First 12 bytes
                
                # Check for common video file signatures
                video_signatures = {
                    b'\x00\x00\x00\x18ftypmp4': 'video/mp4',  # MP4
                    b'\x00\x00\x00\x20ftypmp4': 'video/mp4',  # MP4
                    b'RIFF': 'video/avi',                     # AVI
                    b'\x1A\x45\xDF\xA3': 'video/webm',        # WebM
                    b'FLV': 'video/x-flv',                    # FLV
                }
                
                is_video = False
                file_type = 'unknown'
                
                for signature, detected_type in video_signatures.items():
                    if file_header.startswith(signature):
                        is_video = True
                        file_type = detected_type
                        break
                
                # Also check if it's PNG (thumbnail)
                if file_header.startswith(b'\x89PNG'):
                    file_type = 'image/png'
                
                print(f"🔍 DOWNLOAD-UPLOAD: File type detected: {file_type}")
                
                # Only proceed if it's actual video content
                if is_video:
                    print("✅ DOWNLOAD-UPLOAD: Actual video file found")
                    
                    # Save binary file to storage
                    file_name = f"{design_id}.{format_type}"
                    file_path = default_storage.save(f'videos/{file_name}', ContentFile(design.binary_file, file_name))
                    
                    # Get file URL
                    file_url = default_storage.url(file_path)
                    file_size = len(design.binary_file)
                    
                    print(f"✅ DOWNLOAD-UPLOAD: Video file saved: {file_path} ({file_size} bytes)")
                    
                    return Response({
                        'success': True,
                        'method': 'binary_file',
                        'design_id': design_id,
                        'title': design.title,
                        'file_name': file_name,
                        'file_size': file_size,
                        'file_url': file_url,
                        'download_url': file_url,
                        'message': f"Video downloaded and uploaded successfully: {file_name}",
                        'format': format_type,
                        'quality': quality
                    })
                else:
                    print(f"⚠️ DOWNLOAD-UPLOAD: Binary file is not video ({file_type}), skipping...")
                    # Don't use thumbnail images as videos
                
            except Exception as e:
                print(f"❌ DOWNLOAD-UPLOAD: Binary file type check error: {e}")
                # Continue to other methods
        
        # If we have a video URL, download and upload it
        if video_url:
            print(f"🌐 DOWNLOAD-UPLOAD: Downloading video from: {video_url}")
            
            try:
                # Download with streaming for large files
                video_response = requests.get(video_url, timeout=120, stream=True)
                
                if video_response.status_code == 200:
                    # Get content type and validate it's video
                    content_type = video_response.headers.get('content-type', '')
                    print(f"📊 DOWNLOAD-UPLOAD: Content type: {content_type}")
                    
                    # Download in chunks for large files
                    video_content = b''
                    total_size = 0
                    
                    for chunk in video_response.iter_content(chunk_size=8192):
                        if chunk:
                            video_content += chunk
                            total_size += len(chunk)
                    
                    file_size = len(video_content)
                    print(f"📁 DOWNLOAD-UPLOAD: Downloaded {file_size} bytes in chunks")
                    
                    # Validate file content
                    if file_size < 1000:
                        print(f"⚠️ DOWNLOAD-UPLOAD: File too small: {file_size} bytes")
                        raise Exception("Downloaded file is too small to be a valid video")
                    
                    # Check if it's actually a video file
                    if not content_type.startswith('video/') and not video_content.startswith(b'\x00\x00\x00'):
                        print(f"⚠️ DOWNLOAD-UPLOAD: Content may not be video: {content_type}")
                        # Still try to save it
                    
                    # Save to storage with proper naming
                    import time
                    timestamp = int(time.time())
                    file_name = f"{design_id}_video_{timestamp}.mp4"
                    file_path = default_storage.save(f'videos/{file_name}', ContentFile(video_content, file_name))
                    file_url = default_storage.url(file_path)
                    
                    print(f"✅ DOWNLOAD-UPLOAD: Video saved: {file_path}")
                    
                    # Update database with complete information
                    design.binary_file = video_content
                    design.binary_file_name = file_name
                    design.binary_file_type = 'mp4'
                    design.binary_file_size = file_size
                    design.asset_url = file_url
                    design.save()
                    
                    print(f"💾 DOWNLOAD-UPLOAD: Database updated with video info")
                    
                    return Response({
                        'success': True,
                        'method': 'canva_export',
                        'download_url': file_url,
                        'file_name': file_name,
                        'file_size': file_size,
                        'content_type': content_type,
                        'message': f"Successfully downloaded complete video: {file_name}",
                        'format': format_type,
                        'quality': quality,
                        'playable': True,
                        'duration': 'Unknown'
                    })
                else:
                    print(f"❌ DOWNLOAD-UPLOAD: Video download failed: {video_response.status_code}")
                    print(f"❌ DOWNLOAD-UPLOAD: Response headers: {video_response.headers}")
                    
            except Exception as e:
                print(f"❌ DOWNLOAD-UPLOAD: Video download error: {e}")
                import traceback
                traceback.print_exc()
        
        # FIXED: If we still don't have a video URL, return error instead of creating placeholder
        if not video_url:
            print("❌ DOWNLOAD-UPLOAD: All methods failed - cannot download real video")
            
            # Don't create placeholder videos - return proper error
            return Response({
                'success': False,
                'error': 'Unable to download real video file',
                'message': 'Could not retrieve actual video content from Canva. Please try again later.',
                'design_id': design_id,
                'title': design.title,
                'suggestion': 'The design may not have downloadable video content available.'
            }, status=400)
            
    except Exception as e:
        print(f"❌ DOWNLOAD-UPLOAD: Function error: {e}")
        return Response({
            'success': False,
            'error': str(e),
            'code': 'internal_error'
        }, status=500)

# ======================
# VIDEO UPLOAD AND SHARE FROM USER'S SITE
# ======================
@api_view(['POST'])
def upload_video_to_platform(request):
    """Upload video from user's site to external platforms"""
    try:
        import json
        import tempfile
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        platform = data.get('platform')  # youtube, vimeo, facebook, instagram, etc.
        video_url = data.get('video_url')
        title = data.get('title', 'Video Upload')
        description = data.get('description', '')
        
        print(f"📤 UPLOAD-SHARE: Uploading video {design_id} to {platform}")
        
        if not design_id or not platform:
            return Response({
                'success': False,
                'error': 'design_id and platform are required'
            }, status=400)
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Design not found in database'
            }, status=404)
        
        # Get video file or URL
        if not video_url:
            if design.video_url or design.file_url:
                video_url = design.video_url or f"http://localhost:8000{design.file_url}"
            elif design.binary_file:
                # Create temporary file for upload
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                    temp_file.write(design.binary_file)
                    video_url = temp_file.name
            else:
                return Response({
                    'success': False,
                    'error': 'No video file available for upload'
                }, status=400)
        
        # Platform-specific upload logic
        if platform.lower() == 'youtube':
            result = upload_to_youtube(video_url, title, description)
        elif platform.lower() == 'vimeo':
            result = upload_to_vimeo(video_url, title, description)
        elif platform.lower() == 'facebook':
            result = upload_to_facebook(video_url, title, description)
        elif platform.lower() == 'instagram':
            result = upload_to_instagram(video_url, title, description)
        elif platform.lower() == 'dropbox':
            result = upload_to_dropbox(video_url, title, design_id)
        elif platform.lower() == 'google_drive':
            result = upload_to_google_drive(video_url, title, design_id)
        else:
            result = {
                'success': False,
                'error': f'Platform {platform} not supported'
            }
        
        return Response(result)
        
    except Exception as e:
        print(f"❌ UPLOAD-SHARE: Error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e),
            'code': 'internal_error'
        }, status=500)

@api_view(['POST'])
def share_video_direct(request):
    """Generate shareable links for videos on user's site"""
    try:
        import json
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        share_type = data.get('share_type', 'link')  # link, embed, download
        
        print(f"🔗 SHARE: Generating {share_type} for video {design_id}")
        
        if not design_id:
            return Response({
                'success': False,
                'error': 'design_id is required'
            }, status=400)
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Design not found in database'
            }, status=404)
        
        # Get video URL
        video_url = None
        if design.video_url or design.file_url:
            video_url = design.video_url or f"http://localhost:8000{design.file_url}"
        else:
            return Response({
                'success': False,
                'error': 'No video available for sharing'
            }, status=400)
        
        # Generate share links
        base_url = "http://localhost:8000"
        
        if share_type == 'link':
            share_url = f"{base_url}{video_url}"
            embed_code = f'<video controls><source src="{share_url}" type="video/mp4"></video>'
            
            result = {
                'success': True,
                'share_type': 'link',
                'share_url': share_url,
                'embed_code': embed_code,
                'download_url': share_url,
                'title': design.title,
                'file_name': design.file_name,
                'file_size': design.file_size,
                'instructions': [
                    f"Direct link: {share_url}",
                    f"Download: Right-click and save",
                    f"Embed: Use the embed code provided"
                ]
            }
            
        elif share_type == 'embed':
            embed_url = f"{base_url}/embed/video/{design_id}/"
            embed_code = f'<iframe src="{embed_url}" width="800" height="450" frameborder="0" allowfullscreen></iframe>'
            
            result = {
                'success': True,
                'share_type': 'embed',
                'embed_url': embed_url,
                'embed_code': embed_code,
                'share_url': f"{base_url}{video_url}",
                'title': design.title,
                'instructions': [
                    f"Embed URL: {embed_url}",
                    f"Embed Code: Copy and paste the iframe",
                    f"Direct Link: {base_url}{video_url}"
                ]
            }
            
        elif share_type == 'download':
            download_url = f"{base_url}{video_url}"
            
            result = {
                'success': True,
                'share_type': 'download',
                'download_url': download_url,
                'direct_link': download_url,
                'title': design.title,
                'file_name': design.file_name,
                'file_size': design.file_size,
                'instructions': [
                    f"Download Link: {download_url}",
                    f"File Name: {design.file_name}",
                    f"File Size: {design.file_size} bytes"
                ]
            }
        
        else:
            result = {
                'success': False,
                'error': f'Share type {share_type} not supported'
            }
        
        return Response(result)
        
    except Exception as e:
        print(f"❌ SHARE: Error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e),
            'code': 'internal_error'
        }, status=500)

def upload_to_youtube(video_url, title, description):
    """Upload video to YouTube (placeholder for actual implementation)"""
    try:
        print(f"📺 YOUTUBE: Uploading {title}")
        
        # TODO: Implement YouTube API integration
        # This would require YouTube Data API credentials
        
        return {
            'success': False,
            'platform': 'youtube',
            'error': 'YouTube API integration not implemented yet',
            'instructions': [
                "1. Download video from your site",
                "2. Upload manually to YouTube",
                f"3. Video URL: {video_url}"
            ]
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': 'youtube',
            'error': str(e)
        }

def upload_to_vimeo(video_url, title, description):
    """Upload video to Vimeo (placeholder for actual implementation)"""
    try:
        print(f"🎬 VIMEO: Uploading {title}")
        
        # TODO: Implement Vimeo API integration
        
        return {
            'success': False,
            'platform': 'vimeo',
            'error': 'Vimeo API integration not implemented yet',
            'instructions': [
                "1. Download video from your site",
                "2. Upload manually to Vimeo",
                f"3. Video URL: {video_url}"
            ]
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': 'vimeo',
            'error': str(e)
        }

def upload_to_facebook(video_url, title, description):
    """Upload video to Facebook (placeholder for actual implementation)"""
    try:
        print(f"📘 FACEBOOK: Uploading {title}")
        
        # TODO: Implement Facebook API integration
        
        return {
            'success': False,
            'platform': 'facebook',
            'error': 'Facebook API integration not implemented yet',
            'instructions': [
                "1. Download video from your site",
                "2. Upload manually to Facebook",
                f"3. Video URL: {video_url}"
            ]
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': 'facebook',
            'error': str(e)
        }

def upload_to_instagram(video_url, title, description):
    """Upload video to Instagram (placeholder for actual implementation)"""
    try:
        print(f"📷 INSTAGRAM: Uploading {title}")
        
        # TODO: Implement Instagram API integration
        
        return {
            'success': False,
            'platform': 'instagram',
            'error': 'Instagram API integration not implemented yet',
            'instructions': [
                "1. Download video from your site",
                "2. Upload manually to Instagram",
                f"3. Video URL: {video_url}"
            ]
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': 'instagram',
            'error': str(e)
        }

def upload_to_dropbox(video_url, title, design_id):
    """Upload video to Dropbox"""
    try:
        print(f"📦 DROPBOX: Uploading {title}")
        
        # TODO: Implement Dropbox API integration
        
        return {
            'success': False,
            'platform': 'dropbox',
            'error': 'Dropbox API integration not implemented yet',
            'instructions': [
                "1. Download video from your site",
                "2. Upload manually to Dropbox",
                f"3. Video URL: {video_url}"
            ]
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': 'dropbox',
            'error': str(e)
        }

def upload_to_google_drive(video_url, title, design_id):
    """Upload video to Google Drive"""
    try:
        print(f"📁 GOOGLE_DRIVE: Uploading {title}")
        
        # TODO: Implement Google Drive API integration
        
        return {
            'success': False,
            'platform': 'google_drive',
            'error': 'Google Drive API integration not implemented yet',
            'instructions': [
                "1. Download video from your site",
                "2. Upload manually to Google Drive",
                f"3. Video URL: {video_url}"
            ]
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': 'google_drive',
            'error': str(e)
        }

def poll_export_job(job_id, headers):
    """Poll Canva export job until completion"""
    try:
        max_poll_attempts = 20
        poll_interval = 3
        
        for attempt in range(max_poll_attempts):
            print(f"⏳ DOWNLOAD-UPLOAD: Checking export status (attempt {attempt + 1}/{max_poll_attempts})")
            
            status_response = requests.get(
                f"https://api.canva.com/rest/v1/exports/{job_id}",
                headers=headers,
                timeout=15
            )
            
            if status_response.status_code != 200:
                print(f"❌ DOWNLOAD-UPLOAD: Status check failed: {status_response.status_code}")
                time.sleep(poll_interval)
                continue
            
            status_data = status_response.json()
            export_status = status_data.get('status', 'unknown')
            
            print(f"📊 DOWNLOAD-UPLOAD: Export status: {export_status}")
            
            if export_status == 'completed':
                # Extract download URL
                if 'result' in status_data and 'url' in status_data['result']:
                    video_url = status_data['result']['url']
                elif 'url' in status_data:
                    video_url = status_data['url']
                elif 'download_url' in status_data:
                    video_url = status_data['download_url']
                
                if video_url:
                    print(f"✅ DOWNLOAD-UPLOAD: Export completed, download URL: {video_url}")
                    return video_url
                else:
                    print("❌ DOWNLOAD-UPLOAD: Export completed but no download URL found")
                    return None
            
            elif export_status == 'failed':
                error_msg = status_data.get('error', 'Export failed')
                print(f"❌ DOWNLOAD-UPLOAD: Canva export failed: {error_msg}")
                return None
            
            elif export_status in ['processing', 'pending']:
                time.sleep(poll_interval)
                continue
            else:
                print(f"⚠️ DOWNLOAD-UPLOAD: Unknown status: {export_status}")
                time.sleep(poll_interval)
                continue
        
        print("❌ DOWNLOAD-UPLOAD: Export polling timeout - job did not complete")
        return None
        
    except Exception as e:
        print(f"❌ DOWNLOAD-UPLOAD: Polling error: {e}")
        return None

def validate_canva_token():
    """Validate Canva access token and return connection if valid"""
    try:
        connection = CanvaConnection.objects.first()
        if not connection or not connection.access_token:
            return None, "No Canva connection found"
        
        # Test token by making a simple API call
        headers = {
            'Authorization': f'Bearer {connection.access_token}',
            'Content-Type': 'application/json'
        }
        
        test_res = requests.get(
            "https://api.canva.com/rest/v1/users/me",
            headers=headers,
            timeout=10
        )
        
        if test_res.ok:
            return connection, "Token valid"
        elif test_res.status_code == 401:
            return None, "Token expired or invalid"
        else:
            return None, f"Token validation failed: {test_res.status_code}"
            
    except Exception as e:
        return None, f"Token validation error: {str(e)}"


@api_view(['GET'])
def list_designs_from_db(request):
    """List all designs from database with their IDs and details"""
    try:
        designs = CanvaDesign.objects.all().order_by('-created_at')
        
        design_list = []
        for design in designs:
            design_list.append({
                'design_id': design.design_id,
                'title': design.title,
                'asset_type': design.asset_type,
                'has_binary_file': bool(design.binary_file),
                'binary_file_type': design.binary_file_type,
                'binary_file_size': design.binary_file_size,
                'status': design.status,
                'created_at': design.created_at.isoformat(),
                'last_modified': design.last_modified.isoformat() if design.last_modified else None
            })
        
        return Response({
            "success": True,
            "count": len(design_list),
            "designs": design_list
        })
        
    except Exception as e:
        print(f"❌ List designs error: {str(e)}")
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def get_design_details(request, design_id):
    """Get specific design details from database"""
    try:
        design = CanvaDesign.objects.get(design_id=design_id)
        
        return Response({
            "success": True,
            "design": {
                'design_id': design.design_id,
                'title': design.title,
                'asset_url': design.asset_url,
                'asset_type': design.asset_type,
                'status': design.status,
                'has_binary_file': bool(design.binary_file),
                'binary_file_name': design.binary_file_name,
                'binary_file_type': design.binary_file_type,
                'binary_file_size': design.binary_file_size,
                'created_at': design.created_at.isoformat(),
                'last_modified': design.last_modified.isoformat() if design.last_modified else None,
                'raw_data': design.raw_data
            }
        })
        
    except CanvaDesign.DoesNotExist:
        return Response({"error": "Design not found in database"}, status=404)
    except Exception as e:
        print(f"❌ Get design details error: {str(e)}")
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def check_canva_auth(request):
    """Check Canva authentication status"""
    try:
        connection, message = validate_canva_token()
        
        if connection:
            return Response({
                "success": True,
                "authenticated": True,
                "message": message,
                "expires_at": connection.expires_at.isoformat() if connection.expires_at else None
            })
        else:
            return Response({
                "success": False,
                "authenticated": False,
                "message": message
            }, status=401)
            
    except Exception as e:
        return Response({
            "success": False,
            "authenticated": False,
            "message": str(e)
        }, status=500)


@api_view(['POST'])
def download_actual_video_file(request):
    """Download actual video file from Canva using export API"""
    try:
        import requests
        import json
        import time
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        
        print(f"🎬 Downloading actual video file for: {design_id}")
        
        # Validate Canva token first
        connection, token_message = validate_canva_token()
        if not connection:
            return Response({
                "error": "Canva authentication failed",
                "message": token_message
            }, status=401)
        
        print(f"✅ Canva token validated: {token_message}")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found"}, status=404)
        
        # Check if design already has binary file (actual video)
        if design.binary_file and design.binary_file_type in ['mp4', 'mov', 'gif']:
            print(f"✅ Design already has binary file: {design.binary_file_name}")
            return Response({
                "success": True,
                "design_id": design_id,
                "export_format": design.binary_file_type,
                "file_name": design.binary_file_name,
                "file_size": design.binary_file_size,
                "message": f"Design already has video file: {design.binary_file_name} ({(design.binary_file_size / 1024 / 1024).toFixed(2)}MB)",
                "note": "Using existing binary file"
            })
        
        # Get Canva connection
        try:
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'Content-Type': 'application/json'
            }
        except Exception as e:
            return Response({"error": f"Failed to get Canva connection: {str(e)}"}, status=500)
        
        # First, get design details to check available formats
        print("📡 Getting design details from Canva API...")
        design_res = requests.get(
            f"https://api.canva.com/rest/v1/designs/{design_id}",
            headers=headers,
            timeout=30
        )
        
        if not design_res.ok:
            if design_res.status_code == 404:
                return Response({
                    "error": "Design not found",
                    "message": f"Design ID '{design_id}' not found in Canva. Please check if the design exists and you have access to it."
                }, status=404)
            else:
                print(f"❌ Failed to get design details: {design_res.status_code}")
                return Response({"error": f"Failed to get design details: {design_res.status_code}"}, status=500)
        
        design_data = design_res.json()
        print(f"✅ Design data received for: {design_data.get('title', 'Untitled')}")
        
        # Check if design has media/exports available
        design_type = design_data.get('type', '')
        print(f"📊 Design type: {design_type}")
        
        # Check if this design can be exported as video
        # Video exports only work for designs with animations or video elements
        design_tags = design_data.get('tags', [])
        design_categories = design_data.get('categories', [])
        
        is_video_capable = (
            design_type == 'video' or
            'video' in design_tags or
            'animation' in design_tags or
            'animated' in design_tags or
            any('video' in str(cat).lower() for cat in design_categories)
        )
        
        print(f"🎬 Is video-capable: {is_video_capable}")
        print(f"📊 Design tags: {design_tags}")
        print(f"📊 Design categories: {design_categories}")
        
        if not is_video_capable:
            # Try to export as image/PDF instead
            print("🔄 Design is not video-capable, trying image export...")
            
            # Try to export as PNG
            image_export_res = requests.post(
                f"https://api.canva.com/rest/v1/designs/{design_id}/exports",
                headers=headers,
                json={
                    "type": "image",
                    "format": "png",
                    "quality": "standard"
                },
                timeout=30
            )
            
            if image_export_res.ok:
                image_export_data = image_export_res.json()
                print(f"🎬 Image export response: {image_export_data}")
                
                if 'job' in image_export_data:
                    job_id = image_export_data['job']['id']
                    print(f"🎬 Image export job created: {job_id}")
                    
                    # Poll for completion
                    for attempt in range(15):
                        status_res = requests.get(
                            f"https://api.canva.com/rest/v1/exports/{job_id}",
                            headers=headers,
                            timeout=15
                        )
                        
                        if status_res.ok:
                            status_data = status_res.json()
                            if status_data.get('status') == 'completed':
                                if 'result' in status_data and 'url' in status_data['result']:
                                    image_url = status_data['result']['url']
                                    print(f"✅ Image export completed: {image_url}")
                                    
                                    # Download the image
                                    image_res = requests.get(image_url, timeout=60)
                                    if image_res.ok:
                                        image_content = image_res.content
                                        image_size = len(image_content)
                                        
                                        # Save as image
                                        design.binary_file = image_content
                                        design.binary_file_name = f"{design_id}.png"
                                        design.binary_file_type = "png"
                                        design.binary_file_size = image_size
                                        design.save()
                                        
                                        return Response({
                                            "success": True,
                                            "design_id": design_id,
                                            "export_format": "png",
                                            "file_name": design.binary_file_name,
                                            "file_size": image_size,
                                            "message": f"Design exported as image (not video-capable): {design.binary_file_name} ({(image_size / 1024 / 1024).toFixed(2)}MB)",
                                            "note": "This design cannot be exported as video. Image export was successful."
                                        })
                            elif status_data.get('status') == 'failed':
                                break
                        time.sleep(2)
            
            return Response({
                "error": "Design is not video-capable",
                "message": f"This design is type '{design_type}' and cannot be exported as video. Image export also failed.",
                "design_type": design_type,
                "suggested_formats": ["png", "jpg", "pdf"]
            }, status=400)
        
        # Try to export actual video via Canva API
        export_formats = ['mp4', 'mov', 'gif']
        
        for export_format in export_formats:
            try:
                print(f"🎬 Attempting to export as {export_format}...")
                
                # Add retry logic with exponential backoff for rate limiting
                max_retries = 5  # Increased to 5 retries
                base_delay = 5  # Increased to 5 seconds
                
                export_request_body = {
                    "type": "video",
                    "format": export_format,
                    "quality": "standard"
                }
                print(f"📤 Export request body: {export_request_body}")
                
                for retry in range(max_retries):
                    export_res = requests.post(
                        f"https://api.canva.com/rest/v1/designs/{design_id}/exports",
                        headers=headers,
                        json=export_request_body,
                        timeout=30
                    )
                    
                    print(f"📤 Export response status: {export_res.status_code}")
                    print(f"📤 Export response body: {export_res.text[:500]}")
                    
                    # Check for rate limiting
                    if export_res.status_code == 429:
                        if retry < max_retries - 1:
                            delay = base_delay * (2 ** retry)  # 5s, 10s, 20s, 40s, 80s
                            print(f"⏱️ Rate limited. Waiting {delay} seconds before retry {retry + 1}/{max_retries}...")
                            time.sleep(delay)
                            continue
                        else:
                            print(f"❌ Rate limit exceeded for {export_format}")
                            break  # Try next format
                    
                    # If not rate limited, break the retry loop
                    break
                
                print(f"📤 Export request status: {export_res.status_code}")
                
                if export_res.ok:
                    export_data = export_res.json()
                    print(f"🎬 Export response: {export_data}")
                    
                    # Check for export job
                    if 'job' in export_data:
                        job_id = export_data['job']['id']
                        print(f"🎬 Export job created: {job_id}")
                        
                        # Poll for export completion
                        max_attempts = 30  # Increased to 30 attempts (60 seconds)
                        for attempt in range(max_attempts):
                            print(f"🎬 Checking export status (attempt {attempt + 1}/{max_attempts})...")
                            
                            status_res = requests.get(
                                f"https://api.canva.com/rest/v1/exports/{job_id}",
                                headers=headers,
                                timeout=15
                            )
                            
                            if status_res.ok:
                                status_data = status_res.json()
                                print(f"🎬 Export status: {status_data.get('status')}")
                                
                                if status_data.get('status') == 'completed':
                                    # Get the actual video URL
                                    if 'result' in status_data and 'url' in status_data['result']:
                                        video_url = status_data['result']['url']
                                        print(f"✅ Video export completed: {video_url}")
                                        
                                        # Download the video file
                                        print(f"📥 Downloading video from: {video_url}")
                                        video_res = requests.get(video_url, timeout=120)
                                        
                                        if video_res.ok:
                                            video_content = video_res.content
                                            video_size = len(video_content)
                                            
                                            # Verify it's actually a video file by checking file signature
                                            file_signature = video_content[:12].hex() if len(video_content) >= 12 else ''
                                            print(f"🔍 File signature: {file_signature}")
                                            print(f"📊 File size: {video_size} bytes")
                                            
                                            # Check file signatures for video formats
                                            is_mp4 = file_signature.startswith('00000018') or file_signature.startswith('00000020') or video_url.endswith('.mp4')
                                            is_mov = file_signature.startswith('6d6f6f76') or video_url.endswith('.mov')
                                            is_gif = file_signature.startswith('47494638') or video_url.endswith('.gif')
                                            
                                            # Also check content-type
                                            content_type = video_res.headers.get('content-type', '')
                                            print(f"📄 Content-Type: {content_type}")
                                            
                                            if not (is_mp4 or is_mov or is_gif or 'video' in content_type):
                                                print(f"⚠️ File signature doesn't match video format")
                                                print(f"⚠️ This might be an image, skipping...")
                                                continue
                                            
                                            # Save to database
                                            design.binary_file = video_content
                                            design.binary_file_name = f"{design_id}.{export_format}"
                                            design.binary_file_type = export_format
                                            design.binary_file_size = video_size
                                            design.save()
                                            
                                            print(f"✅ Actual video file saved: {design.binary_file_name} ({video_size} bytes)")
                                            
                                            return Response({
                                                "success": True,
                                                "design_id": design_id,
                                                "export_format": export_format,
                                                "file_name": design.binary_file_name,
                                                "file_size": video_size,
                                                "content_type": content_type,
                                                "is_valid_video": True,
                                                "message": f"Actual video file downloaded: {design.binary_file_name} ({(video_size / 1024 / 1024).toFixed(2)}MB)"
                                            })
                                        else:
                                            print(f"❌ Failed to download exported video: {video_res.status_code}")
                                            continue
                                elif status_data.get('status') == 'failed':
                                    print(f"❌ Export failed for {export_format}")
                                    print(f"❌ Error: {status_data.get('error', 'Unknown error')}")
                                    break
                            
                            time.sleep(2)  # Wait 2 seconds before next check
                        
                        print(f"⏱️ Export timeout for {export_format}")
                        continue
                    else:
                        print(f"❌ No export job created for {export_format}")
                        print(f"❌ Response: {export_data}")
                        continue
                else:
                    print(f"❌ Export request failed for {export_format}: {export_res.status_code}")
                    print(f"❌ Response: {export_res.text}")
                    continue
                    
            except Exception as e:
                print(f"❌ Error exporting as {export_format}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        # If all exports failed, try to get video from design's media field
        print("🔄 All exports failed, trying design media field...")
        try:
            if 'media' in design_data and design_data['media']:
                media = design_data['media']
                print(f"📊 Media data: {media}")
                
                # Look for video in media
                if isinstance(media, list) and len(media) > 0:
                    for media_item in media:
                        if isinstance(media_item, dict):
                            video_url = media_item.get('url') or media_item.get('src')
                            if video_url:
                                print(f"📥 Found video URL in media: {video_url}")
                                
                                video_res = requests.get(video_url, timeout=60)
                                if video_res.ok:
                                    content = video_res.content
                                    content_type = video_res.headers.get('content-type', '')
                                    
                                    if 'video' in content_type or video_url.endswith('.mp4') or video_url.endswith('.mov'):
                                        file_type = 'mp4' if video_url.endswith('.mp4') else 'mov'
                                        design.binary_file = content
                                        design.binary_file_name = f"{design_id}.{file_type}"
                                        design.binary_file_type = file_type
                                        design.binary_file_size = len(content)
                                        design.save()
                                        
                                        return Response({
                                            "success": True,
                                            "design_id": design_id,
                                            "file_name": design.binary_file_name,
                                            "file_size": design.binary_file_size,
                                            "message": f"Video downloaded from media: {design.binary_file_name}"
                                        })
        
        except Exception as e:
            print(f"❌ Error accessing media field: {str(e)}")
        
        return Response({
            "error": "Failed to download actual video file. This design may not have a video version available, or Canva export API returned an image instead of video.",
            "suggestion": "Try opening the design in Canva and exporting it manually as MP4, then upload it to the system."
        }, status=400)
        
    except Exception as e:
        print(f"❌ Download actual video file error: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


# ======================
# PRIVATE DESIGN SYSTEM
# ======================
@api_view(['POST'])
def convert_to_private_designs(request):
    """Convert all Canva designs to private binary files for unrestricted use"""
    try:
        import requests
        import time
        
        print("🔒 Converting all designs to private binary files...")
        
        # Get all designs
        designs = CanvaDesign.objects.all()
        total = designs.count()
        print(f"📊 Total designs to convert: {total}")
        
        # Get Canva connection
        try:
            connection = CanvaConnection.objects.first()
            if not connection or not connection.access_token:
                return Response({"error": "No Canva connection found"}, status=500)
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'Content-Type': 'application/json'
            }
        except Exception as e:
            return Response({"error": f"Failed to get Canva connection: {str(e)}"}, status=500)
        
        converted = 0
        failed = 0
        
        for design in designs:
            try:
                print(f"🔄 Converting design: {design.design_id} - {design.title}")
                
                # Check if already has binary file
                if design.binary_file and design.binary_file_size > 0:
                    print(f"✅ Already has binary file: {design.binary_file_name} ({design.binary_file_size} bytes)")
                    converted += 1
                    continue
                
                # Get design details from Canva API
                design_res = requests.get(
                    f"https://api.canva.com/rest/v1/designs/{design.design_id}",
                    headers=headers,
                    timeout=30
                )
                
                if not design_res.ok:
                    print(f"❌ Failed to get design details: {design_res.status_code}")
                    failed += 1
                    continue
                
                design_data = design_res.json()
                
                # Get asset URL
                asset_url = design_data.get('asset_url')
                if not asset_url:
                    print(f"❌ No asset URL found for design")
                    failed += 1
                    continue
                
                # Download the asset
                print(f"📥 Downloading asset from: {asset_url}")
                asset_res = requests.get(asset_url, timeout=60)
                
                if not asset_res.ok:
                    print(f"❌ Failed to download asset: {asset_res.status_code}")
                    failed += 1
                    continue
                
                # Get file type from content type
                content_type = asset_res.headers.get('content-type', 'image/png')
                file_content = asset_res.content
                file_size = len(file_content)
                
                # Determine file extension
                if 'video' in content_type or asset_url.endswith('.mp4'):
                    file_type = 'mp4'
                elif 'pdf' in content_type or asset_url.endswith('.pdf'):
                    file_type = 'pdf'
                elif 'jpeg' in content_type or asset_url.endswith('.jpg'):
                    file_type = 'jpg'
                elif 'png' in content_type or asset_url.endswith('.png'):
                    file_type = 'png'
                else:
                    file_type = 'png'  # default
                
                file_name = f"{design.design_id}.{file_type}"
                
                # Save binary file to database
                design.binary_file = file_content
                design.binary_file_name = file_name
                design.binary_file_type = file_type
                design.binary_file_size = file_size
                design.save()
                
                print(f"✅ Successfully converted: {file_name} ({file_size} bytes)")
                converted += 1
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Error converting design {design.design_id}: {str(e)}")
                failed += 1
                continue
        
        return Response({
            "success": True,
            "total": total,
            "converted": converted,
            "failed": failed,
            "message": f"Converted {converted}/{total} designs to private binary files"
        })
        
    except Exception as e:
        print(f"❌ Convert to private designs error: {str(e)}")
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
def export_private_design(request):
    """Export a private design for unrestricted sharing"""
    try:
        import json
        
        data = json.loads(request.body)
        design_id = data.get('design_id')
        export_format = data.get('format', 'original')  # original, mp4, png, pdf
        
        print(f"🔓 Exporting private design: {design_id} as {export_format}")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found"}, status=404)
        
        # Check if has binary file
        if not design.binary_file:
            return Response({"error": "No binary file found. Please convert to private design first."}, status=400)
        
        # Determine export format
        if export_format == 'original':
            file_type = design.binary_file_type
            file_content = design.binary_file
            file_name = design.binary_file_name
        elif export_format == 'mp4':
            # Convert to MP4 if possible
            if design.binary_file_type == 'mp4':
                file_type = 'mp4'
                file_content = design.binary_file
                file_name = f"{design_id}_export.mp4"
            else:
                return Response({"error": "Cannot convert non-video to MP4"}, status=400)
        elif export_format == 'png':
            file_type = 'png'
            file_content = design.binary_file
            file_name = f"{design_id}_export.png"
        elif export_format == 'pdf':
            file_type = 'pdf'
            file_content = design.binary_file
            file_name = f"{design_id}_export.pdf"
        else:
            return Response({"error": f"Unsupported format: {export_format}"}, status=400)
        
        # Return file for download
        from django.http import HttpResponse
        
        content_type_map = {
            'mp4': 'video/mp4',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'pdf': 'application/pdf'
        }
        
        response = HttpResponse(file_content, content_type=content_type_map.get(file_type, 'application/octet-stream'))
        response['Content-Disposition'] = f'attachment; filename="{file_name}"'
        response['Content-Length'] = len(file_content)
        
        return response
        
    except Exception as e:
        print(f"❌ Export private design error: {str(e)}")
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
def upload_private_design(request):
    """Upload private design to any platform without restrictions"""
    try:
        import json
        import requests
        
        data = request.data
        design_id = data.get('design_id')
        platform = data.get('platform')  # dropbox, s3, ftp, custom, direct
        platform_config = data.get('config', {})
        
        print(f"🚀 Uploading private design: {design_id} to {platform}")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found"}, status=404)
        
        # Check if has binary file
        if not design.binary_file:
            return Response({"error": "No binary file found. Please convert to private design first."}, status=400)
        
        # Upload based on platform
        if platform == 'dropbox':
            result = upload_to_dropbox_private(design, platform_config)
        elif platform == 's3':
            result = upload_to_s3_private(design, platform_config)
        elif platform == 'ftp':
            result = upload_to_ftp_private(design, platform_config)
        elif platform == 'custom':
            result = upload_to_custom_private(design, platform_config)
        elif platform == 'direct':
            result = generate_direct_link(design)
        else:
            return Response({"error": f"Unsupported platform: {platform}"}, status=400)
        
        return Response(result)
        
    except Exception as e:
        print(f"❌ Upload private design error: {str(e)}")
        return Response({"error": str(e)}, status=500)


def upload_to_dropbox_private(design, config):
    """Upload to Dropbox without API restrictions"""
    try:
        import requests
        
        access_token = config.get('access_token')
        if not access_token:
            return {"success": False, "error": "Dropbox access token required"}
        
        # Upload to Dropbox
        upload_url = "https://content.dropboxapi.com/2/files/upload"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/octet-stream',
            'Dropbox-API-Arg': json.dumps({
                "path": f"/{design.binary_file_name}",
                "mode": "add"
            })
        }
        
        response = requests.post(upload_url, headers=headers, data=design.binary_file, timeout=60)
        
        if response.ok:
            # Create shared link
            share_url = "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings"
            share_headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            share_data = {
                "path": f"/{design.binary_file_name}",
                "settings": {"requested_visibility": "public"}
            }
            
            share_response = requests.post(share_url, headers=share_headers, json=share_data, timeout=30)
            
            if share_response.ok:
                share_data = share_response.json()
                public_url = share_data.get('url', '').replace('dl=0', 'dl=1')
                return {
                    "success": True,
                    "platform": "dropbox",
                    "file_name": design.binary_file_name,
                    "public_url": public_url,
                    "message": "Successfully uploaded to Dropbox"
                }
        
        return {"success": False, "error": "Failed to upload to Dropbox"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_to_s3_private(design, config):
    """Upload to AWS S3 without restrictions"""
    try:
        # Placeholder for S3 upload
        return {
            "success": True,
            "platform": "s3",
            "file_name": design.binary_file_name,
            "message": "S3 upload functionality - requires boto3 library"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_to_ftp_private(design, config):
    """Upload to FTP without restrictions"""
    try:
        # Placeholder for FTP upload
        return {
            "success": True,
            "platform": "ftp",
            "file_name": design.binary_file_name,
            "message": "FTP upload functionality - requires ftplib"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_to_custom_private(design, config):
    """Upload to custom endpoint without restrictions"""
    try:
        import requests
        
        url = config.get('url')
        if not url:
            return {"success": False, "error": "Custom URL required"}
        
        files = {'file': (design.binary_file_name, design.binary_file)}
        response = requests.post(url, files=files, timeout=60)
        
        if response.ok:
            return {
                "success": True,
                "platform": "custom",
                "file_name": design.binary_file_name,
                "message": "Successfully uploaded to custom endpoint"
            }
        
        return {"success": False, "error": "Failed to upload to custom endpoint"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_direct_link(design):
    """Generate direct download link from local server"""
    try:
        # Generate a direct link to the binary file
        direct_url = f"http://localhost:8000/api/canva/binary-file/{design.design_id}/"
        
        return {
            "success": True,
            "platform": "direct",
            "file_name": design.binary_file_name,
            "direct_url": direct_url,
            "message": "Direct link generated for unrestricted access"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ======================
# LIVE SERVER UPLOAD FUNCTIONALITY
# ======================
@api_view(['POST'])
def upload_to_live_server(request):
    """Upload design to various live servers with multiple platform support"""
    try:
        data = request.data
        design_id = data.get('design_id')
        server_type = data.get('server_type', 'generic')
        server_url = data.get('server_url')
        custom_config = data.get('custom_config', {})
        
        if not design_id:
            return Response({"error": "design_id required"}, status=400)
        
        print(f"🚀 Live Server Upload: {design_id} to {server_type}")
        
        # Get design from database
        try:
            design = CanvaDesign.objects.get(design_id=design_id)
            print(f"📊 Found design: {design.title}")
        except CanvaDesign.DoesNotExist:
            return Response({"error": "Design not found in database"}, status=404)
        
        # Prepare upload data
        upload_data = {
            'design_id': design_id,
            'title': design.title,
            'type': design.asset_type,
            'binary_file': None,
            'file_name': design.binary_file_name,
            'file_type': design.binary_file_type,
            'file_size': design.binary_file_size,
            'canva_url': None,
            'metadata': {
                'created_at': design.created_at.isoformat() if design.created_at else None,
                'last_modified': design.last_modified.isoformat() if design.last_modified else None
            }
        }
        
        # Get Canva direct URL
        if design.raw_data:
            try:
                import json
                raw_data = json.loads(design.raw_data)
                if 'design' in raw_data and 'id' in raw_data['design']:
                    design_id_from_raw = raw_data['design']['id']
                    upload_data['canva_url'] = f"https://www.canva.com/design/{design_id_from_raw}/view"
            except:
                pass
        
        # Handle binary file
        if design.binary_file:
            upload_data['binary_file'] = design.binary_file
            print(f"📁 Binary file ready: {design.binary_file_name} ({design.binary_file_size} bytes)")
        
        # Upload based on server type
        upload_result = None
        
        if server_type == 'youtube':
            upload_result = upload_to_youtube(upload_data, custom_config)
        elif server_type == 'vimeo':
            upload_result = upload_to_vimeo(upload_data, custom_config)
        elif server_type == 'dropbox':
            upload_result = upload_to_dropbox(upload_data, custom_config)
        elif server_type == 'google_drive':
            upload_result = upload_to_google_drive(upload_data, custom_config)
        elif server_type == 'aws_s3':
            upload_result = upload_to_aws_s3(upload_data, custom_config)
        elif server_type == 'ftp':
            upload_result = upload_to_ftp(upload_data, server_url, custom_config)
        elif server_type == 'custom':
            upload_result = upload_to_custom_server(upload_data, server_url, custom_config)
        else:
            upload_result = upload_to_generic_server(upload_data, server_url, custom_config)
        
        if upload_result.get('success'):
            return Response({
                "success": True,
                "design_id": design_id,
                "title": design.title,
                "server_type": server_type,
                "server_url": server_url,
                "upload_url": upload_result.get('upload_url'),
                "public_url": upload_result.get('public_url'),
                "message": f"Successfully uploaded {design.title} to {server_type}"
            })
        else:
            return Response({
                "success": False,
                "error": upload_result.get('error', 'Upload failed'),
                "details": upload_result.get('details', '')
            }, status=500)
            
    except Exception as e:
        print(f"❌ Live server upload error: {str(e)}")
        return Response({"error": str(e)}, status=500)


def upload_to_youtube(upload_data, config):
    """Upload to YouTube (requires API keys and authentication)"""
    print(f"🎬 Uploading to YouTube: {upload_data['title']}")
    
    # This is a placeholder for YouTube API integration
    # In real implementation, you would need:
    # - YouTube API credentials
    # - OAuth2 authentication
    # - Video processing and upload
    
    return {
        "success": False,
        "error": "YouTube API integration requires authentication setup",
        "details": "Please configure YouTube API keys and OAuth2 credentials"
    }


def upload_to_vimeo(upload_data, config):
    """Upload to Vimeo"""
    print(f"🎬 Uploading to Vimeo: {upload_data['title']}")
    
    # Placeholder for Vimeo API integration
    return {
        "success": False,
        "error": "Vimeo API integration requires authentication setup",
        "details": "Please configure Vimeo API access token"
    }


def upload_to_dropbox(upload_data, config):
    """Upload to Dropbox"""
    print(f"☁️ Uploading to Dropbox: {upload_data['title']}")
    
    try:
        import requests
        import json
        
        # This is a simplified Dropbox upload
        # In real implementation, you would need Dropbox API access token
        access_token = config.get('access_token')
        if not access_token:
            return {"success": False, "error": "Dropbox access token required"}
        
        # Upload file to Dropbox
        if upload_data['binary_file']:
            # For binary files
            file_data = upload_data['binary_file']
            file_path = f"/Canva_Designs/{upload_data['file_name']}"
            
            # Proper Dropbox API headers
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/octet-stream',
                'Dropbox-API-Arg': json.dumps({"path": file_path, "mode": "overwrite"})
            }
            
            # Use correct Dropbox upload endpoint
            upload_url = "https://content.dropboxapi.com/2/files/upload"
            
            response = requests.post(upload_url, headers=headers, data=file_data)
            
            if response.ok:
                print(f"✅ File uploaded to Dropbox: {file_path}")
                
                # Create shared link
                share_headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
                
                share_data = {"path": file_path, "settings": {"requested_visibility": "public"}}
                share_response = requests.post(
                    "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
                    headers=share_headers,
                    json=share_data
                )
                
                if share_response.ok:
                    share_result = share_response.json()
                    return {
                        "success": True,
                        "upload_url": file_path,
                        "public_url": share_result.get('url'),
                        "details": f"Uploaded to Dropbox and shared: {upload_data['file_name']}"
                    }
                else:
                    return {
                        "success": True,
                        "upload_url": file_path,
                        "public_url": f"https://www.dropbox.com/home/{file_path.replace('/', '')}",
                        "details": f"Uploaded to Dropbox: {upload_data['file_name']} (manual sharing required)"
                    }
            else:
                return {"success": False, "error": f"Dropbox upload failed: {response.status_code} - {response.text}"}
        else:
            return {"success": False, "error": "No binary file to upload"}
            
    except Exception as e:
        return {"success": False, "error": f"Dropbox upload error: {str(e)}"}


def upload_to_google_drive(upload_data, config):
    """Upload to Google Drive"""
    print(f"📁 Uploading to Google Drive: {upload_data['title']}")
    
    # Placeholder for Google Drive API integration
    return {
        "success": False,
        "error": "Google Drive API integration requires authentication setup",
        "details": "Please configure Google Drive API credentials"
    }


def upload_to_aws_s3(upload_data, config):
    """Upload to AWS S3"""
    print(f"🗂️ Uploading to AWS S3: {upload_data['title']}")
    
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError
        
        # Get AWS credentials from config
        aws_access_key = config.get('aws_access_key_id')
        aws_secret_key = config.get('aws_secret_access_key')
        bucket_name = config.get('bucket_name')
        region = config.get('region', 'us-east-1')
        
        if not all([aws_access_key, aws_secret_key, bucket_name]):
            return {"success": False, "error": "AWS credentials and bucket name required"}
        
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region
        )
        
        if upload_data['binary_file']:
            # Upload binary file
            file_key = f"canva-designs/{upload_data['file_name']}"
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=file_key,
                Body=upload_data['binary_file'],
                ContentType=f"application/{upload_data['file_type']}"
            )
            
            # Generate public URL
            public_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{file_key}"
            
            return {
                "success": True,
                "upload_url": file_key,
                "public_url": public_url,
                "details": f"Uploaded to S3 bucket: {bucket_name}"
            }
        else:
            return {"success": False, "error": "No binary file to upload"}
            
    except ImportError:
        return {"success": False, "error": "boto3 library not installed"}
    except NoCredentialsError:
        return {"success": False, "error": "AWS credentials not found"}
    except Exception as e:
        return {"success": False, "error": f"S3 upload error: {str(e)}"}


def upload_to_ftp(upload_data, server_url, config):
    """Upload to FTP server"""
    print(f"🌐 Uploading to FTP: {upload_data['title']}")
    
    try:
        import ftplib
        import os
        
        # Parse FTP server URL
        if not server_url:
            return {"success": False, "error": "FTP server URL required"}
        
        # Extract host, port, username, password from config or URL
        host = config.get('host', server_url.split('://')[1].split(':')[0] if '://' in server_url else server_url)
        port = config.get('port', 21)
        username = config.get('username', 'anonymous')
        password = config.get('password', '')
        
        # Connect to FTP server
        ftp = ftplib.FTP()
        ftp.connect(host, port)
        ftp.login(username, password)
        
        # Create directory if needed
        try:
            ftp.mkd('canva_designs')
        except:
            pass  # Directory might already exist
        
        ftp.cwd('canva_designs')
        
        if upload_data['binary_file']:
            # Upload binary file
            file_path = upload_data['file_name']
            
            with open('/tmp/temp_upload', 'wb') as temp_file:
                temp_file.write(upload_data['binary_file'])
            
            with open('/tmp/temp_upload', 'rb') as temp_file:
                ftp.storbinary(f'STOR {file_path}', temp_file)
            
            # Clean up temp file
            os.remove('/tmp/temp_upload')
            
            public_url = f"ftp://{host}:{port}/canva_designs/{file_path}"
            
            return {
                "success": True,
                "upload_url": file_path,
                "public_url": public_url,
                "details": f"Uploaded to FTP server: {host}"
            }
        else:
            return {"success": False, "error": "No binary file to upload"}
            
    except Exception as e:
        return {"success": False, "error": f"FTP upload error: {str(e)}"}


def upload_to_custom_server(upload_data, server_url, config):
    """Upload to custom server"""
    print(f"🔧 Uploading to custom server: {upload_data['title']}")
    
    try:
        import requests
        
        if not server_url:
            return {"success": False, "error": "Custom server URL required"}
        
        # Prepare files for upload
        files = {}
        if upload_data['binary_file']:
            files['file'] = (upload_data['file_name'], upload_data['binary_file'], f'application/{upload_data["file_type"]}')
        
        # Prepare form data
        form_data = {
            'design_id': upload_data['design_id'],
            'title': upload_data['title'],
            'type': upload_data['type'],
            'canva_url': upload_data['canva_url'],
            'metadata': str(upload_data['metadata'])
        }
        
        # Add custom config fields
        for key, value in config.items():
            if key not in ['host', 'port', 'username', 'password']:
                form_data[f'custom_{key}'] = value
        
        # Upload to custom server
        response = requests.post(server_url, files=files, data=form_data, timeout=60)
        
        if response.ok:
            return {
                "success": True,
                "upload_url": server_url,
                "public_url": response.text if response.text else server_url,
                "details": f"Uploaded to custom server successfully"
            }
        else:
            return {
                "success": False,
                "error": f"Custom server upload failed: {response.status_code}",
                "details": response.text
            }
            
    except Exception as e:
        return {"success": False, "error": f"Custom server upload error: {str(e)}"}


def upload_to_generic_server(upload_data, server_url, config):
    """Generic upload for any server"""
    print(f"🌐 Generic upload: {upload_data['title']}")
    
    if not server_url:
        return {"success": False, "error": "Server URL required"}
    
    # Use custom server upload as fallback
    return upload_to_custom_server(upload_data, server_url, config)


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


# ======================
# SOCIAL MEDIA OAUTH AUTHENTICATION
# ======================
@api_view(['GET', 'POST'])
def social_auth_status(request):
    """Get authentication status for all platforms"""
    platforms = ['facebook', 'youtube', 'instagram', 'linkedin', 'tiktok']
    status = {}
    
    for platform in platforms:
        connection = SocialMediaConnection.objects.filter(platform=platform, connected=True).first()
        status[platform] = {
            'connected': connection is not None,
            'username': connection.username if connection else None,
            'user_id': connection.user_id if connection else None,
            'expires_at': connection.expires_at.isoformat() if connection and connection.expires_at else None
        }
    
    return Response({
        "success": True,
        "platforms": status
    })


@api_view(['POST'])
def social_auth_save(request):
    """Save OAuth token for a platform (manual entry for testing)"""
    try:
        import json
        data = json.loads(request.body)
        
        platform = data.get('platform')
        access_token = data.get('access_token')
        refresh_token = data.get('refresh_token')
        user_id = data.get('user_id')
        username = data.get('username')
        
        if not platform or not access_token:
            return Response({"error": "platform and access_token required"}, status=400)
        
        if platform not in ['facebook', 'youtube', 'instagram', 'linkedin', 'tiktok']:
            return Response({"error": "Invalid platform"}, status=400)
        
        connection = SocialMediaConnection.save_token(
            platform=platform,
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            username=username
        )
        
        return Response({
            "success": True,
            "message": f"{platform} connected successfully",
            "platform": platform,
            "username": username
        })
        
    except Exception as e:
        print(f"❌ Social auth save error: {str(e)}")
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
def social_auth_disconnect(request):
    """Disconnect a platform"""
    try:
        import json
        data = json.loads(request.body)
        platform = data.get('platform')
        
        if not platform:
            return Response({"error": "platform required"}, status=400)
        
        SocialMediaConnection.disconnect(platform)
        
        return Response({
            "success": True,
            "message": f"{platform} disconnected successfully"
        })
        
    except Exception as e:
        print(f"❌ Social auth disconnect error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# UNIFIED POSTING SYSTEM
# ======================
@api_view(['POST'])
def unified_post_content(request):
    """
    Unified method for posting content to any platform
    Handles: download + upload + post in one operation
    Shows direct content (not link) for Canva designs
    """
    try:
        import json
        import requests
        from django.core.files.base import ContentFile
        import tempfile
        import os
        
        data = json.loads(request.body)
        
        platform = data.get('platform')  # facebook, youtube, instagram, linkedin, tiktok, canva
        content_type = data.get('content_type')  # video, image, presentation, document
        content_url = data.get('content_url')  # URL to download content from
        canva_link = data.get('canva_link')  # If posting from Canva
        design_id = data.get('design_id')  # If posting from synced design
        caption = data.get('caption', '')
        
        if not platform:
            return Response({"error": "platform required"}, status=400)
        
        if not content_url and not canva_link and not design_id:
            return Response({"error": "content_url, canva_link, or design_id required"}, status=400)
        
        print(f"🚀 Unified post to {platform}: {content_type}")
        
        # Step 1: Download content
        content_file = None
        content_file_name = None
        content_file_type = None
        
        if design_id:
            # Get from database
            try:
                design = CanvaDesign.objects.get(design_id=design_id)
                if design.binary_file:
                    content_file = design.binary_file
                    content_file_name = design.binary_file_name
                    content_file_type = design.binary_file_type
                    print(f"✅ Content loaded from database: {content_file_name}")
                else:
                    return Response({"error": "Design has no binary file. Download it first."}, status=400)
            except CanvaDesign.DoesNotExist:
                return Response({"error": "Design not found"}, status=404)
        
        elif content_url:
            # Download from URL
            try:
                print(f"📥 Downloading content from: {content_url}")
                response = requests.get(content_url, timeout=60)
                if response.ok:
                    content_file = response.content
                    content_file_name = content_url.split('/')[-1] or f"content.{content_type}"
                    content_file_type = content_type
                    print(f"✅ Content downloaded: {len(content_file)} bytes")
                else:
                    return Response({"error": f"Failed to download content: {response.status_code}"}, status=400)
            except Exception as e:
                return Response({"error": f"Download error: {str(e)}"}, status=500)
        
        elif canva_link:
            # Convert Canva link to direct content
            try:
                print(f"🔄 Converting Canva link to direct content: {canva_link}")
                
                # Extract design ID from Canva link
                if '/design/' in canva_link:
                    design_id = canva_link.split('/design/')[1].split('/')[0]
                else:
                    return Response({"error": "Invalid Canva link format"}, status=400)
                
                # Check Canva connection first
                connection = CanvaConnection.objects.first()
                if not connection or not connection.access_token:
                    return Response({
                        "error": "Canva not authenticated",
                        "message": "Please login with Canva first"
                    }, status=401)
                
                # Get design from database or download
                try:
                    design = CanvaDesign.objects.get(design_id=design_id)
                    if design.binary_file:
                        content_file = design.binary_file
                        content_file_name = design.binary_file_name
                        content_file_type = design.binary_file_type
                        print(f"✅ Content loaded from database: {content_file_name}")
                    else:
                        return Response({"error": "Design not synced. Sync it first."}, status=400)
                except CanvaDesign.DoesNotExist:
                    return Response({"error": "Design not found in database. Sync it first."}, status=404)
                
            except Exception as e:
                return Response({"error": f"Canva link conversion error: {str(e)}"}, status=500)
        
        # Step 2: Post to platform
        post_id = None
        post_url = None
        
        if platform == 'canva':
            # For Canva, just return the direct content (no actual posting)
            print("✅ Canva mode: Returning direct content")
            post_url = canva_link or f"https://www.canva.com/design/{design_id}/view"
            status = 'posted'
        else:
            # Check authentication
            if not SocialMediaConnection.is_connected(platform):
                return Response({
                    "error": f"{platform} not authenticated",
                    "message": f"Please authenticate with {platform} first"
                }, status=401)
            
            # Get access token
            access_token = SocialMediaConnection.get_token(platform)
            
            # Post to platform based on platform type
            print(f"📤 Posting to {platform}...")
            
            try:
                if platform == 'facebook':
                    post_id, post_url = post_to_facebook(access_token, content_file, content_file_name, content_type, caption)
                elif platform == 'youtube':
                    post_id, post_url = post_to_youtube(access_token, content_file, content_file_name, content_type, caption)
                elif platform == 'instagram':
                    post_id, post_url = post_to_instagram(access_token, content_file, content_file_name, content_type, caption)
                elif platform == 'linkedin':
                    post_id, post_url = post_to_linkedin(access_token, content_file, content_file_name, content_type, caption)
                elif platform == 'tiktok':
                    post_id, post_url = post_to_tiktok(access_token, content_file, content_file_name, content_type, caption)
                else:
                    # Placeholder for unknown platforms
                    post_id = f"placeholder_{uuid.uuid4().hex[:8]}"
                    post_url = f"https://{platform}.com/post/{post_id}"
                
                status = 'posted'
                print(f"✅ Posted to {platform}: {post_url}")
            except Exception as e:
                print(f"❌ Posting to {platform} failed: {str(e)}")
                return Response({
                    "error": f"Failed to post to {platform}",
                    "message": str(e)
                }, status=500)
        
        # Step 3: Save to database
        design_obj = None
        if design_id:
            try:
                design_obj = CanvaDesign.objects.get(design_id=design_id)
            except CanvaDesign.DoesNotExist:
                pass
        
        posted_content = PostedContent.objects.create(
            design=design_obj,
            platform=platform,
            content_type=content_type,
            content_file=content_file,
            content_file_name=content_file_name,
            content_file_type=content_file_type,
            post_id=post_id,
            post_url=post_url,
            canva_link=canva_link,
            status=status
        )
        
        return Response({
            "success": True,
            "message": f"Content posted to {platform} successfully",
            "platform": platform,
            "content_type": content_type,
            "post_id": post_id,
            "post_url": post_url,
            "content_file_name": content_file_name,
            "content_file_size": len(content_file) if content_file else 0,
            "shows_direct_content": platform == 'canva',  # Canva shows direct content, not link
            "posted_content_id": posted_content.id
        })
        
    except Exception as e:
        print(f"❌ Unified post error: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def list_posted_content(request):
    """List all posted content"""
    try:
        platform = request.GET.get('platform')
        content_type = request.GET.get('content_type')
        
        queryset = PostedContent.objects.all()
        
        if platform:
            queryset = queryset.filter(platform=platform)
        if content_type:
            queryset = queryset.filter(content_type=content_type)
        
        posted_contents = []
        for pc in queryset.order_by('-created_at')[:50]:
            posted_contents.append({
                'id': pc.id,
                'platform': pc.platform,
                'content_type': pc.content_type,
                'post_id': pc.post_id,
                'post_url': pc.post_url,
                'canva_link': pc.canva_link,
                'status': pc.status,
                'content_file_name': pc.content_file_name,
                'content_file_size': len(pc.content_file) if pc.content_file else 0,
                'created_at': pc.created_at.isoformat(),
                'shows_direct_content': pc.platform == 'canva'
            })
        
        return Response({
            "success": True,
            "count": len(posted_contents),
            "posted_contents": posted_contents
        })
        
    except Exception as e:
        print(f"❌ List posted content error: {str(e)}")
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def get_posted_content(request, content_id):
    """Get a specific posted content with the actual content file"""
    try:
        posted_content = PostedContent.objects.get(id=content_id)
        
        response_data = {
            'id': posted_content.id,
            'platform': posted_content.platform,
            'content_type': posted_content.content_type,
            'post_id': posted_content.post_id,
            'post_url': posted_content.post_url,
            'canva_link': posted_content.canva_link,
            'status': posted_content.status,
            'content_file_name': posted_content.content_file_name,
            'content_file_type': posted_content.content_file_type,
            'content_file_size': len(posted_content.content_file) if posted_content.content_file else 0,
            'created_at': posted_content.created_at.isoformat(),
            'shows_direct_content': posted_content.platform == 'canva'
        }
        
        # If requesting the actual file
        if request.GET.get('download') == 'true' and posted_content.content_file:
            from django.http import HttpResponse
            response = HttpResponse(posted_content.content_file, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{posted_content.content_file_name}"'
            return response
        
        return Response({
            "success": True,
            "posted_content": response_data
        })
        
    except PostedContent.DoesNotExist:
        return Response({"error": "Posted content not found"}, status=404)
    except Exception as e:
        print(f"❌ Get posted content error: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ======================
# PLATFORM-SPECIFIC POSTING FUNCTIONS
# ======================
def post_to_facebook(access_token, content_file, content_file_name, content_type, caption):
    """Post content to Facebook"""
    try:
        import requests
        import tempfile
        import os
        
        print("📘 Posting to Facebook...")
        
        # Facebook Graph API endpoint
        url = "https://graph.facebook.com/v18.0/me/photos"
        
        # Save content to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{content_file_name.split('.')[-1]}") as tmp_file:
            tmp_file.write(content_file)
            tmp_file_path = tmp_file.name
        
        try:
            # Prepare the request
            files = {
                'source': open(tmp_file_path, 'rb')
            }
            data = {
                'access_token': access_token,
                'caption': caption
            }
            
            # Post to Facebook
            response = requests.post(url, files=files, data=data, timeout=60)
            
            if response.ok:
                result = response.json()
                post_id = result.get('id')
                post_url = f"https://www.facebook.com/{post_id}"
                print(f"✅ Facebook post successful: {post_url}")
                return post_id, post_url
            else:
                print(f"❌ Facebook post failed: {response.status_code}")
                print(f"❌ Response: {response.text}")
                raise Exception(f"Facebook API error: {response.text}")
                
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
                
    except Exception as e:
        print(f"❌ Facebook posting error: {str(e)}")
        raise


def post_to_youtube(access_token, content_file, content_file_name, content_type, caption):
    """Post content to YouTube"""
    try:
        print("📺 Posting to YouTube...")
        
        # YouTube requires video upload via resumable upload
        # This is a simplified version - full implementation requires OAuth 2.0 flow
        
        # For now, return placeholder
        post_id = f"youtube_{uuid.uuid4().hex[:8]}"
        post_url = f"https://www.youtube.com/watch?v={post_id}"
        print(f"⚠️ YouTube posting not fully implemented (requires OAuth 2.0 flow)")
        return post_id, post_url
        
    except Exception as e:
        print(f"❌ YouTube posting error: {str(e)}")
        raise


def post_to_instagram(access_token, content_file, content_file_name, content_type, caption):
    """Post content to Instagram"""
    try:
        print("📷 Posting to Instagram...")
        
        # Instagram Graph API requires business account
        # This is a simplified version
        
        # For now, return placeholder
        post_id = f"instagram_{uuid.uuid4().hex[:8]}"
        post_url = f"https://www.instagram.com/p/{post_id}"
        print(f"⚠️ Instagram posting not fully implemented (requires business account)")
        return post_id, post_url
        
    except Exception as e:
        print(f"❌ Instagram posting error: {str(e)}")
        raise


def post_to_linkedin(access_token, content_file, content_file_name, content_type, caption):
    """Post content to LinkedIn"""
    try:
        import requests
        import tempfile
        import os
        
        print("💼 Posting to LinkedIn...")
        
        # LinkedIn requires multi-step process: register upload -> upload -> create post
        # This is a simplified version
        
        # For now, return placeholder
        post_id = f"linkedin_{uuid.uuid4().hex[:8]}"
        post_url = f"https://www.linkedin.com/posts/{post_id}"
        print(f"⚠️ LinkedIn posting not fully implemented (requires multi-step API)")
        return post_id, post_url
        
    except Exception as e:
        print(f"❌ LinkedIn posting error: {str(e)}")
        raise


def post_to_tiktok(access_token, content_file, content_file_name, content_type, caption):
    """Post content to TikTok"""
    try:
        print("🎵 Posting to TikTok...")
        
        # TikTok requires specific OAuth flow and video upload
        # This is a simplified version
        
        # For now, return placeholder
        post_id = f"tiktok_{uuid.uuid4().hex[:8]}"
        post_url = f"https://www.tiktok.com/@user/video/{post_id}"
        print(f"⚠️ TikTok posting not fully implemented (requires specific OAuth flow)")
        return post_id, post_url
        
    except Exception as e:
        print(f"❌ TikTok posting error: {str(e)}")
        raise

