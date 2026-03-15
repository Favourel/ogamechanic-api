from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models, transaction

from couriers.models import DeliveryRequest, DeliveryWaypoint


class LegacyCourierRequest(models.Model):
    class Meta:
        managed = False
        db_table = "rides_courierrequest"

    id = models.UUIDField(primary_key=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )

    pickup_address = models.CharField(max_length=255, blank=True)
    pickup_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    pickup_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    dropoff_address = models.CharField(max_length=255, blank=True)
    dropoff_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    dropoff_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    item_description = models.TextField()
    item_weight = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=32)
    fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    requested_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    total_distance_km = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    total_duration_min = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    route_polyline = models.TextField(blank=True)


class Command(BaseCommand):
    help = "Backfill rides.CourierRequest into couriers.DeliveryRequest"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without writing",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help=(
                "Limit number of CourierRequest rows to migrate (0 = no limit)"
            ),
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        limit = int(options["limit"] or 0)

        qs = LegacyCourierRequest.objects.all().order_by("requested_at")
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(
            self.style.NOTICE(f"Found {total} CourierRequest rows")
        )

        migrated = 0
        skipped = 0

        for cr in qs.iterator():
            # Best-effort idempotency: if a DeliveryRequest already exists with same
            # (customer, driver, pickup/dropoff, requested_at), skip.
            existing = (
                DeliveryRequest.objects.filter(
                    customer=cr.customer,
                    driver=cr.driver,
                    pickup_address=cr.pickup_address,
                    delivery_address=cr.dropoff_address,
                    requested_at=cr.requested_at,
                )
                .first()
            )

            if existing:
                skipped += 1
                continue

            status_map = {
                "requested": "pending",
                "accepted": "assigned",
                "in_progress": "in_transit",
                "completed": "delivered",
                "cancelled": "cancelled",
            }
            delivery_status = status_map.get(cr.status, "pending")

            if dry_run:
                migrated += 1
                continue

            with transaction.atomic():
                dr = DeliveryRequest.objects.create(
                    customer=cr.customer,
                    driver=cr.driver,
                    pickup_address=cr.pickup_address,
                    pickup_latitude=cr.pickup_latitude,
                    pickup_longitude=cr.pickup_longitude,
                    delivery_address=cr.dropoff_address,
                    delivery_latitude=cr.dropoff_latitude,
                    delivery_longitude=cr.dropoff_longitude,
                    package_description=cr.item_description,
                    package_weight=cr.item_weight,
                    base_fare=0,
                    distance_fare=0,
                    total_fare=cr.fare or 0,
                    status=delivery_status,
                    assigned_at=cr.accepted_at,
                    picked_up_at=cr.started_at,
                    delivered_at=cr.completed_at,
                    cancelled_at=cr.cancelled_at,
                    total_distance_km=cr.total_distance_km,
                    total_duration_min=cr.total_duration_min,
                    route_polyline=cr.route_polyline or "",
                )

                # Minimal waypoint migration (pickup/dropoff only)
                # Legacy rides.Waypoint is a different model, so we
                # approximate.
                if (
                    cr.pickup_address
                    and cr.pickup_latitude
                    and cr.pickup_longitude
                ):
                    pickup_wp = DeliveryWaypoint.objects.create(
                        address=cr.pickup_address,
                        latitude=cr.pickup_latitude,
                        longitude=cr.pickup_longitude,
                        waypoint_type="pickup",
                        sequence_order=1,
                    )
                    dr.waypoints.add(pickup_wp)

                if (
                    cr.dropoff_address
                    and cr.dropoff_latitude
                    and cr.dropoff_longitude
                ):
                    dropoff_wp = DeliveryWaypoint.objects.create(
                        address=cr.dropoff_address,
                        latitude=cr.dropoff_latitude,
                        longitude=cr.dropoff_longitude,
                        waypoint_type="dropoff",
                        sequence_order=2,
                    )
                    dr.waypoints.add(dropoff_wp)

                migrated += 1

        suffix = "(dry-run)" if dry_run else ""
        msg = (
            (
                f"Migrated {migrated} CourierRequest rows, skipped {skipped} "
                f"{suffix}"
            ).strip()
        )
        self.stdout.write(self.style.SUCCESS(msg))
