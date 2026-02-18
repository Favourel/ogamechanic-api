import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Get user from scope (assuming authentication middleware)
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Join user's notification group
        self.notification_group_name = f"notifications_{self.user.id}"
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )

        await self.accept()

        # Send unread notifications count
        unread_count = await self.get_unread_notifications_count()
        await self.send(text_data=json.dumps({
            'type': 'notification.count',
            'unread_count': unread_count
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave notification group
        await self.channel_layer.group_discard(
            self.notification_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'mark_read':
                notification_id = data.get('notification_id')
                await self.mark_notification_read(notification_id)

            elif message_type == 'mark_all_read':
                await self.mark_all_notifications_read()

            elif message_type == 'get_notifications':
                page = data.get('page', 1)
                limit = data.get('limit', 10)
                await self.send_notifications_page(page, limit)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def notification_message(self, event):
        """Send notification message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'notification.new',
            'notification': event['message']
        }))

    async def notification_count_update(self, event):
        """Send notification count update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'notification.count_update',
            'unread_count': event['unread_count']
        }))

    @database_sync_to_async
    def get_unread_notifications_count(self):
        """Get count of unread notifications for user"""
        return Notification.objects.filter(
            user=self.user,
            is_read=False
        ).count()

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark a specific notification as read"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=self.user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False

    @database_sync_to_async
    def mark_all_notifications_read(self):
        """Mark all user notifications as read"""
        from django.utils import timezone
        updated_count = Notification.objects.filter(
            user=self.user,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return updated_count

    @database_sync_to_async
    def get_notifications_page(self, page, limit):
        """Get paginated notifications for user"""
        from django.core.paginator import Paginator

        notifications = Notification.objects.filter(
            user=self.user
        ).order_by('-created_at')

        paginator = Paginator(notifications, limit)
        page_obj = paginator.get_page(page)

        return {
            'notifications': [
                {
                    'id': str(notification.id),
                    'title': notification.title,
                    'message': notification.message,
                    'notification_type': notification.notification_type,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat(),
                    'read_at': notification.read_at.isoformat() if notification.read_at else None
                }
                for notification in page_obj
            ],
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        }

    async def send_notifications_page(self, page, limit):
        """Send paginated notifications to WebSocket"""
        notifications_data = await self.get_notifications_page(page, limit)
        await self.send(text_data=json.dumps({
            'type': 'notifications.page',
            'data': notifications_data
        }))

    async def send_notification_count_update(self):
        """Send updated notification count to WebSocket"""
        unread_count = await self.get_unread_notifications_count()
        await self.channel_layer.group_send(
            self.notification_group_name,
            {
                'type': 'notification.count_update',
                'unread_count': unread_count
            }
        )


class NotificationGroupConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for group notifications (admin, broadcast)
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Get user from scope
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Check if user has admin permissions for group notifications
        if not self.user.is_staff:
            await self.close()
            return

        # Join admin notification group
        self.admin_group_name = "admin_notifications"
        await self.channel_layer.group_add(
            self.admin_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        await self.channel_layer.group_discard(
            self.admin_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'broadcast':
                message = data.get('message', '')
                notification_type = data.get('notification_type', 'info')
                await self.broadcast_notification(message, notification_type)

            elif message_type == 'send_to_role':
                role = data.get('role')
                message = data.get('message', '')
                notification_type = data.get('notification_type', 'info')
                await self.send_notification_to_role(role, message, notification_type)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def broadcast_notification(self, message, notification_type):
        """Broadcast notification to all users"""
        from .services import NotificationService

        # Get all active users
        users = await self.get_all_active_users()

        # Create notifications for all users
        for user in users:
            NotificationService.create_notification(
                user=user,
                title="System Announcement",
                message=message,
                notification_type=notification_type
            )

        await self.send(text_data=json.dumps({
            'type': 'broadcast_sent',
            'message': f'Notification sent to {len(users)} users'
        }))

    async def send_notification_to_role(self, role, message, notification_type):
        """Send notification to users with specific role"""
        from .services import NotificationService

        # Get users with specific role
        users = await self.get_users_by_role(role)

        # Create notifications for users with role
        for user in users:
            NotificationService.create_notification(
                user=user,
                title=f"Message for {role.title()}s",
                message=message,
                notification_type=notification_type
            )

        await self.send(text_data=json.dumps({
            'type': 'role_notification_sent',
            'message': f'Notification sent to {len(users)} {role}s'
        }))

    @database_sync_to_async
    def get_all_active_users(self):
        """Get all active users"""
        return list(User.objects.filter(is_active=True))

    @database_sync_to_async
    def get_users_by_role(self, role):
        """Get users with specific role"""
        return list(User.objects.filter(
            roles__name=role,
            is_active=True
        ))
