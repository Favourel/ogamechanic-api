from rest_framework import serializers
from .models import (
    Role,
    Notification,
    MerchantProfile,
    MechanicProfile,
    DriverProfile,
    MechanicReview,
    DriverReview,
    BankAccount,
    Wallet,
    Transaction,
    ContactMessage,
    EmailSubscription,
)
from ogamechanic.modules.utils import api_response
from ogamechanic.modules.exceptions import InvalidRequestException
from .tasks import send_password_reset_email
import jwt
from django.conf import settings
from datetime import datetime, timedelta
from django.utils import timezone
from .models import UserEmailVerification
from django.contrib.auth import get_user_model


# flake8: noqa: E501


User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "description"]


class UserSerializer(serializers.ModelSerializer):
    active_role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "active_role",
            "date_joined",
            "last_login",
            "phone_number",
            "created_at",
            "updated_at",
            "car_make",
            "car_model",
            "car_year",
            "license_plate",
        ]
        read_only_fields = [
            "id",
            "date_joined",
            "last_login",
            "created_at",
            "updated_at",
        ]
        ref_name = "UsersUserSerializer"

    def get_active_role(self, obj):
        return obj.active_role.name if obj.active_role else None


class UserUpdateSerializer(serializers.ModelSerializer):
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), source="role", required=False
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "role_id",
            "is_active",
            "phone_number",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change endpoint.
    """

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match"}
            )
        return data


class PasswordResetSerializer(serializers.Serializer):
    """Serializer for admin password reset"""

    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if not hasattr(user, "email"):
                import traceback

                print(traceback.format_exc())
                raise InvalidRequestException(
                    api_response(
                        message=(
                            "If an account exists with this email, "
                            "you will receive a password reset link"
                        ),
                        status=False,
                    )
                )
        except User.DoesNotExist:
            import traceback

            print(traceback.format_exc())
            raise InvalidRequestException(
                api_response(
                    message=(
                        "If an account exists with this email, "
                        "you will receive a password reset link"
                    ),
                    status=False,
                )
            )
        except Exception as e:
            raise InvalidRequestException(
                api_response(message=str(e), status=False))
        return value

    def save(self):
        import uuid

        email = self.validated_data["email"]
        user = User.objects.get(email=email)

        # Ensure any UUIDs in the payload are converted to str
        payload = {
            "user_email": user.email,
            "user_id": (
                str(user.id) if isinstance(user.id, uuid.UUID) else user.id
            ),  # noqa
            "exp": datetime.utcnow()
            + timedelta(hours=settings.PASSWORD_RESET_TIMEOUT // 3600),
        }

        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        # Send password reset email asynchronously
        send_password_reset_email.delay(email, token)


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "is_read",
            "is_sent",
            "created_at",
            "read_at",
        ]
        read_only_fields = ["id", "is_sent", "created_at", "read_at"]


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, value):
        try:
            verification = UserEmailVerification.objects.get(token=value)
        except UserEmailVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired token.")
        if verification.is_used:
            raise serializers.ValidationError(
                "This token has already been used.")
        if verification.expires_at < timezone.now():
            raise serializers.ValidationError("This token has expired.")
        return value

    def save(self, **kwargs):
        token = self.validated_data["token"]
        verification = UserEmailVerification.objects.get(token=token)
        user = verification.user
        user.is_verified = True
        user.is_active = True  # Ensure the user is set to active
        user.save(update_fields=["is_verified", "is_active"])
        verification.is_used = True
        verification.save(update_fields=["is_used"])
        return user


class UserRegistrationSerializer(serializers.ModelSerializer):
    roles = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), many=True, write_only=True, required=True
    )
    password = serializers.CharField(
        write_only=True, required=True, min_length=8, style={"input_type": "password"}  # noqa
    )
    password_confirm = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}  # noqa
    )
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "roles",
        ]

    def validate_email(self, value):
        value = value.lower().strip()
        # Note: Email uniqueness is now handled at the application level
        # to allow same email for different roles
        return value

    def validate_password(self, value):
        """
        Validate password strength and requirements.
        """
        try:
            from django.contrib.auth.password_validation import (
                validate_password,
            )  # noqa
            from django.core.exceptions import ValidationError

            # Use Django's built-in password validation
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        # Additional custom validations
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one digit."
            )
        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one uppercase letter."
            )
        if not any(char.islower() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one lowercase letter."
            )
        if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one special character."
            )

        return value

    def validate_roles(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one role must be selected."
            )  # noqa
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password fields didn't match."}
            )
        return attrs

    def create(self, validated_data):
        roles = validated_data.pop("roles", [])
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        # Set to False to require email verification before activation
        user.is_active = False
        user.save()
        user.roles.set(roles)
        # Set the first role as active_role if not set
        if roles:
            user.active_role = roles[0]
            user.save(update_fields=["active_role"])
        # Email verification and onboarding logic can be triggered by signals/tasks # noqa
        return user


class MerchantProfileSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    cac_document = serializers.SerializerMethodField()
    selfie = serializers.SerializerMethodField()

    class Meta:
        model = MerchantProfile
        fields = [
            "id",
            "user",
            "location",
            "lga",
            "cac_number",
            "cac_document",
            "selfie",
            "business_address",
            "is_approved",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user",
                            "is_approved", "created_at", "updated_at"]

    def get_user(self, obj):
        from users.serializers import UserSerializer
        return UserSerializer(obj.user).data

    def _get_absolute_url(self, url, request=None):
        if not url:
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if request is not None:
            return request.build_absolute_uri(url)
        # Fallback: try to build absolute URL manually
        from django.conf import settings
        if hasattr(settings, "SITE_DOMAIN"):
            return f"{settings.SITE_DOMAIN}{url}"
        return url

    def get_cac_document(self, obj):
        request = self.context.get('request', None)
        if obj.cac_document and hasattr(obj.cac_document, 'url'):
            return self._get_absolute_url(obj.cac_document.url, request)
        return None

    def get_selfie(self, obj):
        request = self.context.get('request', None)
        if obj.selfie and hasattr(obj.selfie, 'url'):
            return self._get_absolute_url(obj.selfie.url, request)
        return None

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return MerchantProfile.objects.create(**validated_data)


class MechanicProfileSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    cac_document = serializers.SerializerMethodField()
    selfie = serializers.SerializerMethodField()
    government_id_front = serializers.SerializerMethodField()
    government_id_back = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    has_active_repair_request = serializers.SerializerMethodField()

    class Meta:
        model = MechanicProfile
        fields = [
            "id",
            "user",
            "location",
            "latitude",
            "longitude",
            "bio",
            "lga",
            "cac_number",
            "cac_document",
            "selfie",
            "govt_id_type",
            "government_id_front",
            "government_id_back",
            "is_approved",
            "created_at",
            "updated_at",
            "rating",
            "has_active_repair_request",
        ]
        read_only_fields = [
            "id",
            "user",
            "is_approved",
            "created_at",
            "updated_at",
            "rating",
            "cac_document",
            "selfie",
            "government_id_front",
            "government_id_back",
            "has_active_repair_request",
        ]
        ref_name = "UsersMechanicProfileSerializer"

    def get_user(self, obj):
        from users.serializers import UserSerializer
        return UserSerializer(obj.user).data

    def _get_absolute_url(self, url, request=None):
        if not url:
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if request is not None:
            return request.build_absolute_uri(url)
        from django.conf import settings
        if hasattr(settings, "SITE_DOMAIN"):
            return f"{settings.SITE_DOMAIN}{url}"
        return url

    def get_cac_document(self, obj):
        request = self.context.get('request', None)
        if obj.cac_document and hasattr(obj.cac_document, 'url'):
            return self._get_absolute_url(obj.cac_document.url, request)
        return None

    def get_selfie(self, obj):
        request = self.context.get('request', None)
        if obj.selfie and hasattr(obj.selfie, 'url'):
            return self._get_absolute_url(obj.selfie.url, request)
        return None

    def get_government_id_front(self, obj):
        request = self.context.get('request', None)
        if obj.government_id_front and hasattr(obj.government_id_front, 'url'):
            return self._get_absolute_url(obj.government_id_front.url, request)
        return None

    def get_government_id_back(self, obj):
        request = self.context.get('request', None)
        if obj.government_id_back and hasattr(obj.government_id_back, 'url'):
            return self._get_absolute_url(obj.government_id_back.url, request)
        return None

    def get_rating(self, obj):
        from users.models import MechanicReview
        from django.db.models import Avg

        reviews = MechanicReview.objects.filter(mechanic=obj)
        avg_rating = reviews.aggregate(avg=Avg('rating')).get('avg')
        if avg_rating is not None:
            return round(avg_rating, 1)
        return None

    def get_has_active_repair_request(self, obj):
        """
        Check if the mechanic is currently working on a repair request.
        Returns True if mechanic has any repair requests with status
        'accepted' or 'in_progress'.
        """
        # Check if the field was already annotated in the queryset
        if hasattr(obj, 'has_active_repair_request'):
            return obj.has_active_repair_request

        # Fallback: query the database if not annotated
        from mechanics.models import RepairRequest
        return RepairRequest.objects.filter(
            mechanic=obj.user,
            status__in=['accepted', 'in_progress']
        ).exists()

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return MechanicProfile.objects.create(**validated_data)


class DriverProfileSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    license_front_image = serializers.SerializerMethodField()
    license_back_image = serializers.SerializerMethodField()
    vehicle_photo_front = serializers.SerializerMethodField()
    vehicle_photo_back = serializers.SerializerMethodField()
    vehicle_photo_right = serializers.SerializerMethodField()
    vehicle_photo_left = serializers.SerializerMethodField()
    government_id = serializers.SerializerMethodField()
    driver_license = serializers.SerializerMethodField()
    vehicle_photo = serializers.SerializerMethodField()
    insurance_document = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = DriverProfile
        fields = [
            "id",
            "user",
            "full_name",
            "phone_number",
            "city",
            "date_of_birth",
            "gender",
            "address",
            "location",
            "license_number",
            "license_issue_date",
            "license_expiry_date",
            "license_front_image",
            "license_back_image",
            "vin",
            "vehicle_name",
            "plate_number",
            "vehicle_model",
            "vehicle_color",
            "vehicle_photo_front",
            "vehicle_photo_back",
            "vehicle_photo_right",
            "vehicle_photo_left",
            "bank_name",
            "account_number",
            "rating",
            # Legacy fields for backward compatibility
            "government_id",
            "driver_license",
            "vehicle_type",
            "vehicle_registration_number",
            "vehicle_photo",
            "insurance_document",
            "is_approved",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "is_approved",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def get_user(self, obj):
        from users.serializers import UserSerializer
        return UserSerializer(obj.user).data

    def _get_absolute_url(self, url, request=None):
        if not url:
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if request is not None:
            return request.build_absolute_uri(url)
        # Fallback: try to build absolute URL manually
        from django.conf import settings
        if hasattr(settings, "SITE_DOMAIN"):
            return f"{settings.SITE_DOMAIN}{url}"
        return url

    def get_license_front_image(self, obj):
        request = self.context.get('request', None)
        if obj.license_front_image and hasattr(obj.license_front_image, 'url'):
            return self._get_absolute_url(obj.license_front_image.url, request)
        return None

    def get_license_back_image(self, obj):
        request = self.context.get('request', None)
        if obj.license_back_image and hasattr(obj.license_back_image, 'url'):
            return self._get_absolute_url(obj.license_back_image.url, request)
        return None

    def get_vehicle_photo_front(self, obj):
        request = self.context.get('request', None)
        if obj.vehicle_photo_front and hasattr(obj.vehicle_photo_front, 'url'):
            return self._get_absolute_url(obj.vehicle_photo_front.url, request)
        return None

    def get_vehicle_photo_back(self, obj):
        request = self.context.get('request', None)
        if obj.vehicle_photo_back and hasattr(obj.vehicle_photo_back, 'url'):
            return self._get_absolute_url(obj.vehicle_photo_back.url, request)
        return None

    def get_vehicle_photo_right(self, obj):
        request = self.context.get('request', None)
        if obj.vehicle_photo_right and hasattr(obj.vehicle_photo_right, 'url'):
            return self._get_absolute_url(obj.vehicle_photo_right.url, request)
        return None

    def get_vehicle_photo_left(self, obj):
        request = self.context.get('request', None)
        if obj.vehicle_photo_left and hasattr(obj.vehicle_photo_left, 'url'):
            return self._get_absolute_url(obj.vehicle_photo_left.url, request)
        return None

    def get_government_id(self, obj):
        request = self.context.get('request', None)
        if obj.government_id and hasattr(obj.government_id, 'url'):
            return self._get_absolute_url(obj.government_id.url, request)
        return None

    def get_driver_license(self, obj):
        request = self.context.get('request', None)
        if obj.driver_license and hasattr(obj.driver_license, 'url'):
            return self._get_absolute_url(obj.driver_license.url, request)
        return None

    def get_vehicle_photo(self, obj):
        request = self.context.get('request', None)
        if obj.vehicle_photo and hasattr(obj.vehicle_photo, 'url'):
            return self._get_absolute_url(obj.vehicle_photo.url, request)
        return None

    def get_insurance_document(self, obj):
        request = self.context.get('request', None)
        if obj.insurance_document and hasattr(obj.insurance_document, 'url'):
            return self._get_absolute_url(obj.insurance_document.url, request)
        return None

    def get_rating(self, obj):
        from django.db.models import Avg
        from users.models import DriverReview

        reviews = DriverReview.objects.filter(driver=obj)
        avg_rating = reviews.aggregate(avg=Avg('rating')).get('avg')
        if avg_rating is not None:
            return round(avg_rating, 1)
        return None

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return DriverProfile.objects.create(**validated_data)


class DriverLocationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ["latitude", "longitude"]
        ref_name = "UsersDriverLocationUpdateSerializer"


class MechanicReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    # mechanic_id = serializers.PrimaryKeyRelatedField(
    #     read_only=True,
    #     source="mechanic",
    # )
    mechanic_info = serializers.SerializerMethodField()

    class Meta:
        model = MechanicReview
        fields = [
            "id",
            # "mechanic",
            # "mechanic_id",
            "mechanic_info",
            "user",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user",
                            "created_at", "updated_at", "mechanic"]
        ref_name = "UsersMechanicReviewSerializer"

    def validate(self, attrs):
        user = self.context["request"].user
        mechanic = attrs.get("mechanic")

        # Only validate if mechanic is provided (from URL or body)
        if mechanic:
            if (
                self.instance is None
                and MechanicReview.objects.filter(
                    user=user, mechanic=mechanic
                ).exists()  # noqa
            ):
                raise serializers.ValidationError(
                    "You have already reviewed this mechanic."
                )
        return attrs

    def get_mechanic_info(self, obj):
        """
        Return selected info of the mechanic profile.
        """
        mech = getattr(obj, "mechanic", None)
        if mech is None:
            return None
        # Example fields: id, full_name, phone_number
        return {
            "id": getattr(mech, "id", None),
            "full_name": getattr(mech, "full_name", None),
            "phone_number": getattr(mech, "phone_number", None),
            "city": getattr(mech, "city", None),
            "is_approved": getattr(mech, "is_approved", None),
        }


class DriverReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    # driver_id = serializers.PrimaryKeyRelatedField(
    #     queryset=DriverProfile.objects.all(),
    #     source="driver",
    #     write_only=True,
    #     required=False  # Make it optional since it comes from URL
    # )
    driver_info = serializers.SerializerMethodField()

    class Meta:
        model = DriverReview
        fields = [
            "id",
            # "driver",
            # "driver_id",
            "driver_info",
            "user",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at", "driver"]

    def validate(self, attrs):
        user = self.context["request"].user
        driver = attrs.get("driver")

        # Only validate if driver is provided (from URL or body)
        if driver:
            if (
                self.instance is None
                and DriverReview.objects.filter(user=user, driver=driver).exists()
            ):
                raise serializers.ValidationError(
                    "You have already reviewed this driver.")
        return attrs

    def get_driver_info(self, obj):
        """
        Return selected info of the driver profile.
        """
        mech = getattr(obj, "driver", None)
        if mech is None:
            return None
        # Example fields: id, full_name, phone_number
        return {
            "id": getattr(mech, "id", None),
            "full_name": getattr(mech, "full_name", None),
            "phone_number": getattr(mech, "phone_number", None),
            "city": getattr(mech, "city", None),
            "is_approved": getattr(mech, "is_approved", None),
        }


class BankAccountSerializer(serializers.ModelSerializer):
    """Serializer for BankAccount model."""

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_number",
            "account_name",
            "bank_code",
            "bank_name",
            "is_verified",
            "is_active",
            "paystack_recipient_code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "is_verified",
            "paystack_recipient_code",
            "created_at",
            "updated_at",
        ]  # noqa

    def validate_account_number(self, value):
        """Validate account number format."""
        if not value.isdigit() or len(value) < 10:
            raise serializers.ValidationError("Invalid account number format")
        return value

    def validate_bank_code(self, value):
        """Validate bank code format."""
        if not value.isdigit() or len(value) != 3:
            raise serializers.ValidationError("Invalid bank code format")
        return value


class BankAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating bank accounts with Paystack verification."""

    class Meta:
        model = BankAccount
        fields = ["account_number", "account_name", "bank_code"]

    def create(self, validated_data):
        """Create bank account and verify with Paystack."""
        user = self.context["request"].user

        # Check if bank account already exists
        if BankAccount.objects.filter(
            user=user,
            account_number=validated_data["account_number"],
            bank_code=validated_data["bank_code"],
        ).exists():
            raise serializers.ValidationError("Bank account already exists")

        # Get bank name from Paystack
        bank_name = self._get_bank_name(validated_data["bank_code"])
        validated_data["bank_name"] = bank_name

        return super().create(validated_data)

    def _get_bank_name(self, bank_code):
        """Get bank name from Paystack API."""
        from django.conf import settings
        import requests

        try:
            response = requests.get(
                f"https://api.paystack.co/bank/{bank_code}",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"
                },  # noqa
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("name", "Unknown Bank")
        except Exception:
            pass

        return "Unknown Bank"


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for Wallet model."""

    user = UserSerializer(read_only=True)
    balance = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )  # noqa

    class Meta:
        model = Wallet
        fields = [
            "id",
            "user",
            "balance",
            "currency",
            "is_active",
            "daily_limit",
            "monthly_limit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "balance", "created_at", "updated_at"]


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model."""

    wallet = WalletSerializer(read_only=True)
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )  # noqa
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )  # noqa

    class Meta:
        model = Transaction
        fields = [
            "id",
            "wallet",
            "amount",
            "transaction_type",
            "transaction_type_display",
            "reference",
            "description",
            "status",
            "status_display",
            "fee",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "wallet",
            "fee",
            "metadata",
            "created_at",
            "updated_at",
        ]  # noqa


