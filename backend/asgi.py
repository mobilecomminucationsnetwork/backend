# backend/asgi.py
import os
import django
import logging
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

# Logger
logger = logging.getLogger('channels.server')
logger.info("ASGI application starting...")

# api/routing.py dosyasını import etmek için, önce Django'yu ayarlamalıyız
import api.routing

logger.info("WebSocket URL patterns loaded")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                api.routing.websocket_urlpatterns
            )
        )
    ),
})

logger.info("ASGI application initialized with WebSocket support")