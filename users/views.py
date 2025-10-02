import logging
import traceback
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import status as http_status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView
)
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi 
from .serializers import (
    UserSerializer,
    ChangePasswordSerializer,
    PasswordResetSerializer,
    NotificationSerializer,
    EmailVerificationSerializer,
    MerchantProfileSerializer, MechanicProfileSerializer, 
    DriverProfileSerializer, DriverLocationUpdateSerializer,
    StepOneRoleSelectionSerializer,
    StepTwoPrimaryUserInfoSerializer,
    StepTwoDriverSubRoleSerializer,
    StepTwoDriverInfoSerializer,
    StepTwoMechanicInfoSerializer,
    StepTwoMerchantInfoSerializer,
    StepThreeEmailVerificationSerializer,
    StepFourPrimaryUserCarDetailsSerializer,
    StepFourDriverDetailsSerializer,
    StepFourMerchantDetailsSerializer,
    StepFourMechanicDetailsSerializer,
    StepFivePasswordSerializer,
    CustomTokenObtainPairSerializer
)
from django.core.files.storage import default_storage
from ogamechanic.modules.utils import (
    api_response, incoming_request_checks, get_incoming_request_checks,
)
from ogamechanic.modules.paginations import CustomLimitOffsetPagination
from .throttling import UserRateThrottle, AuthRateThrottle
import jwt
from django.conf import settings
from ogamechanic.modules.exceptions import raise_serializer_error_msg
# from ogamechanic.modules.email_validation import DisposableEmailValidator
from users.models import UserActivityLog
# from .services import NotificationService
from django.utils import timezone
from rest_framework import parsers
from rest_framework import permissions
from .serializers import MechanicReviewSerializer
from .models import MechanicReview
from .serializers import DriverReviewSerializer
from .models import DriverReview
from .models import Device
from .models import (
    Notification,
    Wallet, Transaction, BankAccount, SecureDocument,
    DocumentVerificationLog, FileSecurityAudit, Role,
    DriverProfile, MerchantProfile, MechanicProfile
)
from .serializers import (
    WalletSerializer, TransactionSerializer, TransactionListSerializer,
    BankAccountSerializer, BankAccountCreateSerializer,
    WalletTopUpSerializer, WalletWithdrawalSerializer,
    PaystackWebhookSerializer, SecureDocumentSerializer,
    SecureDocumentCreateSerializer, DocumentVerificationLogSerializer,
    FileSecurityAuditSerializer, DocumentVerificationSerializer,
    FileUploadSerializer, RoleSerializer
)

logger = logging.getLogger(__name__)

User = get_user_model()


# UserRegistrationView has been removed in favor of StepByStepRegistrationView
# All new user registration should use the step-by-step flow at /api/users/register/step/<step>/  # noqa


class MerchantProfileManagementView(APIView):
    """
    Comprehensive merchant profile management API.
    
    Provides POST and PUT endpoints for creating and updating merchant profiles.  # noqa
    Requires user to have merchant role before creating/updating profile.
    
    Use Cases:
    - Complete profile for users who registered via step-by-step flow
    - Update existing merchant profiles
    - Create profiles for users who added merchant role later
    
    Note: For new user registration, use step-by-step registration flow.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [
        parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @swagger_auto_schema(
        operation_summary="View Merchant Profile",
        operation_description="""
        **Retrieve the merchant profile for the authenticated user**

        **Requirements:**
        - User must be authenticated
        - User must have 'merchant' role
        - User must already have a merchant profile

        **Returns:**
        - All merchant profile fields for the authenticated user
        """,
        responses={
            200: openapi.Response(
                description="Merchant profile retrieved successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Merchant profile retrieved successfully."),  # noqa
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(
                                    type=openapi.TYPE_INTEGER, 
                                    description="Profile ID"),
                                'user': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    description="User UUID"),
                                'location': openapi.Schema(
                                    type=openapi.TYPE_STRING),
                                'lga': openapi.Schema(
                                    type=openapi.TYPE_STRING),
                                'cac_number': openapi.Schema(
                                    type=openapi.TYPE_STRING),
                                'cac_document': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    description="URL to CAC document"),
                                'selfie': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    description="URL to selfie"),
                                'business_address': openapi.Schema(
                                    type=openapi.TYPE_STRING),
                                'profile_picture': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    description="URL to profile picture"),
                                'is_approved': openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN, example=False),
                                'created_at': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    format='date-time'),
                                'updated_at': openapi.Schema(
                                    type=openapi.TYPE_STRING, format='date-time') # noqa
                            }
                        )
                    }
                )
            ),
            400: openapi.Response(
                description="User does not have merchant role or profile does not exist", # noqa
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False), # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="User does not have a merchant profile."),
                    }
                )
            ),
            401: openapi.Response(description="Authentication required"),
        }
    )
    def get(self, request):
        user = request.user

        # Check if user has merchant role
        if not user.roles.filter(name='merchant').exists():
            return Response(api_response(
                message="User must have merchant role to view merchant profile.", # noqa
                status=False
            ), status=400)

        # Check if user has a merchant profile
        merchant_profile = getattr(user, 'merchant_profile', None)
        if not merchant_profile:
            return Response(api_response(
                message="User does not have a merchant profile.",
                status=False
            ), status=400)

        serializer = MerchantProfileSerializer(
            merchant_profile, context={'request': request})
        return Response(api_response(
            message="Merchant profile retrieved successfully.",
            status=True,
            data=serializer.data
        ), status=200)

    @swagger_auto_schema(
        operation_summary="Create Merchant Profile",
        operation_description="""
        **Create a new merchant profile for authenticated user**
        
        **Requirements:**
        - User must be authenticated
        - User must have 'merchant' role
        - User must not already have a merchant profile
        
        **Profile Fields:**
        - **location**: Business location/address (required)
        - **lga**: Local Government Area (required)
        - **cac_number**: Corporate Affairs Commission number (required)
        - **cac_document**: CAC registration document upload (required)
        - **selfie**: Live photo of merchant for verification (required)
        - **business_address**: Physical business address (optional)
        
        **File Upload Requirements:**
        - **cac_document**: PDF, JPG, JPEG, PNG (max size varies)
        - **selfie**: JPG, JPEG, PNG only (for facial verification)
        
        **Validation:**
        - All required fields must be provided
        - Files must be valid formats
        - CAC number format validation
        - Location and LGA must be valid Nigerian locations
        
        **Process Flow:**
        1. User completes step-by-step registration with merchant role
        2. User calls this endpoint to complete merchant profile
        3. Profile created and awaits admin approval
        4. User can start using merchant features once approved
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["location", "lga", "cac_number", "cac_document", "selfie"], # noqa
            properties={
                "location": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Business location/address in Nigeria",
                    example="Victoria Island, Lagos"
                ),
                "lga": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Local Government Area",
                    example="Eti-Osa"
                ),
                "cac_number": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Corporate Affairs Commission registration number",  # noqa
                    example="RC123456"
                ),
                "cac_document": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="CAC registration certificate (PDF/Image)"
                ),
                "selfie": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Live photo of merchant for verification (Image only)"  # noqa
                ),
                "business_address": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Physical business address (optional)",
                    example="123 Business Street, Victoria Island"
                ),
            }
        ),
        responses={
            201: openapi.Response(
                description="Merchant profile created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),  # noqa
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example="Merchant profile created successfully."),  # noqa
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Profile ID"),  # noqa
                                'user': openapi.Schema(type=openapi.TYPE_STRING, description="User UUID"),  # noqa
                                'location': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'lga': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'cac_number': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'is_approved': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                                'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),  # noqa
                                'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')  # noqa
                            }
                        )
                    }
                )
            ),
            400: openapi.Response(
                description="Invalid request data or user doesn't have merchant role",  # noqa
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="User must have merchant role to create merchant profile."  # noqa
                        ),
                        'errors': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="Field-specific validation errors"
                        ),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'suggestion': openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="Use step-by-step registration to add merchant role"  # noqa
                                )
                            }
                        )
                    }
                )
            ),
            401: openapi.Response(description="Authentication required"),
            409: openapi.Response(
                description="Merchant profile already exists",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Merchant profile already exists. Use PUT to update or delete this profile first."  # noqa
                        )
                    }
                )
            )
        }
    )
    def post(self, request):
        user = request.user
        
        # Check if user has merchant role
        if not user.roles.filter(name='merchant').exists():
            return Response(api_response(
                message="User must have merchant role to create merchant profile.",  # noqa
                status=False,
                data={"suggestion": "Use step-by-step registration to add merchant role"}  # noqa
            ), status=400)
        
        if hasattr(user, 'merchant_profile'):
            return Response(api_response(
                message="Merchant profile already exists. Use PUT to update or delete this profile first.",  # noqa
                status=False
            ), status=400)
            
        serializer = MerchantProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=user)
            return Response(api_response(
                message="Merchant profile created successfully.",
                status=True,
                data=serializer.data
            ), status=201)
        return Response(api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
        ), status=400)

    @swagger_auto_schema(
        operation_summary="Update Merchant Profile",
        operation_description="""
        **Update an existing merchant profile for authenticated user**
        
        **Requirements:**
        - User must be authenticated
        - User must have 'merchant' role
        - User must already have a merchant profile
        
        **Update Features:**
        - Partial updates supported (only send fields to update)
        - File uploads supported for document/selfie updates
        - All profile fields can be updated
        
        **Profile Fields (all optional for updates):**
        - **location**: Business location/address
        - **lga**: Local Government Area
        - **cac_number**: Corporate Affairs Commission number
        - **cac_document**: New CAC registration document upload
        - **selfie**: New live photo of merchant
        - **business_address**: Physical business address
        
        **File Upload Requirements:**
        - **cac_document**: PDF, JPG, JPEG, PNG (max size varies)
        - **selfie**: JPG, JPEG, PNG only (for facial verification)
        
        **Use Cases:**
        - Update business information
        - Upload new/updated documents
        - Change business address or location
        - Update CAC information
        - Replace verification selfie
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=[],
            properties={
                'location': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Business location/address in Nigeria",
                    example="Lekki Phase 1, Lagos"
                ),
                'lga': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Local Government Area",
                    example="Eti-Osa"
                ),
                'cac_number': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Corporate Affairs Commission registration number",  # noqa
                    example="RC654321"
                ),
                'cac_document': openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Updated CAC registration certificate (PDF/Image)"  # noqa
                ),
                'selfie': openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Updated live photo of merchant for verification"  # noqa
                ),
                'business_address': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Updated physical business address",
                    example="456 New Business Avenue, Lekki"
                ),
            }
        ),
        responses={
            200: openapi.Response(
                description="Merchant profile updated successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),  # noqa
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example="Merchant profile updated successfully."),  # noqa
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Profile ID"),  # noqa
                                'user': openapi.Schema(type=openapi.TYPE_STRING, description="User UUID"),  # noqa
                                'location': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'lga': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'cac_number': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'is_approved': openapi.Schema(type=openapi.TYPE_BOOLEAN),  # noqa
                                'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),  # noqa
                                'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')  # noqa
                            }
                        )
                    }
                )
            ),
            400: openapi.Response(
                description="Invalid request data or user doesn't have merchant role",  # noqa
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="User must have merchant role to update merchant profile."  # noqa
                        ),
                        'errors': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="Field-specific validation errors"  # noqa
                        )
                    }
                )
            ),
            401: openapi.Response(description="Authentication required"),
            404: openapi.Response(
                description="Merchant profile not found",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Merchant profile does not exist. Create one first."  # noqa
                        )
                    }
                )
            )
        }
    )
    def put(self, request):
        user = request.user
        
        # Check if user has merchant role
        if not user.roles.filter(name='merchant').exists():
            return Response(api_response(
                message="User must have merchant role to update merchant profile.",  # noqa
                status=False
            ), status=400)
        
        if not hasattr(user, 'merchant_profile'):
            return Response(api_response(
                message="Merchant profile does not exist. Create one first.",  # noqa
                status=False
            ), status=404)
            
        serializer = MerchantProfileSerializer(
            user.merchant_profile, 
            data=request.data, 
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(api_response(
                message="Merchant profile updated successfully.",
                status=True,
                data=serializer.data
            ))
        return Response(api_response(
            message=(
                ", ".join(
                    [
                        f"{field}: {', '.join(errors)}"
                        for field, errors in serializer.errors.items()
                    ]
                )
                if serializer.errors
                else "Invalid data"
            ),
            status=False,
            errors=serializer.errors,
        ), status=400)


class MechanicProfileManagementView(APIView):
    """
    Manage mechanic profiles - create, update, or complete mechanic profile.
    
    Use Cases:
    - Complete profile for users who registered via step-by-step flow
    - Update existing mechanic profiles
    - Create profiles for users who added mechanic role later
    
    Note: For new user registration, use step-by-step registration flow.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [
        parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @swagger_auto_schema(
        operation_summary="View Mechanic Profile",
        operation_description="""
        **Retrieve the merchant profile for the authenticated user**

        **Requirements:**
        - User must be authenticated
        - User must have 'mechanic' role
        - User must already have a mechanic profile

        **Returns:**
        - All mechanic profile fields for the authenticated user
        """,
        responses={200: MechanicProfileSerializer(many=True)}
    )
    def get(self, request):
        user = request.user

        # Check if user has mechanic role
        if not user.roles.filter(name='mechanic').exists():
            return Response(api_response(
                message="User must have mechanic role to view mechanic profile.", # noqa
                status=False
            ), status=400)

        # Check if user has a mechanic profile
        mechanic_profile = getattr(user, 'mechanic_profile', None)
        if not mechanic_profile:
            return Response(api_response(
                message="User does not have a mechanic profile.",
                status=False
            ), status=400)

        serializer = MechanicProfileSerializer(
            mechanic_profile, context={'request': request})
        return Response(api_response(
            message="Mechanic profile retrieved successfully.",
            status=True,
            data=serializer.data
        ), status=200)

    @swagger_auto_schema(
        operation_summary="Create Mechanic Profile",
        operation_description="Complete mechanic profile with documents and details. Use step-by-step registration for new mechanic accounts.",  # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["location", "lga", "cac_number", "cac_document", "selfie"],  # noqa
            properties={
                "location": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Business location/address in Nigeria",
                    example="Ikeja, Lagos"
                ),
                "lga": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Local Government Area",
                    example="Ikeja"
                ),
                "cac_number": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Corporate Affairs Commission registration number",  # noqa
                    example="RC789012"
                ),
                "cac_document": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="CAC registration certificate (PDF/Image)"
                ),
                "selfie": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Live photo of mechanic for verification (Image only)"  # noqa
                ),
            }
        ),
        responses={
            201: openapi.Response("Mechanic profile created successfully"),
            400: openapi.Response("Bad Request - Invalid data or user doesn't have mechanic role"),  # noqa
            409: openapi.Response("Conflict - Mechanic profile already exists")
        }
    )
    def post(self, request):
        user = request.user
        
        # Check if user has mechanic role
        if not user.roles.filter(name='mechanic').exists():
            return Response(api_response(
                message="User must have mechanic role to create mechanic profile.",  # noqa
                status=False,
                data={"suggestion": "Use step-by-step registration to add mechanic role"}  # noqa
            ), status=400)
        
        if hasattr(user, 'mechanic_profile'):
            return Response(api_response(
                message="Mechanic profile already exists. Use PUT to update.",
                status=False
            ), status=400)
            
        serializer = MechanicProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=user)
            return Response(api_response(
                message="Mechanic profile completed. Awaiting admin approval.", # noqa
                status=True,
                data=serializer.data
            ))
        return Response(api_response(
            message=(
                ", ".join(
                    [
                        f"{field}: {', '.join(errors)}"
                        for field, errors in serializer.errors.items()
                    ]  # noqa
                )
                if serializer.errors
                else "Invalid data"
            ),
            status=False,
            errors=serializer.errors,
        ), status=400)