class TransactionListSerializer(serializers.ModelSerializer):
    """Serializer for listing transactions."""

    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )  # noqa
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )  # noqa

    class Meta:
        model = Transaction
        fields = [
            "id",
            "amount",
            "transaction_type",
            "transaction_type_display",
            "reference",
            "description",
            "status",
            "status_display",
            "fee",
            "created_at",
        ]


class WalletTopUpSerializer(serializers.Serializer):
    """Serializer for wallet top-up requests."""

    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=100,  # Minimum top-up amount
        help_text="Amount to top up (minimum 100 NGN)",
    )
    payment_method = serializers.ChoiceField(
        choices=["paystack", "bank_transfer"], help_text="Payment method for top-up"  # noqa
    )
    bank_account_id = serializers.UUIDField(
        required=False, help_text="Bank account ID for bank transfer (optional)"  # noqa
    )

    def validate_amount(self, value):
        """Validate top-up amount."""
        if value < 100:
            raise serializers.ValidationError(
                "Minimum top-up amount is 100 NGN"
            )  # noqa
        if value > 1000000:
            raise serializers.ValidationError(
                "Maximum top-up amount is 1,000,000 NGN"
            )  # noqa
        return value

    def validate(self, data):
        """Validate payment method and bank account."""
        if data["payment_method"] == "bank_transfer" and not data.get(
            "bank_account_id"
        ):  # noqa
            raise serializers.ValidationError(
                "Bank account ID is required for bank transfer"
            )  # noqa
        return data


