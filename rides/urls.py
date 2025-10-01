from django.urls import path
from . import views

app_name = 'rides'

urlpatterns = [
    # Existing ride endpoints
    path('', views.RideListCreateView.as_view(), name='ride-list-create'),
    path('confirm/', views.RideConfirmView.as_view(), name='ride-confirm'),
    path('<uuid:ride_id>/status/', views.RideStatusUpdateView.as_view(), name='ride-status-update'),
    
    # New multiple waypoint endpoints
    path('multi-waypoint/', views.MultiWaypointRideCreateView.as_view(), name='multi-waypoint-ride-create'),
    path('optimize-route/', views.RouteOptimizationView.as_view(), name='route-optimization'),
    path('<uuid:ride_id>/waypoints/', views.WaypointListView.as_view(), name='waypoint-list'),
    path('<uuid:ride_id>/waypoints/<uuid:waypoint_id>/', views.WaypointUpdateView.as_view(), name='waypoint-update'),
    
    # Courier endpoints
    path('courier/options/', views.CourierRequestOptionsView.as_view(), name='courier-options'),
    path('courier/confirm/', views.CourierRequestConfirmView.as_view(), name='courier-confirm'),
    path('courier/<uuid:courier_id>/status/', views.CourierRequestStatusUpdateView.as_view(), name='courier-status-update'),
    path('courier/', views.CourierRequestListView.as_view(), name='courier-list'),
    
    # Analytics
    path('analytics/', views.RideCourierAnalyticsView.as_view(), name='ride-courier-analytics'),
    
    # Location tracking
    path('<uuid:ride_id>/tracking/', views.LocationTrackingView.as_view(), name='location-tracking'),
    path('driver/location/', views.DriverLocationUpdateView.as_view(), name='driver-location-update'),
    path('nearby-drivers/', views.NearbyDriversView.as_view(), name='nearby-drivers'),
    
    # Geocoding
    path('geocode/', views.GeocodingView.as_view(), name='geocode'),
    path('reverse-geocode/', views.ReverseGeocodingView.as_view(), name='reverse-geocode'),
]