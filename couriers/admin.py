from django.contrib import admin
from .models import DeliveryRequest, DeliveryTracking, CourierRating


@admin.register(DeliveryRequest)
class CourierRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer', 'driver', 'pickup_address_preview', 
        'delivery_address_preview', 'status', 'total_fare', 
        'requested_at', 'is_active'
    ]
    list_filter = [
        'status', 'payment_method', 'payment_status', 
        'is_fragile', 'requires_signature', 'requested_at'
    ]
    search_fields = [
        'customer__email', 'driver__email', 'pickup_address', 
        'delivery_address', 'package_description'
    ]
    readonly_fields = [
        'id', 'requested_at', 'assigned_at', 'picked_up_at', 
        'delivered_at', 'cancelled_at', 'last_location_update',
        'estimated_distance', 'estimated_duration', 'base_fare', 
        'distance_fare', 'total_fare', 'is_active', 'can_be_cancelled'
    ]
    date_hierarchy = 'requested_at'
    list_per_page = 20
    
    def pickup_address_preview(self, obj):
        return obj.pickup_address[:50] + '...' if len(obj.pickup_address) > 50 else obj.pickup_address
    pickup_address_preview.short_description = 'Pickup Address'
    
    def delivery_address_preview(self, obj):
        return obj.delivery_address[:50] + '...' if len(obj.delivery_address) > 50 else obj.delivery_address
    delivery_address_preview.short_description = 'Delivery Address'


@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'delivery_request', 'driver', 'latitude', 'longitude', 
        'status', 'timestamp'
    ]
    list_filter = ['timestamp', 'status']
    search_fields = [
        'delivery_request__id', 'driver__email', 'status', 'notes'
    ]
    readonly_fields = ['id', 'timestamp']
    date_hierarchy = 'timestamp'
    list_per_page = 50


@admin.register(CourierRating)
class CourierRatingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'delivery_request', 'customer', 'driver', 
        'overall_rating', 'average_rating', 'created_at'
    ]
    list_filter = [
        'overall_rating', 'delivery_speed_rating', 
        'service_quality_rating', 'communication_rating', 'created_at'
    ]
    search_fields = [
        'delivery_request__id', 'customer__email', 'driver__email', 
        'review'
    ]
    readonly_fields = [
        'id', 'delivery_request', 'customer', 'driver', 
        'created_at', 'updated_at', 'average_rating'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 20
