from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import logging

from .models import RepairRequest
from users.models import MechanicProfile
from users.services import NotificationService
from ogamechanic.modules.location_service import LocationService

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def find_and_notify_mechanics_task(self, repair_request_id, radius_km=5.0):
    """
    Asynchronously find mechanics within the specified radius and send them
    requests.

    Args:
        repair_request_id: UUID of the RepairRequest instance
        radius_km: Radius in kilometers (default: 5.0)

    Returns:
        int: Number of mechanics found and notified
    """
    try:
        repair_request = RepairRequest.objects.get(id=repair_request_id)
    except RepairRequest.DoesNotExist as exc:
        logger.error(
            f"RepairRequest {repair_request_id} not found for "
            "mechanic notification"
        )
        # Use exponential backoff for retries
        retry_delay = 60 * (2 ** self.request.retries)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=retry_delay)
        return 0

    try:
        # Check if request already has a mechanic assigned
        if repair_request.mechanic:
            logger.info(
                f"RepairRequest {repair_request_id} already has a mechanic assigned"
            )
            return 0

        customer_lat = float(repair_request.service_latitude)
        customer_lon = float(repair_request.service_longitude)

        # Find all approved mechanics with location data
        mechanics = MechanicProfile.objects.filter(
            is_approved=True,
            latitude__isnull=False,
            longitude__isnull=False
        ).select_related('user')

        mechanics_within_radius = []

        for mechanic_profile in mechanics:
            mechanic_lat = float(mechanic_profile.latitude)
            mechanic_lon = float(mechanic_profile.longitude)

            # Calculate distance using haversine formula
            distance = LocationService.haversine_distance(
                customer_lat, customer_lon,
                mechanic_lat, mechanic_lon
            )

            if distance <= radius_km:
                mechanics_within_radius.append({
                    'mechanic': mechanic_profile.user,
                    'distance': distance
                })

        # Add mechanics to notified_mechanics and send notifications
        requests_created = 0
        notified_mechanic_ids = []

        for mechanic_data in mechanics_within_radius:
            mechanic = mechanic_data['mechanic']
            distance = mechanic_data['distance']

            # Add to notified mechanics
            notified_mechanic_ids.append(mechanic.id)

            # Send notification to mechanic
            try:
                NotificationService.create_notification(
                    user=mechanic,
                    title="New Repair Request Nearby",
                    message=(
                        f"You have a new repair request within {distance:.1f}km. "
                        f"Service: {repair_request.service_type} for "
                        f"{repair_request.vehicle_make} "
                        f"{repair_request.vehicle_model}. "
                        f"Click to view details."
                    ),
                    notification_type='info',
                    related_object=repair_request,
                    related_object_type='RepairRequest'
                )
                requests_created += 1
            except Exception as e:
                logger.error(
                    f"Failed to send notification to mechanic {mechanic.id}: {e}"
                )

        # Bulk add all notified mechanics
        if notified_mechanic_ids:
            repair_request.notified_mechanics.add(*notified_mechanic_ids)
            logger.info(
                f"Notified {requests_created} mechanics for "
                f"repair request {repair_request_id}"
            )
        return requests_created

    except Exception as exc:
        # Use exponential backoff for retries
        retry_delay = 60 * (2 ** self.request.retries)
        if self.request.retries < self.max_retries:
            logger.error(
                f"Error in find_and_notify_mechanics_task for {repair_request_id}, retrying in {retry_delay}s: {exc}"
            )
            raise self.retry(exc=exc, countdown=retry_delay)
        logger.error(
            f"Error in find_and_notify_mechanics_task for {repair_request_id}: {exc}"
        )
        return 0
