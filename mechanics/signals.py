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

        # Base serialized data (safe for mechanics and tracking rooms, without otp_code)
        base_serializer = RepairRequestSerializer(instance, context={})
        base_data = base_serializer.data

        group_name = f"repair_request_{instance.id}"

        logger.info(f"Broadcasting RepairRequest {instance.id} update via WebSocket to group {group_name}")

        # 1. Broadcast to repair request tracking room
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "repair_request.update",
                "repair_request": base_data,
                "otp_code": instance.otp_code if instance.otp_code else None,
                "customer_id": str(instance.customer_id) if instance.customer_id else None
            }
        )

        # 2. Broadcast to customer's personal notification stream (with otp_code if available)
        if instance.customer_id:
            customer_serializer = RepairRequestSerializer(
                instance,
                context={'user': instance.customer}
            )
            async_to_sync(channel_layer.group_send)(
                f"notifications_{instance.customer_id}",
                {
                    "type": "repair_request.update",
                    "repair_request": customer_serializer.data
                }
            )

        # 3. Broadcast to assigned mechanic's personal notification stream
        if instance.mechanic_id:
            async_to_sync(channel_layer.group_send)(
                f"notifications_{instance.mechanic_id}",
                {
                    "type": "repair_request.update",
                    "repair_request": base_data
                }
            )
    except Exception as e:
        logger.error(f"Failed to send repair request WebSocket update: {e}", exc_info=True)

