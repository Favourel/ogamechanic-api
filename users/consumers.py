import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Notification

logger = logging.getLogger(__name__)

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
        logger.info(f"User {self.user.id} connected to NotificationConsumer")

        # Send unread notifications count
        unread_count = await self.get_unread_notifications_count()
        await self.send(text_data=json.dumps({
            'type': 'notification.count',
            'unread_count': unread_count
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave notification group if it was joined
        if hasattr(self, 'notification_group_name'):
            await self.channel_layer.group_discard(
                self.notification_group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.id} disconnected from NotificationConsumer")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'mark_read':
                notification_id = data.get('notification_id')
                if await self.mark_notification_read(notification_id):
                    await self.send_notification_count_update()

            elif message_type == 'mark_all_read':
                if await self.mark_all_notifications_read():
                    await self.send_notification_count_update()

            elif message_type == 'get_notifications':
                page = data.get('page', 1)
                limit = data.get('limit', 10)
                category = data.get('category')
                await self.send_notifications_page(page, limit, category)

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
        # Update unread count for all user's connected tabs
        await self.send_notification_count_update()

    async def notification_count_update(self, event):
        """Send notification count update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'notification.count_update',
            'unread_count': event['unread_count']
        }))

    @database_sync_to_async
    def get_unread_notifications_count(self, category=None):
        """Get count of unread notifications for user, active role, and category"""
        from django.db.models import Q
        active_role = getattr(self.user, 'active_role', None)
        
        queryset = Notification.objects.filter(
            user=self.user,
            is_read=False
        )
        
        if active_role:
            queryset = queryset.filter(
                Q(role=active_role) | Q(role__isnull=True)
            )
            
            # Defensive fix for legacy untagged notifications
            if active_role.name == 'primary_user':
                queryset = queryset.exclude(
                    Q(role__isnull=True) & 
                    (
                        Q(title__icontains='Repair') | 
                        Q(message__icontains='Repair') |
                        Q(title__icontains='Ride') |
                        Q(message__icontains='Ride')
                    )
                )

        if category:
            if category == "admin_chat":
                queryset = queryset.filter(notification_type="support_chat")
            elif category == "user_chat":
                queryset = queryset.filter(Q(notification_type="chat") | Q(notification_type="user_chat"))
            elif category == "general":
                queryset = queryset.exclude(notification_type__in=["support_chat", "chat", "user_chat"])
            
        return queryset.count()

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark a specific notification as read if it belongs to user and active role"""
        from django.db.models import Q
        active_role = getattr(self.user, 'active_role', None)
        try:
            queryset = Notification.objects.filter(user=self.user)
            if active_role:
                queryset = queryset.filter(
                    Q(role=active_role) | Q(role__isnull=True)
                )
            
            notification = queryset.get(id=notification_id)
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False

    @database_sync_to_async
    def mark_all_notifications_read(self):
        """Mark all user notifications as read for current active role"""
        from django.utils import timezone
        from django.db.models import Q
        
        active_role = getattr(self.user, 'active_role', None)
        
        queryset = Notification.objects.filter(
            user=self.user,
            is_read=False
        )
        
        if active_role:
            queryset = queryset.filter(
                Q(role=active_role) | Q(role__isnull=True)
            )
            
            # Defensive fix for legacy untagged notifications
            if active_role.name == 'primary_user':
                queryset = queryset.exclude(
                    Q(role__isnull=True) & 
                    (
                        Q(title__icontains='Repair') | 
                        Q(message__icontains='Repair') |
                        Q(title__icontains='Ride') |
                        Q(message__icontains='Ride')
                    )
                )
            
        updated_count = queryset.update(is_read=True, read_at=timezone.now())
        return updated_count

    @database_sync_to_async
    def get_notifications_page(self, page, limit, category=None):
        """Get paginated notifications for user, active role, and category"""
        from django.core.paginator import Paginator
        from django.db.models import Q
        
        active_role = getattr(self.user, 'active_role', None)
        
        notifications = Notification.objects.filter(
            user=self.user
        )
        
        if active_role:
            notifications = notifications.filter(
                Q(role=active_role) | Q(role__isnull=True)
            )
            
            # Defensive fix for legacy untagged notifications
            if active_role.name == 'primary_user':
                notifications = notifications.exclude(
                    Q(role__isnull=True) & 
                    (
                        Q(title__icontains='Repair') | 
                        Q(message__icontains='Repair') |
                        Q(title__icontains='Ride') |
                        Q(message__icontains='Ride')
                    )
                )

        if category:
            if category == "admin_chat":
                notifications = notifications.filter(notification_type="support_chat")
            elif category == "user_chat":
                notifications = notifications.filter(Q(notification_type="chat") | Q(notification_type="user_chat"))
            elif category == "general":
                notifications = notifications.exclude(notification_type__in=["support_chat", "chat", "user_chat"])
            
        notifications = notifications.order_by('-created_at')

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
                    'created_at': notification.created_at.isoformat() if notification.created_at else None,
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

    async def send_notifications_page(self, page, limit, category=None):
        """Send paginated notifications to WebSocket"""
        notifications_data = await self.get_notifications_page(page, limit, category)
        await self.send(text_data=json.dumps({
            'type': 'notifications.page',
            'data': notifications_data
        }))

    async def send_notification_count_update(self, category=None):
        """Send updated notification count to WebSocket"""
        unread_count = await self.get_unread_notifications_count(category)
        await self.channel_layer.group_send(
            self.notification_group_name,
            {
                'type': 'notification.count_update',
                'unread_count': unread_count,
                'category': category
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
        logger.info(f"Admin {self.user.id} connected to AdminNotificationConsumer")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave admin notification group if it was joined
        if hasattr(self, 'admin_group_name'):
            await self.channel_layer.group_discard(
                self.admin_group_name,
                self.channel_name
            )
            logger.info(f"Admin {self.user.id} disconnected from AdminNotificationConsumer")

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

    async def send_notification_to_role(self, role_name, message, notification_type):
        """Send notification to users with specific role"""
        from .services import NotificationService
        from .models import Role

        # Get users with specific role
        users = await self.get_users_by_role(role_name)
        
        # Get role object
        @database_sync_to_async
        def get_role_obj(name):
            try:
                return Role.objects.get(name=name)
            except Role.DoesNotExist:
                return None
        
        role_obj = await get_role_obj(role_name)

        # Create notifications for users with role
        for user in users:
            NotificationService.create_notification(
                user=user,
                title=f"Message for {role_name.title()}s",
                message=message,
                notification_type=notification_type,
                role=role_obj
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
