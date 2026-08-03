"""ASGI entrypoint for both HTTP and WebSocket traffic.

Import order matters here. The settings module must be set and Django must be
initialised before anything that touches models is imported, otherwise the
process dies at startup with "Requested setting INSTALLED_APPS, but settings
are not configured" under any real ASGI server.
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.settings')

import django  # noqa: E402

django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_application = get_asgi_application()

from users.middleware import JWTAuthMiddlewareStack  # noqa: E402
from users.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_application,
    'websocket': JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
