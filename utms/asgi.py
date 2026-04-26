import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from apps.transport import routing as transport_routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'utms.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            transport_routing.websocket_urlpatterns
        )
    ),
})
