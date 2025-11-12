import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class RepairRequest(models.Model):
    """
    Model for repair requests from customers to mechanics
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted by Mechanic"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("rejected", "Rejected"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="repair_requests",
        limit_choices_to={"roles__name": "primary_user"},
    )
    mechanic = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_repair_requests",
        limit_choices_to={"roles__name": "mechanic"},
    )
    # Track mechanics who were notified about this request
    notified_mechanics = models.ManyToManyField(
        User,
        related_name="notified_repair_requests",
        limit_choices_to={"roles__name": "mechanic"},
        blank=True,
        help_text="Mechanics who were notified about this repair request"
    )

    # Service details
    service_type = models.CharField(max_length=100)
    vehicle_make = models.CharField(max_length=50)
    vehicle_model = models.CharField(max_length=50)
    vehicle_year = models.PositiveIntegerField()
    vehicle_registration = models.CharField(max_length=20, blank=True)

    # Problem description
    problem_description = models.TextField()
    # symptoms = models.TextField(blank=True)
    estimated_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Location and scheduling
    service_address = models.TextField()
    service_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    service_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    preferred_date = models.DateField()
    preferred_time_slot = models.CharField(
        max_length=20,
        choices=[
            ("morning", "Morning (8AM-12PM)"),
            ("afternoon", "Afternoon (12PM-4PM)"),
            ("evening", "Evening (4PM-8PM)"),
        ],
    )

    # Status and priority
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending")
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )

    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Additional fields
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    actual_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["mechanic"]),
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["requested_at"]),
        ]

    def __str__(self):
        return f"Repair #{str(self.id)[:8]} - {self.customer.email} ({self.status})"  # noqa

    @property
    def is_active(self):
        """Check if repair request is still active"""
        return self.status in ["pending", "accepted", "in_progress"]

    @property
    def can_be_cancelled(self):
        """Check if repair request can be cancelled"""
        return self.status in ["pending", "accepted"]

    def assign_mechanic(self, mechanic, skip_notification_check=False):
        """
        Assign a mechanic to this repair request.
        
        Args:
            mechanic: The mechanic user to assign
            skip_notification_check: If True, allows assignment even if
                mechanic wasn't notified (for manual customer assignment)
        
        Returns:
            bool: True if assignment successful, False otherwise
        """
        if not mechanic.roles.filter(name="mechanic").exists():
            return False
        
        # If request already has a mechanic, cannot reassign
        if self.mechanic and self.mechanic != mechanic:
            return False
        
        # For automatic acceptance (mechanic accepting), check if notified
        if not skip_notification_check:
            if not self.notified_mechanics.filter(id=mechanic.id).exists():
                return False
        
        self.mechanic = mechanic
        self.status = "accepted"
        self.accepted_at = timezone.now()
        self.save()
        return True
    
    def can_mechanic_accept(self, mechanic):
        """Check if a mechanic can accept this request"""
        return (
            self.status == "pending" and
            self.mechanic is None and
            self.notified_mechanics.filter(id=mechanic.id).exists()
        )

    def start_repair(self):
        """Start the repair work"""
        if self.status == "accepted":
            self.status = "in_progress"
            self.started_at = timezone.now()
            self.save()
            return True
        return False

    def complete_repair(self):
        """Mark repair as completed"""
        if self.status == "in_progress":
            self.status = "completed"
            self.completed_at = timezone.now()
            self.save()
            return True
        return False

    def cancel_request(self, reason=""):
        """Cancel the repair request"""
        if self.can_be_cancelled:
            self.status = "cancelled"
            self.cancelled_at = timezone.now()
            self.cancellation_reason = reason
            self.save()
            return True
        return False

    def reject_request(self, reason=""):
        """Reject the repair request"""
        if self.status == "pending":
            self.status = "rejected"
            self.cancellation_reason = reason
            self.save()
            return True
        return False


class TrainingSession(models.Model):
    """
    Model for mechanic training sessions
    """

    STATUS_CHOICES = [
        ("upcoming", "Upcoming"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    SESSION_TYPE_CHOICES = [
        ("basic", "Basic Training"),
        ("advanced", "Advanced Training"),
        ("specialized", "Specialized Training"),
        ("certification", "Certification Course"),
        ("workshop", "Workshop"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    session_type = models.CharField(
        max_length=20, choices=SESSION_TYPE_CHOICES)

    # Instructor and capacity
    instructor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="conducted_training_sessions",
        limit_choices_to={"roles__name": "mechanic"},
    )
    max_participants = models.PositiveIntegerField(default=20)

    # Scheduling
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    # Location
    venue = models.CharField(max_length=200)
    venue_address = models.TextField()
    venue_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    venue_longitude = models.DecimalField(max_digits=9, decimal_places=6)

    # Cost and registration
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    is_free = models.BooleanField(default=False)
    registration_deadline = models.DateTimeField()

    # Status and metadata
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="upcoming")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Additional fields
    materials_provided = models.TextField(blank=True)
    prerequisites = models.TextField(blank=True)
    certificate_offered = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date", "-start_time"]
        indexes = [
            models.Index(fields=["instructor"]),
            models.Index(fields=["status"]),
            models.Index(fields=["session_type"]),
            models.Index(fields=["start_date"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.instructor.email} ({self.status})"

    @property
    def is_registration_open(self):
        """Check if registration is still open"""
        return self.status == "upcoming" and timezone.now() < self.registration_deadline  # noqa

    @property
    def current_participants_count(self):
        """Get current number of participants"""
        return self.participants.count()

    @property
    def is_full(self):
        """Check if session is full"""
        return self.current_participants_count >= self.max_participants

    @property
    def available_spots(self):
        """Get number of available spots"""
        return max(0, self.max_participants - self.current_participants_count)


class TrainingSessionParticipant(models.Model):
    """
    Model to track participants in training sessions
    """

    STATUS_CHOICES = [
        ("registered", "Registered"),
        ("attended", "Attended"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name="participants"
    )
    participant = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="training_sessions"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="registered"
    )

    # Payment and attendance
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("refunded", "Refunded"),
        ],
        default="pending",
    )
    payment_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Timestamps
    registered_at = models.DateTimeField(auto_now_add=True)
    attended_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Certificate
    certificate_issued = models.BooleanField(default=False)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)

    # Feedback
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
    )
    feedback = models.TextField(blank=True)

    class Meta:
        unique_together = ("session", "participant")
        ordering = ["-registered_at"]
        indexes = [
            models.Index(fields=["session"]),
            models.Index(fields=["participant"]),
            models.Index(fields=["status"]),
            models.Index(fields=["payment_status"]),
        ]

    def __str__(self):
        return f"{self.participant.email} - {self.session.title}"

    def mark_attended(self):
        """Mark participant as attended"""
        if self.status == "registered":
            self.status = "attended"
            self.attended_at = timezone.now()
            self.save()
            return True
        return False

    def mark_completed(self):
        """Mark participant as completed"""
        if self.status == "attended":
            self.status = "completed"
            self.completed_at = timezone.now()
            self.save()
            return True
        return False

    def issue_certificate(self):
        """Issue certificate to participant"""
        if self.status == "completed" and self.session.certificate_offered:
            self.certificate_issued = True
            self.certificate_issued_at = timezone.now()
            self.save()
            return True
        return False


class VehicleMake(models.Model):
    """
    Model for vehicle makes that mechanics can specialize in.
    If this instance is a car model, 'parent_make' points to the make.
    If 'parent_make' is null, this is a make; otherwise, it's a model.
    """
    name = models.CharField(max_length=100)
    parent_make = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='models',
        help_text="If this is a car model, select its make. Leave blank for makes." # noqa
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('name', 'parent_make')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['parent_make']),
        ]

    def __str__(self):
        if self.parent_make:
            return f"{self.parent_make.name} {self.name}"
        return self.name


class MechanicVehicleExpertise(models.Model):
    """
    Model to track which vehicle makes a mechanic is expert in
    """
    mechanic = models.ForeignKey(
        'users.MechanicProfile',
        on_delete=models.CASCADE,
        related_name='vehicle_expertise'
    )
    vehicle_make = models.ForeignKey(
        VehicleMake,
        on_delete=models.CASCADE,
        related_name='expert_mechanics'
    )
    years_of_experience = models.PositiveIntegerField(
        default=0,
        help_text="Years of experience with this vehicle make"
    )
    certification_level = models.CharField(
        max_length=50,
        choices=[
            ('basic', 'Basic'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert'),
            ('certified', 'Certified'),
        ],
        default='basic'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('mechanic', 'vehicle_make')
        ordering = ['-years_of_experience', 'vehicle_make__name']
        indexes = [
            models.Index(fields=['mechanic']),
            models.Index(fields=['vehicle_make']),
            models.Index(fields=['certification_level']),
        ]

    def __str__(self):
        return f"{self.mechanic.user.email} - {self.vehicle_make.name} ({self.certification_level})"  # noqa


