from django.contrib import admin
from .models import RentalBooking, RentalReview, RentalPeriod


@admin.register(RentalBooking)
class RentalBookingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer', 'product', 'start_date', 'end_date',
        'status', 'total_amount', 'booking_reference'
    ]
    list_filter = [
        'status', 'start_date', 'end_date', 'booked_at',
        'confirmed_at', 'started_at', 'completed_at'
    ]
    search_fields = [
        'customer__email', 'product__name', 'booking_reference',
        'pickup_location', 'return_location'
    ]
    readonly_fields = [
        'id', 'booking_reference', 'booked_at', 'confirmed_at',
        'started_at', 'completed_at', 'cancelled_at', 'duration_days',
        'is_active', 'can_be_cancelled'
    ]
    date_hierarchy = 'booked_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'id', 'customer', 'product', 'status', 'booking_reference')
        }),
        ('Rental Period', {
            'fields': ('start_date', 'end_date', 'start_time', 'end_time')
        }),
        ('Pricing', {
            'fields': ('daily_rate', 'total_amount', 'deposit_amount')
        }),
        ('Location', {
            'fields': (
                'pickup_location', 'return_location', 'pickup_latitude',
                'pickup_longitude', 'return_latitude', 'return_longitude'
            )
        }),
        ('Additional Information', {
            'fields': ('special_requests', 'cancellation_reason', 'notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'booked_at', 'confirmed_at', 'started_at', 'completed_at',
                'cancelled_at'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(RentalReview)
class RentalReviewAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'rental', 'customer', 'rating', 'created_at'
    ]
    list_filter = [
        'rating', 'created_at', 'updated_at'
    ]
    search_fields = [
        'rental__booking_reference', 'customer__email', 'comment'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'rental', 'customer', 'rating')
        }),
        ('Review Content', {
            'fields': ('comment',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(RentalPeriod)
class RentalPeriodAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'product', 'start_date', 'end_date', 'is_available',
        'daily_rate', 'duration_days'
    ]
    list_filter = [
        'is_available', 'start_date', 'end_date', 'created_at'
    ]
    search_fields = [
        'product__name', 'product__merchant__email', 'notes'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'duration_days', 'total_cost'
    ]
    date_hierarchy = 'start_date'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'product', 'is_available')
        }),
        ('Period Details', {
            'fields': ('start_date', 'end_date', 'daily_rate')
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
