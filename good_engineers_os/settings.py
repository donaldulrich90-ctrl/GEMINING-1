"""Configuration Django — GOOD ENGINEERS OS (migration hors Streamlit).

Points clés :
  - Sessions par cookies signés : aucune base Django à créer/migrer.
  - Les données métier restent dans les fichiers de l'ancienne app
    (app_database.json, geo_data.db, tenant_data/), via GE_DATA_ROOT.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Racine des données métier (réutilise l'ancienne app) -------------------
# Par défaut : le dossier parent du projet (webapp/ vit dans TEST_MINE/).
GE_DATA_ROOT = Path(os.environ.get("GE_DATA_ROOT", BASE_DIR.parent)).resolve()

# --- Clé secrète (persistée pour garder les sessions entre redémarrages) ----
def _load_secret_key():
    env = os.environ.get("GE_SECRET_KEY")
    if env:
        return env
    key_file = BASE_DIR / ".secret_key"
    try:
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key = secrets.token_urlsafe(64)
        key_file.write_text(key, encoding="utf-8")
        return key
    except OSError:
        return "dev-insecure-" + secrets.token_urlsafe(16)


SECRET_KEY = _load_secret_key()
DEBUG = os.environ.get("GE_DEBUG", "1") == "1"

ALLOWED_HOSTS = ["*"]  # restreindre en production via GE_ALLOWED_HOSTS si besoin
_env_hosts = os.environ.get("GE_ALLOWED_HOSTS", "").strip()
if _env_hosts:
    ALLOWED_HOSTS = [h.strip() for h in _env_hosts.split(",") if h.strip()]

# Derrière le reverse-proxy (NPM / OpenResty) : cookies + CSRF corrects
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("GE_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "webcore",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sert les fichiers statiques en production (sans nginx).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "webcore.middleware.AuthTenantMiddleware",
]

ROOT_URLCONF = "good_engineers_os.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "webcore.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "good_engineers_os.wsgi.application"

# Aucune base Django : tout est dans les fichiers de l'ancienne app.
DATABASES = {}

# Sessions par cookies signés (pas de table de sessions).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_NAME = "ge_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Ouagadougou"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise : compression + cache des fichiers statiques (sans manifeste strict,
# pour tolérer un éventuel asset référencé mais absent).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --- Sécurité derrière le reverse-proxy HTTPS de Coolify (Traefik) ----------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