class DriverProfileManagementView(APIView):
    """
    Manage driver profiles - create, update, or complete driver profile.
    
    Use Cases:
    - Complete profile for users who registered via step-by-step flow
    - Update existing driver profiles
    - Create profiles for users who added driver/rider role later
    
    Note: For new user registration, use step-by-step registration flow.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [
        parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @swagger_auto_schema(
        operation_summary="View Driver Profile",
        operation_description="""
        **Retrieve the driver profile for the authenticated user**

        **Requirements:**
        - User must be authenticated
        - User must have 'driver' role
        - User must already have a driver profile

        **Returns:**
        - All driver profile fields for the authenticated user
        """,
        responses={200: DriverProfileSerializer(many=True)}
    )
    def get(self, request):
        user = request.user

        if not (user.roles.filter(name='driver').exists() or 
                user.roles.filter(name='rider').exists()):
            return Response(api_response(
                message="User must have driver or rider role to view driver profile.",  # noqa
                status=False,
            ), status=400)

        # Check if user has a driver profile
        driver_profile = getattr(user, 'driver_profile', None)
        if not driver_profile:
            return Response(api_response(
                message="User does not have a driver profile.",
                status=False
            ), status=400)

        serializer = DriverProfileSerializer(
            driver_profile, context={'request': request})
        return Response(api_response(
            message="Driver profile retrieved successfully.",
            status=True,
            data=serializer.data
        ), status=200)

    @swagger_auto_schema(
        operation_summary="Create Driver Profile",
        operation_description="""
        **Create a comprehensive driver profile for authenticated user**
        
        **Requirements:**
        - User must be authenticated
        - User must have 'driver' or 'rider' role
        - User must not already have a driver profile
        
        **Comprehensive Profile Fields:**
        
        **Personal Information (Required):**
        - **full_name**: Complete legal name
        - **phone_number**: Contact phone number
        - **city**: City of operation
        - **date_of_birth**: Date of birth for age verification
        - **gender**: Gender identification
        - **address**: Complete home address
        - **location**: Operating location/area
        
        **License Information (Required):**
        - **license_number**: Driver's license number
        - **license_issue_date**: License issue date
        - **license_expiry_date**: License expiry date
        - **license_front_image**: Front side of license (image)
        - **license_back_image**: Back side of license (image)
        
        **Vehicle Information (Required):**
        - **vin**: Vehicle Identification Number
        - **vehicle_name**: Vehicle brand/name
        - **plate_number**: License plate number
        - **vehicle_model**: Complete vehicle model info
        - **vehicle_color**: Vehicle color
        
        **Vehicle Photos (Required - 4 angles):**
        - **vehicle_photo_front**: Front view of vehicle
        - **vehicle_photo_back**: Rear view of vehicle
        - **vehicle_photo_right**: Right side view
        - **vehicle_photo_left**: Left side view
        
        **Banking Information (Required):**
        - **bank_name**: Bank name for payments
        - **account_number**: Bank account number
        
        **File Upload Requirements:**
        - **License images**: JPG, JPEG, PNG only
        - **Vehicle photos**: JPG, JPEG, PNG only
        - All images should be clear and readable
        - Maximum file size limits apply
        
        **Validation:**
        - Age verification (must be 18+)
        - License validity check
        - VIN format validation
        - Bank account format validation
        - Image quality requirements
        
        **Process Flow:**
        1. User completes step-by-step registration with driver role
        2. User calls this endpoint to complete comprehensive driver profile
        3. Profile created and awaits admin approval
        4. User can start using driver features once approved
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["full_name", "phone_number", "city", "date_of_birth", "gender", "address", "location", "license_number", "license_issue_date", "license_expiry_date", "license_front_image", "license_back_image", "vin", "vehicle_name", "plate_number", "vehicle_model", "vehicle_color", "vehicle_photo_front", "vehicle_photo_back", "vehicle_photo_right", "vehicle_photo_left", "bank_name", "account_number"],  # noqa
            properties={
                "full_name": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Complete legal name as on license",
                    example="John Doe Adebayo"
                ),
                "phone_number": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Contact phone number",
                    example="+2348012345678"
                ),
                "city": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Primary city of operation",
                    example="Lagos"
                ),
                "date_of_birth": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Date of birth (YYYY-MM-DD)",
                    format='date',
                    example="1990-05-15"
                ),
                "gender": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Gender identification",
                    enum=['male', 'female', 'other', 'prefer_not_to_say'],
                    example="male"
                ),
                "address": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Complete home address",
                    example="123 Main Street, Ikeja, Lagos"
                ),
                "location": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Primary operating location",
                    example="Victoria Island, Lagos"
                ),
                "license_number": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Driver's license number",
                    example="LAG123456789"
                ),
                "license_issue_date": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="License issue date (YYYY-MM-DD)",
                    format='date',
                    example="2020-01-15"
                ),
                "license_expiry_date": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="License expiry date (YYYY-MM-DD)",
                    format='date',
                    example="2025-01-15"
                ),
                "license_front_image": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Front side of driver's license"
                ),
                "license_back_image": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Back side of driver's license"
                ),
                "vin": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Vehicle Identification Number",
                    example="1HGBH41JXMN109186"
                ),
                "vehicle_name": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Vehicle brand/name",
                    example="Toyota Camry"
                ),
                "plate_number": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="License plate number",
                    example="LAG-123-AB"
                ),
                "vehicle_model": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Complete vehicle model information",
                    example="2018 Toyota Camry LE"
                ),
                "vehicle_color": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Vehicle color",
                    example="Silver"
                ),
                "vehicle_photo_front": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Front view of vehicle"
                ),
                "vehicle_photo_back": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Rear view of vehicle"
                ),
                "vehicle_photo_right": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Right side view of vehicle"
                ),
                "vehicle_photo_left": openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="Left side view of vehicle"
                ),
                "bank_name": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Bank name for payment processing",
                    example="First Bank of Nigeria"
                ),
                "account_number": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Bank account number",
                    example="1234567890"
                ),
            }
        ),
        responses={
            201: openapi.Response(
                description="Driver profile created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Driver profile completed successfully. Awaiting admin approval."  # noqa
                        ),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Profile ID"),  # noqa
                                'user': openapi.Schema(type=openapi.TYPE_STRING, description="User UUID"),  # noqa
                                'full_name': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'license_number': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'vehicle_model': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'plate_number': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'is_approved': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                                'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),  # noqa
                                'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')  # noqa
                            }
                        )
                    }
                )
            ),
            400: openapi.Response(
                description="Invalid request data or user doesn't have driver/rider role",  # noqa
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="User must have driver or rider role to create driver profile."  # noqa
                        ),
                        'errors': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="Field-specific validation errors"
                        ),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'suggestion': openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="Use step-by-step registration to add driver role"  # noqa
                                )
                            }
                        )
                    }
                )
            ),
            401: openapi.Response(description="Authentication required"),
            409: openapi.Response(
                description="Driver profile already exists",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Driver profile already exists. Use PUT to update."  # noqa
                        )
                    }
                )
            )
        }
    )
    def post(self, request):
        user = request.user
        
        # Check if user has driver or rider role
        if not (user.roles.filter(name='driver').exists() or 
                user.roles.filter(name='rider').exists()):
            return Response(api_response(
                message="User must have driver or rider role to create driver profile.",  # noqa
                status=False,
                data={"suggestion": "Use step-by-step registration to add driver role"}  # noqa
            ), status=400)
        
        if hasattr(user, 'driver_profile'):
            return Response(api_response(
                message="Driver profile already exists. Use PUT to update.",  # noqa
                status=False
            ), status=400)
            
        serializer = DriverProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=user)
            return Response(api_response(
                message=(
                    "Driver profile completed successfully. "
                    "Awaiting admin approval."
                ),
                status=True,
                data=serializer.data
            ))
        return Response(api_response(
            message=(
                ", ".join(
                    [
                        f"{field}: {', '.join(errors)}"
                        for field, errors in serializer.errors.items()
                    ]  # noqa
                )
                if serializer.errors
                else "Invalid data"
            ),
            status=False,
            errors=serializer.errors,
        ), status=400)


