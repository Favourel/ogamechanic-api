"""
ASGI config for ogamechanic project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

from decouple import config
from dotenv import load_dotenv

load_dotenv()


if config('env', '') == 'prod' or os.getenv('env', 'dev') == 'prod':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.prod')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.dev')

django_asgi_app = get_asgi_application()

# Import routing AFTER Django setup
from channels.routing import ProtocolTypeRouter, URLRouter
from communications.middleware import JWTAuthMiddleware
from communications.routing import websocket_urlpatterns
from users.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from rides.routing import websocket_urlpatterns as rides_websocket_urlpatterns

# Combine all WebSocket URL patterns
all_websocket_urlpatterns = (
    websocket_urlpatterns +
    notification_websocket_urlpatterns +
    rides_websocket_urlpatterns
)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(all_websocket_urlpatterns)
    ),
})
