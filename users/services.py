from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from celery import shared_task
from .models import Notification, User, Device


@shared_task
def send_account_status_email(user_id, action, reason=None):
    """Send email notification about account status change."""
    try:
        user = User.objects.get(id=user_id)
        if action == 'deactivated':
            subject = "Your OGAMECHANIC Account Has Been Deactivated"
            template = 'emails/account_deactivated.html'
        elif action == 'activated':
            subject = "Your OGAMECHANIC Account Has Been Activated"
            template = 'emails/account_activated.html'
        else:
            return

        context = {
            'user': user,
            'reason': reason,
            'timestamp': timezone.now()
        }

        html_content = render_to_string(template, context)
        text_content = strip_tags(html_content)

        send_mail(
            subject=subject,
            message=text_content,
            html_message=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except User.DoesNotExist:
        print(f"User with id {user_id} not found.")
    except Exception as e:
        print(f"Failed to send account status email: {e}")


class NotificationService:
    """
    Service class for handling all types of notifications
    """
    
    @staticmethod
    def create_notification(user, title, message, notification_type='info', 
                          related_object=None, related_object_type=None,
                          role=None): # noqa
        """
        Create an in-app notification for a user.
        
        Args:
            user: User to receive the notification
            title: Notification title
            message: Notification message
            notification_type: Type of notification (info, warning, error, success)
            related_object: Related object (optional)
            related_object_type: Type of related object (optional)
            role: Role for which this notification is intended (optional)
                  If not provided, uses user's active_role
        """
        # Use provided role or fall back to user's active role
        if role is None and hasattr(user, 'active_role'):
            role = user.active_role
        
        notification = Notification.objects.create(
            user=user,
            role=role,
            title=title,
            message=message,
            notification_type=notification_type
        )
        
        # Send real-time notification if user is online
        if hasattr(NotificationService, 'send_realtime_notification'):
            try:
                NotificationService.send_realtime_notification(
                    user, notification
                )
            except Exception:
                pass  # Fail silently for real-time notifications
        
        # Send email notification if user has email notifications enabled
        if (hasattr(user, 'email_notifications') and
                user.email_notifications and
                hasattr(NotificationService, 'send_email_notification')):
            try:
                NotificationService.send_email_notification.delay(
                    user.id, title, message, notification_type
                )
            except Exception:
                pass  # Fail silently for email notifications
        
        # Send push notification if user has devices
        if hasattr(user, 'devices'):
            try:
                if user.devices.filter(is_active=True).exists():
                    if hasattr(NotificationService, 'send_push_notification'):
                        NotificationService.send_push_notification.delay(
                            user.id, title, message, notification_type
                        )
            except Exception:
                pass  # Fail silently for push notifications
        
        return notification
    
    @staticmethod
    def create_bulk_notifications(users, title, message,
                                notification_type='info', role=None): # noqa
        """
        Create notifications for multiple users.
        
        Args:
            users: List of users to receive notifications
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            role: Role for which notifications are intended (optional)
        """
        notifications = []
        for user in users:
            # Use provided role or fall back to user's active role
            user_role = role if role else getattr(user, 'active_role', None)
            
            notification = Notification.objects.create(
                user=user,
                role=user_role,
                title=title,
                message=message,
                notification_type=notification_type
            )
            notifications.append(notification)
        
        # Send bulk email notifications
        from users.services import send_bulk_email_notifications
        send_bulk_email_notifications.delay(
            [user.id for user in users], title, message, notification_type
        )
        
        # Send bulk push notifications
        from users.services import send_bulk_push_notifications
        send_bulk_push_notifications.delay(
            [user.id for user in users], title, message, notification_type
        )
        
        return notifications
    
    @staticmethod
    def send_realtime_notification(user, notification):
        """
        Send real-time notification via WebSocket
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"notifications_{user.id}",
                {
                    "type": "notification.message",
                    "message": {
                        "id": str(notification.id),
                        "title": notification.title,
                        "message": notification.message,
                        "notification_type": notification.notification_type,
                        "created_at": notification.created_at.isoformat(),
                        "is_read": notification.is_read
                    }
                }
            )
        except Exception as e:
            print(f"Failed to send real-time notification: {e}")
    
    @staticmethod
    def get_notification_template(notification_type, context=None):
        """
        Get email template for notification type
        """
        templates = {
            'order_status': 'emails/order_status_notification.html',
            'ride_status': 'emails/ride_status_notification.html',
            'courier_status': 'emails/courier_status_notification.html',
            'rental_status': 'emails/rental_status_notification.html',
            'repair_status': 'emails/repair_status_notification.html',
            'verification': 'emails/verification_notification.html',
            'payment': 'emails/payment_notification.html',
            'security': 'emails/security_notification.html',
            'info': 'emails/info_notification.html',
            'success': 'emails/success_notification.html',
            'warning': 'emails/warning_notification.html',
            'error': 'emails/error_notification.html',
        }
        
        return templates.get(notification_type, templates['info'])
    
    @staticmethod
    def get_email_subject(notification_type, title):
        """
        Get email subject based on notification type
        """
        subjects = {
            'order_status': f'Order Update: {title}',
            'ride_status': f'Ride Update: {title}',
            'courier_status': f'Delivery Update: {title}',
            'rental_status': f'Rental Update: {title}',
            'repair_status': f'Repair Update: {title}',
            'verification': f'Verification Update: {title}',
            'payment': f'Payment Update: {title}',
            'security': f'Security Alert: {title}',
            'info': f'Information: {title}',
            'success': f'Success: {title}',
            'warning': f'Warning: {title}',
            'error': f'Error: {title}',
        }
        
        return subjects.get(notification_type, f'Notification: {title}')


@shared_task
def send_email_notification(user_id, title, message, notification_type='info'): # noqa
    """
    Send email notification asynchronously
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Get email template
        template = NotificationService.get_notification_template(notification_type) # noqa
        context = {
            'user': user,
            'title': title,
            'message': message,
            'notification_type': notification_type,
            'timestamp': timezone.now()
        }
        
        # Render email content
        html_content = render_to_string(template, context)
        text_content = strip_tags(html_content)
        
        # Send email
        send_mail(
            subject=NotificationService.get_email_subject(notification_type, title), # noqa
            message=text_content,
            html_message=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        # Mark notification as sent
        user.notifications.filter(
            title=title, 
            message=message, 
            is_sent=False
        ).update(is_sent=True)
        
    except Exception as e:
        print(f"Failed to send email notification: {e}")


@shared_task
def send_bulk_email_notifications(user_ids, title, message, notification_type='info'): # noqa
    """
    Send bulk email notifications asynchronously
    """
    try:
        users = User.objects.filter(id__in=user_ids, email_notifications=True)
        
        # Get email template
        template = NotificationService.get_notification_template(notification_type) # noqa
        
        for user in users:
            context = {
                'user': user,
                'title': title,
                'message': message,
                'notification_type': notification_type,
                'timestamp': timezone.now()
            }
            
            # Render email content
            html_content = render_to_string(template, context)
            text_content = strip_tags(html_content)
            
            # Send email
            send_mail(
                subject=NotificationService.get_email_subject(notification_type, title), # noqa
                message=text_content,
                html_message=html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        
        # Mark notifications as sent
        Notification.objects.filter(
            user__id__in=user_ids,
            title=title,
            message=message,
            is_sent=False
        ).update(is_sent=True)
        
    except Exception as e:
        print(f"Failed to send bulk email notifications: {e}")


@shared_task
def send_push_notification(user_id, title, message, notification_type='info'):
    """
    Send push notification asynchronously
    """
    try:
        user = User.objects.get(id=user_id)
        devices = user.devices.filter(is_active=True)
        
        if not devices.exists():
            return
        
        # Import FCM here to avoid circular imports
        from firebase_admin import messaging
        
        # Prepare notification data
        notification_data = {
            'title': title,
            'body': message,
            'notification_type': notification_type,
            'timestamp': str(timezone.now()),
            'click_action': 'FLUTTER_NOTIFICATION_CLICK'
        }
        
        # Send to all user devices
        for device in devices:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=message
                    ),
                    data=notification_data,
                    token=device.fcm_token,
                )
                
                messaging.send(message)
                
            except Exception as e:
                print(f"Failed to send push notification to device {device.id}: {e}") # noqa
                # Mark device as inactive if FCM token is invalid
                device.is_active = False
                device.save()
        
    except Exception as e:
        print(f"Failed to send push notification: {e}")


@shared_task
def send_bulk_push_notifications(user_ids, title, message, notification_type='info'): # noqa
    """
    Send bulk push notifications asynchronously
    """
    try:
        users = User.objects.filter(id__in=user_ids)
        
        # Import FCM here to avoid circular imports
        from firebase_admin import messaging
        
        # Prepare notification data
        notification_data = {
            'title': title,
            'body': message,
            'notification_type': notification_type,
            'timestamp': str(timezone.now()),
            'click_action': 'FLUTTER_NOTIFICATION_CLICK'
        }
        
        # Group devices by FCM token
        tokens = []
        for user in users:
            user_tokens = user.devices.filter(is_active=True).values_list('fcm_token', flat=True) # noqa
            tokens.extend(user_tokens)
        
        if not tokens:
            return
        
        # Send to all devices
        try:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=message
                ),
                data=notification_data,
                tokens=tokens,
            )
            
            response = messaging.send_multicast(message)
            
            # Handle failed tokens
            if response.failure_count > 0:
                failed_tokens = []
                for i, result in enumerate(response.responses):
                    if not result.success:
                        failed_tokens.append(tokens[i])
                
                # Mark failed devices as inactive
                Device.objects.filter(fcm_token__in=failed_tokens).update(is_active=False) # noqa
        
        except Exception as e:
            print(f"Failed to send bulk push notifications: {e}")
        
    except Exception as e:
        print(f"Failed to send bulk push notifications: {e}")


