from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from mechanics.models import RepairRequest
from mechanics.serializers import RepairRequestSerializer
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=RepairRequest)
def send_repair_request_websocket_update(sender, instance, created, **kwargs):
    """
    Send real-time updates via WebSocket on any change to a RepairRequest.
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured. Skipping WebSocket update.")
            return

        # Serialize the repair request instance
        serializer = RepairRequestSerializer(instance, context={})
        data = serializer.data

        group_name = f"repair_request_{instance.id}"

        logger.info(f"Broadcasting RepairRequest {instance.id} update via WebSocket to group {group_name}")

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "repair_request.update",
                "repair_request": data
            }
        )
    except Exception as e:
        logger.error(f"Failed to send repair request WebSocket update: {e}", exc_info=True)
