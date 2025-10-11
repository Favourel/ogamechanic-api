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
    OrderStatusUpdateView,
    ProductReviewListCreateView,
    MerchantAnalyticsView,
    FollowMerchantView,
    FollowedMerchantsListView,
    FavoriteProductView,
    FavoriteProductsListView,
    ProductImageListView,
    ProductImageCreateView
)

app_name = 'products'

urlpatterns = [
    path('home/', HomeView.as_view(), name='home'),
    path(
        'products/',
        ProductListCreateView.as_view(),
        name='product-list-create'
    ),
    path(
        'products/<id>/',
        ProductDetailView.as_view(),
        name='product-detail'
    ),
    path(
        'search-product/',
        ProductSearchView.as_view(),
        name='product-search'
    ),
    path(
        'categories/',
        CategoryListView.as_view(),
        name='category-list'
    ),
    path(
        'orders/',
        OrderListView.as_view(),
        name='order-list-create'
    ),
    path(
        'orders/<uuid:order_id>/status/',
        OrderStatusUpdateView.as_view(),
        name='order-status-update'
    ),
    path(
        'cart/',
        CartView.as_view(),
        name='cart'
    ),
    path(
        'checkout/',
        CheckoutView.as_view(),
        name='checkout'
    ),
    # path(
    #     'paystack/init/',
    #     PaystackPaymentInitView.as_view(),
    #     name='paystack-init'
    # ),
    path(
        'paystack/webhook/',
        PaystackWebhookView.as_view(),
        name='paystack-webhook'
    ),

    path(
        'products/<product_id>/images/',
        ProductImageListView.as_view(),
        name='product-image-list'
    ),
    path(
        'products/<product_id>/images/upload/',
        ProductImageCreateView.as_view(),
        name='product-image-upload'
    ),
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
]
