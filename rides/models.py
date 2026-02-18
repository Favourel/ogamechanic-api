import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

# Create your models here.


class Waypoint(models.Model):
    """
    Model representing a waypoint in a ride or delivery route.
    """
    WAYPOINT_TYPES = [
        ('pickup', 'Pickup'),
        ('dropoff', 'Dropoff'),
        ('waypoint', 'Waypoint'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    waypoint_type = models.CharField(max_length=20, choices=WAYPOINT_TYPES)
    sequence_order = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Order of waypoint in the route (1 = first, 2 = second, etc.)"
    )

    # Contact information for pickup/dropoff
    contact_name = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    instructions = models.TextField(blank=True)

    # Status tracking
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence_order']
        indexes = [
            models.Index(fields=['waypoint_type']),
            models.Index(fields=['sequence_order']),
            models.Index(fields=['is_completed']),
        ]

    def __str__(self):
        return f"{self.waypoint_type.title()} #{self.sequence_order} - {self.address}"


class Ride(models.Model):
    """
    Model representing a ride request with support for multiple waypoints.
    """
    if hasattr(uuid, "uuid7"):
        id = models.UUIDField(
            primary_key=True,
            default=uuid.uuid7,
            editable=False
        )
    else:
        id = models.UUIDField(
            primary_key=True,
            default=uuid.uuid4,
            editable=False
        )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rides_requested'
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rides_driven'
    )

    # Legacy fields for backward compatibility
    pickup_address = models.CharField(max_length=255, blank=True)
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_address = models.CharField(max_length=255, blank=True)
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Enhanced routing with waypoints
    waypoints = models.ManyToManyField(Waypoint, related_name='rides')
    current_waypoint_index = models.PositiveIntegerField(default=0, help_text="Current waypoint being processed")

    # Route information
    total_distance_km = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    total_duration_min = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    route_polyline = models.TextField(blank=True, help_text="Encoded polyline for route visualization")

    status = models.CharField(
        max_length=32,
        choices=[
            ('initiated', 'Initiated'),
            ('requested', 'Requested'),
            ('accepted', 'Accepted'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='initiated'
    )
    fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    distance_km = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True)
    duration_min = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def calculate_total_distance_km(self):
        """
        Calculate the total distance in kilometers for all waypoints.
        """
        from math import radians, sin, cos, sqrt, atan2

        waypoints = self.waypoints.all().order_by('sequence_order')
        if len(waypoints) < 2:
            return 0

        total_distance = 0
        R = 6371  # Earth radius in km

        for i in range(len(waypoints) - 1):
            wp1 = waypoints[i]
            wp2 = waypoints[i + 1]

            lat1 = float(wp1.latitude)
            lon1 = float(wp1.longitude)
            lat2 = float(wp2.latitude)
            lon2 = float(wp2.longitude)

            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = (
                sin(dlat / 2) ** 2
                + cos(radians(lat1))
                * cos(radians(lat2))
                * sin(dlon / 2) ** 2
            )
            c = 2 * atan2(sqrt(a), sqrt(1 - a))
            total_distance += R * c

        return total_distance

    def get_current_waypoint(self):
        """Get the current waypoint being processed."""
        return self.waypoints.filter(sequence_order__gt=self.current_waypoint_index).order_by('sequence_order').first()

    def get_next_waypoint(self):
        """Get the next waypoint to be processed."""
        return self.waypoints.filter(sequence_order__gt=self.current_waypoint_index).order_by('sequence_order').first()

    def get_pickup_waypoints(self):
        """Get all pickup waypoints."""
        return self.waypoints.filter(waypoint_type='pickup').order_by('sequence_order')

    def get_dropoff_waypoints(self):
        """Get all dropoff waypoints."""
        return self.waypoints.filter(waypoint_type='dropoff').order_by('sequence_order')

    def get_waypoint_by_type(self, waypoint_type):
        """Get waypoints by type."""
        return self.waypoints.filter(waypoint_type=waypoint_type).order_by('sequence_order')

    def advance_to_next_waypoint(self):
        """Advance to the next waypoint in the route."""
        next_waypoint = self.get_next_waypoint()
        if next_waypoint:
            self.current_waypoint_index = next_waypoint.sequence_order
            self.save()
            return next_waypoint
        return None

    def mark_waypoint_completed(self, waypoint):
        """Mark a waypoint as completed."""
        if waypoint in self.waypoints.all():
            waypoint.is_completed = True
            waypoint.completed_at = timezone.now()
            waypoint.save()
            return True
        return False

    def is_route_completed(self):
        """Check if all waypoints in the route are completed."""
        return self.waypoints.filter(is_completed=False).count() == 0

    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['customer']),
            models.Index(fields=['driver']),
            models.Index(fields=['status']),
            models.Index(fields=['requested_at']),
            models.Index(fields=['current_waypoint_index']),
        ]

    def __str__(self):
        return f"Ride {self.id} by {self.customer.email} ({self.status})"


