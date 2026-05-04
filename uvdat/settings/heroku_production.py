from __future__ import annotations

import os
import ssl

# Redefine these before importing the rest of the settings
os.environ["DJANGO_DATABASE_URL"] = os.environ["DATABASE_URL"]
os.environ["DJANGO_CELERY_BROKER_URL"] = os.environ["CLOUDAMQP_URL"]
os.environ["DJANGO_REDIS_URL"] = os.environ["REDIS_URL"]
# Provided by https://github.com/ianpurvis/heroku-buildpack-version
os.environ["DJANGO_SENTRY_RELEASE"] = os.environ["SOURCE_VERSION"]

from .production import *  # isort: skip

# This needs to be set by the HTTPS terminating reverse proxy.
# Heroku and Render automatically set this.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

<<<<<<< before updating
# Heroku Redis uses self-signed certs
CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]["ssl_cert_reqs"] = ssl.CERT_NONE
=======
# Inform rate limiting that "X-Forwarded-For" should be trusted, as it's appended by Heroku.
ALLAUTH_TRUSTED_PROXY_COUNT = 1
>>>>>>> after updating
