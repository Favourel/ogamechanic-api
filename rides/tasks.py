from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from .models import Ride
from users.models import Device
from django.conf import settings
import logging
from celery import shared_task
from users.models import Notification
from django.utils import timezone
from datetime import timedelta

from firebase_admin import messaging, credentials
from firebase_admin import initialize_app
from django_redis import get_redis_connection
import json

logger = logging.getLogger(__name__)
User = get_user_model()


# Initialize Firebase app (called once in settings.py or at module level)
if not hasattr(settings, 'FIREBASE_INITIALIZED'):
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    initialize_app(cred)
    settings.FIREBASE_INITIALIZED = True


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def notify_drivers_task_fcm(self, ride_id, driver_ids, surge_multiplier):
    """Async task to notify drivers with surge-adjusted pricing via FCM."""
    try:
        ride = Ride.objects.get(id=ride_id)
        redis_conn = get_redis_connection("default")
        cache_key = f"ride:notification:{ride_id}"

        # Check if notification already sent (idempotency)
        if redis_conn.get(cache_key):
            logger.info(
                f"Notification for ride {ride_id} already sent"
            )
            return

        for driver_id in driver_ids:
            try:
                driver = User.objects.get(id=driver_id)
                devices = Device.objects.filter(user=driver, is_active=True)
                if not devices:
                    logger.warning(
                        f"No active devices for driver {driver_id}"
                    )
                    continue

                # Prepare notification payload
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title="New Ride Request",
                        body=(
                            f"Ride from {ride.pickup_address} for "
                            f"₦{ride.fare:.2f} (Surge: {surge_multiplier}x)"
                        ),
                    ),
                    data={
                        "ride_id": str(ride.id),
                        "pickup_address": ride.pickup_address,
                        "dropoff_address": ride.dropoff_address,
                        "suggested_fare": str(ride.suggested_fare),
                        "surge_multiplier": str(surge_multiplier),
                    },
                    tokens=[device.fcm_token for device in devices],
                )

                # Send notification
                response = messaging.send_multicast(message)
                success_count = response.success_count
                failure_count = response.failure_count

                if success_count > 0:
                    logger.info(
                        f"Sent notification to {success_count} devices for "
                        f"driver {driver_id}, ride {ride_id}"
                    )
                if failure_count > 0:
                    for idx, resp in enumerate(response.responses):
                        if resp.exception:
                            logger.error(
                                f"Failed to send to device "
                                f"{devices[idx].fcm_token}: {resp.exception}"
                            )

            except User.DoesNotExist:
                logger.error(
                    f"Driver {driver_id} not found for ride {ride_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to notify driver {driver_id} for ride "
                    f"{ride_id}: {e}"
                )

        # Cache notification to prevent duplicates
        redis_conn.setex(
            cache_key, 3600, json.dumps({"sent": True})
        )  # Cache for 1 hour

    except Ride.DoesNotExist:
        logger.error(
            f"Ride {ride_id} not found for driver notification"
        )
    except Exception as e:
        logger.error(
            f"Task failed for ride {ride_id}: {e}"
        )
        self.retry(countdown=60)  # Retry after 60 seconds


@shared_task
def notify_drivers_task(ride_id, driver_ids):
    """Async task to notify available drivers of a new ride."""
    try:
        # 'ride' is fetched for possible future use, but not used here.
        ride = Ride.objects.get(id=ride_id)
        for driver_id in driver_ids:
            try:
                driver = User.objects.get(id=driver_id)
                subject = "New Ride Request"
                message = (
                    f"Hello {driver.get_full_name() or driver.email},\n\n"
                    f"You have a new ride request\n\n (Ride Customer: {ride.customer}).\n\n" # noqa
                    f"Ride from {ride.pickup_address} for "
                    f"₦{ride.fare:.2f}"
                    "Please check your dashboard or app to accept or decline." # noqa
                )
                # Send email
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [driver.email],
                    fail_silently=False,
                )
                # Create notification object
                Notification.objects.create(
                    user=driver,
                    title="New Ride Request",
                    message=f"You have a new ride request (Ride Customer: {ride.customer}).", # noqa
                    notification_type="info",
                )
                # You can add push notification logic here if available
            except Exception as notify_exc:
                logger.error(
                    f"Failed to notify driver {driver_id} for ride {ride.id}: {notify_exc}" # noqa
                )
            logger.info(f"Notified driver {driver_id} for ride {ride.id}")
    except Ride.DoesNotExist:
        logger.error(f"Ride {ride_id} not found for driver notification")


@shared_task(bind=True, max_retries=3)
def notify_user_of_ride_status_task(self, user_id, ride_id, new_status):
    """
    Async task to notify a user (customer) of a ride status update.
    """
    try:
        user = User.objects.get(id=user_id)
        ride = Ride.objects.get(id=ride_id)
        status_display = new_status.replace("_", " ").capitalize()
        subject = f"Your Ride Status Update: {status_display}"
        message = (
            f"Hello {user.get_full_name() or user.email},\n\n"
            f"Your ride (ID: {ride.id}) status has been updated to '{status_display}'.\n\n" # noqa
            "Please check your dashboard or app for more details."
        )
        # Send email
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        # Create notification object
        Notification.objects.create(
            user=user,
            title="Ride Status Update",
            message=f"Your ride status has been updated to '{status_display}'.", # noqa
            notification_type="info",
        )
        # You can add push notification logic here if available
        logger.info(f"Notified user {user.id} of ride {ride.id} status update to {new_status}") # noqa
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for ride status notification")
    except Ride.DoesNotExist:
        logger.error(f"Ride {ride_id} not found for user status notification")
    except Exception as e:
        logger.error(f"Task failed for user {user_id}, ride {ride_id}: {e}")
        self.retry(countdown=60)


@shared_task
def delete_expired_pending_rides():
    """
    Delete initiated rides that have lasted for more than 30 minutes.
    """
    threshold_time = timezone.now() - timedelta(minutes=30)
    expired_rides = Ride.objects.filter(
        status="initiated", requested_at__lt=threshold_time
    )
    count = expired_rides.count()
    expired_rides.delete()
    logger.info(f"Deleted {count} initiated rides older than 30 minutes.")
