from django.contrib import admin
from . import models


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


class ProductImageInline(admin.TabularInline):
    model = models.ProductImage
    extra = 1
    fields = ('image', 'ordering', 'created_at')
    readonly_fields = ('created_at',)


class ProductVehicleCompatibilityInline(admin.TabularInline):
    model = models.ProductVehicleCompatibility
    extra = 1
    fields = ('make', 'model', 'year_from', 'year_to', 'notes')
    autocomplete_fields = ('make', 'model')


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'merchant', 'category', 'price', 'is_rental', 
        'created_at', 'updated_at'
    )
    search_fields = ('name', 'merchant__email', 'category__name', 'id')
    list_filter = ('is_rental', 'category', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ProductImageInline, ProductVehicleCompatibilityInline]
    autocomplete_fields = ('merchant', 'category',)
    list_per_page = 30  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'ordering', 'created_at')
    search_fields = (
        'product__name', 'product__merchant__email', 'product__id')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)
    autocomplete_fields = ('product',)
    list_per_page = 30  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'status', 'payment_status', 'total_amount', 'created_at', 'updated_at') # noqa
    search_fields = ('id', 'customer__email', 'id')
    list_filter = ('status', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 30  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'price')
    search_fields = ('order__id', 'product__name', 'order__id')
    list_filter = ('order', 'product')
    list_per_page = 30  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'updated_at')
    search_fields = ('user__email', 'id')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 30
    list_max_show_all = 200


@admin.register(models.CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity', 'added_at')
    search_fields = ('cart__user__email', 'product__name', 'cart__id')
    list_filter = ('cart',)
    readonly_fields = ('added_at',)
    list_per_page = 30
    list_max_show_all = 200


@admin.register(models.ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')
    search_fields = ('product__name', 'user__email', 'product__id')
    list_filter = ('rating', 'created_at')
    readonly_fields = ('created_at',)
    list_per_page = 30
    list_max_show_all = 200


# Register all other models from mechanics app that are not already registered above  # noqa
already_registered = {
    models.Category,
    models.Product,
    models.ProductImage,
    models.ProductVehicleCompatibility,
    models.Order,
    models.OrderItem,
    models.Cart,
    models.CartItem,
    models.ProductReview,
}

for model in vars(models).values():
    try:
        if (
            isinstance(model, type)
            and issubclass(model, models.models.Model)
            and model not in already_registered
        ):
            admin.site.register(model)
    except Exception:
        continue
