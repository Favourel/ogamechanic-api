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
    SecureDocument,
    DocumentVerificationLog,
    FileSecurityAudit,
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
    profile_picture = serializers.SerializerMethodField()

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
            "profile_picture",
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

    def get_profile_picture(self, obj):
        request = self.context.get('request', None)
        if obj.profile_picture and hasattr(obj.profile_picture, 'url'):
            return self._get_absolute_url(obj.profile_picture.url, request)
        return None


class MechanicProfileSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    cac_document = serializers.SerializerMethodField()
    selfie = serializers.SerializerMethodField()
    government_id = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = MechanicProfile
        fields = [
            "id",
            "user",
            "location",
            "bio",
            "lga",
            "cac_number",
            "cac_document",
            "selfie",
            "government_id",
            "rating",
            "is_approved",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "location",
            "bio",
            "lga",
            "cac_number",
            "cac_document",
            "selfie",
            "government_id",
            "rating",
            "is_approved",
            "created_at",
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

    def get_government_id(self, obj):
        request = self.context.get('request', None)
        if obj.government_id and hasattr(obj.government_id, 'url'):
            return self._get_absolute_url(obj.government_id.url, request)
        return None

    def get_rating(self, obj):
        from users.models import MechanicReview
        from django.db.models import Avg

        reviews = MechanicReview.objects.filter(mechanic=obj)
        avg_rating = reviews.aggregate(avg=Avg('rating')).get('avg')
        if avg_rating is not None:
            return round(avg_rating, 1)
        return None


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


class DriverLocationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ["latitude", "longitude"]
        ref_name = "UsersDriverLocationUpdateSerializer"


class MechanicReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    mechanic_id = serializers.PrimaryKeyRelatedField(
        queryset=MechanicProfile.objects.all(), source="mechanic", write_only=True  # noqa
    )

    class Meta:
        model = MechanicReview
        fields = [
            "id",
            "mechanic",
            "mechanic_id",
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


class DriverReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    driver_id = serializers.PrimaryKeyRelatedField(
        queryset=DriverProfile.objects.all(), source="driver", write_only=True
    )

    class Meta:
        model = DriverReview
        fields = [
            "id",
            "driver",
            "driver_id",
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
        if (
            self.instance is None
            and DriverReview.objects.filter(user=user, driver=driver).exists()
        ):
            raise serializers.ValidationError(
                "You have already reviewed this driver.")
        return attrs


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


class SecureDocumentSerializer(serializers.ModelSerializer):
    """Serializer for SecureDocument model."""

    user = UserSerializer(read_only=True)
    verified_by = UserSerializer(read_only=True)
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )  # noqa
    verification_status_display = serializers.CharField(
        source="get_verification_status_display", read_only=True
    )  # noqa
    secure_url = serializers.SerializerMethodField()

    class Meta:
        model = SecureDocument
        fields = [
            "id",
            "user",
            "document_type",
            "document_type_display",
            "original_filename",
            "secure_filename",
            "file_path",
            "file_size",
            "file_hash",
            "mime_type",
            "verification_status",
            "verification_status_display",  # noqa
            "is_encrypted",
            "access_count",
            "last_accessed",
            "extracted_info",
            "verification_notes",
            "verified_by",
            "verified_at",
            "uploaded_at",
            "updated_at",
            "expires_at",
            "secure_url",
        ]
        read_only_fields = [
            "id",
            "user",
            "secure_filename",
            "file_path",
            "file_size",
            "file_hash",
            "mime_type",
            "is_encrypted",
            "access_count",
            "last_accessed",
            "extracted_info",
            "verified_by",
            "verified_at",
            "uploaded_at",
            "updated_at",
            "secure_url",
        ]

    def get_secure_url(self, obj):
        """Get secure URL for document access."""
        return obj.get_secure_url()


class SecureDocumentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating secure documents."""

    file = serializers.FileField(write_only=True)

    class Meta:
        model = SecureDocument
        fields = ["document_type", "file"]

    def validate_file(self, value):
        """Validate uploaded file."""
        from ogamechanic.modules.file_storage_service import (
            FileValidationService,
        )  # noqa

        # Determine file type based on document type
        file_type_map = {
            "government_id": "identity",
            "driver_license": "identity",
            "passport": "identity",
            "cac_document": "document",
            "vehicle_registration": "vehicle",
            "insurance_document": "insurance",
            "vehicle_photo": "image",
            "profile_picture": "image",
            "other": "document",
        }

        file_type = file_type_map.get(
            self.initial_data.get("document_type"), "document"
        )  # noqa
        is_valid, error_message = FileValidationService.validate_file(
            value, file_type
        )  # noqa

        if not is_valid:
            raise serializers.ValidationError(error_message)

        return value

    def create(self, validated_data):
        """Create secure document with file processing."""
        file = validated_data.pop("file")
        user = self.context["request"].user
        document_type = validated_data["document_type"]

        # Process file based on document type
        if document_type == "cac_document":
            from ogamechanic.modules.file_storage_service import (
                CACDocumentService,
            )  # noqa

            file_metadata = CACDocumentService.process_cac_document(
                file, str(user.id)
            )  # noqa
        elif document_type in ["government_id", "driver_license", "passport"]:
            from ogamechanic.modules.file_storage_service import (
                IdentityVerificationService,
            )  # noqa

            file_metadata = (
                IdentityVerificationService.process_identity_document(  # noqa
                    file, str(user.id), document_type
                )
            )
        elif document_type in ["vehicle_registration", "insurance_document"]:
            from ogamechanic.modules.file_storage_service import (
                VehicleDocumentService,
            )  # noqa

            file_metadata = VehicleDocumentService.process_vehicle_document(
                file, str(user.id), document_type
            )
        else:
            from ogamechanic.modules.file_storage_service import (
                FileStorageService,
            )  # noqa

            file_metadata = FileStorageService.save_file(
                file, "document", str(user.id), document_type
            )

        # Create SecureDocument instance
        document = SecureDocument.objects.create(
            user=user,
            document_type=document_type,
            original_filename=file_metadata["original_filename"],
            secure_filename=file_metadata["secure_filename"],
            file_path=file_metadata["file_path"],
            file_size=file_metadata["file_size"],
            file_hash=file_metadata["file_hash"],
            mime_type=file_metadata["mime_type"],
            extracted_info=file_metadata.get("extracted_info", {}),
        )

        # Log document upload
        DocumentVerificationLog.objects.create(
            document=document,
            action="upload",
            performed_by=user,
            notes=f"Document uploaded: {document_type}",
            ip_address=self.context["request"].META.get("REMOTE_ADDR"),
            user_agent=self.context["request"].META.get("HTTP_USER_AGENT", ""),
        )

        return document


class DocumentVerificationLogSerializer(serializers.ModelSerializer):
    """Serializer for DocumentVerificationLog model."""

    document = SecureDocumentSerializer(read_only=True)
    performed_by = UserSerializer(read_only=True)
    action_display = serializers.CharField(
        source="get_action_display", read_only=True
    )  # noqa

    class Meta:
        model = DocumentVerificationLog
        fields = [
            "id",
            "document",
            "action",
            "action_display",
            "performed_by",
            "notes",
            "ip_address",
            "user_agent",
            "timestamp",
        ]
        read_only_fields = ["id", "document", "performed_by", "timestamp"]


class FileSecurityAuditSerializer(serializers.ModelSerializer):
    """Serializer for FileSecurityAudit model."""

    user = UserSerializer(read_only=True)
    audit_type_display = serializers.CharField(
        source="get_audit_type_display", read_only=True
    )  # noqa

    class Meta:
        model = FileSecurityAudit
        fields = [
            "id",
            "user",
            "audit_type",
            "audit_type_display",
            "file_path",
            "file_hash",
            "ip_address",
            "user_agent",
            "session_id",
            "success",
            "error_message",
            "metadata",
            "timestamp",
        ]
        read_only_fields = ["id", "user", "timestamp"]


class DocumentVerificationSerializer(serializers.Serializer):
    """Serializer for document verification actions."""

    action = serializers.ChoiceField(choices=["verify", "reject"])
    notes = serializers.CharField(max_length=1000, required=False)

    def validate_action(self, value):
        """Validate verification action."""
        if value not in ["verify", "reject"]:
            raise serializers.ValidationError(
                "Invalid action. Must be 'verify' or 'reject'"
            )  # noqa
        return value


class FileUploadSerializer(serializers.Serializer):
    """Serializer for general file uploads."""

    file = serializers.FileField()
    file_type = serializers.ChoiceField(
        choices=["image", "document", "identity", "vehicle", "insurance"]
    )
    category = serializers.CharField(
        max_length=100, required=False, default="general"
    )  # noqa

    def validate_file(self, value):
        """Validate uploaded file."""
        from ogamechanic.modules.file_storage_service import (
            FileValidationService,
        )  # noqa

        file_type = self.initial_data.get("file_type", "document")
        is_valid, error_message = FileValidationService.validate_file(
            value, file_type
        )  # noqa

        if not is_valid:
            raise serializers.ValidationError(error_message)

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
    vehicle_make_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        required=True,
        help_text="List of vehicle make IDs the mechanic is expert in"
    )
    expertise_details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Optional details for each vehicle make expertise"
    )

    def validate_vehicle_make_ids(self, value):
        """Validate that all vehicle make IDs exist and are active"""
        from mechanics.models import VehicleMake

        vehicle_makes = VehicleMake.objects.filter(
            id__in=value, is_active=True
        )

        if len(vehicle_makes) != len(value):
            invalid_ids = set(value) - set(vehicle_makes.values_list('id', flat=True))  # noqa
            raise serializers.ValidationError(
                f"Invalid or inactive vehicle make IDs: {list(invalid_ids)}"
            )

        return value
    
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
