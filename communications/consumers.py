import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import ChatRoom, Message, ChatNotification

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time chat functionality"""
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope["user"]
        self.chat_room_id = self.scope['url_route']['kwargs']['chat_room_id']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Verify user is participant in this chat room
        is_participant = await self.is_chat_room_participant()
        if not is_participant:
            await self.close()
            return
        
        # Join the chat room group
        self.room_group_name = f'chat_{self.chat_room_id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to chat room',
            'chat_room_id': self.chat_room_id
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave the chat room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'chat_message')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(text_data_json)
            elif message_type == 'typing':
                await self.handle_typing(text_data_json)
            elif message_type == 'read_messages':
                await self.handle_read_messages(text_data_json)
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
    
    async def handle_chat_message(self, data):
        """Handle incoming chat messages"""
        content = data.get('content', '').strip()
        message_type = data.get('message_type', 'text')
        file_url = data.get('file_url', None)
        
        if not content and message_type == 'text':
            return
        
        # Save message to database
        message = await self.save_message(content, message_type, file_url)
        
        # Send message to chat room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': {
                    'id': str(message.id),
                    'content': message.content,
                    'message_type': message.message_type,
                    'file_url': message.file_url,
                    'sender': {
                        'id': str(message.sender.id),
                        'email': message.sender.email,
                        'first_name': message.sender.first_name,
                        'last_name': message.sender.last_name,
                    },
                    'created_at': message.created_at.isoformat(),
                    'is_read': message.is_read
                }
            }
        )
        
        # Create notifications for other participants
        await self.create_notifications(message)
    
    async def handle_typing(self, data):
        """Handle typing indicators"""
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_typing',
                'user_id': str(self.user.id),
                'user_email': self.user.email,
                'is_typing': is_typing
            }
        )
    
    async def handle_read_messages(self, data):
        """Handle marking messages as read"""
        message_ids = data.get('message_ids', [])
        await self.mark_messages_as_read(message_ids)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'messages_read',
                'user_id': str(self.user.id),
                'message_ids': message_ids
            }
        )
    
    async def chat_message(self, event):
        """Send chat message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))
    
    async def user_typing(self, event):
        """Send typing indicator to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'user_typing',
            'user_id': event['user_id'],
            'user_email': event['user_email'],
            'is_typing': event['is_typing']
        }))
    
    async def messages_read(self, event):
        """Send read confirmation to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'user_id': event['user_id'],
            'message_ids': event['message_ids']
        }))
    
    @database_sync_to_async
    def is_chat_room_participant(self):
        """Check if user is participant in the chat room"""
        try:
            chat_room = ChatRoom.objects.get(id=self.chat_room_id)
            return chat_room.participants.filter(id=self.user.id).exists()
        except ChatRoom.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_message(self, content, message_type, file_url):
        """Save message to database"""
        chat_room = ChatRoom.objects.get(id=self.chat_room_id)
        return Message.objects.create(
            chat_room=chat_room,
            sender=self.user,
            content=content,
            message_type=message_type,
            file_url=file_url
        )
    
    @database_sync_to_async
    def create_notifications(self, message):
        """Create notifications for other participants"""
        chat_room = message.chat_room
        other_participants = chat_room.participants.exclude(id=self.user.id)
        
        notifications = []
        for participant in other_participants:
            notification = ChatNotification(
                user=participant,
                chat_room=chat_room,
                message=message
            )
            notifications.append(notification)
        
        ChatNotification.objects.bulk_create(notifications)
    
    @database_sync_to_async
    def mark_messages_as_read(self, message_ids):
        """Mark messages as read"""
        messages = Message.objects.filter(
            id__in=message_ids,
            chat_room_id=self.chat_room_id,
            sender__in=self.get_chat_room_participants().exclude(
                id=self.user.id
            )
        )
        
        for message in messages:
            message.mark_as_read(self.user)
    
    @database_sync_to_async
    def get_chat_room_participants(self):
        """Get chat room participants"""
        chat_room = ChatRoom.objects.get(id=self.chat_room_id)
        return chat_room.participants 


class CallConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for VoIP call signaling (WebRTC)
    """
    async def connect(self):
        self.user = self.scope["user"]
        self.user_id = str(self.user.id)
        if not self.user.is_authenticated:
            await self.close()
            return
        self.room_group_name = f"call_{self.user_id}"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "message": "Connected to call signaling channel",
            "user_id": self.user_id
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get("type")
            # Relay signaling messages to the callee/caller
            if msg_type in ["call_offer", "call_answer", "ice_candidate", "call_status"]:
                target_id = data.get("target_id")
                if not target_id:
                    await self.send(text_data=json.dumps({
                        "type": "error",
                        "message": "Missing target_id for signaling message"
                    }))
                    return
                await self.channel_layer.group_send(
                    f"call_{target_id}",
                    {
                        "type": "signaling.message",
                        "from_id": self.user_id,
                        "payload": data
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": str(e)
            }))

    async def signaling_message(self, event):
        # Relay the signaling message to the WebSocket client
        payload = event["payload"]
        payload["from_id"] = event["from_id"]
        await self.send(text_data=json.dumps(payload)) 