@shared_task
def send_daily_digest():
    """
    Send daily digest notifications to users who prefer daily digest
    """
    try:
        users = User.objects.filter(
            notification_frequency='daily',
            in_app_notifications=True
        )
        
        for user in users:
            # Get unread notifications from the last 24 hours
            yesterday = timezone.now() - timezone.timedelta(days=1)
            notifications = user.notifications.filter(
                created_at__gte=yesterday,
                is_read=False
            ).order_by('-created_at')
            
            if notifications.exists():
                # Create digest notification
                NotificationService.create_notification(
                    user=user,
                    title="Daily Digest",
                    message=f"You have {notifications.count()} unread notifications from the last 24 hours.", # noqa
                    notification_type='info'
                )
        
    except Exception as e:
        print(f"Failed to send daily digest: {e}")


@shared_task
def send_weekly_digest():
    """
    Send weekly digest notifications to users who prefer weekly digest
    """
    try:
        users = User.objects.filter(
            notification_frequency='weekly',
            in_app_notifications=True
        )
        
        for user in users:
            # Get unread notifications from the last 7 days
            week_ago = timezone.now() - timezone.timedelta(days=7)
            notifications = user.notifications.filter(
                created_at__gte=week_ago,
                is_read=False
            ).order_by('-created_at')
            
            if notifications.exists():
                # Create digest notification
                NotificationService.create_notification(
                    user=user,
                    title="Weekly Digest",
                    message=f"You have {notifications.count()} unread notifications from the last week.", # noqa
                    notification_type='info'
                )
        
    except Exception as e:
        print(f"Failed to send weekly digest: {e}")


