from .models import Ride
from django.contrib import admin


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'customer', 'driver', 'pickup_address', 'dropoff_address',
        'status', 'fare', 'requested_at', 'distance_km', 'duration_min'
    )
    list_filter = (
        'status', 'requested_at', 'customer', 'driver'
    )
    search_fields = (
        'id', 'customer__email', 'driver__email', 'pickup_address',
        'dropoff_address'
    )
    readonly_fields = (
        'requested_at', 'accepted_at', 'started_at', 'completed_at',
        'cancelled_at'
    )
    autocomplete_fields = ('customer', 'driver')
    list_per_page = 15  # Enable pagination, 15 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200
