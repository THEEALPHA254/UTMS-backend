from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/trip/(?P<trip_id>\d+)/$', consumers.TripLocationConsumer.as_asgi()),
]
