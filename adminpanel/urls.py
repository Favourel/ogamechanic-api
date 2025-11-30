from django.urls import path
from .views import (
    ApproveMechanicProfileView,
    ApproveDriverProfileView,
    SalesAnalyticsView,
    PendingVerificationsView,
    ApproveRejectVerificationView,
    AdminAnalyticsView,
    AdminCategoryCreateView,
    AdminNotificationView,
    RoleNotificationView,
    # Analytics views
    DashboardView,
    AnalyticsSummaryView,
    AnalyticsReportView,
    RealTimeAnalyticsView,
    AnalyticsCacheView,
)

app_name = 'adminpanel'

urlpatterns = [
    path(
        'approve/mechanic/<uuid:profile_id>/',
        ApproveMechanicProfileView.as_view(),
        name='approve-mechanic-profile',
    ),
    path(
        'approve/driver/<uuid:profile_id>/',
        ApproveDriverProfileView.as_view(),
        name='approve-driver-profile',
    ),

    path(
        'analytics/sales/',
        SalesAnalyticsView.as_view(),
        name='sales-analytics',
    ),
    path('analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),

    # Analytics Dashboard Routes (moved from analytics app)
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('summary/', AnalyticsSummaryView.as_view(), name='summary'),
    path('reports/', AnalyticsReportView.as_view(), name='reports'),
    path('realtime/', RealTimeAnalyticsView.as_view(), name='realtime'),
    path('cache/', AnalyticsCacheView.as_view(), name='cache'),

    path(
        'verifications/pending/',
        PendingVerificationsView.as_view(),
        name='pending-verifications',
    ),
    path(
        'verifications/action/',
        ApproveRejectVerificationView.as_view(),
        name='approve-reject-verification',
    ),
    path(
        'categories/create/',
        AdminCategoryCreateView.as_view(),
        name='admin-category-create',
    ),

    path(
        'admin/notifications/',
        AdminNotificationView.as_view(),
        name='admin-notifications'
    ),
    path(
        'admin/notifications/role/',
        RoleNotificationView.as_view(),
        name='role-notifications'
    ),
]
