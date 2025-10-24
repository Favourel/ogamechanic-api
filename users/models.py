from django.contrib.auth.models import (AbstractBaseUser, 
                                        PermissionsMixin, 
                                        BaseUserManager)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid
# from ogamechanic.modules.validators import CustomEmailValidator

from django.core.validators import FileExtensionValidator
# from django.contrib.gis.db import models as gis_models


class Role(models.Model):
    PRIMARY_USER = 'primary_user'
    DRIVER = 'driver'
    RIDER = 'rider'
    MECHANIC = 'mechanic'
    MERCHANT = 'merchant'
    DEVELOPER = 'developer'

    ROLE_CHOICES = [
        (PRIMARY_USER, _('Primary User')),
        (DRIVER, _('Driver')),
        (RIDER, _('Rider')),
        (MECHANIC, _('Mechanic')),
        (MERCHANT, _('Merchant')),
        (DEVELOPER, _('Developer')),
    ]

    name = models.CharField(
        _('role name'),
        max_length=50,
        choices=ROLE_CHOICES,
        unique=True
    )
    description = models.TextField(_('description'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('role')
        verbose_name_plural = _('roles')
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.get_name_display()


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for the OGAMECHANIC.
    """
    try:
        # Python 3.11+ supports uuid.uuid7
        id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False) # noqa
    except AttributeError:
        # Fallback to uuid4 if uuid7 is not available
        id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # noqa
    email = models.EmailField(
        # Removed unique=True to allow same email for different roles
        # validators=[CustomEmailValidator(allow_disposable=False)],
        # help_text="User's email address. Disposable email addresses are not allowed." # noqa
    )
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    roles = models.ManyToManyField(Role)
    active_role = models.ForeignKey(
        Role, on_delete=models.SET_NULL, 
        null=True, related_name='active_users'
    )
    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        # unique=True,
    )
    is_verified = models.BooleanField(_('verified'), default=False)
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    last_login = models.DateTimeField(_('last login'), null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    # Track login
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_login = models.DateTimeField(null=True, blank=True)

    # Car details (for customers)
    car_make = models.CharField(max_length=50, blank=True, null=True)
    car_model = models.CharField(max_length=50, blank=True, null=True)
    car_year = models.IntegerField(blank=True, null=True)
    license_plate = models.CharField(max_length=20, blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
            models.Index(fields=['last_login']),
            models.Index(
                fields=[
                    'is_staff',
                    'is_active'
                ]
            ),
        ]
        # Note: We'll handle email+role uniqueness at the application level
        # since Django doesn't support unique constraints on ManyToMany fields

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    def is_locked(self):
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False

    def get_lockout_remaining(self):
        if self.is_locked():
            remaining = self.locked_until - timezone.now()
            return max(0, int(remaining.total_seconds()))
        return 0

    def __str__(self):
        return self.email


class UserActivityLog(models.Model):
    """
    Model to track user activities in the system.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activity_logs'
    )
    action = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    object_type = models.CharField(max_length=100, null=True, blank=True)
    object_id = models.CharField(max_length=100, null=True, blank=True)
    severity = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical')
        ],
        default='low'
    )

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'action', 'timestamp']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['severity'])
        ]

    def __str__(self):
        return f"{self.user.email} - {self.action} - {self.timestamp}"


