"""
Django management command to populate the mechanics app with dummy data.
Creates mechanic users, repair requests, training sessions, and participants.
"""

import random
from datetime import datetime, timedelta, time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from mechanics.models import (
    RepairRequest,
    TrainingSession,
    TrainingSessionParticipant,
    VehicleMake,
    MechanicVehicleExpertise,
)
from users.models import MechanicProfile, MechanicReview, Role
from django.core.files.base import ContentFile
from io import BytesIO
from PIL import Image

User = get_user_model()

# Service types for repair requests
SERVICE_TYPES = [
    "Engine Repair",
    "Brake Service",
    "Transmission Service",
    "Electrical Repair",
    "AC Repair",
    "Oil Change",
    "Tire Replacement",
    "Battery Replacement",
    "Suspension Repair",
    "Exhaust System Repair",
    "Diagnostic Service",
    "Preventive Maintenance",
    "Emergency Repair",
    "Body Work",
    "Paint Job",
]

# Vehicle makes and models
VEHICLE_MAKES = [
    "Toyota",
    "Honda",
    "Ford",
    "Nissan",
    "Chevrolet",
    "Hyundai",
    "Kia",
    "Mazda",
    "Subaru",
    "Volkswagen",
    "BMW",
    "Mercedes-Benz",
    "Audi",
    "Lexus",
    "Infiniti",
    "Acura",
    "Volvo",
    "Jaguar",
    "Land Rover",
    "Porsche",
    "Mitsubishi",
    "Suzuki",
    "Isuzu",
    "Peugeot",
    "Renault",
]

VEHICLE_MODELS = [
    "Camry",
    "Civic",
    "Focus",
    "Altima",
    "Malibu",
    "Elantra",
    "Optima",
    "Mazda6",
    "Legacy",
    "Jetta",
    "3 Series",
    "C-Class",
    "A4",
    "ES",
    "Q50",
    "TLX",
    "XC60",
    "XF",
    "Discovery",
    "911",
    "Lancer",
    "Swift",
    "D-Max",
    "308",
    "Megane",
    "Corolla",
    "Accord",
    "Fusion",
    "Sentra",
    "Cruze",
    "Sonata",
    "Forte",
    "CX-5",
    "Outback",
    "Passat",
    "X3",
    "E-Class",
    "Q5",
    "IS",
    "Q60",
    "MDX",
    "XC90",
    "F-PACE",
    "Range Rover",
]

# Problem descriptions
PROBLEM_DESCRIPTIONS = [
    "Engine making strange noises",
    "Car won't start",
    "Brakes squeaking",
    "AC not cooling properly",
    "Transmission slipping",
    "Check engine light on",
    "Battery keeps dying",
    "Steering wheel shaking",
    "Exhaust smoke",
    "Oil leak",
    "Electrical issues",
    "Suspension problems",
    "Tire wear issues",
    "Overheating",
    "Poor fuel economy",
    "Strange vibrations",
    "Dashboard warning lights",
    "Clutch problems",
    "Power steering issues",
    "Radiator problems",
]

# Symptoms descriptions
SYMPTOMS = [
    "Loud knocking sound from engine",
    "Car cranks but won't start",
    "High-pitched squeal when braking",
    "Warm air instead of cold",
    "RPMs revving but car not moving",
    "Orange warning light on dashboard",
    "Headlights dim when starting",
    "Steering wheel vibrates at high speed",
    "Blue smoke from exhaust",
    "Oil spots under car",
    "Lights flickering",
    "Car bounces over bumps",
    "Uneven tire wear",
    "Temperature gauge in red",
    "Frequent trips to gas station",
    "Steering wheel shakes",
    "Multiple warning lights",
    "Clutch pedal feels soft",
    "Hard to turn steering wheel",
    "Coolant leak visible",
]

# Training session data
TRAINING_TITLES = [
    "Basic Engine Maintenance",
    "Advanced Diagnostic Techniques",
    "Hybrid Vehicle Repair",
    "Electric Vehicle Systems",
    "Brake System Overhaul",
    "Transmission Rebuilding",
    "AC System Service",
    "Electrical Troubleshooting",
    "Suspension and Alignment",
    "Exhaust System Repair",
    "Paint and Bodywork",
    "Computer Diagnostics",
    "Safety Procedures",
    "Customer Service Excellence",
    "Business Management for Mechanics",
]

