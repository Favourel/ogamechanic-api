from django.urls import path
from . import views

app_name = "couriers"

urlpatterns = [
    # Existing delivery endpoints
    path("", views.DeliveryRequestListView.as_view(), name="delivery-list"),
    path(
        "<uuid:delivery_id>/",
        views.DeliveryRequestDetailView.as_view(),
        name="delivery-detail",
    ),
    path(
        "<uuid:delivery_id>/status/",
        views.DeliveryStatusUpdateView.as_view(),
        name="delivery-status-update",
    ),
    # New multiple waypoint endpoints
    path(
        "multi-waypoint/",
        views.MultiWaypointDeliveryCreateView.as_view(),
        name="multi-waypoint-delivery-create",
    ),
    path(
        "optimize-route/",
        views.DeliveryRouteOptimizationView.as_view(),
        name="delivery-route-optimization",
    ),
    path(
        "<uuid:delivery_id>/waypoints/",
        views.DeliveryWaypointListView.as_view(),
        name="delivery-waypoint-list",
    ),
    path(
        "<uuid:delivery_id>/waypoints/<uuid:waypoint_id>/",
        views.DeliveryWaypointUpdateView.as_view(),
        name="delivery-waypoint-update",
    ),
    # Tracking and rating
    path(
        "tracking/<uuid:request_id>/",
        views.DeliveryTrackingView.as_view(),
        name="delivery-tracking",
    ),
    path(
        "rate/<uuid:request_id>/",
        views.CourierRatingView.as_view(),
        name="courier-rating",
    ),
]
