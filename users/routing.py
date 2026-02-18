from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Individual user notifications
    re_path(
        r'ws/notifications/$',
        consumers.NotificationConsumer.as_asgi(),
        name='notifications'
    ),

    # Admin/group notifications
    re_path(
        r'ws/admin/notifications/$',
        consumers.NotificationGroupConsumer.as_asgi(),
        name='admin_notifications'
    ),
]