class WalletWithdrawalSerializer(serializers.Serializer):
    """Serializer for wallet withdrawal requests."""

    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=1000,  # Minimum withdrawal amount
        help_text="Amount to withdraw (minimum 1,000 NGN)",
    )
    bank_account_id = serializers.UUIDField(
        help_text="Bank account ID for withdrawal")
    description = serializers.CharField(
        max_length=255, required=False, help_text="Withdrawal description (optional)"  # noqa
    )

    def validate_amount(self, value):
        """Validate withdrawal amount."""
        if value < 1000:
            raise serializers.ValidationError(
                "Minimum withdrawal amount is 1,000 NGN"
            )  # noqa
        if value > 1000000:
            raise serializers.ValidationError(
                "Maximum withdrawal amount is 1,000,000 NGN"
            )  # noqa
        return value


class PaystackWebhookSerializer(serializers.Serializer):
    """Serializer for Paystack webhook data."""

    event = serializers.CharField()
    data = serializers.DictField()

    def validate_data(self, value):
        """Validate webhook data structure."""
        required_fields = ["reference", "status", "amount"]
        for field in required_fields:
            if field not in value:
                raise serializers.ValidationError(
                    f"Missing required field: {field}"
                )  # noqa
        return value


class StepOneRoleSelectionSerializer(serializers.Serializer):
    """Step 1: Role selection"""

    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), required=True
    )

    def validate_role_id(self, value):
        """Validate that the role exists and is valid for registration"""
        valid_roles = ["primary_user", "driver", "mechanic", "merchant"]
        if value.name not in valid_roles:
            raise serializers.ValidationError(
                f"Role '{value.name}' is not available for registration."
            )
        return value


