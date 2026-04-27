from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ======================
# SECURITY
# ======================
SECRET_KEY = "demo-key"
DEBUG = True

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".ngrok-free.app",
    ".ngrok.io"
]

# ======================
# APPS
# ======================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'api',
]

# ======================
# MIDDLEWARE
# ======================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.middleware.RequestLoggerMiddleware',
]

ROOT_URLCONF = 'canva_project.urls'

# ======================
# TEMPLATES
# ======================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, "templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'canva_project.wsgi.application'

# ======================
# DATABASE
# ======================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ======================
# STATIC FILES (🔥 FIX ADDED)
# ======================
STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),   # ✅ IMPORTANT FIX
]

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")  # ✅ production safe

# ======================
# MEDIA FILES
# ======================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ======================
# CANVA API
# ======================
CLIENT_ID = os.getenv("CANVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("CANVA_REDIRECT_URI")

# ======================
# COOKIE SETTINGS (OAuth FIX)
# ======================
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# ======================
# NGROK CONFIG
# ======================
NGROK_URL = os.getenv("NGROK_URL")

if not NGROK_URL:
    NGROK_URL = "http://127.0.0.1:8000"

BASE_URL = NGROK_URL.rstrip("/")