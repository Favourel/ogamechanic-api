"""
Django management command to populate the products app with dummy data.
Creates categories, a production-ready merchant user (okorieemmanuel167@gmail.com) with merchant role and profile,
products, images, reviews, and all related models (orders, order items, follows, favorites, etc).

Also, if the Product model has a 'stock' field, this command will populate
the stock for all existing products that do not have it set.
"""

import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from products.models import (
    Category,
    Product,
    ProductImage,
    ProductReview,
    Order,
    OrderItem,
    FollowMerchant,
    FavoriteProduct,
)
from users.models import MerchantProfile, Role
from django.core.files.base import ContentFile
from io import BytesIO
from PIL import Image

User = get_user_model()

CATEGORY_NAMES = [
    "Engine Parts",
    "Brakes",
    "Suspension",
    "Electrical",
    "Body Parts",
    "Tires",
    "Batteries",
    "Filters",
    "Lights",
    "Interior",
    # "Car",  # For complete cars
    # "Spare Part",  # For spare parts
]

PRODUCT_NAMES = [
    "Oil Filter",
    "Brake Pad",
    "Spark Plug",
    "Shock Absorber",
    "Headlight",
    "Car Battery",
    "Air Filter",
    "Alternator",
    "Radiator",
    "Wiper Blade",
    "Timing Belt",
    "Fuel Pump",
    "Water Pump",
    "Clutch Kit",
    "CV Joint",
    "Steering Rack",
    "Exhaust Muffler",
    "Catalytic Converter",
    "Wheel Bearing",
    "Strut Assembly",
]

CAR_NAMES = [
    "Toyota Camry 2020",
    "Honda Civic 2019",
    "Ford Focus 2021",
    "Nissan Altima 2020",
    "Chevrolet Malibu 2019",
    "Hyundai Elantra 2021",
    "Kia Optima 2020",
    "Mazda 6 2019",
    "Subaru Legacy 2021",
    "Volkswagen Jetta 2020",
    "BMW 3 Series 2019",
    "Mercedes C-Class 2021",
    "Audi A4 2020",
    "Lexus ES 2019",
    "Infiniti Q50 2021",
]

SPARE_PART_NAMES = [
    "Engine Oil 5W-30",
    "Brake Fluid DOT 4",
    "Transmission Fluid",
    "Coolant Antifreeze",
    "Power Steering Fluid",
    "Windshield Washer Fluid",
    "Fuse Box Kit",
    "Relay Switch",
    "Oxygen Sensor",
    "Mass Air Flow Sensor",
    "Throttle Position Sensor",
    "Crankshaft Position Sensor",
    "Camshaft Position Sensor",
    "Knock Sensor",
    "Temperature Sensor",
]

PRODUCT_DESCRIPTIONS = [
    "High quality and durable.",
    "OEM replacement part.",
    "Fits most vehicles.",
    "Tested for performance.",
    "Affordable and reliable.",
    "Easy to install.",
    "Long-lasting material.",
    "Recommended by mechanics.",
    "Best in class.",
    "Top seller in its category.",
    "Premium quality materials used.",
    "Manufacturer certified.",
    "Warranty included.",
    "Professional grade.",
    "Exceeds OEM standards.",
]

CAR_DESCRIPTIONS = [
    "Well maintained vehicle with full service history.",
    "Single owner, garage kept.",
    "Recent major service completed.",
    "Excellent condition, ready to drive.",
    "Low mileage, pristine interior.",
    "All original parts, no accidents.",
    "Regular maintenance performed.",
    "Clean title, no issues.",
    "Recently detailed and inspected.",
    "Perfect for daily commuting.",
]

SPARE_PART_DESCRIPTIONS = [
    "Genuine OEM part with warranty.",
    "High performance aftermarket option.",
    "Compatible with multiple vehicle models.",
    "Meets or exceeds original specifications.",
    "Easy installation with included instructions.",
    "Tested for durability and reliability.",
    "Professional mechanic recommended.",
    "Long-lasting performance guaranteed.",
    "Cost-effective replacement solution.",
    "Quality assured manufacturing.",
]


def generate_image_file(name="dummy.jpg", size=(200, 200), color=(155, 0, 0)):
    """Generate a simple image file in memory."""
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, "JPEG")
    file_obj.seek(0)
    return ContentFile(file_obj.read(), name=name)


