from __future__ import annotations

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from uvdat.core.notifications import AnalyticsConsumer, ConversionConsumer

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        # Wrapping with SentryAsgiMiddleware: https://github.com/getsentry/sentry-python/issues/2556
        "websocket": SentryAsgiMiddleware(
            AuthMiddlewareStack(
                URLRouter(
                    [
                        path(
                            "ws/analytics/project/<int:project_id>/results/",
                            AnalyticsConsumer.as_asgi(),
                            name="analytics-ws",
                        ),
                        path(
                            "ws/conversion/",
                            ConversionConsumer.as_asgi(),
                            name="conversion-ws",
                        ),
                    ]
                )
            )
        ),
    }
)
