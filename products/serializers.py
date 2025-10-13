from rest_framework import serializers
from .models import (Category, Product, ProductImage, 
                     ProductVehicleCompatibility, Order, OrderItem, Cart, 
                     CartItem, ProductReview, FollowMerchant, FavoriteProduct)
from users.serializers import MechanicProfileSerializer, UserSerializer
from django.db.models import Avg


class CategorySerializer(serializers.ModelSerializer):
    sub_categories = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'sub_categories', 'description', 
            'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_sub_categories(self, obj):
        if obj.parent_category is None:
            return CategorySerializer(
                obj.models.all(), many=True
            ).data
        return []


class ProductVehicleCompatibilitySerializer(serializers.Serializer):
    """Serializer for ProductVehicleCompatibility model with array support"""
    make = serializers.IntegerField()
    model = serializers.ListField(
        child=serializers.IntegerField(), 
        required=False,
        allow_empty=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class ProductVehicleCompatibilityReadSerializer(serializers.ModelSerializer):
    """Serializer for reading ProductVehicleCompatibility model"""
    make_name = serializers.CharField(source='make.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    
    class Meta:
        model = ProductVehicleCompatibility
        fields = [
            'id', 'make', 'model', 'make_name', 'model_name',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'make_name', 'model_name'
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    # For reading: return absolute URL; for writing/updating: accept file upload # noqa
    image = serializers.ImageField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'ordering', 'created_at']
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        """Override to return absolute URL for image field."""
        representation = super().to_representation(instance)
        request = self.context.get('request', None)
        image_field = instance.image
        if image_field and hasattr(image_field, 'url'):
            image_url = image_field.url
            if request is not None:
                representation['image'] = request.build_absolute_uri(image_url)
            else:
                from django.conf import settings
                if hasattr(settings, "SITE_DOMAIN"):
                    representation['image'] = f"{settings.SITE_DOMAIN}{image_url}" # noqa
                else:
                    representation['image'] = image_url
        else:
            representation['image'] = None
        return representation


class ProductImageUpdateSerializer(serializers.Serializer):
    image_id = serializers.IntegerField()
    ordering = serializers.IntegerField(required=False)
    image = serializers.ImageField(required=False)


class ProductSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField(read_only=True)
    category = serializers.SerializerMethodField(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True,
    )
    sub_category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True,
    )
    make = serializers.CharField(source='make.name', read_only=True)
    model = serializers.CharField(source='model.name', read_only=True)
    merchant_id = serializers.CharField(source='merchant.id', read_only=True)
    merchant_email = serializers.CharField(
        source='merchant.email', read_only=True)
    vehicle_compatibility = ProductVehicleCompatibilityReadSerializer(
        many=True, read_only=True)

    rating = serializers.SerializerMethodField()
    merchant_rating = serializers.SerializerMethodField()
    purchased_count = serializers.IntegerField(
        source="total_purchased", read_only=True)
    is_in_cart = serializers.BooleanField(read_only=True)
    is_in_favorite_list = serializers.BooleanField(read_only=True)

    DELIVERY_OPTION_CHOICES = [
        ('pickup', 'Pick-up only'),
        ('nationwide', 'Nationwide delivery'),
        ('international', 'International shipping'),
    ]
    availability = serializers.ChoiceField(
        choices=Product.AVAILABILITY_CHOICES,
        error_messages={
            "invalid_choice": "Invalid delivery option. Allowed values are: in_stock, reserved, sold." # noqa
        }
    )
    delivery_option = serializers.ChoiceField(
        choices=DELIVERY_OPTION_CHOICES,
        error_messages={
            "invalid_choice": "Invalid delivery option. Allowed values are: pickup, nationwide, international." # noqa
        }
    )
    fuel_type = serializers.ChoiceField(
        choices=Product.FUEL_TYPE_CHOICES,
        required=False,
        error_messages={
            "invalid_choice": (
                "Invalid fuel type. Allowed values are: " +
                ", ".join([c[0] for c in [
                    ('petrol', 'Petrol'),
                    ('diesel', 'Diesel'),
                    ('electric', 'Electric'),
                    ('hybrid', 'Hybrid'),
                    ('lpg', 'LPG'),
                    ('other', 'Other'),
                ]]) + "."
            )
        }
    )
    condition = serializers.ChoiceField(
        choices=Product.CONDITION_CHOICES,
        required=False,
        error_messages={
            "invalid_choice": (
                "Invalid condition. Allowed values are: " +
                ", ".join([c[0] for c in Product.CONDITION_CHOICES]) + "."
            )
        }
    )
    body_type = serializers.ChoiceField(
        choices=Product.BODY_TYPE_CHOICES,
        required=False,
        error_messages={
            "invalid_choice": (
                "Invalid body type. Allowed values are: " +
                ", ".join([c[0] for c in Product.BODY_TYPE_CHOICES]) + "."
            )
        }
    )
    transmission = serializers.ChoiceField(
        choices=Product.TRANSMISSION_CHOICES,
        required=False,
        error_messages={
            "invalid_choice": (
                "Invalid transmission. Allowed values are: " +
                ", ".join([c[0] for c in Product.TRANSMISSION_CHOICES]) + "."
            )
        }
    )
    mileage_unit = serializers.ChoiceField(
        choices=[
            ('km', 'Kilometers'),
            ('mi', 'Miles'),
        ],
        required=False,
        error_messages={
            "invalid_choice": "Invalid mileage unit. Allowed values are: km, mi." # noqa
        }
    )

    class Meta:
        model = Product
        fields = [
            'id',
            'merchant_id',
            'merchant_email',
            'category',
            'category_id',
            'sub_category_id',
            'name',
            'make',
            'make_id',
            'model',
            'model_id',
            'year',
            'condition',
            'body_type',
            'mileage',
            'mileage_unit',
            'transmission',
            'fuel_type',
            'engine_size',
            'exterior_color',
            'interior_color',
            'number_of_doors',
            'number_of_seats',
            'air_conditioning',
            'leather_seats',
            'navigation_system',
            'bluetooth',
            'parking_sensors',
            'cruise_control',
            'keyless_entry',
            'sunroof',
            'alloy_wheels',
            'description',
            'price',
            'currency',
            'negotiable',
            'discount',
            'availability',
            'stock',
            'is_rental',
            'airbags',
            'abs',
            'traction_control',
            'lane_assist',
            'blind_spot_monitor',
            'delivery_option',
            'images',
            'vehicle_compatibility',
            'created_at',
            'updated_at',
            'rating',
            'merchant_rating',
            'purchased_count',
            'contact_info',
            'is_in_cart',
            'is_in_favorite_list',
        ]
        read_only_fields = [
            'id',
            'merchant_id',
            'merchant_email',
            'make',
            'model',
            'images',
            'vehicle_compatibility',
            'created_at',
            'updated_at',
            'make_id',
            'model_id',
            'category',
            'rating',
            'merchant_rating',
            'purchased_count',
            'is_in_cart',
            'is_in_favorite_list',
        ]
        ref_name = "ProductsProductSerializer"

    def get_images(self, obj):
        request = self.context.get('request', None)
        images = obj.images.all()
        serializer = ProductImageSerializer(
            images, many=True, context={'request': request}
        )
        return serializer.data

    def get_category(self, obj):
        return CategorySerializer(obj.category).data if obj.category else None

    # def get_merchant(self, obj):
    #     return UserSerializer(obj.merchant).data if obj.merchant else None

    def get_rating(self, obj):
        """Return pre-annotated average rating if available"""
        if hasattr(obj, "avg_rating") and obj.avg_rating is not None:
            return round(obj.avg_rating, 1)
        return None

    def get_merchant_rating(self, obj):
        """Efficiently compute average rating for merchant’s products"""
        merchant = obj.merchant
        if not merchant:
            return None
        avg = (
            ProductReview.objects.filter(product__merchant=merchant)
            .aggregate(avg_rating=Avg("rating"))
            .get("avg_rating")
        )
        return round(avg, 1) if avg else None


class ProductCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating products with vehicle compatibility support"""
    vehicle_compatibility = ProductVehicleCompatibilitySerializer(
        many=True, required=False
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True,
    )
    # Subcategory is only required (and visible) when creating a Spare Part product  # noqa
    sub_category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category',
        write_only=True, required=False,
    )

    class Meta:
        model = Product
        fields = [
            'category_id', 'sub_category_id', 'name', 'make', 'make_id',
            'model', 'year', 'condition',
            'body_type', 'mileage', 'mileage_unit', 'transmission', 
            'fuel_type', 'engine_size', 'exterior_color', 'interior_color', 
            'model', 'model_id',
            'number_of_doors', 'number_of_seats', 'air_conditioning', 
            'leather_seats', 'navigation_system', 'bluetooth', 
            'parking_sensors', 'cruise_control', 'keyless_entry',
            'sunroof', 'alloy_wheels', 'description', 'price', 'currency',
            'negotiable', 'discount', 'availability', 'stock', 'is_rental',
            'airbags', 'abs', 'traction_control', 'lane_assist', 
            'blind_spot_monitor', 'delivery_option', 'vehicle_compatibility',
            'contact_info'
        ]

    def validate(self, attrs):
        # Category/Subcategory logic
        category = attrs.get('category_id')
        sub_category = attrs.get('sub_category_id', None)

        contact_info = attrs.get('contact_info', None)
        if contact_info:
            try:
                from ogamechanic.modules.utils import format_phone_number
                attrs['contact_info'] = format_phone_number(contact_info)
            except Exception as e:
                raise serializers.ValidationError({
                    "contact_info": f"Invalid phone number format: {str(e)}"
                })

        # Fetch the real category instance if not passed directly
        if isinstance(category, int):
            from .models import Category
            category = Category.objects.filter(id=category).first()

        # If "Spare Part" (or similar) is chosen as the category, sub_category_id is required  # noqa
        # If "Car" is chosen, sub_category_id is not required and should be null or absent  # noqa
        if category is not None:
            if hasattr(category, 'name'):
                name = category.name.lower()
            else:
                name = str(category).lower()
            if name in ['spare part', 'spare parts']:
                if not sub_category:
                    raise serializers.ValidationError({
                        "sub_category_id": "This field is required when Spare Part is selected as the category."  # noqa
                    })
            elif name in ['car', 'cars']:
                attrs['sub_category'] = None

        # Vehicle compatibility validation
        vehicle_compatibility_data = attrs.get('vehicle_compatibility', [])
        if vehicle_compatibility_data:
            from mechanics.models import VehicleMake
            for idx, compatibility_data in enumerate(vehicle_compatibility_data): # noqa
                make_id = compatibility_data.get('make')
                model_ids = compatibility_data.get('model', [])
                # Validate that make_id exists
                try:
                    make_obj = VehicleMake.objects.get(id=make_id)
                except VehicleMake.DoesNotExist:
                    raise serializers.ValidationError({
                        f"vehicle_compatibility[{idx}].make": f"Vehicle make with ID {make_id} does not exist."  # noqa
                    })
                # If models provided, ensure each model belongs to the make
                if model_ids:
                    for model_id in model_ids:
                        try:
                            model_obj = VehicleMake.objects.get(id=model_id)
                        except VehicleMake.DoesNotExist:
                            raise serializers.ValidationError({
                                f"vehicle_compatibility[{idx}].model": f"Vehicle model with ID {model_id} does not exist."  # noqa
                            })
                        # Model's parent_make_id field must match
                        parent_id = getattr(model_obj, 'parent_make_id', None)
                        if parent_id != make_obj.id:
                            raise serializers.ValidationError({
                                f"vehicle_compatibility[{idx}].model": (
                                    f"Model '{model_obj.name}' (ID {model_id}) does not belong to Make '{make_obj.name}' (ID {make_id})."  # noqa
                                )
                            })

        return attrs

    def create(self, validated_data):
        vehicle_compatibility_data = validated_data.pop(
            'vehicle_compatibility', []
        )
        sub_category = validated_data.pop('sub_category', None)
        product = Product.objects.create(**validated_data)
        if sub_category:
            product.sub_category = sub_category
            product.save()
        
        # Create vehicle compatibility entries
        from mechanics.models import VehicleMake
        for compatibility_data in vehicle_compatibility_data:
            make_id = compatibility_data['make']
            model_ids = compatibility_data.get('model', [])
            notes = compatibility_data.get('notes', '')

            # Defensive: ensure make exists
            try:
                make_obj = VehicleMake.objects.get(id=make_id)
            except VehicleMake.DoesNotExist:
                raise serializers.ValidationError({
                    "vehicle_compatibility": f"Vehicle make with ID {make_id} does not exist."  # noqa
                })
            
            if not model_ids:
                ProductVehicleCompatibility.objects.create(
                    product=product,
                    make=make_obj,
                    notes=notes
                )
            else:
                for model_id in model_ids:
                    try:
                        model_obj = VehicleMake.objects.get(id=model_id)
                    except VehicleMake.DoesNotExist:
                        raise serializers.ValidationError({
                            "vehicle_compatibility": f"Vehicle model with ID {model_id} does not exist."  # noqa
                        })
                    # Defensive: ensure model belongs to make
                    parent_id = getattr(model_obj, 'parent_make_id', None)
                    if parent_id != make_obj.id:
                        raise serializers.ValidationError({
                            "vehicle_compatibility": (
                                f"Model '{model_obj.name}' (ID {model_id}) does not belong to Make '{make_obj.name}' (ID {make_id})."  # noqa
                            )
                        })
                    ProductVehicleCompatibility.objects.create(
                        product=product,
                        make=make_obj,
                        model=model_obj,
                        notes=notes
                    )
        return product

    def update(self, instance, validated_data):
        vehicle_compatibility_data = validated_data.pop(
            'vehicle_compatibility', None)
        sub_category = validated_data.pop('sub_category', None)

        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if sub_category is not None:
            instance.sub_category = sub_category
        instance.save()

        if vehicle_compatibility_data is not None:
            from mechanics.models import VehicleMake
            instance.vehicle_compatibility.all().delete()
            for compatibility_data in vehicle_compatibility_data:
                make_id = compatibility_data['make']
                model_ids = compatibility_data.get('model', [])
                notes = compatibility_data.get('notes', '')

                # Defensive: ensure make exists
                try:
                    make_obj = VehicleMake.objects.get(id=make_id)
                except VehicleMake.DoesNotExist:
                    raise serializers.ValidationError({
                        "vehicle_compatibility": f"Vehicle make with ID {make_id} does not exist."  # noqa
                    })

                if not model_ids:
                    ProductVehicleCompatibility.objects.create(
                        product=instance,
                        make=make_obj,
                        notes=notes
                    )
                else:
                    for model_id in model_ids:
                        try:
                            model_obj = VehicleMake.objects.get(id=model_id)
                        except VehicleMake.DoesNotExist:
                            raise serializers.ValidationError({
                                "vehicle_compatibility": f"Vehicle model with ID {model_id} does not exist." # noqa
                            })
                        # Defensive: ensure model belongs to make
                        parent_id = getattr(model_obj, 'parent_make_id', None)
                        if parent_id != make_obj.id:
                            raise serializers.ValidationError({
                                "vehicle_compatibility": (
                                    f"Model '{model_obj.name}' (ID {model_id}) does not belong to Make '{make_obj.name}' (ID {make_id})."  # noqa
                                )
                            })
                        ProductVehicleCompatibility.objects.create(
                            product=instance,
                            make_id=make_id,
                            model_id=model_id,
                            notes=notes
                        )
        return instance

    # def get_rating(self, obj):
    #     reviews = obj.reviews.all()
    #     if not reviews.exists():
    #         return None
    #     avg = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
    #     return round(avg, 1) if avg is not None else None

    # def get_merchant_rating(self, obj):
    #     merchant = obj.merchant
    #     if not merchant:
    #         return None
    #     products = Product.objects.filter(merchant=merchant)
    #     reviews = ProductReview.objects.filter(product__in=products)
    #     if not reviews.exists():
    #         return None
    #     avg = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
    #     return round(avg, 1) if avg is not None else None

    # def get_purchased_count(self, obj):
    #     from django.db.models import Sum
    #     return (
    #         OrderItem.objects.filter(
    #             product=obj,
    #             order__status='paid'
    #         ).aggregate(
    #             total_purchased=Sum('quantity')
    #         )['total_purchased'] or 0
    #     )

    # def get_is_in_cart(self, obj):
    #     request = self.context.get('request', None)
    #     if request is None or not hasattr(request, "user") or not request.user.is_authenticated:  # noqa
    #         return False
    #     from .models import CartItem, Cart
    #     try:
    #         cart = Cart.objects.get(user=request.user)
    #     except Cart.DoesNotExist:
    #         return False
    #     return CartItem.objects.filter(cart=cart, product=obj).exists()

    # def get_is_in_favorite_list(self, obj):
    #     request = self.context.get('request', None)
    #     if request is None or not hasattr(request, "user") or not request.user.is_authenticated: # noqa
    #         return False
    #     from .models import FavoriteProduct
    #     return FavoriteProduct.objects.filter(product=obj, user=request.user).exists() # noqa


class HomeResponseSerializer(serializers.Serializer):
    mechanics = MechanicProfileSerializer(many=True)
    best_selling_cars = ProductSerializer(many=True)
    best_selling_spare_parts = ProductSerializer(many=True)


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_id', 'quantity', 'price'
        ]
        read_only_fields = [
            'id', 'product', 'price'
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    customer = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'status', 'total_amount', 'items',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'customer', 'status', 'total_amount',
            'created_at', 'updated_at'
        ]

    # def validate_items(self, value):
    #     if not value:
    #         raise serializers.ValidationError(
    #             'Order must have at least one item.'
    #         )
    #     for item in value:
    #         if item['quantity'] < 1:
    #             raise serializers.ValidationError(
    #                 'Quantity must be at least 1.'
    #             )
    #     return value

    # def create(self, validated_data):
    #     items_data = validated_data.pop('items')
    #     customer = self.context['request'].user
    #     order = Order.objects.create(customer=customer)
    #     total = 0
    #     for item in items_data:
    #         product = item['product']
    #         quantity = item['quantity']
    #         price = product.price
    #         total += price * quantity
    #         OrderItem.objects.create(
    #             order=order,
    #             product=product,
    #             quantity=quantity,
    #             price=price
    #         )
    #     order.total_amount = total
    #     order.save()
    #     return order


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    # product_id = serializers.PrimaryKeyRelatedField(
    #     queryset=Product.objects.all(),
    #     source='product',
    #     write_only=True
    # )

    class Meta:
        model = CartItem
        fields = [
            'id', 
            'product', 
            # 'product_id', 
            'quantity', 'added_at'
        ]
        read_only_fields = [
            'id', 
            'product', 
            'added_at'
        ]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'items', 'total_price',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'items', 'total_price',
            'created_at', 'updated_at'
        ]

    def get_total_price(self, obj):
        return sum(
            item.product.price * item.quantity
            for item in obj.items.all()
        )


class ProductReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )

    class Meta:
        model = ProductReview
        fields = [
            'id', 'product', 'product_id', 'user', 'rating',
            'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at', 'product'
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        product = attrs.get('product')
        if (
            self.instance is None and
            ProductReview.objects.filter(user=user, product=product).exists()
        ):
            raise serializers.ValidationError(
                'You have already reviewed this product.'
            )
        return attrs


class FollowMerchantSerializer(serializers.ModelSerializer):
    """Serializer for FollowMerchant model"""
    merchant_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = FollowMerchant
        fields = ['id', 'merchant_id', 'created_at']
        read_only_fields = [
            'id', 'created_at', 'merchant_id'
        ]
    
    def validate_merchant_id(self, value):
        """Validate that the merchant exists and has merchant role"""
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        try:
            merchant = User.objects.get(id=value)
            if not merchant.roles.filter(name='merchant').exists():
                raise serializers.ValidationError(
                    "User is not a merchant."
                )
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Merchant not found."
            )


class FavoriteProductSerializer(serializers.ModelSerializer):
    """Serializer for FavoriteProduct model"""
    product_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = FavoriteProduct
        fields = [
            'id',
            'product',
            'product_id',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'product']

    def validate_product_id(self, value):
        """Validate that the product exists"""
        try:
            Product.objects.get(id=value)
            return value  # Return the UUID value, not the product object
        except Product.DoesNotExist:
            raise serializers.ValidationError(
                "Product not found."
            )

    def create(self, validated_data):
        """Create FavoriteProduct with product_id mapped to product field"""
        product_id = validated_data.pop('product_id')
        product = Product.objects.get(id=product_id)
        validated_data['product'] = product
        return super().create(validated_data)


class FollowMerchantListSerializer(serializers.ModelSerializer):
    """Serializer for listing followed merchants"""
    merchant = UserSerializer(read_only=True)
    merchant_profile = serializers.SerializerMethodField()
    
    class Meta:
        model = FollowMerchant
        fields = ['id', 'merchant', 'merchant_profile', 'created_at']
    
    def get_merchant_profile(self, obj):
        """Get merchant profile information"""
        from users.serializers import MerchantProfileSerializer
        try:
            profile = obj.merchant.merchant_profile
            return MerchantProfileSerializer(profile).data
        except Exception:
            return None


class FavoriteProductListSerializer(serializers.ModelSerializer):
    """Serializer for listing favorite products"""
    product = ProductSerializer(read_only=True)
    is_in_favorite_list = serializers.SerializerMethodField()
    
    class Meta:
        model = FavoriteProduct
        fields = ['id', 'product', 'created_at', 'is_in_favorite_list']
        read_only_fields = [
            'is_in_favorite_list',
            'id',
            'product',
            'created_at'
        ]

    def get_is_in_favorite_list(self, obj):
        """
        Returns True if the current user has this product
        in their favorite list, else False.
        """
        request = self.context.get('request', None)
        if request is None or not request.user or not request.user.is_authenticated: # noqa
            return False
        # Import here to avoid circular import
        from .models import FavoriteProduct

        return FavoriteProduct.objects.filter(product=obj).exists()
