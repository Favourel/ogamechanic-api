from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from .models import RentalBooking, RentalReview, RentalPeriod
from products.models import Product, Category

User = get_user_model()


class RentalBookingModelTest(TestCase):
    def setUp(self):
        # Create roles
        from users.models import Role
        self.customer_role = Role.objects.create(name='customer')
        self.merchant_role = Role.objects.create(name='merchant')
        
        # Create users
        self.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123'
        )
        self.customer.roles.add(self.customer_role)
        
        self.merchant = User.objects.create_user(
            email='merchant@test.com',
            password='testpass123'
        )
        self.merchant.roles.add(self.merchant_role)
        
        # Create category and product
        self.category = Category.objects.create(name='Cars')
        self.product = Product.objects.create(
            merchant=self.merchant,
            category=self.category,
            name='Test Car',
            description='A test car for rental',
            price=Decimal('100.00'),
            is_rental=True
        )
        
        # Create rental booking
        self.rental_booking = RentalBooking.objects.create(
            customer=self.customer,
            product=self.product,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            daily_rate=Decimal('50.00'),
            total_amount=Decimal('200.00'),
            pickup_location='Test Pickup Location',
            return_location='Test Return Location'
        )

    def test_rental_booking_creation(self):
        """Test rental booking creation"""
        self.assertEqual(self.rental_booking.customer, self.customer)
        self.assertEqual(self.rental_booking.product, self.product)
        self.assertEqual(self.rental_booking.status, 'pending')
        self.assertEqual(self.rental_booking.duration_days, 4)

    def test_rental_booking_str_representation(self):
        """Test rental booking string representation"""
        expected = f"Rental {self.rental_booking.booking_reference} - {self.customer.email}"
        self.assertEqual(str(self.rental_booking), expected)

    def test_rental_booking_status_transitions(self):
        """Test rental booking status transitions"""
        # Test confirm booking
        self.assertTrue(self.rental_booking.confirm_booking())
        self.assertEqual(self.rental_booking.status, 'confirmed')
        self.assertIsNotNone(self.rental_booking.confirmed_at)
        
        # Test start rental
        self.assertTrue(self.rental_booking.start_rental())
        self.assertEqual(self.rental_booking.status, 'active')
        self.assertIsNotNone(self.rental_booking.started_at)
        
        # Test complete rental
        self.assertTrue(self.rental_booking.complete_rental())
        self.assertEqual(self.rental_booking.status, 'completed')
        self.assertIsNotNone(self.rental_booking.completed_at)

    def test_rental_booking_cancellation(self):
        """Test rental booking cancellation"""
        self.assertTrue(self.rental_booking.can_be_cancelled)
        self.assertTrue(self.rental_booking.cancel_booking("Test cancellation"))
        self.assertEqual(self.rental_booking.status, 'cancelled')
        self.assertIsNotNone(self.rental_booking.cancelled_at)

    def test_rental_booking_rejection(self):
        """Test rental booking rejection"""
        self.assertTrue(self.rental_booking.reject_booking("Test rejection"))
        self.assertEqual(self.rental_booking.status, 'rejected')


class RentalReviewModelTest(TestCase):
    def setUp(self):
        # Create roles
        from users.models import Role
        self.customer_role = Role.objects.create(name='customer')
        self.merchant_role = Role.objects.create(name='merchant')
        
        # Create users
        self.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123'
        )
        self.customer.roles.add(self.customer_role)
        
        self.merchant = User.objects.create_user(
            email='merchant@test.com',
            password='testpass123'
        )
        self.merchant.roles.add(self.merchant_role)
        
        # Create category and product
        self.category = Category.objects.create(name='Cars')
        self.product = Product.objects.create(
            merchant=self.merchant,
            category=self.category,
            name='Test Car',
            description='A test car for rental',
            price=Decimal('100.00'),
            is_rental=True
        )
        
        # Create rental booking
        self.rental_booking = RentalBooking.objects.create(
            customer=self.customer,
            product=self.product,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            daily_rate=Decimal('50.00'),
            total_amount=Decimal('200.00'),
            pickup_location='Test Pickup Location',
            return_location='Test Return Location'
        )
        
        # Create rental review
        self.rental_review = RentalReview.objects.create(
            rental=self.rental_booking,
            customer=self.customer,
            rating=5,
            comment='Great rental experience!'
        )

    def test_rental_review_creation(self):
        """Test rental review creation"""
        self.assertEqual(self.rental_review.rental, self.rental_booking)
        self.assertEqual(self.rental_review.customer, self.customer)
        self.assertEqual(self.rental_review.rating, 5)
        self.assertEqual(self.rental_review.comment, 'Great rental experience!')

    def test_rental_review_str_representation(self):
        """Test rental review string representation"""
        expected = (f"Review for {self.rental_booking.booking_reference} "
                   f"by {self.customer.email}")
        self.assertEqual(str(self.rental_review), expected)


class RentalPeriodModelTest(TestCase):
    def setUp(self):
        # Create roles
        from users.models import Role
        self.merchant_role = Role.objects.create(name='merchant')
        
        # Create merchant
        self.merchant = User.objects.create_user(
            email='merchant@test.com',
            password='testpass123'
        )
        self.merchant.roles.add(self.merchant_role)
        
        # Create category and product
        self.category = Category.objects.create(name='Cars')
        self.product = Product.objects.create(
            merchant=self.merchant,
            category=self.category,
            name='Test Car',
            description='A test car for rental',
            price=Decimal('100.00'),
            is_rental=True
        )
        
        # Create rental period
        self.rental_period = RentalPeriod.objects.create(
            product=self.product,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=7),
            daily_rate=Decimal('50.00'),
            is_available=True
        )

    def test_rental_period_creation(self):
        """Test rental period creation"""
        self.assertEqual(self.rental_period.product, self.product)
        self.assertEqual(self.rental_period.duration_days, 8)
        self.assertEqual(self.rental_period.total_cost, Decimal('400.00'))
        self.assertTrue(self.rental_period.is_available)

    def test_rental_period_str_representation(self):
        """Test rental period string representation"""
        expected = f"{self.product.name} - {self.rental_period.start_date} to {self.rental_period.end_date}"
        self.assertEqual(str(self.rental_period), expected)