class CourierRequest(models.Model):
    if hasattr(uuid, "uuid7"):
        id = models.UUIDField(
            primary_key=True,
            default=uuid.uuid7,
            editable=False
        )
    else:
        id = models.UUIDField(
            primary_key=True,
            default=uuid.uuid4,
            editable=False
        )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courier_requests'
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courier_deliveries'
    )

    # Legacy fields for backward compatibility
    pickup_address = models.CharField(max_length=255, blank=True)
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_address = models.CharField(max_length=255, blank=True)
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Enhanced routing with waypoints
    waypoints = models.ManyToManyField(Waypoint, related_name='courier_requests')
    current_waypoint_index = models.PositiveIntegerField(default=0, help_text="Current waypoint being processed")

    # Route information
    total_distance_km = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    total_duration_min = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    route_polyline = models.TextField(blank=True, help_text="Encoded polyline for route visualization")

    item_description = models.TextField()
    item_weight = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=32,
        choices=[
            ('requested', 'Requested'),
            ('accepted', 'Accepted'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='requested'
    )
    fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def get_current_waypoint(self):
        """Get the current waypoint being processed."""
        return self.waypoints.filter(sequence_order__gt=self.current_waypoint_index).order_by('sequence_order').first()

    def get_next_waypoint(self):
        """Get the next waypoint to be processed."""
        return self.waypoints.filter(sequence_order__gt=self.current_waypoint_index).order_by('sequence_order').first()

    def get_pickup_waypoints(self):
        """Get all pickup waypoints."""
        return self.waypoints.filter(waypoint_type='pickup').order_by('sequence_order')

    def get_dropoff_waypoints(self):
        """Get all dropoff waypoints."""
        return self.waypoints.filter(waypoint_type='dropoff').order_by('sequence_order')

    def advance_to_next_waypoint(self):
        """Advance to the next waypoint in the route."""
        next_waypoint = self.get_next_waypoint()
        if next_waypoint:
            self.current_waypoint_index = next_waypoint.sequence_order
            self.save()
            return next_waypoint
        return None

    def mark_waypoint_completed(self, waypoint):
        """Mark a waypoint as completed."""
        if waypoint in self.waypoints.all():
            waypoint.is_completed = True
            waypoint.completed_at = timezone.now()
            waypoint.save()
            return True
        return False

    def is_route_completed(self):
        """Check if all waypoints in the route are completed."""
        return self.waypoints.filter(is_completed=False).count() == 0

    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['customer']),
            models.Index(fields=['driver']),
            models.Index(fields=['status']),
            models.Index(fields=['requested_at']),
            models.Index(fields=['current_waypoint_index']),
        ]

    def __str__(self):
        return (
            f"Ride {self.id} by {self.customer.email} ({self.status})" # noqa
        )


class RideRating(models.Model):
    """
    Model for rating ride service
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ride = models.OneToOneField(
        Ride, on_delete=models.CASCADE, related_name="rating"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ride_ratings_given"
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ride_ratings_received"
    )

    # Rating details
    overall_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    driving_skill_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    punctuality_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    vehicle_condition_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    communication_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    # Feedback
    comment = models.TextField(blank=True)
    rated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-rated_at']
        indexes = [
            models.Index(fields=['ride']),
            models.Index(fields=['customer']),
            models.Index(fields=['driver']),
            models.Index(fields=['overall_rating']),
            models.Index(fields=['rated_at']),
        ]

    def __str__(self):
        return f"Rating for Ride {self.ride.id[:8]} - {self.overall_rating}/5"

    @property
    def average_rating(self):
        """Calculate the average of all rating fields"""
        ratings = [
            self.overall_rating,
            self.driving_skill_rating,
            self.punctuality_rating,
            self.vehicle_condition_rating,
            self.communication_rating,
        ]
        return sum(ratings) / len(ratings)
