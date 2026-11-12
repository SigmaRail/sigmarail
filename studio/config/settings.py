"""
Django settings for SigmaRail Studio (Phase 1).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _ensure_verabasel_path() -> None:
    """Prefer monorepo VeraBase/src over any stale installed package."""
    configured = os.environ.get("VERA_BASE_SOURCE", "").strip()
    candidates = [Path(configured).expanduser()] if configured else [
        parent / "VeraBase" / "src" for parent in BASE_DIR.parents
    ]
    vb_src = next((path for path in candidates if path.is_dir()), None)
    if vb_src is None:
        return
    path = str(vb_src)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


_ensure_verabasel_path()

SECRET_KEY = "django-insecure-sigmarail-studio-phase1-dev-only"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver", "host.docker.internal"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Phase 1: Vite SPA on 5173 / preview 4173
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

# Phase 1: no auth
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# Saved screens backend: sqlite (default/tests) or ch (ClickHouse strategy_screens).
# Override with env SCREEN_STORE=sqlite|ch
import os as _os

SCREEN_STORE = _os.environ.get("SCREEN_STORE", "sqlite").strip().lower() or "sqlite"

# Uniform envelope (Phase 6): opt-in via ENVELOPE_JSON=1. Default off so the SPA and
# existing API tests keep the raw response shape until the rollout is coordinated.
if _os.environ.get("ENVELOPE_JSON", "0").strip() == "1":
    REST_FRAMEWORK["EXCEPTION_HANDLER"] = "api.envelope.envelope_exception_handler"
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = ["api.envelope.EnvelopeJSONRenderer"]

SPECTACULAR_SETTINGS = {
    "TITLE": "SigmaRail Studio API",
    "DESCRIPTION": "Screening presets, universe_query_v1 IR preview, backtest compose/submit/read.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