TRAINING_DESCRIPTIONS = [
    "Comprehensive training covering all aspects of modern automotive repair",
    "Hands-on workshop with real vehicle examples",
    "Certification program for professional mechanics",
    "Advanced techniques for experienced technicians",
    "Specialized training for specific vehicle systems",
    "Safety-first approach to automotive repair",
    "Modern diagnostic equipment training",
    "Customer communication and service excellence",
    "Business skills for independent mechanics",
    "Environmental and safety compliance",
]

# Venue locations in Lagos
VENUES = [
    "Lagos State Technical College",
    "Federal College of Education (Technical)",
    "Yaba College of Technology",
    "Lagos Business School",
    "Nigerian Institute of Welding",
    "Automotive Training Center Lagos",
    "Mechanic Village Ikeja",
    "Lagos State Polytechnic",
    "Technical Training Institute",
    "Professional Development Center",
]

VENUE_ADDRESSES = [
    "1 Technical Road, Yaba, Lagos",
    "2 College Road, Akoka, Lagos",
    "3 Sabo Street, Yaba, Lagos",
    "4 Business District, Victoria Island, Lagos",
    "5 Industrial Area, Ikeja, Lagos",
    "6 Training Center, Surulere, Lagos",
    "7 Mechanic Village, Ikeja, Lagos",
    "8 Polytechnic Road, Ikorodu, Lagos",
    "9 Technical Street, Mushin, Lagos",
    "10 Professional Avenue, Lekki, Lagos",
]

# Lagos coordinates (approximate)
LAGOS_COORDINATES = [
    (6.5244, 3.3792),  # Lagos Island
    (6.4474, 3.3903),  # Ikeja
    (6.4922, 3.3724),  # Surulere
    (6.4281, 3.4219),  # Yaba
    (6.4698, 3.5852),  # Victoria Island
    (6.6114, 3.3558),  # Ikorodu
    (6.5244, 3.3792),  # Mushin
    (6.4474, 3.3903),  # Lekki
    (6.4922, 3.3724),  # Apapa
    (6.4281, 3.4219),  # Oshodi
]

# Customer locations in Lagos
CUSTOMER_LOCATIONS = [
    "Victoria Island, Lagos",
    "Ikoyi, Lagos",
    "Lekki, Lagos",
    "Surulere, Lagos",
    "Ikeja, Lagos",
    "Yaba, Lagos",
    "Mushin, Lagos",
    "Oshodi, Lagos",
    "Apapa, Lagos",
    "Ikorodu, Lagos",
    "Mile 2, Lagos",
    "Festac, Lagos",
    "Gbagada, Lagos",
    "Magodo, Lagos",
    "Ogba, Lagos",
]

CUSTOMER_COORDINATES = [
    (6.4281, 3.4219),  # Victoria Island
    (6.4474, 3.3903),  # Ikoyi
    (6.4698, 3.5852),  # Lekki
    (6.4922, 3.3724),  # Surulere
    (6.5244, 3.3792),  # Ikeja
    (6.4474, 3.3903),  # Yaba
    (6.5244, 3.3792),  # Mushin
    (6.4281, 3.4219),  # Oshodi
    (6.4922, 3.3724),  # Apapa
    (6.6114, 3.3558),  # Ikorodu
    (6.4474, 3.3903),  # Mile 2
    (6.4698, 3.5852),  # Festac
    (6.5244, 3.3792),  # Gbagada
    (6.4281, 3.4219),  # Magodo
    (6.4922, 3.3724),  # Ogba
]

# Review comments
REVIEW_COMMENTS = [
    "Excellent service, very professional",
    "Fixed my car quickly and efficiently",
    "Great communication throughout the process",
    "Fair pricing and quality work",
    "Highly recommend this mechanic",
    "Very knowledgeable and experienced",
    "Clean and organized workspace",
    "Honest assessment of the problem",
    "Completed work on time",
    "Friendly and approachable",
    "Used quality parts",
    "Explained everything clearly",
    "Went above and beyond expectations",
    "Reasonable prices for quality work",
    "Will definitely use again",
]


def generate_image_file(name="dummy.jpg", size=(200, 200), color=(155, 0, 0)):
    """Generate a simple image file in memory."""
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, "JPEG")
    file_obj.seek(0)
    return ContentFile(file_obj.read(), name=name)