class LoginView(TokenObtainPairView):
    """
    View for user login using JWT authentication with email or phone number.
    """
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer
    # throttle_classes = [AuthRateThrottle]

    @swagger_auto_schema(
        operation_description=(
            "Login to get JWT tokens and user details "
            "using email or phone number"
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['password'],
                    properties={
                        'email': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description=(
                                "User's email address "
                                "(optional if phone_number provided)"
                            )
                        ),
                        'phone_number': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description=(
                                "User's phone number "
                                "(optional if email provided)"
                            )
                        ),
                        'password': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="User's password"
                        ),
                    },
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Login successful",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'access': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="JWT access token"
                        ),
                        'refresh': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="JWT refresh token"
                        ),
                        'user': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="User details"
                        ),
                    },
                )
            ),
            400: "Bad Request",
            401: "Invalid credentials",
            423: "Account locked",
            # 429: "Too Many Requests"
        }
    )
    def post(self, request, *args, **kwargs):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        # Create a new request with the credentials
        request.data.update(data)
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            # Get the user from the authentication
            from django.contrib.auth import authenticate
            user = authenticate(
                request=request,
                email=data.get('email'),
                phone_number=data.get('phone_number'),
                password=data.get('password')
            )
            
            if user:
                # Reset failed attempts if any
                if (hasattr(user, 'failed_login_attempts') and
                        user.failed_login_attempts > 0):
                    user.failed_login_attempts = 0
                    user.locked_until = None
                    user.save()

                user_data = UserSerializer(user).data

                # Add user details to response
                response_data = response.data
                response_data['user'] = user_data

            # Log successful login
            if user:
                identifier = data.get('email') or data.get('phone_number')
                UserActivityLog.objects.create(
                    user=user,
                    action='login',
                    description=f"Login attempt (identifier: {identifier})",
                    ip_address=request.META.get('REMOTE_ADDR'),
                    object_type='User',
                    object_id=user.id,
                    severity='low'
                )

            return Response(
                api_response(
                    message="Login successful",
                    status=True,
                    data=response_data
                )
            )
        
        return response


class TokenRefreshView(TokenRefreshView):
    """
    View for refreshing JWT tokens.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @swagger_auto_schema(
        operation_description="Refresh JWT token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={
                'refresh': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="JWT refresh token"
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Token refresh successful",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'access': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="New JWT access token"
                        ),
                    },
                )
            ),
            400: "Bad Request",
            401: "Invalid token",
            429: "Too Many Requests"
        }
    )
    def post(self, request, *args, **kwargs):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            return Response(
                api_response(
                    message="Token refresh successful",
                    status=True,
                    data=response.data
                )
            )
        return Response(
            api_response(
                message="Invalid token",
                status=False
            ),
            status=http_status.HTTP_401_UNAUTHORIZED
        )


class PasswordResetRequestView(APIView):
    """
    View for requesting password reset.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @swagger_auto_schema(
        operation_description="Request password reset",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['email'],
                    properties={
                        'email': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="User's email address"
                        ),
                    },
                ),
            },
        ),
        responses={
            200: "Password reset email sent",
            400: "Bad Request",
            429: "Too Many Requests"
        }
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        serializer = PasswordResetSerializer(data=data)
        serializer.is_valid(raise_exception=True) or (
            raise_serializer_error_msg(errors=serializer.errors)
        )

        serializer.save()

        return Response(
            api_response(
                message="Password reset email sent successfully",
                status=True
            )
        )
        # serializer = PasswordResetSerializer(data=data)

        # if serializer.is_valid():
        #     print(serializer)
        #     serializer.save()
        #     return Response(
        #         api_response(
        #             message="Password reset email sent successfully",
        #             status=True
        #         )
        #     )

        # return Response(
        #     api_response(
        #         message="Invalid data",
        #         status=False,
        #         data=serializer.errors
        #     ),
        #     status=http_status.HTTP_400_BAD_REQUEST
        # )


