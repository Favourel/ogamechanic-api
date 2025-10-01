from django.urls import path
from . import views


app_name = 'communications'

urlpatterns = [
    # Chat Room endpoints
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
] 