class StepTwoPrimaryUserInfoSerializer(serializers.Serializer):
    """Step 2: Primary User information"""

    first_name = serializers.CharField(max_length=30, required=True)
    last_name = serializers.CharField(max_length=30, required=True)
    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(max_length=20, required=True)

    def validate_email(self, value):
        value = value.lower().strip()
        # Note: Email uniqueness is now handled at the application level
        # to allow same email for different roles
        return value


class StepTwoDriverSubRoleSerializer(serializers.Serializer):
    """Step 2a: Driver sub-role selection (driver or rider)"""

    sub_role = serializers.ChoiceField(
        choices=[("driver", "Driver"), ("rider", "Rider")], required=True
    )


class StepTwoDriverInfoSerializer(serializers.Serializer):
    """Step 2b: Driver information"""

    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(max_length=20, required=True)
    city = serializers.CharField(max_length=100, required=True)

    def validate_email(self, value):
        value = value.lower().strip()
        # Note: Email uniqueness is now handled at the application level
        # to allow same email for different roles
        return value


class StepTwoMerchantInfoSerializer(serializers.Serializer):
    """Step 2: Merchant information"""

    first_name = serializers.CharField(max_length=30, required=True)
    last_name = serializers.CharField(max_length=30, required=True)
    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(max_length=20, required=True)

    def validate_email(self, value):
        value = value.lower().strip()
        # Note: Email uniqueness is now handled at the application level
        # to allow same email for different roles
        return value