class PasswordResetConfirmView(APIView):
    """
    View for confirming password reset.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @swagger_auto_schema(
        operation_description="Confirm password reset",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['email'],
                    properties={
                        'token': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Password reset token"
                        ),
                        'password': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="New password"
                        ),
                        'password_confirm': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Confirm new password"
                        ),
                    },
                ),
            },
        ),

        responses={
            200: "Password reset successful",
            400: "Bad Request",
            429: "Too Many Requests"
        }
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        token = data.get('token')
        password = data.get('password')
        password_confirm = data.get('password_confirm')

        if password != password_confirm:
            return Response(
                api_response(
                    message="Passwords do not match",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        try:
            # Validate password
            validate_password(password)
            
            # Verify token and get user
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=['HS256']
            )
            user = User.objects.get(id=payload['user_id'])
            
            # Update password
            user.set_password(password)
            user.save()
            
            return Response(
                api_response(
                    message="Password reset successful",
                    status=True
                )
            )
        except ValidationError as e:
            return Response(
                api_response(
                    message="Invalid password",
                    status=False,
                    data={'errors': list(e.messages)}
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except (jwt.InvalidTokenError, User.DoesNotExist):
            return Response(
                api_response(
                    message="Invalid or expired token",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )


class ChangePasswordView(APIView):
    """
    View for changing user password.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_description="Change user password",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'old_password': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Current password"
                        ),
                        'new_password': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="New password"
                        ),
                        'new_password_confirm': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Confirm new password"
                        ),
                    },
                    required=['old_password', 'new_password', 'new_password_confirm'], # noqa
                ),
            },
        ),
        responses={
            200: "Password changed successfully",
            400: "Bad Request",
            401: "Unauthorized",
            429: "Too Many Requests"
        }
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = ChangePasswordSerializer(data=data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(
                serializer.validated_data['old_password']
            ):
                return Response(
                    api_response(
                        message="Invalid old password",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

            try:
                validate_password(
                    serializer.validated_data['new_password'],
                    user
                )
            except ValidationError as e:
                return Response(
                    api_response(
                        message="Invalid password",
                        status=False,
                        data={'errors': list(e.messages)}
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response(
                api_response(
                    message="Password changed successfully",
                    status=True
                )
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )


class LogoutView(APIView):
    """
    View for user logout.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_description="Logout and blacklist the refresh token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={
                'refresh': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="JWT refresh token to blacklist"
                ),
            },
        ),
        responses={
            200: "Logout successful",
            400: "Bad Request",
            401: "Unauthorized",
            429: "Too Many Requests"
        }
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        try:
            refresh_token = data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                api_response(
                    message="Logout successful",
                    status=True
                )
            )
        except Exception:
            return Response(
                api_response(
                    message="Invalid token",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="Get a paginated list of notifications "
        "for the authenticated user.",
        manual_parameters=[
            openapi.Parameter(
                'is_read', openapi.IN_QUERY, description="Filter by read status",  # noqa
                type=openapi.TYPE_BOOLEAN, required=False
            ),
            openapi.Parameter(
                'type', openapi.IN_QUERY, description="Filter by notification type",  # noqa
                type=openapi.TYPE_STRING, required=False
            ),
        ],
        responses={200: NotificationSerializer(many=True)}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), 
                status=http_status.HTTP_400_BAD_REQUEST
            )
            
        notifications = Notification.objects.filter(
            user=request.user).order_by('-created_at')
        
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            is_read = is_read.lower() == 'true'
            notifications = notifications.filter(is_read=is_read)
        notification_type = request.query_params.get('type')

        if notification_type:
            notifications = notifications.filter(
                notification_type=notification_type)
        paginator = self.pagination_class()
        paginated_notifications = paginator.paginate_queryset(
            notifications, request)
        serializer = NotificationSerializer(paginated_notifications, many=True)
        response = paginator.get_paginated_response(serializer.data)

        return Response(api_response(
            message="Notifications retrieved successfully",
            status=True,
            data=response.data
        ))


class NotificationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get a specific notification.",
        responses={200: NotificationSerializer()}
    )
    def get(self, request, notification_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), 
                            status=http_status.HTTP_400_BAD_REQUEST)
        try:
            notification = Notification.objects.get(
                id=notification_id, user=request.user)
            serializer = NotificationSerializer(notification)
            return Response(api_response(
                message="Notification retrieved successfully",
                status=True,
                data=serializer.data
            ))
        except Notification.DoesNotExist:
            return Response(
                api_response(message="Notification not found", status=False), 
                status=http_status.HTTP_404_NOT_FOUND
            )

    @swagger_auto_schema(
        operation_description="Mark notification as read.",
        responses={200: NotificationSerializer()}
    )
    def patch(self, request, notification_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), 
                            status=http_status.HTTP_400_BAD_REQUEST)
        try:
            notification = Notification.objects.get(
                id=notification_id, user=request.user)
            notification.mark_as_read()
            serializer = NotificationSerializer(notification)
            return Response(api_response(
                message="Notification marked as read",
                status=True,
                data=serializer.data
            ))
        except Notification.DoesNotExist:
            return Response(
                api_response(message="Notification not found", 
                             status=False), 
                status=http_status.HTTP_404_NOT_FOUND
                )


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Mark all user notifications as read.",
        responses={200: openapi.Response("All notifications marked as read")},
    )
    def post(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        updated_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response(
            api_response(
                message=f"Marked {updated_count} notifications as read",
                status=True,
                data={"updated_count": updated_count},
            )
        )


class DeviceRegistrationView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Register a device for push notifications",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['fcm_token'],
            properties={
                'fcm_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Firebase Cloud Messaging token"
                ),
            }
        ),
        responses={201: openapi.Response("Device registered successfully")}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            return Response(
                api_response(
                    message="FCM token is required",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        # Create or update device
        device, created = Device.objects.get_or_create(
            fcm_token=fcm_token,
            defaults={'user': request.user, 'is_active': True}
        )
        
        if not created:
            # Update existing device
            device.user = request.user
            device.is_active = True
            device.save()
        
        return Response(
            api_response(
                message="Device registered successfully",
                status=True,
                data={'device_id': str(device.id)}
            ),
            status=http_status.HTTP_201_CREATED
        )

    @swagger_auto_schema(
        operation_description="Unregister a device for push notifications",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['fcm_token'],
            properties={
                'fcm_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Firebase Cloud Messaging token"
                ),
            }
        ),
        responses={200: openapi.Response("Device unregistered successfully")}
    )
    def delete(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            return Response(
                api_response(
                    message="FCM token is required",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        # Deactivate device
        Device.objects.filter(
            fcm_token=fcm_token,
            user=request.user
        ).update(is_active=False)
        
        return Response(
            api_response(
                message="Device unregistered successfully",
                status=True
            )
        )


class EmailVerificationAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @swagger_auto_schema(
        operation_description="Verify a user's email address using a verification token.", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "token": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="The email verification token sent to the user's email." # noqa
                        ),
                    },
                    example={
                        "token": "your-verification-token"
                    } 
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Email verified successfully.",
                examples={
                    "application/json": {
                        "message": "Email verified successfully.",
                        "status": True
                    }
                }
            ),
            400: openapi.Response(
                description="Invalid token or bad request.",
                examples={
                    "application/json": {
                        "message": "Invalid or expired token.",
                        "status": False
                    }
                }
            ),
        }
    )
    def post(self, request):
        """
        Verify a user's email address using a verification token.

        Expects a POST request with a 'token' in the body.
        """
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        serializer = EmailVerificationSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                api_response(
                    message="Email verified successfully.",
                    status=True
                ),
                status=http_status.HTTP_200_OK
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )


class MechanicReviewListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List and create reviews for a mechanic",
        responses={200: MechanicReviewSerializer(many=True)},
    )
    def get(self, request, mechanic_id):
        reviews = (
            MechanicReview.objects
            .filter(mechanic_id=mechanic_id)
            .order_by('-created_at')
        )
        paginator = self.pagination_class()
        paginated_reviews = paginator.paginate_queryset(reviews, request)
        serializer = MechanicReviewSerializer(paginated_reviews, many=True)
        return Response(
            api_response(
                message="Mechanic reviews retrieved successfully.",
                status=True,
                data=serializer.data,
            ),
            status=200,
        )

    @swagger_auto_schema(
        operation_description="Create a review for a mechanic",
        request_body=MechanicReviewSerializer,
        responses={201: MechanicReviewSerializer()},
    )
    def post(self, request, mechanic_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400,
            )
        serializer = MechanicReviewSerializer(
            data=data,
            context={"request": request},
        )
        if serializer.is_valid():
            serializer.save(user=request.user, mechanic_id=mechanic_id)
            return Response(
                api_response(
                    message="Review created successfully.",
                    status=True,
                    data=serializer.data,
                ),
                status=201,
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=400,
        )


class MechanicReviewDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update or delete a mechanic review",
        request_body=MechanicReviewSerializer,
        responses={200: MechanicReviewSerializer()}
    )
    def put(self, request, mechanic_id, pk):
        try:
            review = MechanicReview.objects.get(
                pk=pk,
                mechanic_id=mechanic_id,
                user=request.user
            )
        except MechanicReview.DoesNotExist:
            return Response(
                api_response(
                    message="Review not found.",
                    status=False
                ),
                status=404
            )
        serializer = MechanicReviewSerializer(
            review,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                api_response(
                    message="Review updated successfully.",
                    status=True,
                    data=serializer.data
                )
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=400
        )

    def delete(self, request, mechanic_id, pk):
        try:
            review = MechanicReview.objects.get(
                pk=pk,
                mechanic_id=mechanic_id,
                user=request.user
            )
        except MechanicReview.DoesNotExist:
            return Response(
                api_response(
                    message="Review not found.",
                    status=False
                ),
                status=404
            )
        review.delete()
        return Response(
            api_response(
                message="Review deleted successfully.",
                status=True,
                data={}
            )
        )


class DriverReviewListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @swagger_auto_schema(
        operation_description="List and create reviews for a driver",
        responses={200: DriverReviewSerializer(many=True)},
    )
    def get(self, request, driver_id):
        reviews = (
            DriverReview.objects
            .filter(driver_id=driver_id)
            .order_by('-created_at')
        )
        serializer = DriverReviewSerializer(reviews, many=True)
        return Response(
            api_response(
                message="Driver reviews retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )

    def post(self, request, driver_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        serializer = DriverReviewSerializer(
            data=data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save(user=request.user, driver_id=driver_id)
            return Response(
                api_response(
                    message="Review created successfully.",
                    status=True,
                    data=serializer.data
                ),
                status=201
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=400
        )


class DriverReviewDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update or delete a driver review",
        request_body=DriverReviewSerializer,
        responses={200: DriverReviewSerializer()}
    )
    def put(self, request, driver_id, pk):
        try:
            review = DriverReview.objects.get(
                pk=pk,
                driver_id=driver_id,
                user=request.user
            )
        except DriverReview.DoesNotExist:
            return Response(
                api_response(
                    message="Review not found.",
                    status=False
                ),
                status=404
            )
        serializer = DriverReviewSerializer(
            review,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                api_response(
                    message="Review updated successfully.",
                    status=True,
                    data=serializer.data
                )
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=400
        )

    def delete(self, request, driver_id, pk):
        try:
            review = DriverReview.objects.get(
                pk=pk,
                driver_id=driver_id,
                user=request.user
            )
        except DriverReview.DoesNotExist:
            return Response(
                api_response(
                    message="Review not found.",
                    status=False
                ),
                status=404
            )
        review.delete()
        return Response(
            api_response(
                message="Review deleted successfully.",
                status=True,
                data={}
            )
        )


class DriverLocationUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Update driver current location (latitude, longitude)"
        ),
        request_body=DriverLocationUpdateSerializer,
        responses={200: DriverLocationUpdateSerializer()}
    )
    def patch(self, request):
        user = request.user
        if not hasattr(user, 'driver_profile'):
            return Response(
                api_response(
                    message="User is not a driver.",
                    status=False
                ),
                status=403
            )
        serializer = DriverLocationUpdateSerializer(
            user.driver_profile,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                api_response(
                    message="Driver location updated successfully.",
                    status=True,
                    data=serializer.data
                )
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=400
        )


class BankAccountListCreateView(APIView):
    """List and create bank accounts."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List user's bank accounts",
        responses={200: BankAccountSerializer(many=True)}
    )
    def get(self, request):
        """List user's bank accounts."""
        bank_accounts = BankAccount.objects.filter(
            user=request.user, is_active=True
        ).order_by('-created_at')
        
        serializer = BankAccountSerializer(bank_accounts, many=True)
        return Response(
            api_response(
                message="Bank accounts retrieved successfully",
                status=True,
                data=serializer.data
            )
        )

    @swagger_auto_schema(
        operation_description="Add a new bank account",
        request_body=BankAccountCreateSerializer,
        responses={201: BankAccountSerializer()}
    )
    def post(self, request):
        """Create a new bank account."""
        serializer = BankAccountCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            bank_account = serializer.save(user=request.user)
            
            # Verify account with Paystack
            self._verify_bank_account(bank_account)
            
            response_serializer = BankAccountSerializer(bank_account)
            return Response(
                api_response(
                    message="Bank account added successfully",
                    status=True,
                    data=response_serializer.data
                ),
                status=201
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=400
        )

    def _verify_bank_account(self, bank_account):
        """Verify bank account with Paystack."""
        from django.conf import settings
        import requests
        
        try:
            # Verify account number
            response = requests.post(
                'https://api.paystack.co/bank/resolve',
                json={
                    'account_number': bank_account.account_number,
                    'bank_code': bank_account.bank_code
                },
                headers={'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}'}  # noqa
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    bank_account.account_name = data['data']['account_name']
                    bank_account.is_verified = True
                    bank_account.save()
        except Exception:
            pass


class BankAccountDetailView(APIView):
    """Retrieve, update, and delete bank account."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get bank account details",
        responses={200: BankAccountSerializer()}
    )
    def get(self, request, account_id):
        """Get bank account details."""
        try:
            bank_account = BankAccount.objects.get(
                id=account_id, user=request.user
            )
            serializer = BankAccountSerializer(bank_account)
            return Response(
                api_response(
                    message="Bank account details retrieved",
                    status=True,
                    data=serializer.data
                )
            )
        except BankAccount.DoesNotExist:
            return Response(
                api_response(message="Bank account not found", status=False),
                status=404
            )

    @swagger_auto_schema(
        operation_description="Update bank account",
        request_body=BankAccountSerializer,
        responses={200: BankAccountSerializer()}
    )
    def patch(self, request, account_id):
        """Update bank account."""
        try:
            bank_account = BankAccount.objects.get(
                id=account_id, user=request.user
            )
            serializer = BankAccountSerializer(
                bank_account, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(
                    api_response(
                        message="Bank account updated successfully",
                        status=True,
                        data=serializer.data
                    )
                )
            return Response(
                api_response(message=serializer.errors, status=False),
                status=400
            )
        except BankAccount.DoesNotExist:
            return Response(
                api_response(message="Bank account not found", status=False),
                status=404
            )

    @swagger_auto_schema(
        operation_description="Delete bank account"
    )
    def delete(self, request, account_id):
        """Delete bank account."""
        try:
            bank_account = BankAccount.objects.get(
                id=account_id, user=request.user
            )
            bank_account.is_active = False
            bank_account.save()
            return Response(
                api_response(
                    message="Bank account deleted successfully",
                    status=True
                )
            )
        except BankAccount.DoesNotExist:
            return Response(
                api_response(message="Bank account not found", status=False),
                status=404
            )


class WalletDetailView(APIView):
    """Get wallet details and balance."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get wallet details and balance",
        responses={200: WalletSerializer()}
    )
    def get(self, request):
        """Get wallet details."""
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet)
        return Response(
            api_response(
                message="Wallet details retrieved successfully",
                status=True,
                data=serializer.data
            )
        )


class TransactionListView(APIView):
    """List user's transactions."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List user's transactions with filtering",
        manual_parameters=[
            openapi.Parameter(
                'transaction_type',
                openapi.IN_QUERY,
                description="Filter by transaction type",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description="Filter by transaction status",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'start_date',
                openapi.IN_QUERY,
                description="Filter from date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'end_date',
                openapi.IN_QUERY,
                description="Filter to date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={200: TransactionListSerializer(many=True)}
    )
    def get(self, request):
        """List user's transactions with filtering."""
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        transactions = wallet.transactions.all()

        # Apply filters
        transaction_type = request.query_params.get('transaction_type')
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)  # noqa

        status = request.query_params.get('status')
        if status:
            transactions = transactions.filter(status=status)

        start_date = request.query_params.get('start_date')
        if start_date:
            transactions = transactions.filter(created_at__date__gte=start_date)  # noqa

        end_date = request.query_params.get('end_date')
        if end_date:
            transactions = transactions.filter(created_at__date__lte=end_date)

        # Pagination
        paginator = CustomLimitOffsetPagination()
        paginated_transactions = paginator.paginate_queryset(
            transactions, request
        )
        
        serializer = TransactionListSerializer(paginated_transactions, many=True)  # noqa
        return paginator.get_paginated_response(serializer.data)


class WalletTopUpView(APIView):
    """Top up wallet balance."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Top up wallet balance",
        request_body=WalletTopUpSerializer,
        responses={200: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'payment_reference': openapi.Schema(type=openapi.TYPE_STRING),
                'payment_url': openapi.Schema(type=openapi.TYPE_STRING),
                'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
            }
        )}
    )
    def post(self, request):
        """Top up wallet balance."""
        serializer = WalletTopUpSerializer(data=request.data)
        if serializer.is_valid():
            amount = serializer.validated_data['amount']
            payment_method = serializer.validated_data['payment_method']
            
            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            
            # Check transaction limits
            can_transact, message = wallet.can_transact(amount)
            if not can_transact:
                return Response(
                    api_response(message=message, status=False),
                    status=400
                )

            if payment_method == 'paystack':
                return self._initiate_paystack_payment(request, wallet, amount)
            elif payment_method == 'bank_transfer':
                return self._initiate_bank_transfer(request, wallet, amount, serializer.validated_data)  # noqa
        
        return Response(
            api_response(message=serializer.errors, status=False),
            status=400
        )

    def _initiate_paystack_payment(self, request, wallet, amount):
        """Initiate Paystack payment for wallet top-up."""
        from django.conf import settings
        import requests
        import uuid

        # Create transaction record
        transaction = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type='top_up',
            status='pending',
            reference=f"TOPUP_{uuid.uuid4().hex[:8].upper()}",
            description="Wallet top-up via Paystack"
        )

        # Initialize Paystack payment
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        payload = {
            'email': request.user.email,
            'amount': int(amount * 100),  # Paystack expects kobo
            'reference': transaction.reference,
            'callback_url': f"{settings.PAYSTACK_CALLBACK_URL}/wallet/topup/",
            'metadata': {
                'transaction_id': str(transaction.id),
                'wallet_id': str(wallet.id),
                'user_id': str(request.user.id)
            }
        }

        try:
            response = requests.post(
                'https://api.paystack.co/transaction/initialize',
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json().get('data', {})
                return Response(
                    api_response(
                        message="Payment initialized successfully",
                        status=True,
                        data={
                            'payment_reference': data.get('reference'),
                            'payment_url': data.get('authorization_url'),
                            'amount': amount,
                            'transaction_id': str(transaction.id)
                        }
                    )
                )
            else:
                transaction.mark_as_failed("Paystack initialization failed")
                return Response(
                    api_response(
                        message="Failed to initialize payment",
                        status=False
                    ),
                    status=400
                )
        except Exception as e:
            transaction.mark_as_failed(str(e))
            return Response(
                api_response(
                    message="Payment initialization error",
                    status=False
                ),
                status=500
            )

    def _initiate_bank_transfer(self, request, wallet, amount, data):
        """Initiate bank transfer for wallet top-up."""
        bank_account_id = data.get('bank_account_id')
        
        try:
            bank_account = BankAccount.objects.get(
                id=bank_account_id, user=request.user, is_active=True
            )
        except BankAccount.DoesNotExist:
            return Response(
                api_response(
                    message="Invalid bank account",
                    status=False
                ),
                status=400
            )

        # Create transaction record
        transaction = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type='top_up',
            status='pending',
            reference=f"BANK_TRANSFER_{uuid.uuid4().hex[:8].upper()}",  # noqa
            description=f"Bank transfer to {bank_account.get_display_name()}"
        )

        return Response(
            api_response(
                message="Bank transfer initiated",
                status=True,
                data={
                    'transaction_id': str(transaction.id),
                    'amount': amount,
                    'bank_account': BankAccountSerializer(bank_account).data,
                    'reference': transaction.reference
                }
            )
        )


class WalletWithdrawalView(APIView):
    """Withdraw from wallet to bank account."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Withdraw from wallet to bank account",
        request_body=WalletWithdrawalSerializer,
        responses={200: TransactionSerializer()}
    )
    def post(self, request):
        """Withdraw from wallet to bank account."""
        import uuid

        serializer = WalletWithdrawalSerializer(data=request.data)
        if serializer.is_valid():
            amount = serializer.validated_data['amount']
            bank_account_id = serializer.validated_data['bank_account_id']
            description = serializer.validated_data.get('description', 'Wallet withdrawal')  # noqa

            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            
            # Check if user has sufficient balance
            if wallet.balance < amount:
                return Response(
                    api_response(
                        message="Insufficient wallet balance",
                        status=False
                    ),
                    status=400
                )

            try:
                bank_account = BankAccount.objects.get(
                    id=bank_account_id, user=request.user, is_active=True
                )
            except BankAccount.DoesNotExist:
                return Response(
                    api_response(
                        message="Invalid bank account",
                        status=False
                    ),
                    status=400
                )

            # Create withdrawal transaction
            transaction = Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type='withdrawal',
                status='pending',
                reference=f"WITHDRAWAL_{uuid.uuid4().hex[:8].upper()}",
                description=description,
                metadata={
                    'bank_account_id': str(bank_account.id),
                    'bank_name': bank_account.bank_name,
                    'account_number': bank_account.account_number
                }
            )

            # Process withdrawal (in production, this would integrate with Paystack transfer API)  # noqa
            try:
                # For now, we'll simulate the withdrawal process
                # In production, this would call Paystack's transfer API
                transaction.mark_as_processing()
                
                # Simulate processing delay
                import time
                time.sleep(1)
                
                # Mark as completed (in production, this would be done via webhook)  # noqa
                transaction.mark_as_completed()
                wallet.debit(amount, f"Withdrawal to {bank_account.get_display_name()}")  # noqa

                return Response(
                    api_response(
                        message="Withdrawal initiated successfully",
                        status=True,
                        data=TransactionSerializer(transaction).data
                    )
                )
            except Exception as e:
                transaction.mark_as_failed(str(e))
                return Response(
                    api_response(
                        message="Withdrawal failed",
                        status=False
                    ),
                    status=500
                )

        return Response(
            api_response(message=serializer.errors, status=False),
            status=400
        )


