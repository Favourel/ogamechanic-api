import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class DeliveryWaypoint(models.Model):
    """
    Model representing a waypoint in a delivery route.
    """
    WAYPOINT_TYPES = [
        ('pickup', 'Pickup'),
        ('dropoff', 'Dropoff'),
        ('waypoint', 'Waypoint'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    address = models.TextField()
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
    
    # Package information for this waypoint
    package_description = models.TextField(blank=True)
    package_weight = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0.01), MaxValueValidator(100.0)]
    )
    package_dimensions = models.CharField(max_length=50, blank=True)
    is_fragile = models.BooleanField(default=False)
    requires_signature = models.BooleanField(default=False)
    
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


class DeliveryRequest(models.Model):
    """
    Model for courier/delivery requests with support for multiple waypoints.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("assigned", "Assigned to Driver"),
        ("picked_up", "Picked Up"),
        ("in_transit", "In Transit"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
        ("failed", "Failed"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("online", "Online Payment"),
        ("cash_on_delivery", "Cash on Delivery"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delivery_requests",
        limit_choices_to={"roles__name": "customer"},
    )
    driver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_delivery_requests",
        limit_choices_to={"roles__name": "driver"},
    )

    # Legacy fields for backward compatibility
    pickup_address = models.TextField(blank=True)
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_contact_name = models.CharField(max_length=100, blank=True)
    pickup_contact_phone = models.CharField(max_length=20, blank=True)
    pickup_instructions = models.TextField(blank=True)

    delivery_address = models.TextField(blank=True)
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_contact_name = models.CharField(max_length=100, blank=True)
    delivery_contact_phone = models.CharField(max_length=20, blank=True)
    delivery_instructions = models.TextField(blank=True)

    # Enhanced routing with waypoints
    waypoints = models.ManyToManyField(DeliveryWaypoint, related_name='delivery_requests')
    current_waypoint_index = models.PositiveIntegerField(default=0, help_text="Current waypoint being processed")
    
    # Route information
    total_distance_km = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    total_duration_min = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    route_polyline = models.TextField(blank=True, help_text="Encoded polyline for route visualization")

    # Package details (legacy - now handled by waypoints)
    package_description = models.TextField(blank=True)
    package_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0.01), MaxValueValidator(100.0)],
        null=True, blank=True
    )
    package_dimensions = models.CharField(
        max_length=50, blank=True
    )  # e.g., "30x20x15 cm"
    is_fragile = models.BooleanField(default=False)
    requires_signature = models.BooleanField(default=False)

    # Pricing and payment
    estimated_distance = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )  # in kilometers
    estimated_duration = models.IntegerField(
        null=True, blank=True)  # in minutes
    base_fare = models.DecimalField(max_digits=8, decimal_places=2)
    distance_fare = models.DecimalField(max_digits=8, decimal_places=2)
    total_fare = models.DecimalField(max_digits=8, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default="online"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("failed", "Failed"),
        ],
        default="pending",
    )

    # Status and tracking
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending")
    requested_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Driver location tracking
    driver_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    driver_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    last_location_update = models.DateTimeField(null=True, blank=True)

    # Additional fields
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Courier #{self.id[:8]} - {self.customer.email} ({self.status})" # noqa

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

    @property
    def is_active(self):
        """Check if courier request is still active"""
        return self.status in ["pending", "assigned", "picked_up", "in_transit"] # noqa

    @property
    def can_be_cancelled(self):
        """Check if courier request can be cancelled"""
        return self.status in ["pending", "assigned"]

    def assign_driver(self, driver):
        """Assign a driver to this courier request"""
        if driver.roles.filter(name="driver").exists():
            self.driver = driver
            self.status = "assigned"
            self.assigned_at = timezone.now()
            self.save()
            return True
        return False

    def mark_as_picked_up(self):
        """Mark package as picked up"""
        if self.status == "assigned":
            self.status = "picked_up"
            self.picked_up_at = timezone.now()
            self.save()
            return True
        return False

    def mark_as_in_transit(self):
        """Mark package as in transit"""
        if self.status == "picked_up":
            self.status = "in_transit"
            self.save()
            return True
        return False

    def mark_as_delivered(self):
        """Mark package as delivered"""
        if self.status in ["picked_up", "in_transit"]:
            self.status = "delivered"
            self.delivered_at = timezone.now()
            self.save()
            return True
        return False

    def cancel_request(self, reason=""):
        """Cancel the courier request"""
        if self.can_be_cancelled:
            self.status = "cancelled"
            self.cancelled_at = timezone.now()
            self.cancellation_reason = reason
            self.save()
            return True
        return False

    def update_driver_location(self, latitude, longitude):
        """Update driver's current location"""
        self.driver_latitude = latitude
        self.driver_longitude = longitude
        self.last_location_update = timezone.now()
        self.save()


class DeliveryTracking(models.Model):
    """
    Model for tracking delivery progress and location updates
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_request = models.ForeignKey(
        DeliveryRequest, on_delete=models.CASCADE, 
        related_name="tracking_updates"
    )
    driver = models.ForeignKey(
        User, on_delete=models.CASCADE, 
        related_name="delivery_tracking_updates"
    )

    # Location data
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )  # GPS accuracy in meters

    # Status update
    status = models.CharField(
        max_length=50
    )  # e.g., "Heading to pickup", "At pickup location"
    notes = models.TextField(blank=True)

    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Tracking update for {self.delivery_request.id[:8]} at {self.timestamp}" # noqa


class CourierRating(models.Model):
    """
    Model for rating courier/delivery service
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_request = models.OneToOneField(
        DeliveryRequest, on_delete=models.CASCADE, related_name="rating"
    )
    customer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="courier_ratings_given"
    )
    driver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="courier_ratings_received"
    )

    # Rating details
    overall_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    delivery_speed_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    service_quality_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    communication_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    # Review
    review = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["delivery_request", "customer"]

    def __str__(self):
        return f"Rating {self.overall_rating}/5 for {self.driver.email} by {self.customer.email}" # noqa

    @property
    def average_rating(self):
        """Calculate average rating across all categories, ignoring None values""" # noqa
        ratings = [
            self.overall_rating,
            self.delivery_speed_rating,
            self.service_quality_rating,
            self.communication_rating,
        ]
        valid_ratings = [r for r in ratings if r is not None]
        if not valid_ratings:
            return None
        return sum(valid_ratings) / len(valid_ratings)
