import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class RentalBooking(models.Model):
    """
    Model for car rental bookings
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="rental_bookings",
        limit_choices_to={"roles__name": "customer"},
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="rental_bookings",
        limit_choices_to={
            "is_rental": True
        },
    )

    # Rental period
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(default="09:00:00")
    end_time = models.TimeField(default="17:00:00")

    # Pricing
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    booking_reference = models.CharField(max_length=20, unique=True)

    # Pickup and return
    pickup_location = models.TextField()
    return_location = models.TextField()
    pickup_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    pickup_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    return_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    return_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # Additional information
    special_requests = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Timestamps
    booked_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-booked_at"]
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["product"]),
            models.Index(fields=["status"]),
            models.Index(fields=["start_date"]),
            models.Index(fields=["end_date"]),
            models.Index(fields=["booking_reference"]),
        ]

    def __str__(self):
        return f"Rental {self.booking_reference} - {self.customer.email}"

    @property
    def duration_days(self):
        """Calculate rental duration in days"""
        return (self.end_date - self.start_date).days + 1

    @property
    def is_active(self):
        """Check if rental is currently active"""
        today = timezone.now().date()
        return (
            self.status in ["confirmed", "active"] and
            self.start_date <= today <= self.end_date
        )

    @property
    def can_be_cancelled(self):
        """Check if rental can be cancelled"""
        return self.status in ["pending", "confirmed"]

    def confirm_booking(self):
        """Confirm the rental booking"""
        if self.status == "pending":
            self.status = "confirmed"
            self.confirmed_at = timezone.now()
            self.save()
            return True
        return False

    def start_rental(self):
        """Start the rental period"""
        if self.status == "confirmed":
            self.status = "active"
            self.started_at = timezone.now()
            self.save()
            return True
        return False

    def complete_rental(self):
        """Complete the rental period"""
        if self.status == "active":
            self.status = "completed"
            self.completed_at = timezone.now()
            self.save()
            return True
        return False

    def cancel_booking(self, reason=""):
        """Cancel the rental booking"""
        if self.can_be_cancelled:
            self.status = "cancelled"
            self.cancelled_at = timezone.now()
            self.cancellation_reason = reason
            self.save()
            return True
        return False

    def reject_booking(self, reason=""):
        """Reject the rental booking"""
        if self.status == "pending":
            self.status = "rejected"
            self.cancellation_reason = reason
            self.save()
            return True
        return False

    def save(self, *args, **kwargs):
        """Generate booking reference if not provided"""
        if not self.booking_reference:
            self.booking_reference = f"RENT{str(self.id)[:8].upper()}"
        super().save(*args, **kwargs)


class RentalReview(models.Model):
    """
    Model for rental reviews
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rental = models.OneToOneField(
        RentalBooking,
        on_delete=models.CASCADE,
        related_name="review"
    )
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="rental_reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["rental", "customer"]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rental"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["rating"]),
        ]

    def __str__(self):
        return (f"Review for {self.rental.booking_reference} "
                f"by {self.customer.email}")


class RentalPeriod(models.Model):
    """
    Model to track rental periods and availability
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="rental_periods"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_available = models.BooleanField(default=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_date"]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["start_date"]),
            models.Index(fields=["end_date"]),
            models.Index(fields=["is_available"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.start_date} to {self.end_date}"

    @property
    def duration_days(self):
        """Calculate period duration in days"""
        return (self.end_date - self.start_date).days + 1

    @property
    def total_cost(self):
        """Calculate total cost for the period"""
        return self.daily_rate * self.duration_days
