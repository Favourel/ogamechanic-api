from rest_framework import serializers
from .models import (Category, Product, ProductImage, 
                     Order, OrderItem, Cart, CartItem, ProductReview,
                     FollowMerchant, FavoriteProduct)
from users.serializers import MechanicProfileSerializer, UserSerializer
from django.db.models import Avg


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'ordering', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_image(self, obj):
        request = self.context.get('request', None)
        if obj.image and hasattr(obj.image, 'url'):
            image_url = obj.image.url
            if request is not None:
                return request.build_absolute_uri(image_url)
            # Fallback: try to build absolute URL manually if possible
            from django.conf import settings
            if hasattr(settings, "SITE_DOMAIN"):
                return f"{settings.SITE_DOMAIN}{image_url}"
            return image_url
        return None


class ProductSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True
    )
    merchant = UserSerializer(read_only=True)
    rating = serializers.SerializerMethodField()
    merchant_rating = serializers.SerializerMethodField()
    purchased_count = serializers.SerializerMethodField()
    is_in_cart = serializers.SerializerMethodField()
    is_in_favorite_list = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'merchant', 'category', 'category_id', 'name',
            'description', 'price', 'is_rental', 'images',
            'created_at', 'updated_at', 'rating', 
            'merchant_rating', 'stock', 'purchased_count', 'is_in_cart',
            'is_in_favorite_list'
        ]
        read_only_fields = [
            'id', 'merchant', 'images', 'created_at', 
            'updated_at', 'category', 'stock', 
            'purchased_count', 'merchant_rating', 'is_in_cart',
            'is_in_favorite_list'
        ]
        ref_name = "ProductsProductSerializer"

    def get_images(self, obj):
        request = self.context.get('request', None)
        images = obj.images.all()
        serializer = ProductImageSerializer(
            images, many=True, context={'request': request})
        return serializer.data

    def get_rating(self, obj):
        # Calculate average rating for the product
        reviews = obj.reviews.all()
        if not reviews.exists():
            return None
        avg = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
        # Optionally round to 1 decimal place
        return round(avg, 1) if avg is not None else None

    def get_merchant_rating(self, obj):
        # Calculate average rating for all products of this merchant
        merchant = obj.merchant
        if not merchant:
            return None
        # Get all products for this merchant
        products = Product.objects.filter(merchant=merchant)
        # Get all reviews for these products
        reviews = ProductReview.objects.filter(product__in=products)
        if not reviews.exists():
            return None
        avg = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
        return round(avg, 1) if avg is not None else None

    def get_purchased_count(self, obj):
        # Count the number of successfully purchased items for this product
        # Assuming 'OrderItem' and 'Order' are imported and 'Order' has a 'status' field that marks successful purchases, e.g., 'paid' # noqa
        return OrderItem.objects.filter(
            product=obj,
            order__status='paid'
        ).aggregate(
            total_purchased=serializers.models.Sum('quantity')
        )['total_purchased'] or 0

    def get_is_in_cart(self, obj):
        """
        Returns True if the current user has this product 
        in their cart, else False.
        """
        request = self.context.get('request', None)
        if request is None or not request.user or not request.user.is_authenticated: # noqa
            return False
        # Import here to avoid circular import
        from .models import CartItem, Cart
        try:
            cart = Cart.objects.get(user=request.user)
            
        except Cart.DoesNotExist:
            return False
        return CartItem.objects.filter(cart=cart, product=obj).exists()

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
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )

    class Meta:
        model = CartItem
        fields = [
            'id', 
            'product', 
            'product_id', 'quantity', 'added_at'
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
