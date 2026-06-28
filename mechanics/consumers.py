import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from mechanics.models import RepairRequest

logger = logging.getLogger(__name__)
User = get_user_model()


class RepairRequestTrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time repair request tracking
    """

    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Get repair_id from URL parameters
        self.repair_id = self.scope['url_route']['kwargs']['repair_id']

        # Verify user has access to this repair request
        if not await self.can_access_repair():
            logger.warning(f"User {self.user.id} denied access to repair request {self.repair_id}")
            await self.close()
            return

        # Join repair request tracking group
        self.tracking_group_name = f"repair_request_{self.repair_id}"
        await self.channel_layer.group_add(
            self.tracking_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"User {self.user.id} connected to RepairRequestTrackingConsumer for repair request {self.repair_id}")

        # Send initial repair request data
        repair_data = await self.get_repair_request_data()
        if repair_data:
            await self.send(text_data=json.dumps({
                'type': 'repair_request.data',
                'repair_request': repair_data
            }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave tracking group if it was joined
        if hasattr(self, 'tracking_group_name'):
            await self.channel_layer.group_discard(
                self.tracking_group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.id} disconnected from RepairRequestTrackingConsumer for repair request {self.repair_id}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages (currently read-only tracking)"""
        pass

    async def repair_request_update(self, event):
        """Send repair request update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'repair_request.update',
            'repair_request': event['repair_request']
        }))

    @database_sync_to_async
    def can_access_repair(self):
        """Check if user can access this repair request"""
        try:
            repair = RepairRequest.objects.get(id=self.repair_id)
            if self.user.is_staff:
                return True
            if self.user.id == repair.customer_id:
                return True
            if repair.mechanic_id and self.user.id == repair.mechanic_id:
                return True
            if repair.notified_mechanics.filter(id=self.user.id).exists():
                return True
            return False
        except RepairRequest.DoesNotExist:
            return False

    @database_sync_to_async
    def get_repair_request_data(self):
        """Get serialized repair request data"""
        try:
            repair = RepairRequest.objects.get(id=self.repair_id)
            from mechanics.serializers import RepairRequestSerializer
            serializer = RepairRequestSerializer(repair, context={})
            return serializer.data
        except RepairRequest.DoesNotExist:
            return None
