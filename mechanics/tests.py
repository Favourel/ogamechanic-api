from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.conf import settings

from mechanics.models import RepairRequest, RepairProblemResolve
from users.models import Role, MechanicProfile, Wallet, MechanicReview

User = get_user_model()


class MechanicRequestFlowIntegrationTest(APITestCase):
    """
    Test the complete end-to-end repair request lifecycle:
    1. Booking (pending + OTP generation)
    2. Accept -> in_transit -> arrived
    3. Verify OTP -> in_progress
    4. Complete repair (problem resolutions + actual_cost)
    5. Online Paystack payment & Mechanic Wallet crediting (minus commission)
    6. Cash on Delivery flow & Mechanic Wallet commission debit
    7. Customer rating / review
    8. Mechanic consolidated earnings
    """

    def setUp(self):
        # Setup roles
        self.primary_role, _ = Role.objects.get_or_create(name='primary_user')
        self.mechanic_role, _ = Role.objects.get_or_create(name='mechanic')

        # Setup customer
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='Password123!',
            first_name='John',
            last_name='Customer'
        )
        self.customer.roles.add(self.primary_role)
        self.customer.active_role = self.primary_role
        self.customer.save()

        # Setup mechanic
        self.mechanic = User.objects.create_user(
            email='mechanic@example.com',
            password='Password123!',
            first_name='Mike',
            last_name='Mechanic'
        )
        self.mechanic.roles.add(self.mechanic_role)
        self.mechanic.active_role = self.mechanic_role
        self.mechanic.save()

        self.mechanic_profile = MechanicProfile.objects.create(
            user=self.mechanic,
            location="Marina, Lagos",
            is_approved=True,
            latitude=6.5244,
            longitude=3.3792
        )

        # Setup wallet for mechanic
        self.mechanic_wallet, _ = Wallet.objects.get_or_create(user=self.mechanic)

    def post_inbound(self, url, data):
        return self.client.post(
            url,
            {"requestType": "inbound", "data": data},
            format='json',
            HTTP_X_API_KEY=settings.X_API_KEY
        )

    def patch_inbound(self, url, data):
        return self.client.patch(
            url,
            {"requestType": "inbound", "data": data},
            format='json',
            HTTP_X_API_KEY=settings.X_API_KEY
        )

    def get_inbound(self, url):
        return self.client.get(
            url,
            HTTP_X_API_KEY=settings.X_API_KEY
        )

    def _create_and_progress_repair_to_completed(self, actual_cost=Decimal('50000.00')):
        """Helper to create a repair request and progress it to 'completed' status"""
        repair = RepairRequest.objects.create(
            customer=self.customer,
            mechanic=self.mechanic,
            vehicle_make="Toyota",
            vehicle_model="Camry",
            vehicle_year=2018,
            problem_description="Brake pads replacement and engine servicing",
            estimated_cost=Decimal('45000.00'),
            service_address="123 Broad St, Marina, Lagos",
            service_latitude=Decimal('6.5244'),
            service_longitude=Decimal('3.3792'),
            status="pending"
        )
        # Verify OTP is generated at creation
        self.assertIsNotNone(repair.otp_code)
        self.assertEqual(len(repair.otp_code), 6)

        # Step 2: Accept -> in_transit -> arrived
        repair.status = "accepted"
        repair.save()
        repair.status = "in_transit"
        repair.save()
        repair.status = "arrived"
        repair.save()

        # Step 4: Mechanic submits OTP -> in_progress
        self.client.force_authenticate(user=self.mechanic)
        resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/verify-otp/",
            {"otp_code": repair.otp_code}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        repair.refresh_from_db()
        self.assertEqual(repair.status, "in_progress")
        self.assertTrue(repair.is_otp_verified)

        # Step 5: Mechanic submits resolutions & actual_cost -> completed
        RepairProblemResolve.objects.create(
            repair_request=repair,
            description="Replaced front ceramic brake pads and changed engine oil"
        )
        repair.actual_cost = actual_cost
        repair.status = "completed"
        repair.save()

        return repair

    @patch('requests.post')
    @patch('requests.get')
    def test_option_a_online_paystack_payment_flow(self, mock_get, mock_post):
        """
        Test Option A:
        Customer initializes Paystack payment -> verifies payment ->
        10% commission deducted -> 90% net earnings credited to mechanic wallet ->
        Order becomes verify_completed -> Customer rates mechanic.
        """
        repair = self._create_and_progress_repair_to_completed(actual_cost=Decimal('50000.00'))

        # Step 6 - OPTION A: Customer initiates payment
        self.client.force_authenticate(user=self.customer)

        # Mock Paystack initialize response
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": "https://checkout.paystack.com/test_ref_123",
                    "access_code": "test_access_code",
                    "reference": "REPAIR_TEST_123"
                }
            }
        )

        pay_resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/pay/",
            {"payment_method": "online"}
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(pay_resp.data['status'])
        self.assertEqual(pay_resp.data['data']['authorization_url'], "https://checkout.paystack.com/test_ref_123")
        generated_ref = pay_resp.data['data']['reference']

        repair.refresh_from_db()
        self.assertEqual(repair.payment_method, 'online')
        self.assertEqual(repair.payment_reference, generated_ref)

        # Mock Paystack verify response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": True,
                "data": {
                    "status": "success",
                    "amount": 5000000,  # 50,000 NGN in kobo
                    "reference": generated_ref
                }
            }
        )

        verify_resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/verify-payment/",
            {"reference": generated_ref}
        )
        self.assertEqual(verify_resp.status_code, status.HTTP_200_OK)

        repair.refresh_from_db()
        # Status becomes verify_completed
        self.assertEqual(repair.status, "verify_completed")
        self.assertEqual(repair.payment_status, "paid")
        self.assertIsNotNone(repair.paid_at)

        # 10% Platform Commission = 5,000 NGN; Net Earnings = 45,000 NGN
        self.assertEqual(repair.platform_commission, Decimal('5000.00'))
        self.assertEqual(repair.net_earnings, Decimal('45000.00'))

        # Mechanic Wallet Credited with 45,000 NGN
        self.mechanic_wallet.refresh_from_db()
        self.assertEqual(self.mechanic_wallet.balance, Decimal('45000.00'))

        # Step 7: Customer rates the mechanic
        rate_resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/rate/",
            {
                "rating": 5,
                "comment": "Mike did an exceptional job, car drives like new!"
            }
        )
        self.assertEqual(rate_resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(rate_resp.data['status'])

        review = MechanicReview.objects.get(mechanic=self.mechanic_profile, user=self.customer)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Mike did an exceptional job, car drives like new!")

        # Step 8: Mechanic checks consolidated earnings
        self.client.force_authenticate(user=self.mechanic)
        earnings_resp = self.get_inbound("/api/v1/users/earnings/")
        self.assertEqual(earnings_resp.status_code, status.HTTP_200_OK)
        mechanic_earnings = earnings_resp.data['data']['mechanic_earnings']
        self.assertEqual(Decimal(str(mechanic_earnings['total_earnings'])), Decimal('45000.00'))
        self.assertEqual(mechanic_earnings['completed_tasks'], 1)

    def test_option_b_cash_on_delivery_flow(self):
        """
        Test Option B:
        Customer pays cash in hand to mechanic -> Customer confirms ->
        Platform commission debited from Mechanic Wallet ->
        Order becomes verify_completed.
        """
        # Give mechanic initial wallet balance of 10,000 NGN
        self.mechanic_wallet.balance = Decimal('10000.00')
        self.mechanic_wallet.save()

        repair = self._create_and_progress_repair_to_completed(actual_cost=Decimal('50000.00'))

        # Step 6 - OPTION B: Customer confirms cash payment
        self.client.force_authenticate(user=self.customer)
        pay_resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/pay/",
            {"payment_method": "cash_on_delivery"}
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(pay_resp.data['status'])

        repair.refresh_from_db()
        self.assertEqual(repair.payment_method, "cash_on_delivery")
        self.assertEqual(repair.payment_status, "paid")
        self.assertEqual(repair.status, "verify_completed")
        self.assertEqual(repair.platform_commission, Decimal('5000.00'))
        self.assertEqual(repair.net_earnings, Decimal('45000.00'))

        # Platform commission of 5,000 NGN is debited from mechanic wallet (10,000 - 5,000 = 5,000)
        self.mechanic_wallet.refresh_from_db()
        self.assertEqual(self.mechanic_wallet.balance, Decimal('5000.00'))

    def test_webhook_handles_online_repair_payment(self):
        """
        Test that PaystackWebhookView automatically handles REPAIR_ references
        """
        repair = self._create_and_progress_repair_to_completed(actual_cost=Decimal('30000.00'))
        ref = f"REPAIR_AUTO_WEBHOOK_{repair.id.hex[:8].upper()}"
        repair.payment_reference = ref
        repair.payment_method = 'online'
        repair.save()

        # Send webhook event
        webhook_data = {
            "event": "charge.success",
            "data": {
                "reference": ref,
                "amount": 3000000,  # 30,000 NGN in kobo
                "metadata": {
                    "repair_request_id": str(repair.id)
                }
            }
        }

        # Mock HMAC signature verification
        with patch('hmac.compare_digest', return_value=True):
            resp = self.client.post(
                "/api/v1/users/paystack/webhook/",
                webhook_data,
                format='json',
                HTTP_X_PAYSTACK_SIGNATURE="valid_dummy_signature"
            )
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        repair.refresh_from_db()
        self.assertEqual(repair.status, "verify_completed")
        self.assertEqual(repair.payment_status, "paid")
        self.assertEqual(repair.platform_commission, Decimal('3000.00'))
        self.assertEqual(repair.net_earnings, Decimal('27000.00'))

        self.mechanic_wallet.refresh_from_db()
        self.assertEqual(self.mechanic_wallet.balance, Decimal('27000.00'))

    def test_payment_required_before_transitioning_to_verify_completed(self):
        """
        Ensure customer cannot manually PATCH status to 'verify_completed'
        without completing payment first.
        """
        repair = self._create_and_progress_repair_to_completed(actual_cost=Decimal('20000.00'))

        self.client.force_authenticate(user=self.customer)
        resp = self.patch_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/",
            {"status": "verify_completed"}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Payment is required", resp.data['message'])

    def test_actual_cost_exceeding_variance_threshold_is_rejected(self):
        """
        Mechanic cannot set actual_cost exceeding estimated_cost by more than
        the configured variance threshold (default 30%) without customer-approved add-ons.
        """
        repair = RepairRequest.objects.create(
            customer=self.customer,
            mechanic=self.mechanic,
            vehicle_make="Toyota",
            vehicle_model="Corolla",
            vehicle_year=2020,
            problem_description="Clutch issue",
            estimated_cost=Decimal('20000.00'),
            service_address="Victoria Island, Lagos",
            service_latitude=Decimal('6.4281'),
            service_longitude=Decimal('3.4219'),
            status="in_progress",
            is_otp_verified=True
        )

        self.client.force_authenticate(user=self.mechanic)

        # Attempt to set actual_cost to 35,000 NGN (+75%, max allowed is 26,000 NGN)
        resp = self.patch_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/",
            {
                "actual_cost": 35000.00,
                "status": "completed"
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exceeds the maximum allowed estimate", str(resp.data))

    def test_actual_cost_within_variance_threshold_is_accepted(self):
        """
        Mechanic can complete repair when actual_cost is within the 30% variance threshold.
        """
        repair = RepairRequest.objects.create(
            customer=self.customer,
            mechanic=self.mechanic,
            vehicle_make="Toyota",
            vehicle_model="Corolla",
            vehicle_year=2020,
            problem_description="Clutch issue",
            estimated_cost=Decimal('20000.00'),
            service_address="Victoria Island, Lagos",
            service_latitude=Decimal('6.4281'),
            service_longitude=Decimal('3.4219'),
            status="in_progress",
            is_otp_verified=True
        )

        self.client.force_authenticate(user=self.mechanic)

        # 24,000 is +20% (well within 30% threshold of 26,000)
        resp = self.patch_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/",
            {
                "actual_cost": 24000.00,
                "status": "completed"
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        repair.refresh_from_db()
        self.assertEqual(repair.status, "completed")
        self.assertEqual(repair.actual_cost, Decimal('24000.00'))

    def test_itemized_addon_approval_flow_expands_allowed_cost(self):
        """
        Test Approach C:
        1. Mechanic finds extra fault, adds itemized resolution with cost (+25,000 NGN).
        2. Resolution starts as 'pending'.
        3. Customer reviews and approves resolution.
        4. estimated_cost expands from 20,000 to 45,000 NGN.
        5. Mechanic can now complete the job at 45,000 NGN successfully.
        """
        repair = RepairRequest.objects.create(
            customer=self.customer,
            mechanic=self.mechanic,
            vehicle_make="Honda",
            vehicle_model="Civic",
            vehicle_year=2020,
            problem_description="Engine overheating",
            estimated_cost=Decimal('20000.00'),
            service_address="Lekki Phase 1, Lagos",
            service_latitude=Decimal('6.4474'),
            service_longitude=Decimal('3.4723'),
            status="in_progress",
            is_otp_verified=True
        )

        # 1. Mechanic submits add-on resolution
        self.client.force_authenticate(user=self.mechanic)
        resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/problem-resolves/",
            {
                "description": "Cracked radiator replacement",
                "additional_cost": 25000.00
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resolve_id = resp.data['data']['id']
        self.assertEqual(resp.data['data']['status'], 'pending')

        # 2. Customer lists resolutions
        self.client.force_authenticate(user=self.customer)
        get_resp = self.get_inbound(f"/api/v1/mechanics/repair-requests/{repair.id}/problem-resolves/")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_resp.data['data']), 1)
        self.assertEqual(get_resp.data['data'][0]['status'], 'pending')

        # 3. Customer approves add-on
        resp_approve = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/problem-resolves/{resolve_id}/respond/",
            {"action": "approve"}
        )
        self.assertEqual(resp_approve.status_code, status.HTTP_200_OK)
        repair.refresh_from_db()
        self.assertEqual(repair.estimated_cost, Decimal('45000.00'))  # 20,000 + 25,000

        # 4. Mechanic can now complete at 45,000 NGN
        self.client.force_authenticate(user=self.mechanic)
        resp_complete = self.patch_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/",
            {
                "actual_cost": 45000.00,
                "status": "completed"
            }
        )
        self.assertEqual(resp_complete.status_code, status.HTTP_200_OK)
        repair.refresh_from_db()
        self.assertEqual(repair.status, "completed")
        self.assertEqual(repair.actual_cost, Decimal('45000.00'))

    def test_customer_can_reject_itemized_addon(self):
        """
        Customer rejects an add-on; estimated_cost is unchanged and inflated cost is blocked.
        """
        repair = RepairRequest.objects.create(
            customer=self.customer,
            mechanic=self.mechanic,
            vehicle_make="Honda",
            vehicle_model="Civic",
            vehicle_year=2020,
            problem_description="Engine check",
            estimated_cost=Decimal('20000.00'),
            service_address="Lekki Phase 1, Lagos",
            service_latitude=Decimal('6.4474'),
            service_longitude=Decimal('3.4723'),
            status="in_progress",
            is_otp_verified=True
        )

        # Mechanic adds expensive add-on
        self.client.force_authenticate(user=self.mechanic)
        resp = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/problem-resolves/",
            {
                "description": "Entire ECU unit replacement",
                "additional_cost": 80000.00
            }
        )
        resolve_id = resp.data['data']['id']

        # Customer rejects
        self.client.force_authenticate(user=self.customer)
        resp_reject = self.post_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/problem-resolves/{resolve_id}/respond/",
            {"action": "reject"}
        )
        self.assertEqual(resp_reject.status_code, status.HTTP_200_OK)
        repair.refresh_from_db()
        self.assertEqual(repair.estimated_cost, Decimal('20000.00'))  # Unchanged

        # Mechanic tries to set actual_cost to 100,000 NGN -> blocked!
        self.client.force_authenticate(user=self.mechanic)
        resp_fail = self.patch_inbound(
            f"/api/v1/mechanics/repair-requests/{repair.id}/",
            {
                "actual_cost": 100000.00,
                "status": "completed"
            }
        )
        self.assertEqual(resp_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exceeds the maximum allowed estimate", str(resp_fail.data))
