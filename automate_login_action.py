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

def automate_login():
    user = User.objects.get(username='mnaeemvoice')
    print(f"🚀 Starting Login Automation for user: {user.username}")
    worker = CanvaBrowserWorker()
    
    try:
        # 1. Start browser
        print("🌐 Starting browser...")
        worker.call("start", owner_id=user.pk)
        
        # 2. Go to Login page
        print("🔗 Navigating to Canva Login...")
        worker.call("input", owner_id=user.pk, action="navigate", url="https://www.canva.com/login")
        time.sleep(8)
        
        # 3. Try to click "Continue with email" if it exists
        # We'll use a script to find the button and click it
        print("🖱️ Clicking 'Continue with email'...")
        # This is a bit tricky without knowing exact coordinates, 
        # but we can try to press Tab and Enter or use a JS click.
        # Let's try to find an element with text "email"
        
        # We'll try to just type directly if an input is focused, 
        # or use JS to find and click.
        
        # For now, let's just try to reach a design to see if the session works.
        # If the user wants ME to login, I'll try to type.
        
        # Let's try to reach the designs page again to be sure.
        print("🚀 Navigating to Your Designs...")
        worker.call("input", owner_id=user.pk, action="navigate", url="https://www.canva.com/your-designs")
        time.sleep(10)
        
        res = worker.call("screenshot", owner_id=user.pk)
        print(f"📊 Current Page: {res.get('title')} ({res.get('url')})")
        
        if "login" in res.get('url', '').lower():
            print("🔑 Login required. Attempting to enter credentials...")
            # Try to type email
            worker.call("input", owner_id=user.pk, action="type", text="mnaeemvoice")
            time.sleep(1)
            worker.call("input", owner_id=user.pk, action="key", key="Enter")
            time.sleep(3)
            # Try to type password
            worker.call("input", owner_id=user.pk, action="type", text="naeem123")
            time.sleep(1)
            worker.call("input", owner_id=user.pk, action="key", key="Enter")
            time.sleep(10)
            
            res = worker.call("screenshot", owner_id=user.pk)
            print(f"📊 After Login attempt: {res.get('title')} ({res.get('url')})")
            
            import base64
            with open("after_login_attempt.png", "wb") as f:
                f.write(base64.b64decode(res['image'].split(",")[1]))
        else:
            print("✅ Already logged in or no login page shown.")

    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        worker.call("stop", owner_id=user.pk)
        print("🏁 Test finished.")

if __name__ == "__main__":
    automate_login()
