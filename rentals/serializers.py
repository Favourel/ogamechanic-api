from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import RentalBooking, RentalReview, RentalPeriod
from products.models import Product

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for nested representations"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number']
        ref_name = "RentalsUserSerializer"


class ProductSerializer(serializers.ModelSerializer):
    """Basic product serializer for nested representations"""
    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'is_rental']
        ref_name = "RentalsProductSerializer"


class RentalBookingSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    product = ProductSerializer(read_only=True)
    customer_id = serializers.UUIDField(write_only=True, required=True)
    product_id = serializers.UUIDField(write_only=True, required=True)
    duration_days = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    can_be_cancelled = serializers.ReadOnlyField()

    class Meta:
        model = RentalBooking
        fields = [
            'id', 'customer', 'product', 'customer_id', 'product_id',
            'start_date', 'end_date', 'start_time', 'end_time',
            'daily_rate', 'total_amount', 'deposit_amount',
            'status', 'booking_reference', 'pickup_location',
            'return_location', 'pickup_latitude', 'pickup_longitude',
            'return_latitude', 'return_longitude', 'special_requests',
            'cancellation_reason', 'notes', 'booked_at', 'confirmed_at',
            'started_at', 'completed_at', 'cancelled_at',
            'duration_days', 'is_active', 'can_be_cancelled'
        ]
        read_only_fields = [
            'id', 'customer', 'product', 'booking_reference',
            'booked_at', 'confirmed_at', 'started_at', 'completed_at',
            'cancelled_at', 'duration_days', 'is_active', 'can_be_cancelled'
        ]

    def create(self, validated_data):
        customer_id = validated_data.pop('customer_id')
        product_id = validated_data.pop('product_id')
        
        validated_data['customer_id'] = customer_id
        validated_data['product_id'] = product_id
        
        return super().create(validated_data)


class RentalBookingListSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    product = ProductSerializer(read_only=True)
    duration_days = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()

    class Meta:
        model = RentalBooking
        fields = [
            'id', 'customer', 'product', 'start_date', 'end_date',
            'daily_rate', 'total_amount', 'status', 'booking_reference',
            'duration_days', 'is_active'
        ]


class RentalBookingStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalBooking
        fields = ['status', 'notes', 'cancellation_reason']


class RentalReviewSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    rental = RentalBookingListSerializer(read_only=True)
    customer_id = serializers.UUIDField(write_only=True, required=True)
    rental_id = serializers.UUIDField(write_only=True, required=True)

    class Meta:
        model = RentalReview
        fields = [
            'id', 'rental', 'customer', 'rental_id', 'customer_id',
            'rating', 'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'rental', 'customer', 'created_at', 'updated_at'
        ]

    def create(self, validated_data):
        customer_id = validated_data.pop('customer_id')
        rental_id = validated_data.pop('rental_id')
        
        validated_data['customer_id'] = customer_id
        validated_data['rental_id'] = rental_id
        
        return super().create(validated_data)


class RentalReviewListSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    rental = RentalBookingListSerializer(read_only=True)

    class Meta:
        model = RentalReview
        fields = [
            'id', 'customer', 'rental', 'rating', 'comment',
            'created_at'
        ]


class RentalPeriodSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.UUIDField(write_only=True, required=True)
    duration_days = serializers.ReadOnlyField()
    total_cost = serializers.ReadOnlyField()

    class Meta:
        model = RentalPeriod
        fields = [
            'id', 'product', 'product_id', 'start_date', 'end_date',
            'is_available', 'daily_rate', 'notes', 'created_at',
            'updated_at', 'duration_days', 'total_cost'
        ]
        read_only_fields = [
            'id', 'product', 'created_at', 'updated_at',
            'duration_days', 'total_cost'
        ]

    def create(self, validated_data):
        product_id = validated_data.pop('product_id')
        validated_data['product_id'] = product_id
        return super().create(validated_data)


class RentalPeriodListSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    duration_days = serializers.ReadOnlyField()
    total_cost = serializers.ReadOnlyField()

    class Meta:
        model = RentalPeriod
        fields = [
            'id', 'product', 'start_date', 'end_date', 'is_available',
            'daily_rate', 'duration_days', 'total_cost'
        ] 