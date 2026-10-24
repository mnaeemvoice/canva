import os
import django
import sys
import time
from pathlib import Path
import base64

# Setup Django environment
sys.path.append('/home/pc/Documents/canva')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'canva_project.settings')
django.setup()

from api.remote_canva_browser import CanvaBrowserWorker
from django.contrib.auth.models import User

def final_verify():
    user = User.objects.get(username='mnaeemvoice')
    print(f"🚀 Final Verification for user: {user.username}")
    worker = CanvaBrowserWorker()
    
    try:
        # 1. Start browser
        print("🌐 Starting browser...")
        res = worker.call("start", owner_id=user.pk)
        print(f"   Start Result: {res.get('success')}")
        if not res.get('success'):
            print(f"❌ Browser failed to start: {res.get('error')}")
            return
        
        # 2. Go to Login page
        print("🔗 Navigating to Canva Login...")
        res = worker.call("input", owner_id=user.pk, action="navigate", url="https://www.canva.com/login")
        time.sleep(15) 
        
        res = worker.call("screenshot", owner_id=user.pk)
        if res.get('success'):
            with open("verify_step1_login.png", "wb") as f:
                f.write(base64.b64decode(res['image'].split(",")[1]))
            print(f"📸 Login Page: {res.get('title')} - {res.get('url')}")
        
        # 3. Go to Your Designs
        print("🚀 Navigating to Your Designs...")
        res = worker.call("input", owner_id=user.pk, action="navigate", url="https://www.canva.com/your-designs")
        time.sleep(15)
        
        res = worker.call("screenshot", owner_id=user.pk)
        if res.get('success'):
            with open("verify_step2_designs.png", "wb") as f:
                f.write(base64.b64decode(res['image'].split(",")[1]))
            print(f"📸 Designs Page: {res.get('title')} - {res.get('url')}")
            
            title = res.get('title', '').lower()
            if "can't show this page" in title or "403" in title or "cloudflare" in title:
                print("❌ BOT DETECTION DETECTED!")
            else:
                print("✅ SUCCESS! No bot detection page found.")
        else:
            print(f"❌ Screenshot 2 failed: {res.get('error')}")

    except Exception as e:
        print(f"💥 Error in test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        worker.call("stop", owner_id=user.pk)
        print("🏁 Test finished.")

if __name__ == "__main__":
    final_verify()
