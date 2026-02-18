from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import DeliveryRequest, DeliveryTracking, CourierRating

User = get_user_model()


class DeliveryRequestModelTest(TestCase):
    """Test DeliveryRequest model functionality"""

    def setUp(self):
        self.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123'
        )
        self.driver = User.objects.create_user(
            email='driver@test.com',
            password='testpass123'
        )

    def test_delivery_request_creation(self):
        """Test creating a delivery request"""
        delivery_request = DeliveryRequest.objects.create(
            customer=self.customer,
            pickup_address="123 Pickup St, Lagos",
            pickup_latitude=6.5244,
            pickup_longitude=3.3792,
            pickup_contact_name="John Doe",
            pickup_contact_phone="+2341234567890",
            delivery_address="456 Delivery Ave, Lagos",
            delivery_latitude=6.5244,
            delivery_longitude=3.3792,
            delivery_contact_name="Jane Smith",
            delivery_contact_phone="+2340987654321",
            package_description="Test package",
            package_weight=2.5,
            base_fare=500.00,
            distance_fare=200.00,
            total_fare=700.00
        )

        self.assertEqual(delivery_request.customer, self.customer)
        self.assertEqual(delivery_request.status, 'pending')
        self.assertEqual(delivery_request.total_fare, 700.00)
        self.assertTrue(delivery_request.is_active)
        self.assertTrue(delivery_request.can_be_cancelled)

    def test_delivery_request_status_transitions(self):
        """Test delivery request status transitions"""
        delivery_request = DeliveryRequest.objects.create(
            customer=self.customer,
            pickup_address="123 Pickup St, Lagos",
            pickup_latitude=6.5244,
            pickup_longitude=3.3792,
            pickup_contact_name="John Doe",
            pickup_contact_phone="+2341234567890",
            delivery_address="456 Delivery Ave, Lagos",
            delivery_latitude=6.5244,
            delivery_longitude=3.3792,
            delivery_contact_name="Jane Smith",
            delivery_contact_phone="+2340987654321",
            package_description="Test package",
            package_weight=2.5,
            base_fare=500.00,
            distance_fare=200.00,
            total_fare=700.00
        )

        # Test assigning driver
        self.assertTrue(delivery_request.assign_driver(self.driver))
        self.assertEqual(delivery_request.status, 'assigned')
        self.assertEqual(delivery_request.driver, self.driver)

        # Test marking as picked up
        self.assertTrue(delivery_request.mark_as_picked_up())
        self.assertEqual(delivery_request.status, 'picked_up')

        # Test marking as delivered
        self.assertTrue(delivery_request.mark_as_delivered())
        self.assertEqual(delivery_request.status, 'delivered')
        self.assertFalse(delivery_request.is_active)


class DeliveryTrackingModelTest(TestCase):
    """Test DeliveryTracking model functionality"""

    def setUp(self):
        self.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123'
        )
        self.driver = User.objects.create_user(
            email='driver@test.com',
            password='testpass123'
        )
        self.delivery_request = DeliveryRequest.objects.create(
            customer=self.customer,
            driver=self.driver,
            pickup_address="123 Pickup St, Lagos",
            pickup_latitude=6.5244,
            pickup_longitude=3.3792,
            pickup_contact_name="John Doe",
            pickup_contact_phone="+2341234567890",
            delivery_address="456 Delivery Ave, Lagos",
            delivery_latitude=6.5244,
            delivery_longitude=3.3792,
            delivery_contact_name="Jane Smith",
            delivery_contact_phone="+2340987654321",
            package_description="Test package",
            package_weight=2.5,
            base_fare=500.00,
            distance_fare=200.00,
            total_fare=700.00
        )

    def test_tracking_update_creation(self):
        """Test creating a tracking update"""
        tracking_update = DeliveryTracking.objects.create(
            delivery_request=self.delivery_request,
            driver=self.driver,
            latitude=6.5244,
            longitude=3.3792,
            status="Heading to pickup location",
            notes="Driver is on the way"
        )

        self.assertEqual(tracking_update.delivery_request, self.delivery_request)
        self.assertEqual(tracking_update.driver, self.driver)
        self.assertEqual(tracking_update.status, "Heading to pickup location")


class CourierRatingModelTest(TestCase):
    """Test CourierRating model functionality"""

    def setUp(self):
        self.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123'
        )
        self.driver = User.objects.create_user(
            email='driver@test.com',
            password='testpass123'
        )
        self.delivery_request = DeliveryRequest.objects.create(
            customer=self.customer,
            driver=self.driver,
            pickup_address="123 Pickup St, Lagos",
            pickup_latitude=6.5244,
            pickup_longitude=3.3792,
            pickup_contact_name="John Doe",
            pickup_contact_phone="+2341234567890",
            delivery_address="456 Delivery Ave, Lagos",
            delivery_latitude=6.5244,
            delivery_longitude=3.3792,
            delivery_contact_name="Jane Smith",
            delivery_contact_phone="+2340987654321",
            package_description="Test package",
            package_weight=2.5,
            base_fare=500.00,
            distance_fare=200.00,
            total_fare=700.00,
            status='delivered'
        )

    def test_rating_creation(self):
        """Test creating a courier rating"""
        rating = CourierRating.objects.create(
            delivery_request=self.delivery_request,
            customer=self.customer,
            driver=self.driver,
            overall_rating=5,
            delivery_speed_rating=4,
            service_quality_rating=5,
            communication_rating=4,
            review="Great service, very professional!"
        )

        self.assertEqual(rating.delivery_request, self.delivery_request)
        self.assertEqual(rating.customer, self.customer)
        self.assertEqual(rating.driver, self.driver)
        self.assertEqual(rating.overall_rating, 5)
        self.assertEqual(rating.average_rating, 4.5)
