"""
ASGI config for ogamechanic project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
import django

# Initialize Django
# django.setup()

# Import routing after Django is set up
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from communications.routing import websocket_urlpatterns
from users.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from rides.routing import websocket_urlpatterns as rides_websocket_urlpatterns

from decouple import config
from dotenv import load_dotenv

load_dotenv()


if config('env', '') == 'prod' or os.getenv('env', 'dev') == 'prod':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.prod')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.dev')

django_asgi_app = get_asgi_application()

# Combine all WebSocket URL patterns
all_websocket_urlpatterns = (
    websocket_urlpatterns + 
    notification_websocket_urlpatterns + 
    rides_websocket_urlpatterns
)

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(all_websocket_urlpatterns)
    ),
})