# Business-specific notification methods
class OrderNotificationService:
    """Service for order-related notifications"""
    
    @staticmethod
    def order_created(order):
        """Notify customer when order is created"""
        NotificationService.create_notification(
            user=order.customer,
            title="Order Created",
            message=f"Your order #{order.id} has been created successfully.",
            notification_type='success'
        )
    
    @staticmethod
    def order_status_updated(order):
        """Notify customer when order status changes"""
        status_messages = {
            'paid': "Your order has been paid successfully.",
            'shipped': "Your order has been shipped.",
            'completed': "Your order has been completed.",
            'cancelled': "Your order has been cancelled."
        }
        
        message = status_messages.get(order.status, f"Your order status has been updated to {order.status}.") # noqa
        
        NotificationService.create_notification(
            user=order.customer,
            title=f"Order {order.status.title()}",
            message=message,
            notification_type='order_status'
        )
    
    @staticmethod
    def order_review_received(order, review):
        """Notify merchant when order receives a review"""
        NotificationService.create_notification(
            user=order.items.first().product.merchant,
            title="New Review Received",
            message=f"You received a {review.rating}-star review for order #{order.id}.", # noqa
            notification_type='info'
        )


class RideNotificationService:
    """Service for ride-related notifications"""
    
    @staticmethod
    def ride_requested(ride):
        """Notify driver when ride is requested"""
        NotificationService.create_notification(
            user=ride.driver,
            title="New Ride Request",
            message=f"You have a new ride request from {ride.customer.email}.",
            notification_type='info'
        )
    
    @staticmethod
    def ride_status_updated(ride):
        """Notify customer when ride status changes"""
        status_messages = {
            'accepted': "Your ride request has been accepted.",
            'active': "Your ride has started.",
            'completed': "Your ride has been completed.",
            'cancelled': "Your ride has been cancelled."
        }
        
        message = status_messages.get(ride.status, f"Your ride status has been updated to {ride.status}.") # noqa
        
        NotificationService.create_notification(
            user=ride.customer,
            title=f"Ride {ride.status.title()}",
            message=message,
            notification_type='ride_status'
        )
    
    @staticmethod
    def driver_location_updated(ride):
        """Notify customer when driver location is updated"""
        NotificationService.create_notification(
            user=ride.customer,
            title="Driver Location Updated",
            message="Your driver's location has been updated.",
            notification_type='info'
        )


