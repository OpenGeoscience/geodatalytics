from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import django_stubs_ext
from environ import Env
import osgeo.gdal

from resonant_settings.allauth import *
from resonant_settings.celery import *
from resonant_settings.django import *
from resonant_settings.django_extensions import *
from resonant_settings.logging import *
from resonant_settings.oauth_toolkit import *
from resonant_settings.rest_framework import *

django_stubs_ext.monkeypatch()

env = Env()

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent

ROOT_URLCONF = "uvdat.urls"

ASGI_APPLICATION = "uvdat.asgi.application"

INSTALLED_APPS = [
    # Install local apps first, to ensure any overridden resources are found first
    "uvdat.core.apps.CoreConfig",
    # Apps with overrides
    "auth_style",
    "resonant_settings.allauth_support",
    # Everything else
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.gis",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "django_extensions",
    "django_filters",
    "django_large_image",
    "drf_yasg",
    "guardian",
    "oauth2_provider",
    "resonant_utils",
    "rest_framework",
    "rest_framework.authtoken",
    "s3_file_field",
]

MIDDLEWARE = [
    # CorsMiddleware must be added before other response-generating middleware,
    # so it can potentially add CORS headers to those responses too.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoiseMiddleware must be directly after SecurityMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # GZipMiddleware can be after WhiteNoiseMiddleware, as WhiteNoise performs its own compression
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.contrib.sites.middleware.CurrentSiteMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# Internal datetimes are timezone-aware, so this only affects rendering and form input
TIME_ZONE = "UTC"

DATABASES = {
    "default": {
        **env.db_url("DJANGO_DATABASE_URL", engine="django.contrib.gis.db.backends.postgis"),
        "OPTIONS": {
            "pool": {
                # Adjust this pool size according to your postgres add-on service tier,
                # web dyno count, WEB_CONCURRENCY, etc.
                "max_size": env.int("DJANGO_DATABASE_POOL_MAX_SIZE", default=4),
            },
        },
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# https://github.com/girder/large_image_wheels#geodjango
GDAL_LIBRARY_PATH = osgeo.GDAL_LIBRARY_PATH
GEOS_LIBRARY_PATH = osgeo.GEOS_LIBRARY_PATH

STORAGES: dict[str, dict[str, Any]] = {
    # Inject the "default" storage in particular run configurations
    "staticfiles": {
        # CompressedManifestStaticFilesStorage does not work properly with drf-
        # https://github.com/axnsan12/drf-yasg/issues/761
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

STATIC_ROOT = BASE_DIR / "staticfiles"
# Django staticfiles auto-creates any intermediate directories, but do so here to prevent warnings.
STATIC_ROOT.mkdir(exist_ok=True)

# Django's docs suggest that STATIC_URL should be a relative path,
# for convenience serving a site on a subpath.
STATIC_URL = "static/"

# Make Django and Allauth redirects consistent, but both may be changed.
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_SIGNUP_FORM_CLASS = "resonant_utils.allauth.FullNameSignupForm"

# Use codes for email verification; links can be modified by Microsoft Safe Links
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True

AUTHENTICATION_BACKENDS.append("guardian.backends.ObjectPermissionBackend")
# django-guardian; raise PermissionDenied exception instead of redirecting to login page
GUARDIAN_RAISE_403 = True
# django-guardian; disable anonymous user permissions
ANONYMOUS_USER_NAME = None
# Append this
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] += [
    "rest_framework.authentication.TokenAuthentication",
]
REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = ["uvdat.core.access_control.GuardianPermission"]
REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"] = ["uvdat.core.access_control.GuardianFilter"]

CORS_ALLOWED_ORIGINS: list[str] = env.list("DJANGO_CORS_ALLOWED_ORIGINS", cast=str, default=[])
CORS_ALLOWED_ORIGIN_REGEXES: list[str] = env.list(
    "DJANGO_CORS_ALLOWED_ORIGIN_REGEXES", cast=str, default=[]
)

# django-channels with Redis
CHANNEL_LAYERS: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": env.url("DJANGO_REDIS_URL").geturl(),
                    # Use database /1 for Channels backend,
                    # in case other services use /0 in the future
                    "db": 1,
                },
            ]
        },
    }
}

# Large image cache with Redis
LARGE_IMAGE_CACHE_BACKEND = "redis"
LARGE_IMAGE_CACHE_REDIS_URL = env.url("DJANGO_REDIS_URL").geturl()

UVDAT_WEB_URL: str = env.url("DJANGO_UVDAT_WEB_URL").geturl()
UVDAT_ENABLE_FLOOD_SIMULATION: bool = env.bool("DJANGO_UVDAT_ENABLE_FLOOD_SIMULATION", default=True)
UVDAT_ENABLE_FLOOD_NETWORK_FAILURE: bool = env.bool(
    "DJANGO_UVDAT_ENABLE_FLOOD_NETWORK_FAILURE", default=True
)
UVDAT_ENABLE_NETWORK_RECOVERY: bool = env.bool("DJANGO_UVDAT_ENABLE_NETWORK_RECOVERY", default=True)
UVDAT_ENABLE_GEOAI_SEGMENTATION: bool = env.bool(
    "DJANGO_UVDAT_ENABLE_GEOAI_SEGMENTATION", default=True
)
UVDAT_ENABLE_CREATE_ROAD_NETWORK: bool = env.bool(
    "DJANGO_UVDAT_ENABLE_CREATE_ROAD_NETWORK", default=True
)

logging.getLogger("pyvips").setLevel(logging.ERROR)
logging.getLogger("rasterio").setLevel(logging.ERROR)
logging.getLogger("large-image-converter").setLevel(logging.ERROR)

osgeo.gdal.SetConfigOption("OGR_GEOJSON_MAX_OBJ_SIZE", "500")  # MB
