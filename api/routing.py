# api/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/doors/(?P<door_id>[\w-]+)/$', consumers.DoorConsumer.as_asgi()),
]