from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r'ws/repair-requests/(?P<repair_id>[^/]+)/tracking/$',
        consumers.RepairRequestTrackingConsumer.as_asgi(),
        name='repair_request_tracking'
    ),
]
