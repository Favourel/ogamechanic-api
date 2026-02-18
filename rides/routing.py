from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Ride tracking
    re_path(
        r'ws/rides/(?P<ride_id>[^/]+)/tracking/$',
        consumers.RideTrackingConsumer.as_asgi(),
        name='ride_tracking'
    ),

    # Driver location updates
    re_path(
        r'ws/driver/location/$',
        consumers.DriverLocationConsumer.as_asgi(),
        name='driver_location'
    ),

    # Courier delivery tracking
    re_path(
        r'ws/couriers/(?P<delivery_id>[^/]+)/tracking/$',
        consumers.CourierTrackingConsumer.as_asgi(),
        name='courier_tracking'
    ),
]