class RentalNotificationService:
    """Service for rental-related notifications"""
    
    @staticmethod
    def rental_booked(rental):
        """Notify customer when rental is booked"""
        NotificationService.create_notification(
            user=rental.customer,
            title="Rental Booked",
            message=f"Your rental booking #{rental.booking_reference} has been created successfully.", # noqa
            notification_type='success'
        )
    
    @staticmethod
    def rental_status_updated(rental):
        """Notify customer when rental status changes"""
        status_messages = {
            'confirmed': "Your rental booking has been confirmed.",
            'active': "Your rental period has started.",
            'completed': "Your rental has been completed.",
            'cancelled': "Your rental has been cancelled."
        }
        
        message = status_messages.get(rental.status, f"Your rental status has been updated to {rental.status}.") # noqa
        
        NotificationService.create_notification(
            user=rental.customer,
            title=f"Rental {rental.status.title()}",
            message=message,
            notification_type='rental_status'
        )


class MechanicNotificationService:
    """Service for mechanic-related notifications"""
    
    @staticmethod
    def repair_requested(repair):
        """Notify mechanic when repair is requested"""
        NotificationService.create_notification(
            user=repair.mechanic,
            title="New Repair Request",
            message=f"You have a new repair request from {repair.customer.email}.", # noqa
            notification_type='info'
        )
    
    @staticmethod
    def repair_status_updated(repair):
        """Notify customer when repair status changes"""
        status_messages = {
            'accepted': "Your repair request has been accepted.",
            'in_progress': "Your repair is in progress.",
            'completed': "Your repair has been completed.",
            'cancelled': "Your repair has been cancelled."
        }
        
        message = status_messages.get(repair.status, f"Your repair status has been updated to {repair.status}.") # noqa
        
        NotificationService.create_notification(
            user=repair.customer,
            title=f"Repair {repair.status.title()}",
            message=message,
            notification_type='repair_status'
        )


class VerificationNotificationService:
    """Service for verification-related notifications"""
    
    @staticmethod
    def profile_approved(user, profile_type):
        """Notify user when profile is approved"""
        NotificationService.create_notification(
            user=user,
            title="Profile Approved",
            message=f"Your {profile_type} profile has been approved. You can now use all features.", # noqa
            notification_type='success'
        )
    
    @staticmethod
    def profile_rejected(user, profile_type, reason=""):
        """Notify user when profile is rejected"""
        message = f"Your {profile_type} profile has been rejected."
        if reason:
            message += f" Reason: {reason}"
        
        NotificationService.create_notification(
            user=user,
            title="Profile Rejected",
            message=message,
            notification_type='warning'
        ) 