class Command(BaseCommand):
    help = "Populate the products app with dummy data for merchant okorieemmanuel167@gmail.com and set stock for all products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--customers",
            type=int,
            default=10,
            help="Number of customer users to create (default: 10)",
        )
        parser.add_argument(
            "--clear", action="store_true", help="Clear existing data before populating"
        )

    def handle(self, *args, **options):
        # --- Populate stock for all existing products if not set ---
        updated_count = 0
        try:
            for product in Product.objects.all():
                if getattr(product, "stock", None) in [None, 0]:
                    if hasattr(product, "category") and getattr(product.category, "name", "").lower() == "car":
                        product.stock = 1
                    else:
                        product.stock = random.randint(5, 100)
                    product.save(update_fields=["stock"])
                    updated_count += 1
            if updated_count:
                self.stdout.write(self.style.SUCCESS(f"Populated stock for {updated_count} existing products."))
            else:
                self.stdout.write(self.style.SUCCESS("All existing products already have stock set."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error populating stock for existing products: {e}"))

        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            FavoriteProduct.objects.all().delete()
            FollowMerchant.objects.all().delete()
            ProductReview.objects.all().delete()
            OrderItem.objects.all().delete()
            Order.objects.all().delete()
            ProductImage.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing data cleared."))

        with transaction.atomic():
            # Create categories
            categories = []
            for cat_name in CATEGORY_NAMES:
                cat, _ = Category.objects.get_or_create(
                    name=cat_name, defaults={
                        "description": f"Category for {cat_name}"}
                )
                categories.append(cat)
            self.stdout.write(
                self.style.SUCCESS(f"Created {len(categories)} categories.")
            )

            # Get or create the merchant role
            # merchant_role, _ = Role.objects.get_or_create(name="merchant")

            # # Create the production merchant user and profile
            # merchant_email = "okorieemmanuel167@gmail.com"
            # merchant_user, created = User.objects.get_or_create(
            #     email=merchant_email,
            #     defaults={
            #         "email": merchant_email,
            #         "is_active": True,
            #         "is_staff": True,
            #         "first_name": "Emmanuel",
            #         "last_name": "Okorie",
            #     },
            # )
            # if created:
            #     merchant_user.set_password("StrongPassword!2024")
            #     merchant_user.save()
            # merchant_user.roles.add(merchant_role)
            # merchant_user.active_role = merchant_role
            # merchant_user.save()
            # merchant_profile, _ = MerchantProfile.objects.get_or_create(
            #     user=merchant_user,
            #     defaults={
            #         "cac_number": "RC2024001",
            #         "is_approved": True,
            #         "business_address": "1 Okorie Emmanuel St, Lagos",
            #     },
            # )
            # self.stdout.write(
            #     self.style.SUCCESS(
            #         f"Merchant user '{merchant_email}' and profile created."
            #     )
            # )

            # # Create products for the merchant
            # products = []
            # car_products = []
            # spare_part_products = []

            # # Regular products
            # for j in range(6):
            #     name = f"{random.choice(PRODUCT_NAMES)} {j+1} (okorieemmanuel167@gmail.com)"
            #     category = random.choice(
            #         [cat for cat in categories if cat.name not in ["Car", "Spare Part"]]
            #     )
            #     price = round(random.uniform(5000, 50000), 2)
            #     description = random.choice(PRODUCT_DESCRIPTIONS)
            #     is_rental = random.choice([True, False])
            #     stock = random.randint(5, 100)
            #     product = Product.objects.create(
            #         merchant=merchant_user,
            #         category=category,
            #         name=name,
            #         description=description,
            #         price=price,
            #         is_rental=is_rental,
            #         stock=stock,
            #     )
            #     # Add 2 images per product
            #     for img_idx in range(2):
            #         img_file = generate_image_file(
            #             name=f"{name.replace(' ', '_').lower()}_{img_idx+1}.jpg",
            #             color=(
            #                 random.randint(0, 255),
            #                 random.randint(0, 255),
            #                 random.randint(0, 255),
            #             ),
            #         )
            #         ProductImage.objects.create(
            #             product=product, image=img_file, ordering=img_idx
            #         )
            #     products.append(product)

            # # Car products
            # car_category = next((cat for cat in categories if cat.name == "Car"), None)
            # if car_category:
            #     for j in range(2):
            #         name = f"{random.choice(CAR_NAMES)} {j+1} (okorieemmanuel167@gmail.com)"
            #         price = round(random.uniform(2000000, 15000000), 2)
            #         description = random.choice(CAR_DESCRIPTIONS)
            #         product = Product.objects.create(
            #             merchant=merchant_user,
            #             category=car_category,
            #             name=name,
            #             description=description,
            #             price=price,
            #             is_rental=False,
            #             stock=1,
            #         )
            #         for img_idx in range(3):
            #             img_file = generate_image_file(
            #                 name=f"{name.replace(' ', '_').lower()}_{img_idx+1}.jpg",
            #                 size=(400, 300),
            #                 color=(
            #                     random.randint(0, 255),
            #                     random.randint(0, 255),
            #                     random.randint(0, 255),
            #                 ),
            #             )
            #             ProductImage.objects.create(
            #                 product=product, image=img_file, ordering=img_idx
            #             )
            #         car_products.append(product)
            #         products.append(product)

            # # Spare part products
            # spare_part_category = next((cat for cat in categories if cat.name == "Spare Part"), None)
            # if spare_part_category:
            #     for j in range(3):
            #         name = f"{random.choice(SPARE_PART_NAMES)} {j+1} (okorieemmanuel167@gmail.com)"
            #         price = round(random.uniform(1000, 25000), 2)
            #         description = random.choice(SPARE_PART_DESCRIPTIONS)
            #         stock = random.randint(10, 200)
            #         product = Product.objects.create(
            #             merchant=merchant_user,
            #             category=spare_part_category,
            #             name=name,
            #             description=description,
            #             price=price,
            #             is_rental=False,
            #             stock=stock,
            #         )
            #         for img_idx in range(2):
            #             img_file = generate_image_file(
            #                 name=f"{name.replace(' ', '_').lower()}_{img_idx+1}.jpg",
            #                 color=(
            #                     random.randint(0, 255),
            #                     random.randint(0, 255),
            #                     random.randint(0, 255),
            #                 ),
            #             )
            #             ProductImage.objects.create(
            #                 product=product, image=img_file, ordering=img_idx
            #             )
            #         spare_part_products.append(product)
            #         products.append(product)

            # self.stdout.write(
            #     self.style.SUCCESS(
            #         f"Created {len(products)} products (including cars and spare parts) for merchant '{merchant_email}'."
            #     )
            # )

            # # Create customer users for orders
            # num_customers = options["customers"]
            # customer_users = []
            # for i in range(1, num_customers + 1):
            #     email = f"customer{i}@example.com"
            #     user, created = User.objects.get_or_create(
            #         email=email,
            #         defaults={
            #             "email": email,
            #             "is_active": True,
            #             "first_name": f"Customer{i}",
            #             "last_name": "Demo",
            #         },
            #     )
            #     if created:
            #         user.set_password("password123")
            #         user.save()
            #     customer_users.append(user)

            # self.stdout.write(
            #     self.style.SUCCESS(
            #         f"Created {len(customer_users)} customer users."
            #     )
            # )

            # # Create orders and order items for the merchant's products
            # orders_created = 0
            # for customer in customer_users:
            #     # Each customer makes 1-2 orders from the merchant's products
            #     for _ in range(random.randint(1, 2)):
            #         order = Order.objects.create(
            #             customer=customer,
            #             status=random.choice(["paid", "completed", "shipped"]),
            #             total_amount=0,
            #         )
            #         # Add 1-3 items per order, only from this merchant's products
            #         order_items = random.sample(products, random.randint(1, min(3, len(products))))
            #         order_total = 0
            #         for product in order_items:
            #             quantity = random.randint(1, 3)
            #             item_total = product.price * quantity
            #             order_total += item_total
            #             OrderItem.objects.create(
            #                 order=order,
            #                 product=product,
            #                 quantity=quantity,
            #                 price=product.price,
            #             )
            #         order.total_amount = order_total
            #         order.save()
            #         orders_created += 1

            # self.stdout.write(
            #     self.style.SUCCESS(
            #         f"Created {orders_created} orders with order items for merchant '{merchant_email}'."
            #     )
            # )

            # # Create dummy reviews for the merchant's products
            # for product in products:
            #     for _ in range(random.randint(1, 3)):
            #         reviewer_email = f"user{random.randint(1, 1000)}@example.com"
            #         reviewer, _ = User.objects.get_or_create(
            #             email=reviewer_email,
            #             defaults={"email": reviewer_email, "is_active": True},
            #         )
            #         ProductReview.objects.get_or_create(
            #             product=product,
            #             user=reviewer,
            #             defaults={
            #                 "rating": random.randint(3, 5),
            #                 "comment": random.choice(PRODUCT_DESCRIPTIONS),
            #             },
            #         )
            # self.stdout.write(self.style.SUCCESS(
            #     f"Dummy product reviews created for merchant '{merchant_email}'."
            # ))

            # # Create follow relationships between customers and the merchant
            # follows_created = 0
            # for customer in customer_users:
            #     FollowMerchant.objects.get_or_create(
            #         user=customer,
            #         merchant=merchant_user
            #     )
            #     follows_created += 1

            # self.stdout.write(
            #     self.style.SUCCESS(f"Created {follows_created} follow relationships for merchant '{merchant_email}'.")
            # )

            # # Create favorite products for customers (from merchant's products)
            # favorites_created = 0
            # for customer in customer_users:
            #     num_favorites = random.randint(2, min(5, len(products)))
            #     favorite_products = random.sample(products, num_favorites)
            #     for product in favorite_products:
            #         FavoriteProduct.objects.get_or_create(
            #             user=customer,
            #             product=product
            #         )
            #         favorites_created += 1

            # self.stdout.write(
            #     self.style.SUCCESS(f"Created {favorites_created} favorite products for merchant '{merchant_email}'.")
            # )

            # Final summary
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n=== DUMMY DATA POPULATION COMPLETE ===\n"
                    f"Categories: {len(categories)}\n"
                    # f"Merchant: {merchant_email}\n"
                    # f"Customers: {len(customer_users)}\n"
                    # f"Products: {len(products)}\n"
                    # f"  - Cars: {len(car_products)}\n"
                    # f"  - Spare Parts: {len(spare_part_products)}\n"
                    # f"  - Other Products: {len(products) - len(car_products) - len(spare_part_products)}\n"
                    # f"Orders: {orders_created}\n"
                    # f"Reviews: {ProductReview.objects.filter(product__merchant=merchant_user).count()}\n"
                    # f"Images: {ProductImage.objects.filter(product__merchant=merchant_user).count()}\n"
                    # f"Follow Relationships: {follows_created}\n"
                    # f"Favorite Products: {favorites_created}\n"
                )
            )