class StepTwoMechanicInfoSerializer(serializers.Serializer):
    """Step 2: Mechanic information"""

    first_name = serializers.CharField(max_length=30, required=True)
    last_name = serializers.CharField(max_length=30, required=True)
    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(max_length=20, required=True)

    def validate_email(self, value):
        value = value.lower().strip()
        # Note: Email uniqueness is now handled at the application level
        # to allow same email for different roles
        return value


class StepThreeEmailVerificationSerializer(serializers.Serializer):
    """Step 3: Email verification"""

    email = serializers.EmailField(required=True)
    verification_code = serializers.CharField(max_length=6, required=True)

    def validate_verification_code(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError(
                "Verification code must be a 6-digit number."
            )
        return value


class StepFourPrimaryUserCarDetailsSerializer(serializers.Serializer):
    """Step 4: Primary User car details (optional)"""

    car_make = serializers.CharField(
        max_length=50, required=False, allow_blank=True)
    car_model = serializers.CharField(
        max_length=50, required=False, allow_blank=True)
    car_year = serializers.IntegerField(
        min_value=1900, max_value=2030, required=False, allow_null=True
    )
    license_plate = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    has_car = serializers.BooleanField(default=False)

    def validate(self, attrs):
        has_car = attrs.get("has_car", False)

        if has_car:
            # If user has a car, require car details
            if not attrs.get("car_make"):
                raise serializers.ValidationError(
                    {"car_make": "Car make is required when you have a car."}
                )
            if not attrs.get("car_model"):
                raise serializers.ValidationError(
                    {"car_model": "Car model is required when you have a car."}
                )

        return attrs


class StepFourDriverDetailsSerializer(serializers.Serializer):
    """Step 4: Driver comprehensive details"""

    # Personal Information
    full_name = serializers.CharField(max_length=255, required=True)
    date_of_birth = serializers.DateField(required=True)
    gender = serializers.ChoiceField(
        choices=[
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other"),
            ("prefer_not_to_say", "Prefer not to say"),
        ],
        required=True,
    )
    address = serializers.CharField(max_length=255, required=True)
    location = serializers.CharField(max_length=255, required=True)

    # License Information
    license_number = serializers.CharField(max_length=50, required=True)
    license_issue_date = serializers.DateField(required=True)
    license_expiry_date = serializers.DateField(required=True)
    license_front_image = serializers.ImageField(required=True)
    license_back_image = serializers.ImageField(required=True)

    # Vehicle Information
    vin = serializers.CharField(max_length=50, required=True)
    vehicle_name = serializers.CharField(max_length=100, required=True)
    plate_number = serializers.CharField(max_length=20, required=True)
    vehicle_model = serializers.CharField(max_length=100, required=True)
    vehicle_color = serializers.CharField(max_length=50, required=True)

    # Vehicle Photos
    vehicle_photo_front = serializers.ImageField(required=True)
    vehicle_photo_back = serializers.ImageField(required=True)
    vehicle_photo_right = serializers.ImageField(required=True)
    vehicle_photo_left = serializers.ImageField(required=True)

    # Bank Information
    bank_name = serializers.CharField(max_length=100, required=True)
    account_number = serializers.CharField(max_length=20, required=True)


class StepFourMerchantDetailsSerializer(serializers.Serializer):
    """Step 4: Merchant details"""

    location = serializers.CharField(max_length=255, required=True)
    lga = serializers.CharField(max_length=100, required=True)
    cac_number = serializers.CharField(max_length=100, required=True)
    cac_document = serializers.FileField(required=True)
    selfie = serializers.ImageField(required=True)


class StepFourMechanicDetailsSerializer(serializers.Serializer):
    """Step 4: Mechanic details including vehicle expertise"""

    location = serializers.CharField(max_length=255, required=True)
    lga = serializers.CharField(max_length=100, required=True)
    cac_number = serializers.CharField(max_length=100, required=False)
    cac_document = serializers.FileField(required=False)
    selfie = serializers.ImageField(required=False)
    govt_id_type = serializers.ChoiceField(
        choices=[
            ("NIN", "NIN"),
            ("drivers_license", "Drivers license"),
            ("voters_card", "Voters card"),
            ("international_passport", "International passport"),
            ("permanent_voters_card", "Permanent voter’s card"),
        ],
        required=False
    )
    government_id_front = serializers.FileField(required=False)
    government_id_back = serializers.FileField(required=False)

    # Vehicle expertise fields
    # vehicle_make_ids = serializers.ListField(
    #     child=serializers.IntegerField(),
    #     min_length=1,
    #     required=True,
    #     help_text="List of vehicle make IDs the mechanic is expert in"
    # )
    expertise_details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Optional details for each vehicle make expertise"
    )

    # def validate_vehicle_make_ids(self, value):
    #     """Validate that all vehicle make IDs exist and are active"""
    #     from mechanics.models import VehicleMake

    #     vehicle_makes = VehicleMake.objects.filter(
    #         id__in=value, is_active=True
    #     )

    #     if len(vehicle_makes) != len(value):
    #         invalid_ids = set(value) - set(vehicle_makes.values_list('id', flat=True))  # noqa
    #         raise serializers.ValidationError(
    #             f"Invalid or inactive vehicle make IDs: {list(invalid_ids)}"
    #         )

    #     return value

    def validate_expertise_details(self, value):
        """Validate expertise details if provided"""
        if not value:
            return value

        # Check that each detail has required fields
        for detail in value:
            if 'vehicle_make_id' not in detail:
                raise serializers.ValidationError(
                    "Each expertise detail must include 'vehicle_make_id'"
                )

            if 'years_of_experience' in detail:
                years = detail['years_of_experience']
                if not isinstance(years, int) or years < 0:
                    raise serializers.ValidationError(
                        "Years of experience must be a non-negative integer"
                    )

            if 'certification_level' in detail:
                valid_levels = [
                    'basic', 'intermediate', 'advanced', 'expert', 'certified']
                if detail['certification_level'] not in valid_levels:
                    raise serializers.ValidationError(
                        f"Invalid certification level. Must be one of: {valid_levels}"  # noqa
                    )

        return value