class Notification(models.Model):
    """
    Model to store in-app notifications for users.
    """
    NOTIFICATION_TYPES = [
        ('info', _('Information')),
        ('warning', _('Warning')),
        ('error', _('Error')),
        ('success', _('Success')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(_('title'), max_length=200, default="Enter title")
    message = models.TextField(_('message'))
    notification_type = models.CharField(
        _('notification type'),
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default='info'
    )
    
    # Status
    is_read = models.BooleanField(_('is read'), default=False)
    is_sent = models.BooleanField(_('is sent'), default=False)
    
    # Timestamps
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    read_at = models.DateTimeField(_('read at'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_sent(self):
        """Mark notification as sent (for email notifications)."""
        self.is_sent = True
        self.save(update_fields=['is_sent'])


class UserEmailVerification(models.Model):
    """
    Model to store email verification tokens for users.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='email_verification')
    token = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        # Shorten to fit within 79 characters
        return f"Email verification for {self.user.email}"

    class Meta:
        verbose_name = _('user email verification')
        verbose_name_plural = _('user email verifications')
        indexes = [
            models.Index(
                fields=['token']
            ),
            models.Index(
                fields=['expires_at']
            ),
        ]


class Device(models.Model):
    user = models.ForeignKey(
        'User', on_delete=models.CASCADE, 
        related_name='devices')
    fcm_token = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MerchantProfile(models.Model):
    user = models.OneToOneField(
        'User', on_delete=models.CASCADE, related_name='merchant_profile'
    )
    # Updated fields for new onboarding
    location = models.CharField(max_length=255, blank=True, null=True)
    lga = models.CharField(
        max_length=100, blank=True, null=True
    )  # Local Government Area
    cac_number = models.CharField(max_length=100)
    cac_document = models.FileField(
        upload_to='merchant/cac_documents/',
        validators=[FileExtensionValidator(
            ['jpg', 'jpeg', 'png', 'pdf']
        )],
        blank=True, null=True
    )
    selfie = models.ImageField(
        upload_to='merchant/selfies/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        blank=True, null=True,
        help_text="Live photo of merchant"
    )
    
    # Legacy fields for backward compatibility
    is_approved = models.BooleanField(default=False)
    business_address = models.CharField(max_length=255)
    profile_picture = models.ImageField(
        upload_to='merchant/profile_pics/', blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('merchant profile')
        verbose_name_plural = _('merchant profiles')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['cac_number']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return (
            f"MerchantProfile: {self.user.email}"
        )


class MechanicProfile(models.Model):
    user = models.OneToOneField(
        'User', on_delete=models.CASCADE, related_name='mechanic_profile'
    )
    # Updated fields for new onboarding (same as merchant)
    location = models.CharField(max_length=255, blank=True, null=True)
    bio = models.TextField(null=True, blank=True)
    lga = models.CharField(
        max_length=100, blank=True, null=True
    )  # Local Government Area
    cac_number = models.CharField(max_length=100, blank=True, null=True)
    cac_document = models.FileField(
        upload_to='mechanic/cac_documents/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])],
        blank=True, null=True
    )
    selfie = models.ImageField(
        upload_to='mechanic/selfies/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        blank=True, null=True,
        help_text="Live photo of mechanic"
    )
    GOVT_ID_TYPE_CHOICES = [
        ("NIN", "NIN"),
        ("drivers_license", "Drivers license"),
        ("voters_card", "Voters card"),
        ("international_passport", "International passport"),
        ("permanent_voters_card", "Permanent voter’s card"),
    ]

    govt_id_type = models.CharField(
        max_length=32,
        choices=GOVT_ID_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Type of government ID provided"
    )
    government_id_front = models.FileField(
        upload_to='mechanic/ids/government_id/front/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])],
        blank=True, null=True,
        help_text="Front of Government Identity Card"
    )
    government_id_back = models.FileField(
        upload_to='mechanic/ids/government_id/back/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])],
        blank=True, null=True,
        help_text="Back of Government Identity Card"
    )

    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('mechanic profile')
        verbose_name_plural = _('mechanic profiles')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"MechanicProfile: {self.user.email}"


class MechanicReview(models.Model):
    mechanic = models.ForeignKey(
        MechanicProfile,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mechanic_reviews'
    )
    rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('mechanic', 'user')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mechanic']),
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return (
            f"Review by {self.user.email} for {self.mechanic.user.email}"
        )


# Add average rating method to MechanicProfile
setattr(
    MechanicProfile,
    'average_rating',
    lambda self: self.reviews.aggregate(
        avg=models.Avg('rating')
    )['avg'] or 0
)


class DriverProfile(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    
    user = models.OneToOneField(
        'User', on_delete=models.CASCADE, related_name='driver_profile'
    )
    
    # Personal Information
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    city = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True) # noqa
    address = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    
    # License Information
    license_number = models.CharField(max_length=50, blank=True, null=True)
    license_issue_date = models.DateField(blank=True, null=True)
    license_expiry_date = models.DateField(blank=True, null=True)
    license_front_image = models.ImageField(
        upload_to='driver/licenses/front/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        blank=True, null=True
    )
    license_back_image = models.ImageField(
        upload_to='driver/licenses/back/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        blank=True, null=True
    )
    
    # Vehicle Information
    vin = models.CharField(max_length=50, blank=True, null=True)
    vehicle_name = models.CharField(max_length=100, blank=True, null=True)
    plate_number = models.CharField(max_length=20, blank=True, null=True)
    vehicle_model = models.CharField(max_length=100, blank=True, null=True)
    vehicle_color = models.CharField(max_length=50, blank=True, null=True)
    
    # Vehicle Photos
    vehicle_photo_front = models.ImageField(
        upload_to='driver/vehicle_photos/front/',
        blank=True, null=True
    )
    vehicle_photo_back = models.ImageField(
        upload_to='driver/vehicle_photos/back/',
        blank=True, null=True
    )
    vehicle_photo_right = models.ImageField(
        upload_to='driver/vehicle_photos/right/',
        blank=True, null=True
    )
    vehicle_photo_left = models.ImageField(
        upload_to='driver/vehicle_photos/left/',
        blank=True, null=True
    )
    
    # Bank Information
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    
    # Legacy fields for backward compatibility
    government_id = models.FileField(
        upload_to='driver/ids/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])],
        blank=True, null=True
    )
    driver_license = models.FileField(
        upload_to='driver/licenses/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])],
        blank=True, null=True
    )
    vehicle_type = models.CharField(
        max_length=50,
        choices=[
            ('car', 'Car'),
            ('motorcycle', 'Motorcycle'),
            ('van', 'Van'),
            ('truck', 'Truck'),
            ('bicycle', 'Bicycle'),
            ('other', 'Other'),
        ],
        blank=True,
        null=True
    )
    vehicle_registration_number = models.CharField(
        max_length=50, blank=True, null=True)
    vehicle_photo = models.ImageField(
        upload_to='driver/vehicle_photos/',
        blank=True, null=True
    )
    insurance_document = models.FileField(
        upload_to='driver/insurance/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])],
        blank=True, null=True
    )
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Enhanced fields for better driver management
    vehicle_info = models.TextField(blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    vehicle_model = models.CharField(max_length=100, blank=True)
    vehicle_color = models.CharField(max_length=50, blank=True)
    is_available = models.BooleanField(default=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_rides = models.PositiveIntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # noqa
    
    # Enhanced location tracking fields with spatial support
    # Note: For development with SQLite, we'll use regular fields
    # For production with PostgreSQL, uncomment the PointField
    # location = gis_models.PointField(null=True, blank=True, srid=4326)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True) # noqa
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True) # noqa
    last_location_update = models.DateTimeField(null=True, blank=True)
    
    # Additional spatial tracking fields
    current_ride = models.ForeignKey(
        'rides.Ride', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_driver'
    )
    is_online = models.BooleanField(default=False)
    last_online = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('driver profile')
        verbose_name_plural = _('driver profiles')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['phone_number']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_available']),
            models.Index(fields=['is_online']),
        ]

    def __str__(self):
        return f"DriverProfile: {self.user.email}"

    def update_location(self, lat: float, lon: float):
        """
        Update driver location with enhanced tracking
        """
        from django.utils import timezone
        from ogamechanic.modules.location_service import LocationService # noqa
        
        self.latitude = lat
        self.longitude = lon
        self.last_location_update = timezone.now()
        self.save()

    def get_distance_to(self, lat: float, lon: float) -> float:
        """
        Calculate distance to a point in kilometers using Haversine formula
        """
        if not self.latitude or not self.longitude:
            return float('inf')
        
        from ogamechanic.modules.location_service import LocationService
        return LocationService.haversine_distance(
            float(self.latitude), float(self.longitude), lat, lon
        )

    def is_within_radius(self, lat: float, lon: float, radius_km: float) -> bool: # noqa
        """
        Check if driver is within specified radius
        """
        distance = self.get_distance_to(lat, lon)
        return distance <= radius_km


class DriverReview(models.Model):
    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='driver_reviews'
    )
    rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('driver', 'user')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['driver']),
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return (
            f"Review by {self.user.email} for {self.driver.user.email}"
        )


# Add average rating method to DriverProfile
setattr(
    DriverProfile,
    'average_rating',
    lambda self: self.reviews.aggregate(
        avg=models.Avg('rating')
    )['avg'] or 0
)


class BankAccount(models.Model):
    """
    Bank account model for Paystack integration.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bank_accounts'
    )
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=255)
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    paystack_recipient_code = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text=_('Paystack recipient code for transfers')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('bank account')
        verbose_name_plural = _('bank accounts')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['is_active']),
        ]
        unique_together = ['user', 'account_number', 'bank_code']

    def __str__(self):
        return f"{self.account_name} - {self.bank_name} ({self.account_number})" # noqa

    def get_display_name(self):
        """Get formatted display name for the bank account."""
        return f"{self.account_name} - {self.bank_name}"


