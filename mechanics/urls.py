from django.urls import path
from . import views

app_name = "mechanics"

urlpatterns = [
    # Repair Requests
    path(
        "repair-requests/",
        views.RepairRequestListView.as_view(),
        name="repair-request-list",
    ),
    path(
        "repair-requests/<uuid:repair_id>/",
        views.RepairRequestDetailView.as_view(),
        name="repair-request-detail",
    ),
    path(
        "repair-requests/<uuid:repair_id>/respond/",
        views.MechanicResponseView.as_view(),
        name="mechanic-respond",
    ),
    # Available Mechanics
    path(
        "available-mechanics/",
        views.AvailableMechanicsView.as_view(),
        name="available-mechanics",
    ),
    # Vehicle Makes
    path(
        "vehicle-makes/",
        views.VehicleMakeListView.as_view(),
        name="vehicle-makes",
    ),
    path(
        "mechanics/<uuid:mechanic_id>/",
        views.MechanicDetailView.as_view(),
        name="mechanic-detail",
    ),

    path(
        "mechanic-analytics/",
        views.MechanicAnalyticsView.as_view(),
        name="mechanic-analytics",
    ),
    # Training Sessions
    # path(
    #     "training-sessions/",
    #     views.TrainingSessionListView.as_view(),
    #     name="training-session-list",
    # ),
    # path(
    #     "training-sessions/<uuid:session_id>/",
    #     views.TrainingSessionDetailView.as_view(),
    #     name="training-session-detail",
    # ),
    # path(
    #     "training-sessions/<uuid:session_id>/participants/",
    #     views.TrainingSessionParticipantListView.as_view(),
    #     name="training-session-participants",
    # ),
]