class PaystackWebhookView(APIView):
    """Handle Paystack webhooks for wallet transactions."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @swagger_auto_schema(
        operation_description="Handle Paystack webhooks",
        request_body=PaystackWebhookSerializer,
        responses={200: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'status': openapi.Schema(type=openapi.TYPE_STRING)
            }
        )}
    )
    def post(self, request):
        """Handle Paystack webhooks."""
        from django.conf import settings
        import hmac
        import hashlib
        
        # Verify webhook signature
        signature = request.headers.get('X-Paystack-Signature')
        if not signature:
            return Response({'status': 'error'}, status=400)

        # Verify signature
        expected_signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return Response({'status': 'error'}, status=400)

        # Process webhook
        event = request.data.get('event')
        data = request.data.get('data', {})
        reference = data.get('reference')

        if event == 'charge.success' and reference:
            try:
                from django.db import transaction
                with transaction.atomic():
                    # Handle wallet top-up
                    if reference.startswith('TOPUP_'):
                        self._handle_wallet_topup(data)
                    # Handle order payment
                    else:
                        self._handle_order_payment(data)
            except Exception as e:
                from django.utils.log import logger
                logger.error(f"Webhook processing error: {e}")
                return Response({'status': 'error'}, status=500)

        return Response({'status': 'success'})

    def _handle_wallet_topup(self, data):
        """Handle wallet top-up webhook."""
        reference = data.get('reference')
        amount = data.get('amount', 0) / 100  # Convert from kobo to naira
        
        try:
            transaction = Transaction.objects.select_for_update().get(
                reference=reference, status='pending'
            )
            
            if transaction.transaction_type == 'top_up':
                transaction.mark_as_completed()
                transaction.wallet.credit(amount, "Wallet top-up via Paystack")  # noqa
                
                # Send notification
                self._send_topup_notification(transaction)
        except Transaction.DoesNotExist:
            pass

    def _handle_order_payment(self, data):
        """Handle order payment webhook."""
        from products.models import Order
        
        reference = data.get('reference')
        
        try:
            order = Order.objects.select_for_update().get(
                payment_reference=reference
            )
            if order.payment_status != 'paid':
                order.payment_status = 'paid'
                order.status = 'paid'
                order.paid_at = timezone.now()
                order.save()
        except Order.DoesNotExist:
            pass

    def _send_topup_notification(self, transaction):
        """Send top-up notification to user."""
        from users.services import NotificationService
        
        NotificationService.create_notification(
            user=transaction.wallet.user,
            title="Wallet Top-up Successful",
            message=f"Your wallet has been credited with {transaction.amount} NGN",  # noqa
            notification_type='success'
        )


class SecureDocumentListCreateView(APIView):
    """List and create secure documents."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List user's secure documents",
        manual_parameters=[
            openapi.Parameter(
                'document_type',
                openapi.IN_QUERY,
                description="Filter by document type",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'verification_status',
                openapi.IN_QUERY,
                description="Filter by verification status",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={200: SecureDocumentSerializer(many=True)}
    )
    def get(self, request):
        """List user's secure documents."""
        documents = SecureDocument.objects.filter(user=request.user)
        
        # Apply filters
        document_type = request.query_params.get('document_type')
        if document_type:
            documents = documents.filter(document_type=document_type)
        
        verification_status = request.query_params.get('verification_status')
        if verification_status:
            documents = documents.filter(verification_status=verification_status)  # noqa
        
        # Pagination
        paginator = CustomLimitOffsetPagination()
        paginated_documents = paginator.paginate_queryset(documents, request)
        
        serializer = SecureDocumentSerializer(paginated_documents, many=True)
        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_description="Upload a secure document",
        request_body=SecureDocumentCreateSerializer,
        responses={201: SecureDocumentSerializer()}
    )
    def post(self, request):
        """Upload a secure document."""
        serializer = SecureDocumentCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            document = serializer.save()
            
            # Log file upload audit
            FileSecurityAudit.objects.create(
                user=request.user,
                audit_type='upload',
                file_path=document.file_path,
                file_hash=document.file_hash,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key,
                metadata={
                    'document_type': document.document_type,
                    'file_size': document.file_size,
                    'mime_type': document.mime_type
                }
            )
            
            response_serializer = SecureDocumentSerializer(document)
            return Response(
                api_response(
                    message="Document uploaded successfully",
                    status=True,
                    data=response_serializer.data
                ),
                status=201
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=400
        )


class SecureDocumentDetailView(APIView):
    """Retrieve, update, and delete secure document."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get secure document details",
        responses={200: SecureDocumentSerializer()}
    )
    def get(self, request, document_id):
        """Get secure document details."""
        try:
            document = SecureDocument.objects.get(
                id=document_id, user=request.user
            )
            
            # Increment access count
            document.increment_access_count()
            
            # Log file access
            FileSecurityAudit.objects.create(
                user=request.user,
                audit_type='access',
                file_path=document.file_path,
                file_hash=document.file_hash,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key
            )
            
            serializer = SecureDocumentSerializer(document)
            return Response(
                api_response(
                    message="Document details retrieved",
                    status=True,
                    data=serializer.data
                )
            )
        except SecureDocument.DoesNotExist:
            return Response(
                api_response(message="Document not found", status=False),
                status=404
            )

    @swagger_auto_schema(
        operation_description="Delete secure document"
    )
    def delete(self, request, document_id):
        """Delete secure document."""
        try:
            document = SecureDocument.objects.get(
                id=document_id, user=request.user
            )
            
            # Log file deletion
            FileSecurityAudit.objects.create(
                user=request.user,
                audit_type='delete',
                file_path=document.file_path,
                file_hash=document.file_hash,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key
            )
            
            document.delete()
            return Response(
                api_response(
                    message="Document deleted successfully",
                    status=True
                )
            )
        except SecureDocument.DoesNotExist:
            return Response(
                api_response(message="Document not found", status=False),
                status=404
            )


class DocumentVerificationView(APIView):
    """Admin view for document verification."""
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @swagger_auto_schema(
        operation_description="Verify or reject a document",
        request_body=DocumentVerificationSerializer,
        responses={200: SecureDocumentSerializer()}
    )
    def post(self, request, document_id):
        """Verify or reject a document."""
        try:
            document = SecureDocument.objects.get(id=document_id)
            serializer = DocumentVerificationSerializer(data=request.data)
            
            if serializer.is_valid():
                action = serializer.validated_data['action']
                notes = serializer.validated_data.get('notes', '')
                
                if action == 'verify':
                    document.mark_as_verified(request.user, notes)
                    message = "Document verified successfully"
                else:
                    document.mark_as_rejected(notes)
                    message = "Document rejected"
                
                # Log verification action
                DocumentVerificationLog.objects.create(
                    document=document,
                    action=action,
                    performed_by=request.user,
                    notes=notes,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                response_serializer = SecureDocumentSerializer(document)
                return Response(
                    api_response(
                        message=message,
                        status=True,
                        data=response_serializer.data
                    )
                )
            
            return Response(
                api_response(message=serializer.errors, status=False),
                status=400
            )
        except SecureDocument.DoesNotExist:
            return Response(
                api_response(message="Document not found", status=False),
                status=404
            )


class DocumentVerificationLogView(APIView):
    """View for document verification logs."""
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @swagger_auto_schema(
        operation_description="List document verification logs",
        manual_parameters=[
            openapi.Parameter(
                'document_id',
                openapi.IN_QUERY,
                description="Filter by document ID",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'action',
                openapi.IN_QUERY,
                description="Filter by action",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={200: DocumentVerificationLogSerializer(many=True)}
    )
    def get(self, request):
        """List document verification logs."""
        logs = DocumentVerificationLog.objects.all()
        
        # Apply filters
        document_id = request.query_params.get('document_id')
        if document_id:
            logs = logs.filter(document_id=document_id)
        
        action = request.query_params.get('action')
        if action:
            logs = logs.filter(action=action)
        
        # Pagination
        paginator = CustomLimitOffsetPagination()
        paginated_logs = paginator.paginate_queryset(logs, request)
        
        serializer = DocumentVerificationLogSerializer(paginated_logs, many=True)  # noqa
        return paginator.get_paginated_response(serializer.data)


class FileSecurityAuditView(APIView):
    """View for file security audit logs."""
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @swagger_auto_schema(
        operation_description="List file security audit logs",
        manual_parameters=[
            openapi.Parameter(
                'audit_type',
                openapi.IN_QUERY,
                description="Filter by audit type",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description="Filter by user ID",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'success',
                openapi.IN_QUERY,
                description="Filter by success status",
                type=openapi.TYPE_BOOLEAN,
                required=False
            )
        ],
        responses={200: FileSecurityAuditSerializer(many=True)}
    )
    def get(self, request):
        """List file security audit logs."""
        audits = FileSecurityAudit.objects.all()
        
        # Apply filters
        audit_type = request.query_params.get('audit_type')
        if audit_type:
            audits = audits.filter(audit_type=audit_type)
        
        user_id = request.query_params.get('user_id')
        if user_id:
            audits = audits.filter(user_id=user_id)
        
        success = request.query_params.get('success')
        if success is not None:
            audits = audits.filter(success=success.lower() == 'true')
        
        # Pagination
        paginator = CustomLimitOffsetPagination()
        paginated_audits = paginator.paginate_queryset(audits, request)
        
        serializer = FileSecurityAuditSerializer(paginated_audits, many=True)
        return paginator.get_paginated_response(serializer.data)


class FileUploadView(APIView):
    """General file upload view."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Upload a file securely",
        request_body=FileUploadSerializer,
        responses={201: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'file_path': openapi.Schema(type=openapi.TYPE_STRING),
                'file_hash': openapi.Schema(type=openapi.TYPE_STRING),
                'secure_url': openapi.Schema(type=openapi.TYPE_STRING),
            }
        )}
    )
    def post(self, request):
        """Upload a file securely."""
        serializer = FileUploadSerializer(data=request.data)
        if serializer.is_valid():
            file = serializer.validated_data['file']
            file_type = serializer.validated_data['file_type']
            category = serializer.validated_data.get('category', 'general')
            
            try:
                from ogamechanic.modules.file_storage_service import FileStorageService  # noqa
                file_metadata = FileStorageService.save_file(
                    file, file_type, str(request.user.id), category
                )
                
                # Log file upload
                FileSecurityAudit.objects.create(
                    user=request.user,
                    audit_type='upload',
                    file_path=file_metadata['file_path'],
                    file_hash=file_metadata['file_hash'],
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    session_id=request.session.session_key,
                    metadata={
                        'file_type': file_type,
                        'category': category,
                        'file_size': file_metadata['file_size'],
                        'mime_type': file_metadata['mime_type']
                    }
                )
                
                return Response(
                    api_response(
                        message="File uploaded successfully",
                        status=True,
                        data={
                            'file_path': file_metadata['file_path'],
                            'file_hash': file_metadata['file_hash'],
                            'secure_url': f"/media/{file_metadata['file_path']}"  # noqa
                        }
                    ),
                    status=201
                )
            except Exception as e:
                return Response(
                    api_response(
                        message=f"File upload failed: {str(e)}",
                        status=False
                    ),
                    status=500
                )
        
        return Response(
            api_response(message=serializer.errors, status=False),
            status=400
        )