class Wallet(models.Model):
    """
    Enhanced wallet model to store user balances.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    currency = models.CharField(
        max_length=10, default='NGN'
    )
    # Enhanced wallet features
    is_active = models.BooleanField(default=True)
    daily_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=100000.00,
        help_text=_('Daily transaction limit')
    )
    monthly_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=1000000.00,
        help_text=_('Monthly transaction limit')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('wallet')
        verbose_name_plural = _('wallets')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"Wallet of {self.user.email} - Balance: {self.balance} {self.currency}" # noqa

    def credit(self, amount, description="Wallet credit"):
        """Credit the wallet by a given amount."""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        self.balance = models.F('balance') + amount
        self.save(update_fields=['balance'])
        self.refresh_from_db(fields=['balance'])
        
        # Create transaction record
        Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='credit',
            description=description,
            status='completed'
        )

    def debit(self, amount, description="Wallet debit"):
        """Debit the wallet by a given amount."""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        if self.balance < amount:
            raise ValueError("Insufficient balance")
        
        self.balance = models.F('balance') - amount
        self.save(update_fields=['balance'])
        self.refresh_from_db(fields=['balance'])
        
        # Create transaction record
        Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='debit',
            description=description,
            status='completed'
        )

    def get_daily_transactions_total(self):
        """Get total transactions for today."""
        from django.utils import timezone
        
        today = timezone.now().date()
        return self.transactions.filter(
            created_at__date=today
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    def get_monthly_transactions_total(self):
        """Get total transactions for current month."""
        from django.utils import timezone
        
        now = timezone.now()
        return self.transactions.filter(
            created_at__year=now.year,
            created_at__month=now.month
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    def can_transact(self, amount):
        """Check if wallet can perform transaction within limits."""
        if not self.is_active:
            return False, "Wallet is inactive"
        
        if self.balance < amount:
            return False, "Insufficient balance"
        
        daily_total = self.get_daily_transactions_total()
        if daily_total + amount > self.daily_limit:
            return False, "Daily transaction limit exceeded"
        
        monthly_total = self.get_monthly_transactions_total()
        if monthly_total + amount > self.monthly_limit:
            return False, "Monthly transaction limit exceeded"
        
        return True, "Transaction allowed"


class Transaction(models.Model):
    """
    Enhanced transaction model to record wallet transactions.
    """
    TRANSACTION_TYPES = (
        ('credit', _('Credit')),
        ('debit', _('Debit')),
        ('refund', _('Refund')),
        ('withdrawal', _('Withdrawal')),
        ('deposit', _('Deposit')),
        ('payment', _('Payment')),
        ('top_up', _('Top Up')),
        ('transfer', _('Transfer')),
        ('fee', _('Fee')),
    )

    TRANSACTION_STATUSES = (
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('cancelled', _('Cancelled')),
    )

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text=_('External reference or transaction ID')
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    status = models.CharField(
        max_length=20,
        choices=TRANSACTION_STATUSES,
        default='completed'
    )
    # Enhanced transaction tracking
    fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text=_('Transaction fee')
    )
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text=_('Additional transaction metadata')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('transaction')
        verbose_name_plural = _('transactions')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return (
            f"{self.transaction_type.title()} of {self.amount} {self.wallet.currency} " # noqa
            f"for {self.wallet.user.email} ({self.status})"
        )

    @property
    def net_amount(self):
        """Get net amount after fees."""
        return self.amount - self.fee

    def mark_as_processing(self):
        """Mark transaction as processing."""
        self.status = 'processing'
        self.save(update_fields=['status', 'updated_at'])

    def mark_as_completed(self):
        """Mark transaction as completed."""
        self.status = 'completed'
        self.save(update_fields=['status', 'updated_at'])

    def mark_as_failed(self, reason=None):
        """Mark transaction as failed."""
        self.status = 'failed'
        if reason:
            self.description = f"Failed: {reason}"
        self.save(update_fields=['status', 'description', 'updated_at'])

    def mark_as_cancelled(self, reason=None):
        """Mark transaction as cancelled."""
        self.status = 'cancelled'
        if reason:
            self.description = f"Cancelled: {reason}"
        self.save(update_fields=['status', 'description', 'updated_at'])


class SecureDocument(models.Model):
    """
    Enhanced secure document model for identity verification and file storage.
    """
    DOCUMENT_TYPES = (
        ('government_id', _('Government ID')),
        ('driver_license', _('Driver License')),
        ('passport', _('Passport')),
        ('cac_document', _('CAC Document')),
        ('vehicle_registration', _('Vehicle Registration')),
        ('insurance_document', _('Insurance Document')),
        ('vehicle_photo', _('Vehicle Photo')),
        ('profile_picture', _('Profile Picture')),
        ('other', _('Other')),
    )
    
    VERIFICATION_STATUSES = (
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('verified', _('Verified')),
        ('rejected', _('Rejected')),
        ('expired', _('Expired')),
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='secure_documents'
    )
    document_type = models.CharField(
        max_length=50,
        choices=DOCUMENT_TYPES
    )
    original_filename = models.CharField(max_length=255)
    secure_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.PositiveIntegerField()
    file_hash = models.CharField(max_length=64)  # SHA-256 hash
    mime_type = models.CharField(max_length=100)
    
    # Verification and security
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUSES,
        default='pending'
    )
    is_encrypted = models.BooleanField(default=True)
    access_count = models.PositiveIntegerField(default=0)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    # Document metadata
    extracted_info = models.JSONField(default=dict, blank=True)
    verification_notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = _('secure document')
        verbose_name_plural = _('secure documents')
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['document_type']),
            models.Index(fields=['verification_status']),
            models.Index(fields=['uploaded_at']),
            models.Index(fields=['file_hash']),
        ]
        unique_together = ['user', 'document_type', 'file_hash']
    
    def __str__(self):
        return f"{self.document_type} - {self.user.email}"
    
    def get_secure_url(self, expires_in: int = 3600) -> str:
        """Get secure, time-limited URL for document access."""
        from ogamechanic.modules.file_storage_service import FileSecurityService # noqa
        return FileSecurityService.generate_secure_url(self.file_path, expires_in) # noqa
    
    def mark_as_verified(self, verified_by_user, notes: str = ""):
        """Mark document as verified."""
        self.verification_status = 'verified'
        self.verified_by = verified_by_user
        self.verified_at = timezone.now()
        self.verification_notes = notes
        self.save()
    
    def mark_as_rejected(self, notes: str = ""):
        """Mark document as rejected."""
        self.verification_status = 'rejected'
        self.verification_notes = notes
        self.save()
    
    def increment_access_count(self):
        """Increment access count and update last accessed."""
        self.access_count += 1
        self.last_accessed = timezone.now()
        self.save(update_fields=['access_count', 'last_accessed'])
    
    def is_expired(self) -> bool:
        """Check if document is expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class DocumentVerificationLog(models.Model):
    """
    Model to track document verification activities.
    """
    ACTION_TYPES = (
        ('upload', _('Upload')),
        ('verify', _('Verify')),
        ('reject', _('Reject')),
        ('access', _('Access')),
        ('delete', _('Delete')),
        ('update', _('Update')),
    )
    
    document = models.ForeignKey(
        SecureDocument,
        on_delete=models.CASCADE,
        related_name='verification_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    performed_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='document_actions'
    )
    notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('document verification log')
        verbose_name_plural = _('document verification logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['document']),
            models.Index(fields=['action']),
            models.Index(fields=['performed_by']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.action} - {self.document} by {self.performed_by.email}"


class FileSecurityAudit(models.Model):
    """
    Model to track file security and access audit trail.
    """
    AUDIT_TYPES = (
        ('access', _('Access')),
        ('upload', _('Upload')),
        ('download', _('Download')),
        ('delete', _('Delete')),
        ('modify', _('Modify')),
        ('security_check', _('Security Check')),
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='file_audits'
    )
    audit_type = models.CharField(max_length=20, choices=AUDIT_TYPES)
    file_path = models.CharField(max_length=500)
    file_hash = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('file security audit')
        verbose_name_plural = _('file security audits')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['audit_type']),
            models.Index(fields=['file_path']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['success']),
        ]
    
    def __str__(self):
        return f"{self.audit_type} - {self.user.email} - {self.file_path}"
