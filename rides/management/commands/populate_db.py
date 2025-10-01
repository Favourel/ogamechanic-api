import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from rides.models import Ride
from users.models import DriverProfile  # Import DriverProfile
from users.models import Role  # Import Role for assigning roles
from faker import Faker

User = get_user_model()
fake = Faker()


class Command(BaseCommand):
    help = "Populate the database with fake users and rides"

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=10,
            help='Number of users to create'
        )
        parser.add_argument(
            '--rides',
            type=int,
            default=30,
            help='Number of rides to create'
        )

    def handle(self, *args, **options):
        num_users = options['users']
        num_rides = options['rides']

        # Get or create the customer and driver roles
        customer_role, _ = Role.objects.get_or_create(name="customer")
        driver_role, _ = Role.objects.get_or_create(name="rider")

        # Create fake users
        users = []
        for _ in range(num_users):
            email = fake.unique.email()
            first_name = fake.first_name()
            last_name = fake.last_name()
            user = User.objects.create_user(
                email=email,
                password='Password123!',
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            # Assign both customer and driver roles to the user
            user.roles.add(customer_role, driver_role)
            # Optionally set the active_role to customer by default
            if hasattr(user, "active_role"):
                user.active_role = customer_role
                user.save(update_fields=["active_role"])
            users.append(user)
        self.stdout.write(
            self.style.SUCCESS(f'Created {len(users)} users.')
        )

        # Create approved driver profiles for half of the users
        drivers = []
        for user in random.sample(users, k=max(1, len(users)//2)):
            # Create a DriverProfile and mark as approved
            driver_profile, created = DriverProfile.objects.get_or_create(
                user=user,
                defaults={
                    "full_name": f"{user.first_name} {user.last_name}",
                    "phone_number": fake.phone_number(),
                    "date_of_birth": fake.date_of_birth(minimum_age=21, maximum_age=60), # noqa
                    "address": fake.address(),
                    "government_id": fake.ssn(),
                    "driver_license": fake.license_plate(),
                    "vehicle_type": random.choice(["car", "bike", "van"]),
                    "vehicle_registration_number": fake.license_plate(),
                    "vehicle_photo": None,
                    "insurance_document": None,
                    "is_approved": True,
                }
            )
            if not created:
                driver_profile.is_approved = True
                driver_profile.save(update_fields=["is_approved"])
            drivers.append(user)

        # Create fake rides
        for _ in range(num_rides):
            customer = random.choice(users)
            # Only assign a driver with an approved driver profile
            driver = random.choice(drivers) if drivers and random.random() > 0.5 else None # noqa
            pickup_address = fake.address()
            dropoff_address = fake.address()
            pickup_latitude = fake.latitude()
            pickup_longitude = fake.longitude()
            dropoff_latitude = fake.latitude()
            dropoff_longitude = fake.longitude()
            status = random.choice([
                'requested',
                'accepted',
                'in_progress',
                'completed',
                'cancelled'
            ])
            fare = round(random.uniform(500, 5000), 2)
            Ride.objects.create(
                customer=customer,
                driver=driver,
                pickup_address=pickup_address,
                pickup_latitude=pickup_latitude,
                pickup_longitude=pickup_longitude,
                dropoff_address=dropoff_address,
                dropoff_latitude=dropoff_latitude,
                dropoff_longitude=dropoff_longitude,
                status=status,
                fare=fare,
            )
        self.stdout.write(
            self.style.SUCCESS(f'Created {num_rides} rides.')
        )