class StepFivePasswordSerializer(serializers.Serializer):
    """Step 5: Password setup"""

    password = serializers.CharField(
        required=True, min_length=8, style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        required=True, style={"input_type": "password"}
    )

    def validate_password(self, value):
        """Validate password strength and requirements."""
        try:
            from django.contrib.auth.password_validation import (
                validate_password,
            )  # noqa
            from django.core.exceptions import ValidationError

            # Use Django's built-in password validation
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))

        # Additional custom validations
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one digit."
            )
        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one uppercase letter."
            )
        if not any(char.islower() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one lowercase letter."
            )
        if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one special character."
            )

        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password fields didn't match."}
            )
        return attrs


class CustomTokenObtainPairSerializer(serializers.Serializer):
    """
    Custom serializer for JWT token obtain that
    supports both email and phone number
    """

    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    password = serializers.CharField(required=True)

    def validate(self, attrs):
        email = attrs.get("email")
        phone_number = attrs.get("phone_number")
        password = attrs.get("password")

        # Clean empty strings
        email = email.strip() if email else None
        phone_number = phone_number.strip() if phone_number else None

        # Validate that either email or phone_number is provided
        if not email and not phone_number:
            raise serializers.ValidationError(
                {"non_field_errors": (
                    "Either email or phone_number must be provided")}
            )

        # Use the custom authentication backend
        from django.contrib.auth import authenticate

        # Try to authenticate with email or phone number
        if email:
            user = authenticate(
                request=self.context.get("request"), email=email, password=password  # noqa
            )
        else:
            user = authenticate(
                request=self.context.get("request"),
                phone_number=phone_number,
                password=password,
            )

        if not user:
            raise serializers.ValidationError(
                 "Invalid credentials."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"non_field_errors": "User account is disabled"}
            )

        # Generate JWT tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class ContactMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for contact us messages
    """
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = ContactMessage
        fields = [
            'id',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'contact_number',
            'message',
            'company_name',
            'status',
            'is_read',
            'created_at',
            'updated_at',
            'responded_at',
            'response_notes',
        ]
        read_only_fields = [
            'id',
            'status',
            'is_read',
            'created_at',
            'updated_at',
            'responded_at',
            'response_notes',
            'full_name',
        ]

    def create(self, validated_data):
        # Get IP address and user agent from request if available
        request = self.context.get('request')
        if request:
            validated_data['ip_address'] = self.get_client_ip(request)
            validated_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')

        return super().create(validated_data)

    def get_client_ip(self, request):
        """Get the client IP address from the request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating contact messages (limited fields)
    """
    class Meta:
        model = ContactMessage
        fields = [
            'first_name',
            'last_name',
            'email',
            'contact_number',
            'message',
            'company_name',
        ]

    def validate_email(self, value):
        """Validate email format"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Please enter a valid email address.")
        return value.lower().strip()

    def validate_contact_number(self, value):
        """Basic phone number validation"""
        if not value:
            raise serializers.ValidationError("Contact number is required.")
        # Remove any non-digit characters
        # for basic validation
        digits_only = ''.join(filter(str.isdigit, value))
        if len(digits_only) < 7:
            raise serializers.ValidationError("Please enter a valid contact number.")
        return value

    def validate_message(self, value):
        """Validate message content"""
        if not value or len(value.strip()) < 10:
            raise serializers.ValidationError("Message must be at least 10 characters long.")
        return value.strip()


class EmailSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for email subscriptions
    """
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = EmailSubscription
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'status',
            'subscribed_at',
            'unsubscribed_at',
            'source',
        ]
        read_only_fields = [
            'id',
            'status',
            'subscribed_at',
            'unsubscribed_at',
            'full_name',
        ]


class EmailSubscriptionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating email subscriptions
    """
    class Meta:
        model = EmailSubscription
        fields = [
            'email',
            'first_name',
            'last_name',
        ]

    def validate_email(self, value):
        """Validate email format and check for duplicates"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Please enter a valid email address.")

        # Check if email is already subscribed and active
        email = value.lower().strip()
        existing = EmailSubscription.objects.filter(
            email=email,
            status='active'
        ).first()

        if existing:
            raise serializers.ValidationError(
                "This email address is already subscribed to our newsletter."
            )

        return email

    def create(self, validated_data):
        # Get additional metadata from request if available
        request = self.context.get('request')
        if request:
            # Try to get IP and user agent
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            validated_data['ip_address'] = ip
            validated_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')

        return super().create(validated_data)


class ContactMessageAdminSerializer(serializers.ModelSerializer):
    """
    Serializer for admin contact message management
    """
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = ContactMessage
        fields = [
            'id',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'contact_number',
            'message',
            'company_name',
            'status',
            'is_read',
            'created_at',
            'updated_at',
            'responded_at',
            'response_notes',
        ]
        read_only_fields = [
            'id',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'contact_number',
            'message',
            'company_name',
            'created_at',
            'updated_at',
        ]

    def update(self, instance, validated_data):
        # Automatically set responded_at when status changes to resolved or closed
        new_status = validated_data.get('status')
        if new_status in ['resolved', 'closed'] and instance.status not in ['resolved', 'closed']:
            validated_data['responded_at'] = timezone.now()

        return super().update(instance, validated_data)
