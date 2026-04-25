from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'demo-key'
DEBUG = True
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".ngrok-free.app"
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',   # 🔥 ADD THIS
    'django.contrib.staticfiles',

    'rest_framework',
    'api',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',  # 🔥 ADD THIS
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'canva_project.urls'



BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
       'DIRS': [os.path.join(BASE_DIR, "templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # 🔥 IMPORTANT
                'django.contrib.auth.context_processors.auth',  # 🔥 FIX
                'django.contrib.messages.context_processors.messages',  # 🔥 FIX
            ],
        },
    },
]

WSGI_APPLICATION = 'canva_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

STATIC_URL = 'static/'

 
CLIENT_ID = os.getenv("CANVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("CANVA_REDIRECT_URI")

SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
BASE_URL = "https://e016-160-250-51-6.ngrok-free.app"
NGROK_URL = "https://e016-160-250-51-6.ngrok-free.app"