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
    PendingVerificationsView,
    UserActivationView,
    # AdminAnalyticsView,
    AdminCategoryCreateView,
    AdminNotificationView,
    RoleNotificationView,
    # Analytics endpoints
    DashboardOverviewView,
    UserGrowthAnalyticsView,
    UserActivityAnalyticsView,
    ConsolidatedAnalyticsView,
    ServiceAnalyticsView,
    RevenueAnalyticsView,
    TopPerformersView,
    GeographicHeatMapView,
    OngoingActivitiesFeedView,
    # Feedback Management endpoints
    ProductReviewManagementView,
    MerchantReviewManagementView,
    MechanicReviewManagementView,
    DriverReviewManagementView,
    AdminChatMessageView,
    # Contact Message Management
    ContactMessageListView,
    ContactMessageDetailView,
    EmailSubscriptionListView,
    PrimaryUserProfileSummaryView,
    PrimaryUserMechanicTabView,
    PrimaryUserCourierTabView,
    PrimaryUserRidesTabView,
    PrimaryUserRentalsTabView,
    PrimaryUserProductsTabView,
    PrimaryUserActivityLogTabView,
    MerchantProviderDetailView,
    MechanicProviderDetailView,
    DriverProviderDetailView,
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
        'analytics/consolidated/',
        ConsolidatedAnalyticsView.as_view(),
        name='consolidated-analytics',
    ),
    # path('analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),

    path(
        'verifications/pending/',
        PendingVerificationsView.as_view(),
        name='pending-verifications',
    ),

    path(
        'users/activation/',
        UserActivationView.as_view(),
        name='user-activation',
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
        'analytics/users/activities/',
        UserActivityAnalyticsView.as_view(),
        name='user-activity-analytics'
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

    # Feedback Management endpoints
    path(
        'feedback/reviews/products/',
        ProductReviewManagementView.as_view(),
        name='product-review-management'
    ),
    path(
        'feedback/reviews/merchants/',
        MerchantReviewManagementView.as_view(),
        name='merchant-review-management'
    ),
    path(
        'feedback/reviews/mechanics/',
        MechanicReviewManagementView.as_view(),
        name='mechanic-review-management'
    ),
    path(
        'feedback/reviews/drivers/',
        DriverReviewManagementView.as_view(),
        name='driver-review-management'
    ),
    path(
        'feedback/chat/messages/',
        AdminChatMessageView.as_view(),
        name='admin-chat-messages'
    ),
    # Contact Message Management endpoints
    path(
        'contact/messages/',
        ContactMessageListView.as_view(),
        name='contact-messages'
    ),
    path(
        'contact/messages/<uuid:message_id>/',
        ContactMessageDetailView.as_view(),
        name='contact-message-detail'
    ),
    path(
        'contact/messages/<uuid:message_id>/update/',
        ContactMessageListView.as_view(),
        name='contact-message-update'
    ),
    path(
        'subscribers/',
        EmailSubscriptionListView.as_view(),
        name='email-subscribers'
    ),

    path(
        'users/primary/<uuid:user_id>/profile/summary/',
        PrimaryUserProfileSummaryView.as_view(),
        name='primary-user-profile-summary',
    ),
    path(
        'users/primary/<uuid:user_id>/profile/mechanic/',
        PrimaryUserMechanicTabView.as_view(),
        name='primary-user-profile-mechanic',
    ),
    path(
        'users/primary/<uuid:user_id>/profile/courier/',
        PrimaryUserCourierTabView.as_view(),
        name='primary-user-profile-courier',
    ),
    path(
        'users/primary/<uuid:user_id>/profile/rides/',
        PrimaryUserRidesTabView.as_view(),
        name='primary-user-profile-rides',
    ),
    path(
        'users/primary/<uuid:user_id>/profile/rentals/',
        PrimaryUserRentalsTabView.as_view(),
        name='primary-user-profile-rentals',
    ),
    path(
        'users/primary/<uuid:user_id>/profile/products/',
        PrimaryUserProductsTabView.as_view(),
        name='primary-user-profile-products',
    ),
    path(
        'users/primary/<uuid:user_id>/profile/activity-logs/',
        PrimaryUserActivityLogTabView.as_view(),
        name='primary-user-profile-activity-logs',
    ),
    path(
        'users/merchant/<uuid:user_id>/detail/',
        MerchantProviderDetailView.as_view(),
        name='merchant-provider-detail',
    ),
    path(
        'users/mechanic/<uuid:user_id>/detail/',
        MechanicProviderDetailView.as_view(),
        name='mechanic-provider-detail',
    ),
    path(
        'users/driver/<uuid:user_id>/detail/',
        DriverProviderDetailView.as_view(),
        name='driver-provider-detail',
    ),
]
