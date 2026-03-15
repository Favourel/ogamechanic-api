from django.urls import path
from . import views


app_name = 'communications'

urlpatterns = [
    # ── Peer-to-Peer Chat Endpoints ──────────────────────────────────
    path('chat-rooms/', views.ChatRoomListView.as_view(),
         name='chat-room-list'),
    path('chat-rooms/<uuid:chat_room_id>/',
         views.ChatRoomDetailView.as_view(), name='chat-room-detail'),

    # Message endpoints
    path('chat-rooms/<uuid:chat_room_id>/messages/',
         views.MessageListView.as_view(), name='message-list'),
    path('chat-rooms/<uuid:chat_room_id>/messages/<uuid:message_id>/',
         views.MessageDetailView.as_view(), name='message-detail'),
    path('chat-rooms/<uuid:chat_room_id>/mark-read/',
         views.MarkMessagesReadView.as_view(), name='mark-messages-read'),

    # Notification endpoints
    path('notifications/', views.ChatNotificationListView.as_view(),
         name='notification-list'),

    # ── Support Chat Endpoints ───────────────────────────────────────
    path('support/conversations/',
         views.SupportConversationListView.as_view(),
         name='support-conversation-list'),
    path('support/conversations/<uuid:conversation_id>/',
         views.SupportConversationDetailView.as_view(),
         name='support-conversation-detail'),
    path('support/conversations/<uuid:conversation_id>/messages/',
         views.SupportMessageListView.as_view(),
         name='support-message-list'),
    path('support/conversations/<uuid:conversation_id>/mark-read/',
         views.SupportMarkReadView.as_view(),
         name='support-mark-read'),
    path('support/upload/',
         views.SupportFileUploadView.as_view(),
         name='support-file-upload'),
]
