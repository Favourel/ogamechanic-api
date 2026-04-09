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


class SupportChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time support chat (per conversation).

    Connect: ws/support/chat/<conversation_id>/?token=<JWT>
    """

    async def connect(self):
        self.user = self.scope.get("user")
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Verify the user has access to this conversation
        has_access = await self.check_access()
        if not has_access:
            await self.close()
            return

        self.room_group_name = f"support_chat_{self.conversation_id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.accept()

        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "message": "Connected to support chat",
            "conversation_id": self.conversation_id,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get("type", "chat_message")

            if msg_type == "chat_message":
                await self.handle_chat_message(data)
            elif msg_type == "typing":
                await self.handle_typing(data)
            elif msg_type == "read_messages":
                await self.handle_read_messages(data)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid JSON format",
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": str(e),
            }))

    # ── Message handlers ────────────────────────────────────────────

    async def handle_chat_message(self, data):
        content = data.get("content", "").strip()
        message_type = data.get("message_type", "text")
        file_url = data.get("file_url")

        if not content and message_type == "text":
            return

        message_data = await self.save_message(content, message_type, file_url)

        # Broadcast to conversation group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message_data,
            },
        )

        # Notify admin dashboard of new message
        await self.channel_layer.group_send(
            "support_admin_dashboard",
            {
                "type": "conversation_updated",
                "conversation_id": self.conversation_id,
                "message": message_data,
            },
        )

        # Trigger push notification for offline recipient
        await self.trigger_push_notification(message_data)

    async def handle_typing(self, data):
        is_typing = data.get("is_typing", False)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_typing",
                "user_id": str(self.user.id),
                "user_name": self.user.first_name or self.user.email,
                "is_typing": is_typing,
            },
        )

    async def handle_read_messages(self, data):
        message_ids = data.get("message_ids", [])
        if not message_ids:
            return

        await self.mark_messages_read(message_ids)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "messages_read",
                "user_id": str(self.user.id),
                "message_ids": message_ids,
            },
        )

    # ── Event senders (called by channel layer) ─────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "message": event["message"],
        }))

    async def user_typing(self, event):
        # Don't send typing indicator back to the sender
        if event["user_id"] != str(self.user.id):
            await self.send(text_data=json.dumps({
                "type": "user_typing",
                "user_id": event["user_id"],
                "user_name": event["user_name"],
                "is_typing": event["is_typing"],
            }))

    async def messages_read(self, event):
        await self.send(text_data=json.dumps({
            "type": "messages_read",
            "user_id": event["user_id"],
            "message_ids": event["message_ids"],
        }))

    async def conversation_status_changed(self, event):
        await self.send(text_data=json.dumps({
            "type": "conversation_status_changed",
            "status": event["status"],
            "updated_by": event["updated_by"],
        }))

    # ── Database helpers ────────────────────────────────────────────

    @database_sync_to_async
    def check_access(self):
        from .models import SupportConversation

        try:
            conv = SupportConversation.objects.get(id=self.conversation_id)
            # Customer can access their own conversation
            if conv.customer_id == self.user.id:
                return True
            # Staff/admin can access any conversation
            if self.user.is_staff:
                return True
            return False
        except SupportConversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, content, message_type, file_url):
        from .models import SupportConversation, SupportMessage

        conversation = SupportConversation.objects.get(id=self.conversation_id)

        # If an admin sends the first reply, assign themselves
        if (
            self.user.is_staff
            and not conversation.assigned_admin
            and conversation.status == "open"
        ):
            conversation.assigned_admin = self.user
            conversation.status = "in_progress"
            conversation.save(update_fields=["assigned_admin", "status", "updated_at"])

        msg = SupportMessage.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            message_type=message_type,
        )

        # Handle file attachment: save the file_url to the file_attachment field
        if file_url and message_type in ("image", "file"):
            import base64
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage
            from urllib.parse import urlparse
            import os

            if file_url.startswith("data:"):
                # Base64-encoded data sent directly over WebSocket
                # Format: data:image/png;base64,iVBOR...
                try:
                    header, encoded = file_url.split(",", 1)
                    # Extract extension from MIME type (e.g., "image/png" -> "png")
                    mime_type = header.split(":")[1].split(";")[0]
                    ext = mime_type.split("/")[1] if "/" in mime_type else "bin"
                    file_data = base64.b64decode(encoded)
                    file_name = f"support_attachments/{conversation.id}/{msg.id}.{ext}"
                    saved_path = default_storage.save(file_name, ContentFile(file_data))
                    msg.file_attachment = saved_path
                    msg.save(update_fields=["file_attachment"])
                    file_url = default_storage.url(saved_path)
                except Exception:
                    pass  # If base64 parsing fails, keep file_url as-is
            else:
                # file_url is a URL from a prior REST upload (/support/upload/)
                # Extract the relative storage path from the URL
                parsed = urlparse(file_url)
                relative_path = parsed.path
                # Strip leading /media/ prefix if present
                if relative_path.startswith("/media/"):
                    relative_path = relative_path[len("/media/"):]
                elif relative_path.startswith("/"):
                    relative_path = relative_path[1:]

                # Check if this file already exists in storage
                if default_storage.exists(relative_path):
                    msg.file_attachment = relative_path
                    msg.save(update_fields=["file_attachment"])

        # Build the absolute file URL for the response
        actual_file_url = None
        if msg.file_attachment:
            actual_file_url = msg.file_attachment.url
        elif file_url:
            actual_file_url = file_url

        # Touch conversation's updated_at
        conversation.save(update_fields=["updated_at"])

        return {
            "id": str(msg.id),
            "content": msg.content,
            "message_type": msg.message_type,
            "file_url": actual_file_url,
            "sender": {
                "id": str(msg.sender.id),
                "email": msg.sender.email,
                "first_name": msg.sender.first_name,
                "last_name": msg.sender.last_name,
                "is_staff": msg.sender.is_staff,
            },
            "is_read": msg.is_read,
            "created_at": msg.created_at.isoformat(),
            "conversation_id": str(conversation.id),
        }

    @database_sync_to_async
    def mark_messages_read(self, message_ids):
        from .models import SupportMessage
        from django.utils import timezone as tz

        SupportMessage.objects.filter(
            id__in=message_ids,
            conversation_id=self.conversation_id,
            is_read=False,
        ).exclude(sender=self.user).update(
            is_read=True,
            read_at=tz.now(),
        )

    @database_sync_to_async
    def trigger_push_notification(self, message_data):
        """Queue a Celery task for push notification."""
        from .tasks import send_support_push_notification

        send_support_push_notification.delay(
            conversation_id=str(self.conversation_id),
            sender_id=str(self.user.id),
            message_preview=message_data["content"][:100],
        )


class AdminDashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for the admin support dashboard.
    Admins receive real-time updates about all support conversations.

    Connect: ws/support/dashboard/?token=<JWT>
    """

    async def connect(self):
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated or not self.user.is_staff:
            await self.close()
            return

        self.dashboard_group = "support_admin_dashboard"

        await self.channel_layer.group_add(
            self.dashboard_group,
            self.channel_name,
        )
        await self.accept()

        # Send initial dashboard data
        dashboard_data = await self.get_dashboard_summary()
        await self.send(text_data=json.dumps({
            "type": "dashboard_init",
            "data": dashboard_data,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "dashboard_group"):
            await self.channel_layer.group_discard(
                self.dashboard_group,
                self.channel_name,
            )

    async def receive(self, text_data):
        """Handle admin actions from the dashboard."""
        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            if msg_type == "assign_conversation":
                await self.handle_assign(data)
            elif msg_type == "update_status":
                await self.handle_status_update(data)
            elif msg_type == "update_priority":
                await self.handle_priority_update(data)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid JSON format",
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": str(e),
            }))

    # ── Admin action handlers ───────────────────────────────────────

    async def handle_assign(self, data):
        conversation_id = data.get("conversation_id")
        admin_id = data.get("admin_id", str(self.user.id))
        result = await self.assign_admin(conversation_id, admin_id)

        if result:
            await self.channel_layer.group_send(
                self.dashboard_group,
                {
                    "type": "conversation_assigned",
                    "conversation_id": conversation_id,
                    "admin_id": admin_id,
                    "admin_name": result["admin_name"],
                },
            )

    async def handle_status_update(self, data):
        conversation_id = data.get("conversation_id")
        new_status = data.get("status")

        if new_status not in ("open", "in_progress", "resolved", "closed"):
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid status value.",
            }))
            return

        result = await self.update_conversation_status(
            conversation_id, new_status
        )

        if result:
            # Notify dashboard
            await self.channel_layer.group_send(
                self.dashboard_group,
                {
                    "type": "conversation_status_updated",
                    "conversation_id": conversation_id,
                    "status": new_status,
                    "updated_by": str(self.user.id),
                },
            )
            # Notify the conversation room
            await self.channel_layer.group_send(
                f"support_chat_{conversation_id}",
                {
                    "type": "conversation_status_changed",
                    "status": new_status,
                    "updated_by": str(self.user.id),
                },
            )

    async def handle_priority_update(self, data):
        conversation_id = data.get("conversation_id")
        new_priority = data.get("priority")

        if new_priority not in ("low", "medium", "high", "urgent"):
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid priority value.",
            }))
            return

        await self.update_conversation_priority(conversation_id, new_priority)

        await self.channel_layer.group_send(
            self.dashboard_group,
            {
                "type": "conversation_priority_updated",
                "conversation_id": conversation_id,
                "priority": new_priority,
            },
        )

    # ── Event senders (called by channel layer) ─────────────────────

    async def conversation_updated(self, event):
        """New message in a conversation."""
        await self.send(text_data=json.dumps({
            "type": "conversation_updated",
            "conversation_id": event["conversation_id"],
            "message": event["message"],
        }))

    async def new_conversation(self, event):
        """A new support conversation was created."""
        await self.send(text_data=json.dumps({
            "type": "new_conversation",
            "conversation": event["conversation"],
        }))

    async def conversation_assigned(self, event):
        await self.send(text_data=json.dumps({
            "type": "conversation_assigned",
            "conversation_id": event["conversation_id"],
            "admin_id": event["admin_id"],
            "admin_name": event["admin_name"],
        }))

    async def conversation_status_updated(self, event):
        await self.send(text_data=json.dumps({
            "type": "conversation_status_updated",
            "conversation_id": event["conversation_id"],
            "status": event["status"],
            "updated_by": event["updated_by"],
        }))

    async def conversation_priority_updated(self, event):
        await self.send(text_data=json.dumps({
            "type": "conversation_priority_updated",
            "conversation_id": event["conversation_id"],
            "priority": event["priority"],
        }))

    # ── Database helpers ────────────────────────────────────────────

    @database_sync_to_async
    def get_dashboard_summary(self):
        from .models import SupportConversation

        conversations = SupportConversation.objects.filter(
            status__in=["open", "in_progress"],
        ).select_related("customer", "assigned_admin").order_by("-updated_at")[:50]

        return {
            "open_count": SupportConversation.objects.filter(status="open").count(),
            "in_progress_count": SupportConversation.objects.filter(
                status="in_progress"
            ).count(),
            "conversations": [
                {
                    "id": str(c.id),
                    "subject": c.subject,
                    "status": c.status,
                    "priority": c.priority,
                    "customer": {
                        "id": str(c.customer.id),
                        "email": c.customer.email,
                        "first_name": c.customer.first_name,
                        "last_name": c.customer.last_name,
                    },
                    "assigned_admin": (
                        {
                            "id": str(c.assigned_admin.id),
                            "email": c.assigned_admin.email,
                            "first_name": c.assigned_admin.first_name,
                        }
                        if c.assigned_admin
                        else None
                    ),
                    "unread_count": c.unread_count_for(self.user),
                    "updated_at": c.updated_at.isoformat(),
                    "created_at": c.created_at.isoformat(),
                }
                for c in conversations
            ],
        }

    @database_sync_to_async
    def assign_admin(self, conversation_id, admin_id):
        from .models import SupportConversation

        try:
            conv = SupportConversation.objects.get(id=conversation_id)
            admin = User.objects.get(id=admin_id, is_staff=True)
            conv.assigned_admin = admin
            if conv.status == "open":
                conv.status = "in_progress"
            conv.save(update_fields=["assigned_admin", "status", "updated_at"])
            return {"admin_name": admin.first_name or admin.email}
        except (SupportConversation.DoesNotExist, User.DoesNotExist):
            return None

    @database_sync_to_async
    def update_conversation_status(self, conversation_id, new_status):
        from .models import SupportConversation
        from django.utils import timezone as tz

        try:
            conv = SupportConversation.objects.get(id=conversation_id)
            conv.status = new_status
            if new_status == "resolved":
                conv.resolved_at = tz.now()
                if not conv.assigned_admin:
                    conv.assigned_admin = self.user
            conv.save()
            return True
        except SupportConversation.DoesNotExist:
            return False

    @database_sync_to_async
    def update_conversation_priority(self, conversation_id, new_priority):
        from .models import SupportConversation

        SupportConversation.objects.filter(id=conversation_id).update(
            priority=new_priority
        )
