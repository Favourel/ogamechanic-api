from django.test import TestCase, override_settings
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User, Role, MechanicProfile, Wallet, BankAccount
from products.models import Category, Product, Order, OrderItem
from mechanics.models import RepairRequest
from decimal import Decimal


TEST_MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    WHITENOISE_MANIFEST_STRICT=False,
    MIDDLEWARE=TEST_MIDDLEWARE,
)
class AdminCategoryAndAccountManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create admin user
        self.admin_role, _ = Role.objects.get_or_create(
            name=Role.ADMIN, defaults={"description": "Admin"}
        )
        self.primary_role, _ = Role.objects.get_or_create(
            name=Role.PRIMARY_USER, defaults={"description": "Primary User"}
        )
        self.mechanic_role, _ = Role.objects.get_or_create(
            name=Role.MECHANIC, defaults={"description": "Mechanic"}
        )

        self.admin_user = User.objects.create_superuser(
            email="admin@test.com",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="User",
        )
        self.admin_user.roles.add(self.admin_role)
        self.admin_user.is_staff = True
        self.admin_user.save()

        # Regular primary user
        self.primary_user = User.objects.create_user(
            email="customer@test.com",
            password="CustomerPass123!",
            first_name="John",
            last_name="Doe",
            phone_number="08012345678",
        )
        self.primary_user.roles.add(self.primary_role)
        self.primary_user.active_role = self.primary_role
        self.primary_user.save()

        # Mechanic user
        self.mechanic_user = User.objects.create_user(
            email="mechanic@test.com",
            password="MechanicPass123!",
            first_name="Mike",
            last_name="Fixer",
            phone_number="08087654321",
        )
        self.mechanic_user.roles.add(self.mechanic_role)
        self.mechanic_profile = MechanicProfile.objects.create(
            user=self.mechanic_user,
            location="12 Ikeja Way, Lagos",
            is_approved=True,
        )

        # Category
        self.category = Category.objects.create(
            name="Engine Parts",
            description="All engine components",
        )

        self.headers = {
            "HTTP_X_API_KEY": settings.X_API_KEY,
        }
        self.client.force_authenticate(user=self.admin_user)

    def test_get_categories_list(self):
        url = "/api/v1/admin/categories/"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        res_data = response.json()
        self.assertTrue(res_data["status"])
        self.assertGreaterEqual(res_data["data"]["total_count"], 1)

    def test_get_category_detail(self):
        url = f"/api/v1/admin/categories/{self.category.pk}/"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        res_data = response.json()
        self.assertTrue(res_data["status"])
        self.assertEqual(res_data["data"]["name"], "Engine Parts")

    def test_update_category_put(self):
        url = f"/api/v1/admin/categories/{self.category.pk}/"
        payload = {
            "requestType": "inbound",
            "data": {
                "name": "Engine & Transmission",
                "description": "Updated engine components and transmission parts",
            },
        }
        response = self.client.put(url, data=payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Engine & Transmission")
        self.assertEqual(self.category.description, "Updated engine components and transmission parts")

    def test_update_category_patch(self):
        url = f"/api/v1/admin/categories/{self.category.pk}/"
        payload = {
            "requestType": "inbound",
            "data": {
                "description": "Patched description only",
            },
        }
        response = self.client.patch(url, data=payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Engine Parts")
        self.assertEqual(self.category.description, "Patched description only")

    def test_delete_category_success(self):
        new_cat = Category.objects.create(name="Disposable Cat", description="temp")
        url = f"/api/v1/admin/categories/{new_cat.pk}/"
        response = self.client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Category.objects.filter(pk=new_cat.pk).exists())

    def test_delete_category_protected(self):
        # Product references category with on_delete=models.PROTECT
        product = Product.objects.create(
            name="Test Alternator",
            merchant=self.admin_user,
            category=self.category,
            price=Decimal("45000.00"),
        )
        url = f"/api/v1/admin/categories/{self.category.pk}/"
        response = self.client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        res_data = response.json()
        self.assertFalse(res_data["status"])
        self.assertIn("products associated with it", res_data["message"])

    def test_account_detail_view_path(self):
        # Add wallet & bank account
        Wallet.objects.create(user=self.primary_user, balance=Decimal("15000.00"), currency="NGN")
        BankAccount.objects.create(
            user=self.primary_user,
            account_name="John Doe",
            account_number="0123456789",
            bank_name="GTBank",
            bank_code="058",
        )

        # Create RepairRequest
        RepairRequest.objects.create(
            customer=self.primary_user,
            mechanic=self.mechanic_user,
            service_type="Brake Repair",
            vehicle_make="Toyota",
            vehicle_model="Corolla",
            vehicle_year=2018,
            problem_description="Brake pads worn out",
            service_address="Victoria Island, Lagos",
            service_latitude=Decimal("6.4281"),
            service_longitude=Decimal("3.4219"),
            status="completed",
            actual_cost=Decimal("25000.00"),
            estimated_cost=Decimal("25000.00"),
        )

        # Create Order with OrderItem
        product = Product.objects.create(
            name="Synthetic Oil 5W-30",
            merchant=self.admin_user,
            category=self.category,
            price=Decimal("18000.00"),
        )
        order = Order.objects.create(
            customer=self.primary_user,
            status="completed",
            payment_status="paid",
            total_amount=Decimal("36000.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=2,
            price=Decimal("18000.00"),
        )

        url = f"/api/v1/admin/management/accounts/{self.primary_user.id}/"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]

        # Check user info
        self.assertEqual(data["user"]["email"], "customer@test.com")
        self.assertEqual(data["user"]["first_name"], "John")

        # Check action summaries
        mech_summary = data["action_summaries"]["mechanic_requests"]
        self.assertEqual(mech_summary["total_attempted"], 1)
        self.assertEqual(mech_summary["completed"], 1)
        self.assertEqual(mech_summary["total_spent"], 25000.0)

        prod_summary = data["action_summaries"]["product_orders"]
        self.assertEqual(prod_summary["total_orders"], 1)
        self.assertEqual(prod_summary["completed"], 1)
        self.assertEqual(prod_summary["total_items_purchased"], 2)
        self.assertEqual(prod_summary["total_spent"], 36000.0)

        # Check recent actions contain full details
        recent_repairs = data["recent_actions"]["mechanic_requests"]
        self.assertEqual(len(recent_repairs), 1)
        self.assertEqual(recent_repairs[0]["status"], "completed")
        self.assertEqual(recent_repairs[0]["vehicle"]["make"], "Toyota")
        self.assertEqual(recent_repairs[0]["problem_description"], "Brake pads worn out")
        self.assertEqual(recent_repairs[0]["mechanic"]["name"], "Mike Fixer")

        recent_orders = data["recent_actions"]["product_orders"]
        self.assertEqual(len(recent_orders), 1)
        self.assertEqual(recent_orders[0]["items_count"], 1)
        self.assertEqual(recent_orders[0]["items"][0]["product"]["name"], "Synthetic Oil 5W-30")
        self.assertEqual(recent_orders[0]["items"][0]["quantity"], 2)
        self.assertEqual(recent_orders[0]["items"][0]["subtotal"], 36000.0)

    def test_account_detail_query_param_delegation(self):
        # Test delegation via /management/accounts/?user_id=<id>
        url = f"/api/v1/admin/management/accounts/?user_id={self.primary_user.id}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["user"]["id"], str(self.primary_user.id))

    def test_account_detail_section_filtering(self):
        # Section mechanic_requests
        url = f"/api/v1/admin/management/accounts/{self.primary_user.id}/?section=mechanic_requests"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertIn("repairs", data)
        self.assertIn("summary", data)

        # Section products
        url = f"/api/v1/admin/management/accounts/{self.primary_user.id}/?section=products"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertIn("orders", data)
        self.assertIn("summary", data)
