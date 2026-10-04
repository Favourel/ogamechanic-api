from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework import status
from users.models import User, Role
from products.models import Product, ProductView
from products.view_tracker import record_product_view

TEST_MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    WHITENOISE_MANIFEST_STRICT=False,
    MIDDLEWARE=TEST_MIDDLEWARE,
)
class ProductViewTrackingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.factory = APIRequestFactory()

        # Roles
        self.merchant_role, _ = Role.objects.get_or_create(
            name=Role.MERCHANT, defaults={"description": "Merchant"}
        )
        self.customer_role, _ = Role.objects.get_or_create(
            name=Role.PRIMARY_USER, defaults={"description": "Primary User"}
        )
        self.admin_role, _ = Role.objects.get_or_create(
            name=Role.ADMIN, defaults={"description": "Admin"}
        )

        # Merchant
        self.merchant = User.objects.create_user(
            email="vendor@test.com",
            password="VendorPass123!",
            first_name="Victor",
            last_name="Vendor",
            phone_number="08012345671",
        )
        self.merchant.roles.add(self.merchant_role)

        # Second merchant
        self.other_merchant = User.objects.create_user(
            email="other_vendor@test.com",
            password="VendorPass123!",
            first_name="Oscar",
            last_name="Other",
            phone_number="08012345672",
        )
        self.other_merchant.roles.add(self.merchant_role)

        # Customer 1
        self.customer1 = User.objects.create_user(
            email="customer1@test.com",
            password="CustomerPass123!",
            first_name="Alice",
            last_name="Smith",
            phone_number="08012345673",
        )
        self.customer1.roles.add(self.customer_role)

        # Customer 2
        self.customer2 = User.objects.create_user(
            email="customer2@test.com",
            password="CustomerPass123!",
            first_name="Bob",
            last_name="Jones",
            phone_number="08012345674",
        )
        self.customer2.roles.add(self.customer_role)

        # Admin
        self.admin_user = User.objects.create_superuser(
            email="admin@test.com",
            password="AdminPass123!",
            first_name="Admin",
            last_name="Root",
        )
        self.admin_user.roles.add(self.admin_role)
        self.admin_user.is_staff = True
        self.admin_user.save()

        # Product
        self.product = Product.objects.create(
            merchant=self.merchant,
            name="2020 Honda Civic",
            price=Decimal("12000000.00"),
            is_active=True,
        )

        self.headers = {
            "HTTP_X_API_KEY": settings.X_API_KEY,
        }

    def test_record_product_view_first_view(self):
        """First view increments views_count, unique_views_count, and creates ProductView."""
        request = self.factory.get("/")
        request.user = self.customer1
        request.META["REMOTE_ADDR"] = "192.168.1.50"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)"

        success, reason = record_product_view(self.product, request)
        self.assertTrue(success)
        self.assertEqual(reason, "new_unique_view")

        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 1)
        self.assertEqual(self.product.unique_views_count, 1)

        view_entry = ProductView.objects.get(product=self.product, user=self.customer1)
        self.assertEqual(view_entry.view_count, 1)
        self.assertEqual(view_entry.ip_address, "192.168.1.50")

    def test_record_product_view_self_view_suppressed(self):
        """Vendor viewing their own product is ignored."""
        request = self.factory.get("/")
        request.user = self.merchant
        request.META["REMOTE_ADDR"] = "192.168.1.50"

        success, reason = record_product_view(self.product, request)
        self.assertFalse(success)
        self.assertEqual(reason, "self_view")

        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 0)
        self.assertEqual(self.product.unique_views_count, 0)
        self.assertEqual(ProductView.objects.count(), 0)

    def test_record_product_view_bot_detected_suppressed(self):
        """Requests from web bots / crawlers are ignored."""
        request = self.factory.get("/")
        request.user = self.customer1
        request.META["REMOTE_ADDR"] = "66.249.66.1"
        request.META["HTTP_USER_AGENT"] = "Googlebot/2.1 (+http://www.google.com/bot.html)"

        success, reason = record_product_view(self.product, request)
        self.assertFalse(success)
        self.assertEqual(reason, "bot_detected")

        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 0)

    def test_record_product_view_cooldown(self):
        """Repeat views within cooldown are ignored, after cooldown they increment."""
        request = self.factory.get("/")
        request.user = self.customer1
        request.META["REMOTE_ADDR"] = "192.168.1.50"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"

        # 1st view
        success1, _ = record_product_view(self.product, request, cooldown_minutes=15)
        self.assertTrue(success1)

        # Immediate 2nd view (should be ignored due to cooldown)
        success2, reason2 = record_product_view(self.product, request, cooldown_minutes=15)
        self.assertFalse(success2)
        self.assertEqual(reason2, "cooldown_active")

        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 1)
        self.assertEqual(self.product.unique_views_count, 1)

        # Fast forward time beyond cooldown
        view_entry = ProductView.objects.get(product=self.product, user=self.customer1)
        ProductView.objects.filter(id=view_entry.id).update(
            last_viewed_at=timezone.now() - timedelta(minutes=20)
        )

        # 3rd view after cooldown
        success3, reason3 = record_product_view(self.product, request, cooldown_minutes=15)
        self.assertTrue(success3)
        self.assertEqual(reason3, "repeat_view_incremented")

        self.product.refresh_from_db()
        view_entry.refresh_from_db()
        self.assertEqual(self.product.views_count, 2)
        self.assertEqual(self.product.unique_views_count, 1)  # Unique viewers remains 1
        self.assertEqual(view_entry.view_count, 2)

    def test_record_product_view_guest_tracking(self):
        """Guest views with IP address are recorded properly."""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.META["HTTP_X_FORWARDED_FOR"] = "102.89.23.4, 172.68.10.1"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"

        success, reason = record_product_view(self.product, request)
        self.assertTrue(success)
        self.assertEqual(reason, "new_unique_view")

        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 1)
        self.assertEqual(self.product.unique_views_count, 1)

        view_entry = ProductView.objects.get(product=self.product, ip_address="102.89.23.4")
        self.assertIsNone(view_entry.user)
        self.assertEqual(view_entry.view_count, 1)

    def test_product_detail_view_records_view_and_returns_counts(self):
        """Calling product detail view tracks view and returns views_count in serializer."""
        self.client.force_authenticate(user=self.customer1)
        url = reverse('products:product-detail', kwargs={'id': self.product.id})
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertIn("views_count", data)
        self.assertIn("unique_views_count", data)
        self.assertEqual(data["views_count"], 1)
        self.assertEqual(data["unique_views_count"], 1)

        # Check DB
        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 1)
        self.assertEqual(self.product.unique_views_count, 1)

    def test_product_viewers_endpoint_authorization(self):
        """Product owner and admin can view viewers; others receive 403; unauth receives 401."""
        url = reverse('products:product-viewers', kwargs={'id': self.product.id})

        # 1. Unauthenticated -> 401
        res_unauth = self.client.get(url, **self.headers)
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Other merchant -> 403
        self.client.force_authenticate(user=self.other_merchant)
        res_forbidden = self.client.get(url, **self.headers)
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Regular customer -> 403
        self.client.force_authenticate(user=self.customer1)
        res_customer = self.client.get(url, **self.headers)
        self.assertEqual(res_customer.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Product owner (merchant) -> 200
        self.client.force_authenticate(user=self.merchant)
        res_owner = self.client.get(url, **self.headers)
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)

        # 5. Admin / staff -> 200
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get(url, **self.headers)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    def test_product_viewers_endpoint_data_and_pagination(self):
        """Product viewers endpoint returns accurate metrics and customer details."""
        # Create views for customer1, customer2, and a guest
        ProductView.objects.create(
            product=self.product,
            user=self.customer1,
            ip_address="192.168.1.1",
            view_count=5,
        )
        ProductView.objects.create(
            product=self.product,
            user=self.customer2,
            ip_address="192.168.1.2",
            view_count=2,
        )
        ProductView.objects.create(
            product=self.product,
            user=None,
            ip_address="192.168.1.99",
            view_count=3,
        )
        # Update product denormalized counts
        Product.objects.filter(id=self.product.id).update(
            views_count=10,
            unique_views_count=3,
        )

        self.client.force_authenticate(user=self.merchant)
        url = reverse('products:product-viewers', kwargs={'id': self.product.id}) + "?limit=10&offset=0"
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]

        self.assertEqual(data["product_id"], str(self.product.id))
        self.assertEqual(data["product_name"], "2020 Honda Civic")
        self.assertEqual(data["total_views"], 10)
        self.assertEqual(data["unique_viewers_count"], 3)
        self.assertEqual(data["registered_customers_count"], 2)
        self.assertEqual(data["guest_viewers_count"], 1)
        self.assertEqual(data["total_registered_viewers"], 2)
        self.assertEqual(len(data["viewers"]), 2)

        emails = [v["email"] for v in data["viewers"]]
        self.assertIn("customer1@test.com", emails)
        self.assertIn("customer2@test.com", emails)

    def test_merchant_analytics_view_analytics(self):
        """MerchantAnalyticsView includes view_analytics with total views and top products."""
        # Setup views on product
        Product.objects.filter(id=self.product.id).update(
            views_count=42,
            unique_views_count=18,
        )

        self.client.force_authenticate(user=self.merchant)
        url = reverse('products:merchant-analytics')
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertIn("view_analytics", data)
        self.assertEqual(data["view_analytics"]["total_product_views"], 42)
        self.assertEqual(data["view_analytics"]["total_unique_viewers"], 18)
        self.assertTrue(len(data["view_analytics"]["top_viewed_products"]) >= 1)
        self.assertEqual(data["view_analytics"]["top_viewed_products"][0]["name"], "2020 Honda Civic")
