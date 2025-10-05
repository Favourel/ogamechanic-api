import uuid
from django.db import models
from django.conf import settings


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    # Use uuid.uuid7 if available, else fallback to uuid4
    try:
        id = models.UUIDField(
            primary_key=True,
            default=uuid.uuid7,
            editable=False
        )
    except AttributeError:
        id = models.UUIDField(
            primary_key=True,
            default=uuid.uuid4,
            editable=False
        )

    merchant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='products'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        null=True,
        blank=True
    )

    # Car Name / Listing Name
    name = models.CharField(
        max_length=255,
        help_text="Short descriptive name, e.g., '2019 Toyota Corolla LE'"
    )

    # Make, Model, Year
    from mechanics.models import VehicleMake

    make = models.ForeignKey(
        VehicleMake,
        on_delete=models.PROTECT,
        help_text="Car manufacturer, e.g., Toyota, Honda",
        null=True,
        blank=True,
        related_name="products_by_make"
    )
    model = models.ForeignKey(
        VehicleMake,
        on_delete=models.PROTECT,
        help_text="Car model, e.g., Camry, Civic",
        null=True,
        blank=True,
        related_name="products_by_model"
    )
    year = models.PositiveIntegerField(
        help_text="Year of manufacture, e.g., 2019",
        null=True,
        blank=True,
    )

    # Condition
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('used', 'Used'),
        ('certified', 'Certified Pre-owned'),
        ('other', 'Other'),
    ]
    condition = models.CharField(
        max_length=16,
        choices=CONDITION_CHOICES,
        default='other'
    )

    # Body Type
    BODY_TYPE_CHOICES = [
        ('sedan', 'Sedan'),
        ('suv', 'SUV'),
        ('hatchback', 'Hatchback'),
        ('coupe', 'Coupe'),
        ('truck', 'Truck'),
        ('van', 'Van'),
        ('convertible', 'Convertible'),
        ('wagon', 'Wagon'),
        ('other', 'Other'),
    ]
    body_type = models.CharField(
        max_length=16,
        choices=BODY_TYPE_CHOICES,
        default='other'
    )

    # Mileage / Odometer
    mileage = models.PositiveIntegerField(
        help_text="Mileage/Odometer reading",
        null=True,
        blank=True,
    )
    MILEAGE_UNIT_CHOICES = [
        ('km', 'Kilometers'),
        ('mi', 'Miles'),
    ]
    mileage_unit = models.CharField(
        max_length=2,
        choices=MILEAGE_UNIT_CHOICES,
        default='km'
    )

    # Transmission
    TRANSMISSION_CHOICES = [
        ('automatic', 'Automatic'),
        ('manual', 'Manual'),
        ('cvt', 'CVT'),
        ('semi-automatic', 'Semi-automatic'),
        ('other', 'Other'),
    ]
    transmission = models.CharField(
        max_length=16,
        choices=TRANSMISSION_CHOICES,
        default='other'
    )

    # Fuel Type
    FUEL_TYPE_CHOICES = [
        ('petrol', 'Petrol'),
        ('diesel', 'Diesel'),
        ('electric', 'Electric'),
        ('hybrid', 'Hybrid'),
        ('lpg', 'LPG'),
        ('other', 'Other'),
    ]
    fuel_type = models.CharField(
        max_length=16,
        choices=FUEL_TYPE_CHOICES,
        default='other'
    )

    # Engine Size / Power
    engine_size = models.CharField(
        max_length=32,
        help_text="e.g., 2.0L, 150hp",
        null=True,
        blank=True,
    )

    # Color (Exterior & Interior)
    exterior_color = models.CharField(
        max_length=32,
        help_text="Exterior color",
        null=True,
        blank=True,
    )
    interior_color = models.CharField(
        max_length=32,
        help_text="Interior color",
        null=True,
        blank=True,
    )

    # Number of Doors & Seats
    number_of_doors = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    number_of_seats = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    # Features (Dropdowns/Booleans)
    air_conditioning = models.BooleanField(
        default=False,
        help_text="Air Conditioning / Climate Control"
    )
    leather_seats = models.BooleanField(
        default=False,
        help_text="Leather Seats"
    )
    navigation_system = models.BooleanField(
        default=False,
        help_text="Navigation / Infotainment System"
    )
    bluetooth = models.BooleanField(
        default=False,
        help_text="Bluetooth / AUX / USB"
    )
    parking_sensors = models.BooleanField(
        default=False,
        help_text="Parking Sensors / Reverse Camera"
    )
    cruise_control = models.BooleanField(
        default=False,
        help_text="Cruise Control"
    )
    keyless_entry = models.BooleanField(
        default=False,
        help_text="Keyless Entry / Push Start"
    )
    sunroof = models.BooleanField(
        default=False,
        help_text="Sunroof / Panoramic Roof"
    )
    alloy_wheels = models.BooleanField(
        default=False,
        help_text="Alloy Wheels"
    )
    airbags = models.BooleanField(
        default=False,
        help_text="Airbags"
    )
    abs = models.BooleanField(
        default=False,
        help_text="Anti-lock Braking System (ABS)"
    )
    traction_control = models.BooleanField(
        default=False,
        help_text="Traction Control"
    )
    lane_assist = models.BooleanField(
        default=False,
        help_text="Lane Assist"
    )
    blind_spot_monitor = models.BooleanField(
        default=False,
        help_text="Blind Spot Monitor"
    )
    # safety_features = models.TextField(
    #     blank=True,
    #     help_text="Comma-separated list of safety features (e.g., Airbags, ABS, Traction Control, Lane Assist, Blind Spot Monitor, etc.)" # noqa
    # )

    # Description
    description = models.TextField(blank=True)

    # Pricing & Availability
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    currency = models.CharField(
        max_length=8,
        default='NGN',
        help_text="Currency code, e.g., NGN, USD"
    )
    negotiable = models.BooleanField(
        default=False,
        help_text="Is the price negotiable?"
    )
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Discount amount, if any"
    )
    AVAILABILITY_CHOICES = [
        ('in_stock', 'In stock'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
    ]
    availability = models.CharField(
        max_length=16,
        choices=AVAILABILITY_CHOICES,
        default='in_stock'
    )

    # Stock (for multiple units, e.g., fleet sales)
    stock = models.PositiveIntegerField(default=1)

    # Rental Option (if applicable)
    is_rental = models.BooleanField(default=False)

    # Pick-up / Delivery Option
    DELIVERY_OPTION_CHOICES = [
        ('pickup', 'Pick-up only'),
        ('nationwide', 'Nationwide delivery'),
        ('international', 'International shipping'),
    ]
    delivery_option = models.CharField(
        max_length=16,
        choices=DELIVERY_OPTION_CHOICES,
        default='pickup'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['merchant']),
            models.Index(fields=['name']),
            models.Index(fields=['make']),
            models.Index(fields=['model']),
            models.Index(fields=['year']),
            models.Index(fields=['condition']),
            models.Index(fields=['body_type']),
            models.Index(fields=['price']),
            models.Index(fields=['availability']),
            models.Index(fields=['is_rental']),
            models.Index(fields=['stock']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.year} {self.make} {self.model}) by {self.merchant.email}" # noqa


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images'
    )
    image = models.ImageField(upload_to='products/images/')
    ordering = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ordering', 'created_at']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['ordering']),
        ]

    def __str__(self):
        return f"Image for {self.product.name} ({self.product.merchant.email})"

    def get_image_url(self):
        if not self.image:
            return None
        else:
            return self.image.url


