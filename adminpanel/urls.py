from django.urls import path
from .views import (
    # Authentication
    AdminLoginView,
    AdminForgotPasswordView,
    AdminResetPasswordView,
    # Management
    EcommerceManagementView,
    AccountManagementView,
    MechanicManagementView,
    ApproveMechanicProfileView,
    ApproveDriverProfileView,
    SalesAnalyticsView,
    PendingVerificationsView,
    ApproveRejectVerificationView,
    # AdminAnalyticsView,
    AdminCategoryCreateView,
    AdminNotificationView,
    RoleNotificationView,
    # Analytics endpoints
    DashboardOverviewView,
    UserGrowthAnalyticsView,
    MerchantAnalyticsView,
    ServiceAnalyticsView,
    RevenueAnalyticsView,
    TopPerformersView,
    GeographicHeatMapView,
    OngoingActivitiesFeedView,
)

app_name = 'adminpanel'

urlpatterns = [
    # Authentication endpoints
    path(
        'authentication/login/staff/',
        AdminLoginView.as_view(),
        name='admin-login'
    ),
    path(
        'authentication/forgot-password/staff/',
        AdminForgotPasswordView.as_view(),
        name='admin-forgot-password'
    ),
    path(
        'authentication/reset-password/staff/',
        AdminResetPasswordView.as_view(),
        name='admin-reset-password'
    ),

    # Management endpoints (with query params)
    path(
        'management/ecommerce/',
        EcommerceManagementView.as_view(),
        name='ecommerce-management'
    ),
    path(
        'management/accounts/',
        AccountManagementView.as_view(),
        name='account-management'
    ),
    path(
        'management/mechanics/',
        MechanicManagementView.as_view(),
        name='mechanic-management'
    ),

    # Specific management actions
    path(
        'approve/mechanic/<uuid:user_id>/',
        ApproveMechanicProfileView.as_view(),
        name='approve-mechanic-profile',
    ),
    path(
        'approve/driver/<uuid:user_id>/',
        ApproveDriverProfileView.as_view(),
        name='approve-driver-profile',
    ),

    path(
        'analytics/sales/',
        SalesAnalyticsView.as_view(),
        name='sales-analytics',
    ),
    # path('analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),

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

    # Analytics endpoints
    path(
        'analytics/dashboard/overview/',
        DashboardOverviewView.as_view(),
        name='dashboard-overview'
    ),
    path(
        'analytics/users/growth/',
        UserGrowthAnalyticsView.as_view(),
        name='user-growth-analytics'
    ),
    path(
        'analytics/merchants/',
        MerchantAnalyticsView.as_view(),
        name='merchant-analytics'
    ),
    path(
        'analytics/services/',
        ServiceAnalyticsView.as_view(),
        name='service-analytics'
    ),
    path(
        'analytics/revenue/',
        RevenueAnalyticsView.as_view(),
        name='revenue-analytics'
    ),
    path(
        'analytics/top-performers/',
        TopPerformersView.as_view(),
        name='top-performers'
    ),
    path(
        'analytics/geographic-heatmap/',
        GeographicHeatMapView.as_view(),
        name='geographic-heatmap'
    ),
    path(
        'analytics/ongoing-activities/',
        OngoingActivitiesFeedView.as_view(),
        name='ongoing-activities'
    ),
]
