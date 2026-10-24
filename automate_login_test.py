import os
import django
import sys
import time
from pathlib import Path

# Setup Django environment
sys.path.append('/home/pc/Documents/canva')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'canva_project.settings')
django.setup()

from api.remote_canva_browser import CanvaBrowserWorker
from django.contrib.auth.models import User

def automate_test():
    user = User.objects.get(username='mnaeemvoice')
    print(f"🚀 Starting Test for user: {user.username}")
    worker = CanvaBrowserWorker()
    
    try:
        # 1. Start browser
        print("🌐 Starting browser...")
        worker.call("start", owner_id=user.pk)
        
        # 2. Go to Login page
        print("🔗 Navigating to Canva Login...")
        worker.call("input", owner_id=user.pk, action="navigate", url="https://www.canva.com/login")
        time.sleep(10)
        
        # 3. Take screenshot of login page
        print("📸 Screenshot: Login Page")
        res = worker.call("screenshot", owner_id=user.pk)
        if res.get('success'):
            import base64
            with open("step1_login_page.png", "wb") as f:
                f.write(base64.b64decode(res['image'].split(",")[1]))
            print(f"   URL: {res.get('url')}")
            print(f"   Title: {res.get('title')}")

        # 4. Try to find "Continue with email" or email input
        # Note: Canva UI varies. We'll try common selectors.
        print("⌨️ Attempting to enter credentials...")
        # Often there's a button "Continue with email"
        # We'll just try to type and press enter if we can find an input
        # Or just navigate to a design to see if 403 happens
        
        print("🚀 Navigating to Your Designs to check for 403...")
        worker.call("input", owner_id=user.pk, action="navigate", url="https://www.canva.com/your-designs")
        time.sleep(15)
        
        print("📸 Screenshot: Designs Page")
        res = worker.call("screenshot", owner_id=user.pk)
        if res.get('success'):
            import base64
            with open("step2_designs_page.png", "wb") as f:
                f.write(base64.b64decode(res['image'].split(",")[1]))
            print(f"   URL: {res.get('url')}")
            print(f"   Title: {res.get('title')}")
            
            title = res.get('title', '').lower()
            if "can't show this page" in title or "403" in title:
                print("❌ Still getting 403 on designs page.")
            else:
                print("✅ Designs page loaded (or at least no 403).")

    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        worker.call("stop", owner_id=user.pk)
        print("🏁 Test finished.")

if __name__ == "__main__":
    automate_test()