ORDER_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('paid', 'Paid'),
    ('shipped', 'Shipped'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    status = models.CharField(
        max_length=32,
        choices=ORDER_STATUS_CHOICES,
        default='pending'
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Order {self.id} by {self.customer.email}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, 
                              on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2)  # price at time of order # noqa

    class Meta:
        indexes = [
            models.Index(fields=['order']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f"{self.product.name} x{self.quantity} (Order {self.order.id})"


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.email}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, 
                             related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'product')
        indexes = [
            models.Index(fields=['cart']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f"{self.product.name} x{self.quantity} (Cart {self.cart.id})"


PAYMENT_METHOD_CHOICES = [
    ('online', 'Online (Paystack)'),
    ('cash_on_delivery', 'Cash on Delivery'),
]

PAYMENT_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('paid', 'Paid'),
    ('failed', 'Failed'),
    ('refunded', 'Refunded'),
]

# Update Order model
Order.add_to_class('payment_method', models.CharField(
    max_length=32,
    choices=PAYMENT_METHOD_CHOICES,
    default='online',
))
Order.add_to_class('payment_status', models.CharField(
    max_length=32,
    choices=PAYMENT_STATUS_CHOICES,
    default='pending',
))
Order.add_to_class('payment_reference', models.CharField(
    max_length=128,
    blank=True,
    null=True,
))
Order.add_to_class('paid_at', models.DateTimeField(
    blank=True,
    null=True,
))


class ProductReview(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_reviews'
    )
    rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return (
            f"Review by {self.user.email} for {self.product.name}"
        )


# Add average rating method to Product
setattr(
    Product,
    'average_rating',
    lambda self: self.reviews.aggregate(
        avg=models.Avg('rating')
    )['avg'] or 0
)


class FollowMerchant(models.Model):
    """
    Model to track which merchants a user follows
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='following_merchants'
    )
    merchant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='followers',
        limit_choices_to={'roles__name': 'merchant'}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'merchant')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['merchant']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} follows {self.merchant.email}"


class FavoriteProduct(models.Model):
    """
    Model to track which products a user has favorited
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorite_products'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='favorited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['product']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} favorited {self.product.name}"
