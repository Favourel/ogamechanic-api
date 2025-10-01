from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication endpoints
    # Note: Legacy /register/ endpoint removed - use step-by-step registration
    path(
        'register/step/<int:step>/',
        views.StepByStepRegistrationView.as_view(),
        name='step_by_step_register'
    ),
    path('login/', views.LoginView.as_view(), name='login'),
    path(
        'token/refresh/',
        views.TokenRefreshView.as_view(),
        name='token_refresh'
    ),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Password management
    path(
        'password/reset/',
        views.PasswordResetRequestView.as_view(),
        name='password_reset'
    ),
    path(
        'password/reset/confirm/',
        views.PasswordResetConfirmView.as_view(),
        name='password_reset_confirm'
    ),
    path(
        'password/change/',
        views.ChangePasswordView.as_view(),
        name='change_password'
    ),

    # Profile management
    path(
        'profile/primary/',
        views.PrimaryUserProfileView.as_view(),
        name='primary_user_profile'
    ),
    path('roles/', views.RoleManagementView.as_view(), name='role_management'),
    path('roles/list/', views.RoleListView.as_view(), name='role_list'),
    
    # Email verification
    path(
        'verify-email/',
        views.EmailVerificationAPIView.as_view(),
        name='verify_email'
    ),

    # Profile Management endpoints
    path(
        'profile/merchant/',
        views.MerchantProfileManagementView.as_view(),
        name='merchant_profile'
    ),
    path(
        'profile/mechanic/',
        views.MechanicProfileManagementView.as_view(),
        name='mechanic_profile'
    ),
    path(
        'profile/driver/',
        views.DriverProfileManagementView.as_view(),
        name='driver_profile'
    ),

    # Driver location
    path(
        'driver/location/',
        views.DriverLocationUpdateView.as_view(),
        name='driver_location'
    ),

    # Reviews
    path(
        'mechanics/<uuid:mechanic_id>/reviews/',
        views.MechanicReviewListCreateView.as_view(),
        name='mechanic_reviews'
    ),
    path(
        'mechanics/<uuid:mechanic_id>/reviews/<int:pk>/',
        views.MechanicReviewDetailView.as_view(),
        name='mechanic_review_detail'
    ),
    path(
        'drivers/<uuid:driver_id>/reviews/',
        views.DriverReviewListCreateView.as_view(),
        name='driver_reviews'
    ),
    path(
        'drivers/<uuid:driver_id>/reviews/<int:pk>/',
        views.DriverReviewDetailView.as_view(),
        name='driver_review_detail'
    ),

    # Notifications
    path(
        'notifications/',
        views.NotificationListView.as_view(),
        name='notification-list'
    ),
    path(
        'notifications/<int:notification_id>/',
        views.NotificationDetailView.as_view(),
        name='notification-detail'
    ),
    path(
        'notifications/mark-all-read/',
        views.NotificationMarkAllReadView.as_view(),
        name='mark-all-read'
    ),

    path(
        'notifications/devices/',
        views.DeviceRegistrationView.as_view(),
        name='device-registration'
    ),

    # Payment and Wallet Management
    path(
        'wallet/',
        views.WalletDetailView.as_view(),
        name='wallet-detail'
    ),
    path(
        'wallet/topup/',
        views.WalletTopUpView.as_view(),
        name='wallet-topup'
    ),
    path(
        'wallet/withdraw/',
        views.WalletWithdrawalView.as_view(),
        name='wallet-withdraw'
    ),
    path(
        'transactions/',
        views.TransactionListView.as_view(),
        name='transaction-list'
    ),

    # Bank Account Management
    path(
        'bank-accounts/',
        views.BankAccountListCreateView.as_view(),
        name='bank-account-list-create'
    ),
    path(
        'bank-accounts/<uuid:account_id>/',
        views.BankAccountDetailView.as_view(),
        name='bank-account-detail'
    ),

    # Paystack Webhooks
    path(
        'paystack/webhook/',
        views.PaystackWebhookView.as_view(),
        name='paystack-webhook'
    ),

    # Security and File Storage
    path(
        'documents/',
        views.SecureDocumentListCreateView.as_view(),
        name='secure-document-list-create'
    ),
    path(
        'documents/<uuid:document_id>/',
        views.SecureDocumentDetailView.as_view(),
        name='secure-document-detail'
    ),
    path(
        'documents/<uuid:document_id>/verify/',
        views.DocumentVerificationView.as_view(),
        name='document-verification'
    ),
    path(
        'documents/verification-logs/',
        views.DocumentVerificationLogView.as_view(),
        name='document-verification-logs'
    ),
    path(
        'documents/security-audits/',
        views.FileSecurityAuditView.as_view(),
        name='file-security-audits'
    ),
    path(
        'files/upload/',
        views.FileUploadView.as_view(),
        name='file-upload'
    ),
    path(
        'files/cac-upload/',
        views.CACUploadView.as_view(),
        name='cac-upload'
    ),
]
