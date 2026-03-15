"""
Celery tasks for the support chat system.
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(
    name="communications.send_support_push_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_support_push_notification(
    self, conversation_id, sender_id, message_preview
):
    """
    Send a push notification to the other party in a support conversation
    when they are offline (not connected to the WebSocket).
    """
    from django.contrib.auth import get_user_model
    from communications.models import SupportConversation

    User = get_user_model()

    try:
        conversation = SupportConversation.objects.select_related(
            "customer", "assigned_admin"
        ).get(id=conversation_id)

        sender = User.objects.get(id=sender_id)

        # Determine the recipient
        if sender.is_staff:
            recipient = conversation.customer
        else:
            recipient = conversation.assigned_admin

        if not recipient:
            logger.info(
                f"No recipient for push notification "
                f"(conversation={conversation_id})"
            )
            return

        # Build notification payload
        sender_name = sender.first_name or sender.email
        title = f"Support: {conversation.subject}"
        body = f"{sender_name}: {message_preview}"

        # Attempt Firebase push notification
        try:
            from users.services import NotificationService
            NotificationService.create_notification(
                user=recipient,
                title=title,
                message=body,
                notification_type="support_chat",
            )
            logger.info(
                f"Push notification sent to {recipient.email} "
                f"for conversation {conversation_id}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to send push notification: {e}"
            )

    except SupportConversation.DoesNotExist:
        logger.error(
            f"Conversation {conversation_id} not found for push notification."
        )
    except Exception as exc:
        logger.error(
            f"Error sending push notification: {exc}", exc_info=True
        )
        raise self.retry(exc=exc)


@shared_task(name="communications.auto_close_stale_conversations")
def auto_close_stale_conversations():
    """
    Automatically close support conversations that have been resolved
    for more than 7 days, or open/in_progress with no activity for 30 days.
    """
    from communications.models import SupportConversation

    now = timezone.now()

    # Close resolved conversations older than 7 days
    resolved_cutoff = now - timedelta(days=7)
    resolved_closed = SupportConversation.objects.filter(
        status="resolved",
        resolved_at__lt=resolved_cutoff,
    ).update(status="closed")

    # Close stale open/in_progress conversations (no activity for 30 days)
    stale_cutoff = now - timedelta(days=30)
    stale_closed = SupportConversation.objects.filter(
        status__in=["open", "in_progress"],
        updated_at__lt=stale_cutoff,
    ).update(status="closed")

    logger.info(
        f"Auto-close: {resolved_closed} resolved → closed, "
        f"{stale_closed} stale → closed."
    )