class Command(BaseCommand):
    help = "Populate the mechanics app with dummy data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mechanics",
            type=int,
            default=10,
            help="Number of mechanic users to create (default: 10)",
        )
        parser.add_argument(
            "--customers",
            type=int,
            default=20,
            help="Number of customer users to create (default: 20)",
        )
        parser.add_argument(
            "--repair-requests",
            type=int,
            default=50,
            help="Number of repair requests to create (default: 50)",
        )
        parser.add_argument(
            "--training-sessions",
            type=int,
            default=15,
            help="Number of training sessions to create (default: 15)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before populating",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            TrainingSessionParticipant.objects.all().delete()
            TrainingSession.objects.all().delete()
            RepairRequest.objects.all().delete()
            MechanicVehicleExpertise.objects.all().delete()
            MechanicReview.objects.all().delete()
            MechanicProfile.objects.all().delete()
            VehicleMake.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing data cleared."))

        with transaction.atomic():
            # Create vehicle makes first
            vehicle_makes = []
            for make_name in VEHICLE_MAKES:
                vehicle_make, _ = VehicleMake.objects.get_or_create(
                    name=make_name,
                    defaults={
                        "description": f"Vehicle make: {make_name}",
                        "is_active": True
                    }
                )
                vehicle_makes.append(vehicle_make)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(vehicle_makes)} vehicle makes."
                )
            )

            # Get or create the mechanic role
            mechanic_role, _ = Role.objects.get_or_create(name="mechanic")
            primary_user_role, _ = Role.objects.get_or_create(
                name="primary_user")

            # Create mechanic users and profiles
            num_mechanics = options["mechanics"]
            mechanic_users = []
            for i in range(1, num_mechanics + 1):
                email = f"mechanic{i}@example.com"
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "email": email,
                        "is_active": True,
                        "first_name": f"Mechanic{i}",
                        "last_name": "Professional",
                    },
                )
                if created:
                    user.set_password("password123")
                    user.save()
                user.roles.add(mechanic_role)
                user.active_role = mechanic_role
                user.save()

                # Create mechanic profile
                mechanic_profile, _ = MechanicProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "location": random.choice(CUSTOMER_LOCATIONS),
                        "lga": f"LGA {i}",
                        "cac_number": f"RC{i:03d}",
                        # 75% approved
                        "is_approved": random.choice([True, True, True, False]),
                    },
                )

                # Add profile images
                if not mechanic_profile.selfie:
                    selfie_file = generate_image_file(
                        name=f"mechanic_{i}_selfie.jpg",
                        size=(300, 300),
                        color=(
                            random.randint(100, 200),
                            random.randint(100, 200),
                            random.randint(100, 200),
                        ),
                    )
                    mechanic_profile.selfie = selfie_file
                    mechanic_profile.save()

                mechanic_users.append(user)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(mechanic_users)} mechanic users and profiles."
                )
            )

            # Create vehicle expertise for mechanics
            expertise_created = 0
            for mechanic_user in mechanic_users:
                mechanic_profile = mechanic_user.mechanic_profile
                
                # Each mechanic specializes in 2-5 vehicle makes
                num_expertise = random.randint(2, 5)
                selected_makes = random.sample(vehicle_makes, num_expertise)
                
                for vehicle_make in selected_makes:
                    MechanicVehicleExpertise.objects.create(
                        mechanic=mechanic_profile,
                        vehicle_make=vehicle_make,
                        years_of_experience=random.randint(1, 15),
                        certification_level=random.choice([
                            'basic', 'intermediate', 'advanced', 'expert', 'certified'
                        ])
                    )
                    expertise_created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {expertise_created} vehicle expertise records."
                )
            )

            # Create customer users
            num_customers = options["customers"]
            customer_users = []
            for i in range(1, num_customers + 1):
                email = f"customer{i}@example.com"
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "email": email,
                        "is_active": True,
                        "first_name": f"Customer{i}",
                        "last_name": "User",
                    },
                )
                if created:
                    user.set_password("password123")
                    user.save()
                user.roles.add(primary_user_role)
                user.active_role = primary_user_role
                user.save()
                customer_users.append(user)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(customer_users)} customer users.")
            )

            # Create repair requests
            num_repair_requests = options["repair_requests"]
            repair_requests = []
            for i in range(num_repair_requests):
                customer = random.choice(customer_users)
                mechanic = (
                    random.choice(mechanic_users)
                    if random.choice([True, False])
                    else None
                )

                # Random dates in the past 6 months
                days_ago = random.randint(1, 180)
                requested_date = timezone.now() - timedelta(days=days_ago)

                # Random preferred date (1-30 days from request)
                preferred_days = random.randint(1, 30)
                preferred_date = requested_date.date() + timedelta(days=preferred_days)

                # Random coordinates for customer location
                coord_idx = random.randint(0, len(CUSTOMER_COORDINATES) - 1)
                lat, lng = CUSTOMER_COORDINATES[coord_idx]

                # Add some random variation to coordinates
                lat += random.uniform(-0.01, 0.01)
                lng += random.uniform(-0.01, 0.01)

                repair_request = RepairRequest.objects.create(
                    customer=customer,
                    mechanic=mechanic,
                    service_type=random.choice(SERVICE_TYPES),
                    vehicle_make=random.choice(VEHICLE_MAKES),
                    vehicle_model=random.choice(VEHICLE_MODELS),
                    vehicle_year=random.randint(2000, 2024),
                    vehicle_registration=f"LAG{random.randint(100000, 999999)}",
                    problem_description=random.choice(PROBLEM_DESCRIPTIONS),
                    symptoms=random.choice(SYMPTOMS),
                    estimated_cost=round(random.uniform(5000, 100000), 2),
                    service_address=random.choice(CUSTOMER_LOCATIONS),
                    service_latitude=lat,
                    service_longitude=lng,
                    preferred_date=preferred_date,
                    preferred_time_slot=random.choice(
                        ["morning", "afternoon", "evening"]
                    ),
                    status=random.choice(
                        ["pending", "accepted", "in_progress",
                            "completed", "cancelled"]
                    ),
                    priority=random.choice(
                        ["low", "medium", "high", "urgent"]),
                    requested_at=requested_date,
                    notes=f"Additional notes for repair request {i+1}",
                )

                # Set timestamps based on status
                if repair_request.status in ["accepted", "in_progress", "completed"]:
                    repair_request.accepted_at = requested_date + timedelta(
                        hours=random.randint(1, 24)
                    )
                    repair_request.mechanic = mechanic

                if repair_request.status in ["in_progress", "completed"]:
                    repair_request.started_at = repair_request.accepted_at + timedelta(
                        hours=random.randint(1, 48)
                    )

                if repair_request.status == "completed":
                    repair_request.completed_at = repair_request.started_at + timedelta(
                        hours=random.randint(2, 72)
                    )
                    repair_request.actual_cost = round(
                        repair_request.estimated_cost *
                        random.uniform(0.8, 1.2), 2
                    )

                if repair_request.status == "cancelled":
                    repair_request.cancelled_at = requested_date + timedelta(
                        hours=random.randint(1, 48)
                    )
                    repair_request.cancellation_reason = "Customer cancelled"

                repair_request.save()
                repair_requests.append(repair_request)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(repair_requests)} repair requests.")
            )

            # Create training sessions
            num_training_sessions = options["training_sessions"]
            training_sessions = []
            for i in range(num_training_sessions):
                instructor = random.choice(mechanic_users)

                # Random future dates
                days_ahead = random.randint(7, 90)
                start_date = timezone.now().date() + timedelta(days=days_ahead)
                end_date = start_date + timedelta(days=random.randint(1, 5))

                # Random times
                start_time = time(
                    hour=random.randint(8, 10), minute=random.choice([0, 30])
                )
                end_time = time(
                    hour=random.randint(14, 18), minute=random.choice([0, 30])
                )

                # Registration deadline (before start date)
                reg_deadline = timezone.make_aware(
                    datetime.combine(
                        start_date -
                        timedelta(days=random.randint(1, 7)), time(23, 59)
                    )
                )

                # Random venue
                venue_idx = random.randint(0, len(VENUES) - 1)
                lat, lng = LAGOS_COORDINATES[venue_idx]
                lat += random.uniform(-0.01, 0.01)
                lng += random.uniform(-0.01, 0.01)

                training_session = TrainingSession.objects.create(
                    title=random.choice(TRAINING_TITLES),
                    description=random.choice(TRAINING_DESCRIPTIONS),
                    session_type=random.choice(
                        [
                            "basic",
                            "advanced",
                            "specialized",
                            "certification",
                            "workshop",
                        ]
                    ),
                    instructor=instructor,
                    max_participants=random.randint(10, 50),
                    start_date=start_date,
                    end_date=end_date,
                    start_time=start_time,
                    end_time=end_time,
                    venue=VENUES[venue_idx],
                    venue_address=VENUE_ADDRESSES[venue_idx],
                    venue_latitude=lat,
                    venue_longitude=lng,
                    cost=round(random.uniform(10000, 100000), 2),
                    is_free=random.choice(
                        [True, False, False, False]),  # 25% free
                    registration_deadline=reg_deadline,
                    status=random.choice(
                        ["upcoming", "in_progress", "completed", "cancelled"]
                    ),
                    materials_provided="All necessary tools and materials provided",
                    prerequisites="Basic mechanical knowledge recommended",
                    certificate_offered=random.choice([True, False]),
                )
                training_sessions.append(training_session)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(training_sessions)} training sessions."
                )
            )

            # Create training session participants
            participants_created = 0
            for session in training_sessions:
                # Random number of participants (up to max_participants)
                num_participants = random.randint(
                    0, min(session.max_participants, 15))
                session_participants = random.sample(
                    customer_users, min(num_participants, len(customer_users))
                )

                for participant in session_participants:
                    # Random registration date (before session start)
                    reg_days_before = random.randint(1, 30)
                    reg_date = session.start_date - \
                        timedelta(days=reg_days_before)

                    participant_obj = TrainingSessionParticipant.objects.create(
                        session=session,
                        participant=participant,
                        status=random.choice(
                            [
                                "registered",
                                "attended",
                                "completed",
                                "cancelled",
                                "no_show",
                            ]
                        ),
                        payment_status=random.choice(
                            ["pending", "paid", "refunded"]),
                        payment_amount=session.cost if not session.is_free else 0,
                        registered_at=timezone.make_aware(
                            datetime.combine(reg_date, time(12, 0))
                        ),
                        rating=(
                            random.randint(3, 5)
                            if random.choice([True, False])
                            else None
                        ),
                        feedback=(
                            random.choice(REVIEW_COMMENTS)
                            if random.choice([True, False])
                            else ""
                        ),
                    )

                    # Set attendance/completion dates based on status
                    if participant_obj.status in ["attended", "completed"]:
                        participant_obj.attended_at = timezone.make_aware(
                            datetime.combine(
                                session.start_date, session.start_time)
                        )

                    if participant_obj.status == "completed":
                        participant_obj.completed_at = timezone.make_aware(
                            datetime.combine(session.end_date,
                                             session.end_time)
                        )
                        if session.certificate_offered:
                            participant_obj.certificate_issued = True
                            participant_obj.certificate_issued_at = (
                                participant_obj.completed_at
                            )

                    participant_obj.save()
                    participants_created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {participants_created} training session participants."
                )
            )

            # Create mechanic reviews
            reviews_created = 0
            for mechanic_user in mechanic_users:
                mechanic_profile = mechanic_user.mechanic_profile

                # Create 2-5 reviews per mechanic
                num_reviews = random.randint(2, 5)
                reviewers = random.sample(
                    customer_users, min(num_reviews, len(customer_users))
                )

                for reviewer in reviewers:
                    MechanicReview.objects.get_or_create(
                        mechanic=mechanic_profile,
                        user=reviewer,
                        defaults={
                            "rating": random.randint(3, 5),
                            "comment": random.choice(REVIEW_COMMENTS),
                        },
                    )
                    reviews_created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {reviews_created} mechanic reviews.")
            )

            # Final summary
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n=== MECHANICS DUMMY DATA POPULATION COMPLETE ===\n"
                    f"Vehicle Makes: {len(vehicle_makes)}\n"
                    f"Mechanics: {len(mechanic_users)}\n"
                    f"Vehicle Expertise: {expertise_created}\n"
                    f"Customers: {len(customer_users)}\n"
                    f"Repair Requests: {len(repair_requests)}\n"
                    f"Training Sessions: {len(training_sessions)}\n"
                    f"Training Participants: {participants_created}\n"
                    f"Mechanic Reviews: {reviews_created}\n"
                    f"Approved Mechanics: {MechanicProfile.objects.filter(is_approved=True).count()}\n"
                )
            )
