from django.urls import path
from .views import (
    ProductListCreateView,
    ProductDetailView,
    ProductSearchView,
    CategoryListView,
    HomeView,
    OrderListView,
    CartView,
    CheckoutView,
    # PaystackPaymentInitView,
    PaystackWebhookView,
    PaymentVerificationView,
    OrderStatusUpdateView,
    ProductReviewListCreateView,
    MerchantAnalyticsView,
    FollowMerchantView,
    FollowedMerchantsListView,
    FavoriteProductView,
    FavoriteProductsListView,
    ProductImageListView,
    ProductImageCreateView,
    BiddingWindowView,
    BidView,
    UserBidsListView,
    ActiveBiddingProductListView,
    BidUpdateView
)

app_name = 'products'

urlpatterns = [
    # Search and Discovery
    path('search/', ProductSearchView.as_view(), name='product-search'),
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('home/', HomeView.as_view(), name='home'),
    
    # Product Management
    path('products/', ProductListCreateView.as_view(), name='product-list-create'),
    path('products/<uuid:product_id>/images/upload/', ProductImageCreateView.as_view(), name='product-image-create'),
    path('products/<uuid:id>/', ProductDetailView.as_view(), name='product-detail'),
    path('products/<uuid:product_id>/images/', ProductImageListView.as_view(), name='product-image-list'),
    
    # Orders and Cart
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('cart/', CartView.as_view(), name='cart'),
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    
    # Payments
    # path('payment/initialize/', PaystackPaymentInitView.as_view(), name='payment-init'),
    path('payment/webhook/', PaystackWebhookView.as_view(), name='payment-webhook'),
    path('payment/verify/', PaymentVerificationView.as_view(), name='payment-verify'),
    
    # Reviews and Analytics
    path('orders/<uuid:order_id>/status-update/', OrderStatusUpdateView.as_view(), name='order-status-update'),
    path(
        'products/<uuid:product_id>/reviews/',
        ProductReviewListCreateView.as_view(),
        name='product-review-list-create'
    ),
    path(
        'merchant/analytics/',
        MerchantAnalyticsView.as_view(),
        name='merchant-analytics'
    ),
    # Follow/Unfollow Merchants
    path(
        'follow-merchant/',
        FollowMerchantView.as_view(),
        name='follow-merchant'
    ),
    path(
        'followed-merchants/',
        FollowedMerchantsListView.as_view(),
        name='followed-merchants'
    ),
    # Favorite Products
    path(
        'favorite-product/',
        FavoriteProductView.as_view(),
        name='favorite-product'
    ),
    path(
        'favorite-products/',
        FavoriteProductsListView.as_view(),
        name='favorite-products'
    ),
    # Bidding
    path(
        'bidding/active-products/',
        ActiveBiddingProductListView.as_view(),
        name='active-bidding-products'
    ),
    path(
        'bidding/my-bids/',
        UserBidsListView.as_view(),
        name='user-bids'
    ),
    path(
        'products/<uuid:product_id>/bidding/',
        BiddingWindowView.as_view(),
        name='bidding-window'
    ),
    path(
        'bidding/<uuid:bidding_window_id>/bids/',
        BidView.as_view(),
        name='bids-list-create'
    ),
    path(
        'bids/<uuid:bid_id>/',
        BidUpdateView.as_view(),
        name='bid-update'
    ),
]