class CACUploadView(APIView):
    """Specialized view for CAC document uploads."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Upload CAC document for merchant verification",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['file'],
            properties={
                'file': openapi.Schema(type=openapi.TYPE_FILE),
            }
        ),
        responses={201: SecureDocumentSerializer()}
    )
    def post(self, request):
        """Upload CAC document."""
        if 'file' not in request.FILES:
            return Response(
                api_response(message="No file provided", status=False),
                status=400
            )
        
        file = request.FILES['file']
        
        try:
            from ogamechanic.modules.file_storage_service import CACDocumentService  # noqa
            file_metadata = CACDocumentService.process_cac_document(file, str(request.user.id))  # noqa
            
            # Create secure document
            document = SecureDocument.objects.create(
                user=request.user,
                document_type='cac_document',
                original_filename=file_metadata['original_filename'],
                secure_filename=file_metadata['secure_filename'],
                file_path=file_metadata['file_path'],
                file_size=file_metadata['file_size'],
                file_hash=file_metadata['file_hash'],
                mime_type=file_metadata['mime_type'],
                extracted_info=file_metadata.get('cac_info', {})
            )
            
            # Log document upload
            DocumentVerificationLog.objects.create(
                document=document,
                action='upload',
                performed_by=request.user,
                notes="CAC document uploaded for merchant verification",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            serializer = SecureDocumentSerializer(document)
            return Response(
                api_response(
                    message="CAC document uploaded successfully",
                    status=True,
                    data=serializer.data
                ),
                status=201
            )
        except Exception as e:
            return Response(
                api_response(
                    message=f"CAC document upload failed: {str(e)}",
                    status=False
                ),
                status=500
            )


class RoleManagementView(APIView):
    """
    View for managing user roles and active role switching.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_description="Switch active role or manage user roles",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'active_role_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="ID of the role to set as active"
                ),
                'add_roles': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                    description="Role IDs to add to user"
                ),
                'remove_roles': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                    description="Role IDs to remove from user"
                ),
            }
        ),
        responses={
            200: openapi.Response(
                description="Role management successful",
                schema=UserSerializer()
            ),
            400: "Bad Request",
            401: "Unauthorized",
            429: "Too Many Requests"
        }
    )
    def put(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        active_role_id = data.get('active_role_id')
        add_roles = data.get('add_roles', [])
        remove_roles = data.get('remove_roles', [])

        # Validate active role
        if active_role_id:
            try:
                new_active_role = Role.objects.get(id=active_role_id)
                if new_active_role not in user.roles.all():
                    return Response(
                        api_response(
                            message=(
                                "You can only set a role as active if you have "  # noqa
                                "that role."
                            ),
                            status=False
                        ),
                        status=http_status.HTTP_400_BAD_REQUEST
                    )
                user.active_role = new_active_role
            except Role.DoesNotExist:
                return Response(
                    api_response(
                        message="Invalid role ID.",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

        # Handle role additions
        if add_roles:
            try:
                roles_to_add = Role.objects.filter(id__in=add_roles)
                user.roles.add(*roles_to_add)
            except Exception as e:
                return Response(
                    api_response(
                        message=f"Error adding roles: {str(e)}",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

        # Handle role removals
        if remove_roles:
            try:
                roles_to_remove = Role.objects.filter(id__in=remove_roles)
                # Check if trying to remove active role
                if user.active_role in roles_to_remove:
                    return Response(
                        api_response(
                            message=(
                                "You cannot remove your active role. "
                                "Please set a different active role first."
                            ),
                            status=False
                        ),
                        status=http_status.HTTP_400_BAD_REQUEST
                    )
                user.roles.remove(*roles_to_remove)
            except Exception as e:
                return Response(
                    api_response(
                        message=f"Error removing roles: {str(e)}",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

        user.save()
        
        return Response(
            api_response(
                message="Role management successful",
                status=True,
                data=UserSerializer(user).data
            )
        )

    @swagger_auto_schema(
        operation_description="Get user's current roles and active role",
        responses={
            200: openapi.Response(
                description="User roles retrieved successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'roles': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                                    'name': openapi.Schema(type=openapi.TYPE_STRING), # noqa
                                    'description': openapi.Schema(type=openapi.TYPE_STRING), # noqa
                                }
                            )
                        ),
                        'active_role': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                                'name': openapi.Schema(type=openapi.TYPE_STRING), # noqa
                                'description': openapi.Schema(type=openapi.TYPE_STRING), # noqa
                            }
                        ),
                    }
                )
            ),
            401: "Unauthorized"
        }
    )
    def get(self, request):
        user = request.user
        roles_data = RoleSerializer(user.roles.all(), many=True).data
        active_role_data = RoleSerializer(user.active_role).data if user.active_role else None # noqa
        
        return Response(
            api_response(
                message="User roles retrieved successfully",
                status=True,
                data={
                    'roles': roles_data,
                    'active_role': active_role_data
                }
            )
        )


