from pathlib import Path
import os
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY and not os.environ.get("DJANGO_DEBUG") == "True":
    raise ValueError("DJANGO_SECRET_KEY environment variable is required in production.")
SECRET_KEY = SECRET_KEY or "dev-insecure-key-for-local-development-only"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# Hosts that can access this app. In production, set DJANGO_ALLOWED_HOSTS
# to a comma-separated list like "yourdomain.com,www.yourdomain.com".
ALLOWED_HOSTS: list[str] = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1,attendacetracker.duckdns.org,49.36.99.36",
    ).split(",")
    if h.strip()
]

# Allow all hosts for local Wi-Fi testing if DEBUG is True
if DEBUG:
    ALLOWED_HOSTS = ['*']

# Authentication redirects
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "checkin_checkout"

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "axes",
    "attendance",
]

# DRF Settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle"
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/minute",
        "user": "500/minute"
    }
}

from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "attendance_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "attendance_site.wsgi.application"

# Database

import dj_database_url

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True

# Static files

STATIC_URL = "static/"
# In production, collectstatic will write here; in dev you can still use it.
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"

# -----------------------------------------------------------------------------
# YAML configuration (attendance + logging)
# -----------------------------------------------------------------------------

CONFIG_FILE = os.environ.get(
    "ATTENDANCE_CONFIG_FILE",
    str(BASE_DIR / "config" / "settings.yaml"),
)

# Ensure logs directory exists
LOGS_DIR = BASE_DIR / "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        APP_CONFIG = yaml.safe_load(f) or {}
except FileNotFoundError:
    APP_CONFIG = {}

ATTENDANCE_CONFIG = APP_CONFIG.get("attendance", {})

DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# Logging: prefer YAML config; fall back to sane console/file defaults.
LOGGING = APP_CONFIG.get("logging") or DEFAULT_LOGGING_CONFIG

# ------------------------------------------------------------------
# Security hardening for production
# ------------------------------------------------------------------
if not DEBUG:
    # Trust these origins for CSRF (update when you know your domain)
    CSRF_TRUSTED_ORIGINS = [
        f"https://{host}"
        for host in ALLOWED_HOSTS
        if host not in ("localhost", "127.0.0.1")
    ]

    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_HSTS_SECONDS = 31536000  # one year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ------------------------------------------------------------------
# Content Security Policy (CSP) Settings
# ------------------------------------------------------------------
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",
    "https://fonts.googleapis.com",
    "https://cdn.jsdelivr.net",
)
CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",
    "https://cdn.jsdelivr.net",
)
CSP_FONT_SRC = (
    "'self'",
    "https://fonts.gstatic.com",
    "data:",
)
CSP_IMG_SRC = (
    "'self'",
    "data:",
)

# ------------------------------------------------------------------
# SECURITY: CORS Settings
# ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", 
    "http://localhost:8000,http://127.0.0.1:8000,http://attendacetracker.duckdns.org,https://attendacetracker.duckdns.org"
)
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in CORS_ALLOWED_ORIGINS.split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# SECURITY: Brute-force Protection (django-axes)
# ------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = int(os.environ.get("LOGIN_RATE_LIMIT", 5))
AXES_COOLOFF_TIME = 1  # 1 hour lockout
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

# ------------------------------------------------------------------
# SECURITY: Rate Limiting global cache (django-ratelimit)
# ------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ratelimit-cache",
    }
}
RATELIMIT_VIEW = 'attendance_site.urls.ratelimited_error'

# ------------------------------------------------------------------
# EMAIL CONFIGURATION
# ------------------------------------------------------------------
# Prints emails (like password reset) to the console log instead of crashing
# For production via SMTP, change EMAIL_BACKEND and set EMAIL_HOST etc.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
