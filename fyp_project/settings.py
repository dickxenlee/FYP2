import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fallback-key-change-me')

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

# ── Production security (applied only when DEBUG is False) ──
if not DEBUG:
    if SECRET_KEY.startswith('django-insecure-'):
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            'Set a strong SECRET_KEY environment variable for production.'
        )
    # Render/most hosts terminate HTTPS at a proxy and forward this header,
    # so Django knows the request is secure (fixes CSRF + redirect issues).
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Trust the deployed domain(s) for cross-origin POSTs (e.g. your-app.onrender.com).
    CSRF_TRUSTED_ORIGINS = [
        f'https://{h.strip()}' for h in ALLOWED_HOSTS
        if h.strip() and h.strip() not in ('127.0.0.1', 'localhost', '*')
    ]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'fyp_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
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

WSGI_APPLICATION = 'fyp_project.wsgi.application'

# The database is chosen by the DATABASE_URL environment variable:
#   • Render (online)  → PostgreSQL  (Render sets DATABASE_URL automatically)
#   • Your PC (XAMPP)  → mysql://root:@127.0.0.1:3306/fyp_db?charset=utf8mb4
#   • Not set          → local SQLite file (db.sqlite3)
# Same code runs everywhere — only the env var changes.
import dj_database_url

# Use DATABASE_URL only when it is a real database URL (contains "://", e.g.
# postgres://... or mysql://...). Any empty, blank, or malformed value is
# treated as "not set" and safely falls back to the local SQLite file, so a bad
# env var on the host can never crash startup.
_db_url = os.environ.get('DATABASE_URL', '').strip()
if '://' in _db_url:
    DATABASES = {'default': dj_database_url.parse(_db_url, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# MySQL/MariaDB only: enable strict mode so bad data raises an error instead of
# being silently truncated. Skipped for PostgreSQL (Render) and SQLite.
if DATABASES['default']['ENGINE'].endswith('mysql'):
    DATABASES['default'].setdefault('OPTIONS', {})
    DATABASES['default']['OPTIONS']['init_command'] = "SET sql_mode='STRICT_TRANS_TABLES'"

AUTHENTICATION_BACKENDS = [
    'core.auth_backends.EmailOrUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kuala_Lumpur'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# core/static is auto-discovered via AppDirectoriesFinder (core is an installed app).

# WhiteNoise serves static files in production (DEBUG=False) with compression.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/workspace/'
LOGOUT_REDIRECT_URL = '/'

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