class RoleListView(APIView):
    """
    API to retrieve all available user roles for registration and display.
    
    This endpoint provides a list of all roles that users can select during
    the registration process. Essential for populating role selection dropdowns
    in the frontend.
    """
    permission_classes = [AllowAny]  # Allow public access for registration

    @swagger_auto_schema(
        operation_summary="Get Available User Roles",
        operation_description="""
        **Retrieve all available user roles for registration**
        
        **Purpose:**
        - Provides list of all user roles available in the system
        - Used by frontend for role selection dropdowns
        - Essential for step 1 of registration process
        
        **Available Roles:**
        - **primary_user**: Basic users who may have cars (formerly customer)
        - **driver**: Professional drivers providing ride services
        - **rider**: Users who need ride services (sub-role of driver)
        - **merchant**: Business users selling products/services
        - **mechanic**: Service providers offering mechanical services
        - **developer**: System administrators and developers
        
        **Usage in Registration:**
        1. Frontend calls this endpoint to get available roles
        2. User selects desired role from the list
        3. Role ID is used in step 1 of registration process
        4. Role determines subsequent registration steps and requirements
        
        **Response Format:**
        Returns an array of role objects, each containing:
        - **id**: Unique role identifier (use this in registration)
        - **name**: Role system name (e.g., 'primary_user', 'driver')
        - **description**: Human-readable role description
        
        **Frontend Implementation Notes:**
        - Cache this data as roles rarely change
        - Use role.id for API calls, role.description for UI display
        - Filter roles based on your app's requirements if needed
        - Consider role-specific UI flows based on selected role
        """,
        responses={
            200: openapi.Response(
                description="Roles retrieved successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN,
                            example=True,
                            description="Success status"
                        ),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Roles retrieved successfully",
                            description="Success message"
                        ),
                        'data': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Array of available roles",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        example=1,
                                        description="Unique role identifier"
                                    ),
                                    'name': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="primary_user",
                                        description="Role system name"
                                    ),
                                    'description': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="Primary User",
                                        description="Human-readable role description"  # noqa
                                    )
                                },
                                required=['id', 'name', 'description']
                            )
                        )
                    },
                    required=['status', 'message', 'data']
                ),
                examples={
                    'application/json': {
                        'status': True,
                        'message': 'Roles retrieved successfully',
                        'data': [
                            {'id': 1, 'name': 'primary_user', 'description': 'Primary User'},  # noqa
                            {'id': 2, 'name': 'driver', 'description': 'Driver'},  # noqa
                            {'id': 3, 'name': 'rider', 'description': 'Rider'},  # noqa
                            {'id': 4, 'name': 'merchant', 'description': 'Merchant'},  # noqa
                            {'id': 5, 'name': 'mechanic', 'description': 'Mechanic'}  # noqa
                        ]
                    }
                }
            ),
            500: openapi.Response(
                description="Internal server error",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),  # noqa
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="An error occurred while retrieving roles"
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """Get all available roles."""
        try:
            roles = Role.objects.all().order_by('id')
            roles_data = RoleSerializer(roles, many=True).data
            
            return Response(
                api_response(
                    message="Roles retrieved successfully",
                    status=True,
                    data=roles_data
                )
            )
        except Exception as e:
            return Response(
                api_response(
                    message=f"Error retrieving roles: {str(e)}",
                    status=False
                ),
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StepByStepRegistrationView(APIView):
    """
    Comprehensive step-by-step user registration process.
    
    This API handles user registration through 5 distinct steps:
    1. Role selection (primary_user, driver, merchant, mechanic)
    2. User information collection (role-specific)
    3. Email verification with 6-digit code
    4. Role-specific details collection
    5. Password setup and account creation
    
    The process uses Django sessions to maintain state between steps.
    Each step validates previous steps and guides users to the next step.

    **Image/File Upload Format:**
    For any step that requires uploading images or files (such as license images, selfies, CAC documents, vehicle photos, etc.), # noqa
    you MUST send the request as `multipart/form-data` (not JSON). 
    All image and file fields should be sent as file uploads in the form-data body, 
    while other fields (strings, numbers, etc.) can be sent as regular form fields.

    - For steps that do NOT require file/image uploads, you may use JSON.
    - For steps that require file/image uploads (e.g., step 4 for driver, merchant, mechanic), use `multipart/form-data` and include files in the request.
    - In Swagger UI, use the "Try it out" button and select "multipart/form-data" for these steps.

    Example for step 4 (driver):
      - Content-Type: multipart/form-data
      - Fields:
        - full_name: John Driver
        - license_front_image: (file upload)
        - license_back_image: (file upload)
        - vehicle_photo_front: (file upload)
        - ... (other fields as text or file as appropriate)
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    parser_classes = [
        parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @swagger_auto_schema(
        operation_summary="Step-by-Step User Registration",
        operation_description="""
        Multi-step registration process for different user roles.

        **Steps Overview**
        1. Role selection (`primary_user`, `driver`, `merchant`, `mechanic`)
        2. User information collection (role-specific)
        3. Email verification with 6-digit code
        4. Role-specific details (may include file uploads)
        5. Password setup and account creation

        **Important Notes**
        - For steps **without files**: send `application/json`
        - For steps **with files (e.g., selfies, license, CAC docs)**: send `multipart/form-data` # noqa
        - Always include:  
        - `requestType`: must be `"inbound"`  
        - `data`: step-specific payload
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Request type identifier (must be 'inbound')",
                    example="inbound"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Step-specific data payload",
                    example={
                        "step_1": {"role_id": 1}, 
                        "step_2_primary_user": { 
                            "first_name": "John", "last_name": "Doe",
                            "email": "john@example.com", "phone_number":
                            "08012345678"
                        },
                        "step_2_driver_sub_role": {
                             "sub_role": "driver"
                        },
                        "step_2_driver_info": {"email": "driver@example.com", "phone_number": "08012345678", "city": "Lagos" }, # noqa
                        "step_2_merchant_mechanic": {"first_name": "Jane", "last_name": "Smith", "email": "jane@example.com", "phone_number": "08087654321" },  # noqa
                        "step_3": {
                            "email": "john@example.com", 
                            "verification_code": "123456" },  # noqa
                        "step_4_primary_user": {
                            "has_car": True, "car_make": "Toyota", 
                            "car_model": "Corolla", "car_year": 2020, 
                            "license_plate": "ABC123"
                        }, 
                        # For step_4_driver, step_4_merchant, step_4_mechanic: # All image/file fields must be sent as file uploads in multipart/form-data # noqa 
                        "step_4_driver": {
                            "full_name": "John Driver", 
                            "date_of_birth": "1990-01-01", "gender": "male", "address": "123 Street", "location": "Lagos", "license_number": "LIC123", "license_issue_date": "2015-01-01", "license_expiry_date": "2025-01-01", "license_front_image": "(file upload)", "license_back_image": "(file upload)", "vin": "VIN123", "vehicle_name": "Toyota", "plate_number": "ABC123", "vehicle_model": "Corolla", "vehicle_color": "Red", "vehicle_photo_front": "(file upload)", "vehicle_photo_back": "(file upload)", "vehicle_photo_right": "(file upload)", "vehicle_photo_left": "(file upload)", "bank_name": "GTBank", "account_number": "0123456789" },  # noqa
                        "step_4_merchant": { "location": "Lagos", "lga": "Ikeja", "cac_number": "CAC123", "cac_document": "(file upload)", "selfie": "(file upload)" }, "step_4_mechanic": { "location": "Lagos", "lga": "Ikeja", "cac_number": "CAC123", "cac_document": "(file upload)", "selfie": "(file upload)", "vehicle_make_ids": [1, 2], "expertise_details": [ { "vehicle_make_id": 1, "years_of_experience": 5, "certification_level": "advanced" }, { "vehicle_make_id": 2, "years_of_experience": 2, "certification_level": "basic" } ] },  # noqa
                        "step_5": { "password": "strongpassword", "confirm_password": "strongpassword" }  # noqa
                    }
                )
            },
            required=['requestType', 'data']
        ),
        responses={
            200: openapi.Response(
                description="Step completed successfully"
            ),
            201: openapi.Response(
                description="Registration completed successfully (step 5)"
            ),
            400: openapi.Response(
                description="Invalid request data or step requirements not met"
            ),
            429: openapi.Response(description="Too many requests - rate limited")  # noqa
        }
    )
    def post(self, request, step):
        """Handle different steps of registration"""
        
        if step == 1:
            return self.step_one_role_selection(request)
        elif step == 2:
            return self.step_two_user_info(request)
        elif step == 3:
            return self.step_three_email_verification(request)
        elif step == 4:
            return self.step_four_details(request)
        elif step == 5:
            return self.step_five_password_setup(request)
        else:
            logger.critical(
                f"Stepbystep registration post: {traceback.format_exc()}")

            return Response(
                api_response(
                    message="Invalid step number",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

    def step_one_role_selection(self, request):
        """Step 1: Role selection"""
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = StepOneRoleSelectionSerializer(data=data)
        if serializer.is_valid():
            role = serializer.validated_data['role_id']
            
            # Store role selection in session
            request.session['registration_role_id'] = role.id
            request.session['registration_step'] = 1
            
            return Response(
                api_response(
                    message="Role selected successfully",
                    status=True,
                    data={
                        'role_id': role.id,
                        'role_name': role.name,
                        'next_step': 2
                    }
                )
            )
        
        return Response(
            api_response(
                message="Invalid role selection",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def step_two_user_info(self, request):
        """Step 2: User information based on role"""
        role_id = request.session.get('registration_role_id')
        if not role_id:
            return Response(
                api_response(
                    message="Please select a role first",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            return Response(
                api_response(
                    message="Invalid role",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        # Handle driver's special case - sub-role selection first
        if role.name == 'driver':
            # Check if this is sub-role selection or driver info
            if 'sub_role' in data:
                return self.step_two_driver_sub_role(request, data)
            elif 'email' in data:
                return self.step_two_driver_info(request, data)
            else:
                return Response(
                    api_response(
                        message="Please select driver or rider first",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

        # Choose serializer based on role
        if role.name == 'primary_user':
            serializer = StepTwoPrimaryUserInfoSerializer(data=data)
        elif role.name == 'mechanic':
            serializer = StepTwoMechanicInfoSerializer(data=data)
        elif role.name == 'merchant':
            serializer = StepTwoMerchantInfoSerializer(data=data)
        else:
            return Response(
                api_response(
                    message="Invalid role for registration",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        if serializer.is_valid():
            # Store user info in session
            request.session['registration_user_info'] = serializer.validated_data  # noqa
            request.session['registration_step'] = 2
            
            # Send verification email
            email = serializer.validated_data['email']
            verification_code = self.generate_verification_code()
            request.session['verification_code'] = verification_code
            request.session['verification_email'] = email
            
            # Send email
            self.send_verification_email(email, verification_code)
            
            return Response(
                api_response(
                    message="User info saved. Verification code sent to email.",  # noqa
                    status=True,
                    data={'next_step': 3}
                )
            )
        
        logger.critical(
            f"step_two_user_info: {serializer.errors}\n {traceback.format_exc()}") # noqa
        return Response(
            api_response(
                message="Invalid user information",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def step_two_driver_sub_role(self, request, data):
        """Step 2a: Driver sub-role selection"""
        serializer = StepTwoDriverSubRoleSerializer(data=data)
        if serializer.is_valid():
            request.session['registration_driver_sub_role'] = (
                serializer.validated_data['sub_role']
            )
            return Response(
                api_response(
                    message="Sub-role selected. Please provide information.",
                    status=True,
                    data={'next_step': '2b'}
                )
            )
        return Response(
            api_response(
                message="Invalid sub-role selection",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def step_two_driver_info(self, request, data):
        """Step 2b: Driver information"""
        # Check if sub-role was selected
        driver_sub_role = request.session.get('registration_driver_sub_role')
        if not driver_sub_role:
            return Response(
                api_response(
                    message="Please select driver or rider sub-role first",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = StepTwoDriverInfoSerializer(data=data)
        if serializer.is_valid():
            # Store driver info and sub-role
            user_info = serializer.validated_data
            user_info['driver_sub_role'] = driver_sub_role
            request.session['registration_user_info'] = user_info
            request.session['registration_step'] = 2
            
            # Send verification email
            email = serializer.validated_data['email']
            verification_code = self.generate_verification_code()
            request.session['verification_code'] = verification_code
            request.session['verification_email'] = email
            
            # Send email
            self.send_verification_email(email, verification_code)
            
            return Response(
                api_response(
                    message="Driver info saved. Verification code sent.",
                    status=True,
                    data={'next_step': 3}
                )
            )
        
        return Response(
            api_response(
                message="Invalid driver information",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def step_three_email_verification(self, request):
        """Step 3: Email verification"""
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = StepThreeEmailVerificationSerializer(data=data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['verification_code']
            
            # Check if code matches
            stored_code = request.session.get('verification_code')
            stored_email = request.session.get('verification_email')
            
            if not stored_code or not stored_email:
                return Response(
                    api_response(
                        message="Verification session expired. Please start over.",  # noqa
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )
            
            if email != stored_email:
                return Response(
                    api_response(
                        message="Email does not match verification session",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )
            
            if code != stored_code:
                return Response(
                    api_response(
                        message="Invalid verification code",
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )
            
            # Mark email as verified
            request.session['email_verified'] = True
            request.session['registration_step'] = 3
            
            # Determine next step based on role
            role_id = request.session.get('registration_role_id')
            role = Role.objects.get(id=role_id)
            
            next_step = 4 if role.name == 'primary_user' else 4
            
            return Response(
                api_response(
                    message="Email verified successfully",
                    status=True,
                    data={'next_step': next_step}
                )
            )
        
        return Response(
            api_response(
                message="Invalid verification data",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def step_four_details(self, request):
        """Step 4: Role-specific details

        **IMPORTANT:** If this step requires uploading images or files (e.g., license images, selfies, CAC documents, vehicle photos), # noqa
        you MUST send the request as `multipart/form-data` and include the files as file uploads. 
        Do NOT send images/files as base64 or JSON fields.
        """
        role_id = request.session.get('registration_role_id')
        if not role_id:
            return Response(
                api_response(
                    message="Please select a role first",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            return Response(
                api_response(
                    message="Invalid role",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        # Choose serializer and message based on role
        if role.name == 'primary_user':
            serializer = StepFourPrimaryUserCarDetailsSerializer(data=data)
            success_message = "Car details saved"
            session_key = 'registration_car_details'
        elif role.name == 'driver':
            serializer = StepFourDriverDetailsSerializer(data=data)
            success_message = "Driver details saved"
            session_key = 'registration_driver_details'
        elif role.name == 'merchant':
            serializer = StepFourMerchantDetailsSerializer(data=data)
            success_message = "Merchant details saved"
            session_key = 'registration_merchant_details'
        elif role.name == 'mechanic':
            serializer = StepFourMechanicDetailsSerializer(data=data)
            success_message = "Mechanic details saved"
            session_key = 'registration_mechanic_details'
        else:
            return Response(
                api_response(
                    message="Invalid role for this step",
                    status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        if serializer.is_valid():
            # Store details in session
            details = dict(serializer.validated_data)

            # Persist uploaded files and store only file paths in session to avoid pickling errors # noqa
            def save_file(value):
                try:
                    if not value:
                        return value
                    # Save using original name; storage will handle collisions
                    path = default_storage.save(
                        getattr(value, 'name', 'upload'), value)
                    return path
                except Exception:
                    return value

            if role.name == 'driver':
                file_keys = [
                    'license_front_image', 'license_back_image',
                    'vehicle_photo_front', 'vehicle_photo_back',
                    'vehicle_photo_right', 'vehicle_photo_left',
                ]
            elif role.name == 'merchant':
                file_keys = ['cac_document', 'selfie']
            elif role.name == 'mechanic':
                file_keys = ['cac_document', 'selfie']
            else:
                file_keys = []

            for k in file_keys:
                if k in details:
                    details[k] = save_file(details.get(k))

            request.session[session_key] = details
            request.session['registration_step'] = 4
            
            return Response(
                api_response(
                    message=success_message,
                    status=True,
                    data={'next_step': 5}
                )
            )
        logger.critical(
            f"Step four: {serializer.errors}\n {traceback.format_exc()}")
        
        return Response(
            api_response(
                message="Invalid details",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def step_five_password_setup(self, request):
        """Step 5: Password setup and account creation"""
        # Check if all previous steps are complete
        required_data = [
            'registration_role_id',
            'registration_user_info',
            'email_verified'
        ]
        
        for key in required_data:
            if not request.session.get(key):
                return Response(
                    api_response(
                        message="Previous steps not completed. Please start over.",  # noqa
                        status=False
                    ),
                    status=http_status.HTTP_400_BAD_REQUEST
                )

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = StepFivePasswordSerializer(data=data)
        if serializer.is_valid():
            # Store password in session for account creation
            request.session['password'] = serializer.validated_data['password']
            request.session['registration_step'] = 5
            
            try:
                # Create user account
                user = self.create_user_account(request.session)
                
                # Log the user in after registration
                # from django.contrib.auth import login
                # login(request, user)

                # Generate JWT tokens
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                refresh_token = str(refresh)
                
                # Clear session data
                self.clear_registration_session(request)
                
                return Response(
                    api_response(
                        message="Account created successfully! You are now logged in.",  # noqa
                        status=True,
                        data={
                            'access': access_token,
                            'refresh': refresh_token,
                            'user_id': str(user.id),
                            'email': user.email,
                            'role': user.active_role.name
                        }
                    ),
                    status=http_status.HTTP_201_CREATED
                )
                
            except Exception as e:
                return Response(
                    api_response(
                        message=f"Error creating account: {str(e)}",
                        status=False
                    ),
                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        logger.critical(
            f"step_five_password_setup: {serializer.errors}\n {traceback.format_exc()}") # noqa
        return Response(
            api_response(
                message="Invalid password data",
                status=False,
                errors=serializer.errors
            ),
            status=http_status.HTTP_400_BAD_REQUEST
        )

    def generate_verification_code(self):
        """Generate a 6-digit verification code"""
        import random
        return str(random.randint(100000, 999999))

    def send_verification_email(self, email, code):
        """Send verification email with code using Celery background task"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from .tasks import send_step_by_step_verification_email
            # Send verification email as background task
            send_step_by_step_verification_email.delay(email, code)
            logger.info(f"Step-by-step verification email task queued for {email}: {code}")  # noqa
        except Exception as e:
            logger.error(f"Failed to queue verification email task: {e}")
            # Fallback to direct sending if Celery is not available
            logger.error(f"Failed to queue verification email task: {e}")

    def create_user_account(self, session_data):
        """Create the user account with all collected data"""
        role_id = session_data['registration_role_id']
        user_info = session_data['registration_user_info']
        password = session_data.get('password')
    
        if not password:
            raise ValueError("Password is required for account creation")
        
        # Get role to determine account creation logic
        role = Role.objects.get(id=role_id)
        
        # Check if user with this email already exists
        email = user_info['email'].lower().strip()
        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            # Check if user already has this role
            if existing_user.roles.filter(id=role_id).exists():
                raise ValueError(f"User with email {email} already has the {role.name} role")   # noqa

            # User exists but doesn't have this role - add the role
            user = existing_user
            user.roles.add(role)

            # Update user data if needed (merge information)
            if role.name != 'driver' and (user_info.get('first_name') or user_info.get('last_name')):   # noqa
                if user_info.get('first_name') and not user.first_name:
                    user.first_name = user_info['first_name']
                if user_info.get('last_name') and not user.last_name:
                    user.last_name = user_info['last_name']
                user.save()

            # Update phone number if not set
            if user_info.get('phone_number') and not user.phone_number:
                user.phone_number = user_info['phone_number']
                user.save()

            # Add car details if primary user has a car and user doesn't have car details   # noqa
            if role.name == 'primary_user':
                car_details = session_data.get('registration_car_details', {})
                if car_details.get('has_car') and not user.car_make:
                    user.car_make = car_details.get('car_make', '')
                    user.car_model = car_details.get('car_model', '')
                    user.car_year = car_details.get('car_year')
                    user.license_plate = car_details.get('license_plate', '')
                    user.save()
        else:
            # Create new user
            # Prepare basic user data
            if role.name == 'driver':
                # For drivers, we only have email, phone, city from step 2
                user_data = {
                    'email': user_info['email'],
                    'phone_number': user_info['phone_number'],
                    'is_active': True,
                    'is_verified': True
                }
            else:
                # For primary_user, merchant, mechanic - we have first_name, last_name  # noqa
                user_data = {
                    'email': user_info['email'],
                    'first_name': user_info.get('first_name', ''),
                    'last_name': user_info.get('last_name', ''),
                    'phone_number': user_info['phone_number'],
                    'is_active': True,
                    'is_verified': True
                }
            
            # Add car details if primary user has a car
            if role.name == 'primary_user':
                car_details = session_data.get('registration_car_details', {})
                if car_details.get('has_car'):
                    user_data.update({
                        'car_make': car_details.get('car_make', ''),
                        'car_model': car_details.get('car_model', ''),
                        'car_year': car_details.get('car_year'),
                        'license_plate': car_details.get('license_plate', '')
                    })
            
            # Create user
            user = User.objects.create_user(
                password=password,
                **user_data
            )
        
        # Assign role (only for new users, existing users already had role added above)   # noqa
        if not existing_user:
            if role.name == 'driver':
                # For drivers, determine actual role based on sub_role
                driver_sub_role = user_info.get('driver_sub_role', 'driver')
                if driver_sub_role == 'rider':
                    rider_role, _ = Role.objects.get_or_create(
                        name=Role.RIDER,
                        defaults={'description': 'Rider'}
                    )
                    user.roles.add(rider_role)
                    user.active_role = rider_role
                else:
                    user.roles.add(role)
                    user.active_role = role
            else:
                user.roles.add(role)
                user.active_role = role
            
            user.save()
        else:
            # For existing users, set the new role as active role
            user.active_role = role
            user.save()
        
        # Create profile based on role
        self.create_user_profile(user, session_data, role)
        
        return user

    def create_user_profile(self, user, session_data, role):
        """Create role-specific profile"""
        if role.name == 'driver' or (role.name == 'driver' and session_data['registration_user_info'].get('driver_sub_role') == 'driver'):  # noqa
            # Create driver profile
            driver_details = session_data.get('registration_driver_details', {})  # noqa
            user_info = session_data['registration_user_info']
            
            DriverProfile.objects.create(
                user=user,
                full_name=driver_details.get('full_name', ''),
                phone_number=user_info.get('phone_number', ''),
                city=user_info.get('city', ''),
                date_of_birth=driver_details.get('date_of_birth'),
                gender=driver_details.get('gender'),
                address=driver_details.get('address', ''),
                location=driver_details.get('location', ''),
                license_number=driver_details.get('license_number', ''),
                license_issue_date=driver_details.get('license_issue_date'),
                license_expiry_date=driver_details.get('license_expiry_date'),
                license_front_image=driver_details.get('license_front_image'),
                license_back_image=driver_details.get('license_back_image'),
                vin=driver_details.get('vin', ''),
                vehicle_name=driver_details.get('vehicle_name', ''),
                plate_number=driver_details.get('plate_number', ''),
                vehicle_model=driver_details.get('vehicle_model', ''),
                vehicle_color=driver_details.get('vehicle_color', ''),
                vehicle_photo_front=driver_details.get('vehicle_photo_front'),
                vehicle_photo_back=driver_details.get('vehicle_photo_back'),
                vehicle_photo_right=driver_details.get('vehicle_photo_right'),
                vehicle_photo_left=driver_details.get('vehicle_photo_left'),
                bank_name=driver_details.get('bank_name', ''),
                account_number=driver_details.get('account_number', ''),
            )
        
        elif role.name == 'merchant':
            # Create merchant profile
            merchant_details = session_data.get('registration_merchant_details', {})  # noqa
            
            MerchantProfile.objects.create(
                user=user,
                location=merchant_details.get('location', ''),
                lga=merchant_details.get('lga', ''),
                cac_number=merchant_details.get('cac_number', ''),
                cac_document=merchant_details.get('cac_document'),
                selfie=merchant_details.get('selfie'),
                business_address=merchant_details.get('location', ''),
            )
        
        elif role.name == 'mechanic':
            # Create mechanic profile
            mechanic_details = session_data.get('registration_mechanic_details', {})  # noqa
            
            mechanic_profile = MechanicProfile.objects.create(
                user=user,
                location=mechanic_details.get('location', ''),
                lga=mechanic_details.get('lga', ''),
                cac_number=mechanic_details.get('cac_number', ''),
                cac_document=mechanic_details.get('cac_document'),
                selfie=mechanic_details.get('selfie'),
            )
            
            # Create vehicle expertise records
            self.create_mechanic_vehicle_expertise(
                mechanic_profile, mechanic_details)

    def create_mechanic_vehicle_expertise(self, mechanic_profile, mechanic_details):  # noqa
        """Create vehicle expertise records for mechanic"""
        from mechanics.models import VehicleMake, MechanicVehicleExpertise
        
        vehicle_make_ids = mechanic_details.get('vehicle_make_ids', [])
        expertise_details = mechanic_details.get('expertise_details', [])
        
        # Create a mapping of vehicle_make_id to expertise details
        expertise_map = {}
        for detail in expertise_details:
            vehicle_make_id = detail.get('vehicle_make_id')
            if vehicle_make_id:
                expertise_map[vehicle_make_id] = detail
        
        # Create expertise records for each vehicle make
        for vehicle_make_id in vehicle_make_ids:
            try:
                vehicle_make = VehicleMake.objects.get(id=vehicle_make_id)
                
                # Get expertise details for this vehicle make
                detail = expertise_map.get(vehicle_make_id, {})
                
                MechanicVehicleExpertise.objects.create(
                    mechanic=mechanic_profile,
                    vehicle_make=vehicle_make,
                    years_of_experience=detail.get('years_of_experience', 0),
                    certification_level=detail.get(
                        'certification_level', 'basic')
                )
            except VehicleMake.DoesNotExist as e:
                import logging
                from rest_framework.exceptions import ValidationError

                logger = logging.getLogger(__name__)
                logger.error(f"VehicleMake with id {vehicle_make_id} does not exist: {e}")  # noqa

                raise ValidationError(
                    {"vehicle_make_id": f"Vehicle make with id {vehicle_make_id} does not exist."}  # noqa
                )

    def clear_registration_session(self, request):
        """Clear all registration session data"""
        keys_to_clear = [
            'registration_role_id',
            'registration_user_info',
            'registration_car_details',
            'registration_driver_details',
            'registration_merchant_details',
            'registration_mechanic_details',
            'registration_driver_sub_role',
            'verification_code',
            'verification_email',
            'email_verified',
            'registration_step',
            'password'
        ]
        
        for key in keys_to_clear:
            if key in request.session:
                del request.session[key]


class PrimaryUserProfileView(APIView):
    """
    API view for managing primary user profile details.
    
    This view handles:
    - GET: Retrieve primary user profile details
    - PUT: Update primary user profile details
    - PATCH: Partial update of primary user profile details
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_summary="Get Primary User Profile",
        operation_description="Retrieve the current user's primary user profile details",  # noqa
        responses={
            200: openapi.Response(
                description="Profile details retrieved successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'user_id': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'first_name': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'last_name': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'email': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'phone_number': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'car_make': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'car_model': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'car_year': openapi.Schema(type=openapi.TYPE_INTEGER),  # noqa
                                'license_plate': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'date_joined': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'is_verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),  # noqa
                            }
                        )
                    }
                )
            ),
            401: 'Unauthorized',
            404: 'Profile not found'
        }
    )
    def get(self, request):
        """Get primary user profile details"""
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        try:
            user = request.user
            
            # Check if user has primary_user role
            if not user.roles.filter(name='primary_user').exists():
                return Response(
                    api_response(
                        message="User does not have primary user role",
                        status=False
                    ),
                    status=http_status.HTTP_403_FORBIDDEN
                )
            
            # Prepare profile data
            profile_data = {
                'user_id': str(user.id),
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'email': user.email,
                'phone_number': user.phone_number or '',
                'car_make': user.car_make or '',
                'car_model': user.car_model or '',
                'car_year': user.car_year,
                'license_plate': user.license_plate or '',
                'date_joined': user.date_joined.isoformat() if user.date_joined else None,  # noqa
                'is_verified': user.is_verified,
                'active_role': user.active_role.name if user.active_role else None  # noqa
            }
            
            return Response(
                api_response(
                    message="Profile retrieved successfully",
                    status=True,
                    data=profile_data
                ),
                status=http_status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                api_response(
                    message=f"Error retrieving profile: {str(e)}",
                    status=False
                ),
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @swagger_auto_schema(
        operation_summary="Update Primary User Profile",
        operation_description="Update the current user's primary user profile details",  # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                'car_make': openapi.Schema(type=openapi.TYPE_STRING),
                'car_model': openapi.Schema(type=openapi.TYPE_STRING),
                'car_year': openapi.Schema(type=openapi.TYPE_INTEGER),
                'license_plate': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            200: openapi.Response(
                description="Profile updated successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'user_id': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'first_name': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'last_name': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'phone_number': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'car_make': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'car_model': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                                'car_year': openapi.Schema(type=openapi.TYPE_INTEGER),  # noqa
                                'license_plate': openapi.Schema(type=openapi.TYPE_STRING),  # noqa
                            }
                        )
                    }
                )
            ),
            400: 'Bad Request - Validation Error',
            401: 'Unauthorized',
            403: 'Forbidden - User does not have primary user role'
        }
    )
    def put(self, request):
        """Update primary user profile details"""
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        try:
            user = request.user
            
            # Check if user has primary_user role
            if not user.roles.filter(name='primary_user').exists():
                return Response(
                    api_response(
                        message="User does not have primary user role",
                        status=False
                    ),
                    status=http_status.HTTP_403_FORBIDDEN
                )
            
            # Validate and update profile data
            data = request.data
            
            # Update user fields
            if 'first_name' in data:
                user.first_name = data['first_name']
            if 'last_name' in data:
                user.last_name = data['last_name']
            if 'phone_number' in data:
                user.phone_number = data['phone_number']
            
            # Update car details
            if 'car_make' in data:
                user.car_make = data['car_make']
            if 'car_model' in data:
                user.car_model = data['car_model']
            if 'car_year' in data:
                user.car_year = data['car_year']
            if 'license_plate' in data:
                user.license_plate = data['license_plate']
            
            user.save()
            
            # Prepare updated profile data
            profile_data = {
                'user_id': str(user.id),
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'phone_number': user.phone_number or '',
                'car_make': user.car_make or '',
                'car_model': user.car_model or '',
                'car_year': user.car_year,
                'license_plate': user.license_plate or '',
            }
            
            return Response(
                api_response(
                    message="Profile updated successfully",
                    status=True,
                    data=profile_data
                ),
                status=http_status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                api_response(
                    message=f"Error updating profile: {str(e)}",
                    status=False
                ),
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @swagger_auto_schema(
        operation_summary="Partial Update Primary User Profile",
        operation_description="Partially update the current user's primary user profile details",  # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                'car_make': openapi.Schema(type=openapi.TYPE_STRING),
                'car_model': openapi.Schema(type=openapi.TYPE_STRING),
                'car_year': openapi.Schema(type=openapi.TYPE_INTEGER),
                'license_plate': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            200: 'Profile partially updated successfully',
            400: 'Bad Request - Validation Error',
            401: 'Unauthorized',
            403: 'Forbidden - User does not have primary user role'
        }
    )
    def patch(self, request):
        """Partial update of primary user profile details"""
        return self.put(request)


