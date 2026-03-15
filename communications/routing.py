from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Existing peer-to-peer chat
    re_path(
        r'ws/chat/(?P<chat_room_id>[^/]+)/$',
        consumers.ChatConsumer.as_asgi()
    ),

    # Support chat — per conversation
    re_path(
        r'ws/support/chat/(?P<conversation_id>[^/]+)/$',
        consumers.SupportChatConsumer.as_asgi(),
        name='support_chat',
    ),

    # Support admin dashboard — real-time updates
    re_path(
        r'ws/support/dashboard/$',
        consumers.AdminDashboardConsumer.as_asgi(),
        name='support_dashboard',
    ),
]
