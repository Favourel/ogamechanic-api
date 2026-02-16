from rest_framework import status as http_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from django.contrib.auth import authenticate
from datetime import timedelta
from decimal import Decimal

from ogamechanic.modules.utils import (
    api_response,
    incoming_request_checks,
    get_incoming_request_checks,
)
from users.models import User, MechanicProfile, MerchantProfile, DriverProfile, Role
from users.serializers import (
    MechanicProfileSerializer,
    DriverProfileSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetSerializer,
    ContactMessageSerializer,
    ContactMessageAdminSerializer,
    EmailSubscriptionSerializer,
)
from products.models import Order, OrderItem, ProductReview
from products.serializers import CategorySerializer
from users.services import NotificationService
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# ADMIN AUTHENTICATION ENDPOINTS
# ============================================================================


class AdminLoginView(TokenObtainPairView):
    """
    Admin login endpoint - only allows users with admin/staff privileges
    """

    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    @swagger_auto_schema(
        operation_description="Admin login with email and password",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["requestType", "data"],
            properties={
                "requestType": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)",
                ),
                "data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=["email", "password"],
                    properties={
                        "email": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Admin email address"
                        ),
                        "password": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Admin password"
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
                        "access": openapi.Schema(
                            type=openapi.TYPE_STRING, description="JWT access token"
                        ),
                        "refresh": openapi.Schema(
                            type=openapi.TYPE_STRING, description="JWT refresh token"
                        ),
                        "user": openapi.Schema(
                            type=openapi.TYPE_OBJECT, description="Admin user details"
                        ),
                    },
                ),
            ),
            400: "Bad Request",
            401: "Invalid credentials",
            403: "Not authorized - Admin access required",
        },
    )
    def post(self, request, *args, **kwargs):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return Response(
                api_response(
                    message="Email and password are required", status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Authenticate user
        user = authenticate(request=request, email=email, password=password)

        if not user:
            return Response(
                api_response(
                    message="Invalid email or password", status=False),
                status=http_status.HTTP_401_UNAUTHORIZED,
            )

        # Check if user is admin or staff
        if not (user.is_staff or user.is_superuser):
            return Response(
                api_response(
                    message="Access denied. Admin privileges required.", status=False
                ),
                status=http_status.HTTP_403_FORBIDDEN,
            )

        # Check if account is active
        if not user.is_active:
            return Response(
                api_response(message="Account is inactive", status=False),
                status=http_status.HTTP_403_FORBIDDEN,
            )

        # Generate tokens
        request.data.update(data)
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            response_data = response.data
            response_data["user"] = {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
            }

            return Response(
                api_response(
                    message="Login successful", status=True, data=response_data
                )
            )

        return response


class AdminForgotPasswordView(APIView):
    """
    Admin forgot password - sends reset email to admin users only
    """

    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Request password reset for admin account",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["requestType", "data"],
            properties={
                "requestType": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)",
                ),
                "data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=["email"],
                    properties={
                        "email": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Admin email address"
                        ),
                    },
                ),
            },
        ),
        responses={
            200: "Password reset email sent",
            400: "Bad Request",
            403: "Not an admin account",
            404: "Email not found",
        },
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        email = data.get("email")
        if not email:
            return Response(
                api_response(message="Email is required", status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Check if user exists and is admin
        try:
            user = User.objects.get(email=email)

            if not (user.is_staff or user.is_superuser):
                return Response(
                    api_response(
                        message="This email is not associated with an admin account",  # noqa
                        status=False,
                    ),
                    status=http_status.HTTP_403_FORBIDDEN,
                )

            # Use the existing password reset serializer
            serializer = PasswordResetSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(
                api_response(
                    message="Password reset email sent successfully", status=True
                )
            )

        except User.DoesNotExist:
            # Return generic message for security
            return Response(
                api_response(
                    message="If this email exists in our system, you will receive a password reset link",  # noqa
                    status=True,
                )
            )


class AdminResetPasswordView(APIView):
    """
    Admin reset password with token
    """

    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Reset admin password using token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["requestType", "data"],
            properties={
                "requestType": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)",
                ),
                "data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=["token", "password", "confirm_password"],
                    properties={
                        "token": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Password reset token from email",
                        ),
                        "password": openapi.Schema(
                            type=openapi.TYPE_STRING, description="New password"
                        ),
                        "confirm_password": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Confirm new password"
                        ),
                    },
                ),
            },
        ),
        responses={
            200: "Password reset successful",
            400: "Bad Request",
            404: "Invalid or expired token",
        },
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        token = data.get("token")
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if not all([token, password, confirm_password]):
            return Response(
                api_response(
                    message="Token, password and confirm_password are required",
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if password != confirm_password:
            return Response(
                api_response(message="Passwords do not match", status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Validate token and get user
        import jwt
        from django.conf import settings
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            # Decode JWT token
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=["HS256"])
            user = User.objects.get(id=payload["user_id"])

            # Verify user is admin
            if not (user.is_staff or user.is_superuser):
                return Response(
                    api_response(
                        message="This token is not valid for admin accounts",
                        status=False,
                    ),
                    status=http_status.HTTP_403_FORBIDDEN,
                )

            # Validate password
            validate_password(password)

            # Set new password
            user.set_password(password)
            user.save()

            return Response(
                api_response(
                    message="Password reset successful. You can now login with your new password",  # noqa
                    status=True,
                )
            )

        except (jwt.InvalidTokenError, User.DoesNotExist, ValidationError) as e:  # noqa
            print(f"Password reset error: {e}")
            return Response(
                api_response(
                    message="Invalid or expired reset token", status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )


# ============================================================================
# ADMIN MANAGEMENT ENDPOINTS
# ============================================================================


class EcommerceManagementView(APIView):
    """
    Unified ecommerce management endpoint
    Query params: type=product|order|customer|category
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get ecommerce data (products, orders, customers, or categories)",
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description="Type of data (product, order, customer, category)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of items to return",
                type=openapi.TYPE_INTEGER,
                default=50,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Offset for pagination",
                type=openapi.TYPE_INTEGER,
                default=0,
            ),
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Search term",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (for orders)",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={200: openapi.Response("Ecommerce data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        data_type = request.query_params.get("type")
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        search = request.query_params.get("search", "")
        status_filter = request.query_params.get("status", "")

        if not data_type:
            return Response(
                api_response(
                    message="Query parameter 'type' is required (product, order, customer, category)",  # noqa
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if data_type == "product":
            return self._get_products(limit, offset, search)
        elif data_type == "order":
            return self._get_orders(limit, offset, search, status_filter)
        elif data_type == "customer":
            return self._get_customers(limit, offset, search)
        elif data_type == "category":
            return self._get_categories(limit, offset, search)
        else:
            return Response(
                api_response(
                    message="Invalid type. Use: product, order, customer, or category",
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

    def _get_products(self, limit, offset, search):
        """Get products with optional search"""
        from products.models import Product
        from products.serializers import ProductSerializer

        queryset = Product.objects.all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(sku__icontains=search)
            )

        total_count = queryset.count()
        products = queryset.select_related("merchant", "category")[
            offset: offset + limit
        ]  # noqa

        serializer = ProductSerializer(products, many=True)

        return Response(
            api_response(
                message="Products retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "products": serializer.data,
                },
            )
        )

    def _get_orders(self, limit, offset, search, status_filter):
        """Get orders with optional filters"""
        from products.models import Order
        from products.serializers import OrderSerializer

        queryset = Order.objects.all()

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if search:
            queryset = queryset.filter(
                Q(id__icontains=search)
                | Q(customer__email__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
            )

        total_count = queryset.count()
        orders = queryset.select_related("customer").prefetch_related("items__product")[
            offset: offset + limit
        ]

        serializer = OrderSerializer(orders, many=True)

        return Response(
            api_response(
                message="Orders retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "orders": serializer.data,
                },
            )
        )

    def _get_customers(self, limit, offset, search):
        """Get customers (users who have placed orders)"""

        queryset = User.objects.filter(orders__isnull=False).distinct()

        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone_number__icontains=search)
            )

        total_count = queryset.count()
        customers = queryset.annotate(
            total_orders=Count("orders"), total_spent=Sum("orders__total_amount")
        )[offset: offset + limit]

        customers_data = []
        for customer in customers:
            customers_data.append(
                {
                    "id": str(customer.id),
                    "email": customer.email,
                    "name": f"{customer.first_name} {customer.last_name}",
                    "phone_number": customer.phone_number,
                    "total_orders": customer.total_orders,
                    "total_spent": float(customer.total_spent or 0),
                    "date_joined": customer.date_joined.isoformat(),
                    "is_active": customer.is_active,
                }
            )

        return Response(
            api_response(
                message="Customers retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "customers": customers_data,
                },
            )
        )

    def _get_categories(self, limit, offset, search):
        """Get product categories with product counts and prices"""
        from products.models import Category

        queryset = Category.objects.annotate(
            product_count=Count("products"), total_price=Sum("products__price")
        )

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        total_count = queryset.count()
        categories = queryset[offset: offset + limit]

        categories_data = []
        for category in categories:
            categories_data.append(
                {
                    "id": str(category.id),
                    "name": category.name,
                    "description": category.description,
                    "product_count": category.product_count,
                    "total_price": float(category.total_price or 0),
                    "is_active": getattr(category, "is_active", True),
                }
            )

        return Response(
            api_response(
                message="Categories retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "categories": categories_data,
                },
            )
        )


class AccountManagementView(APIView):
    """
    Unified account management endpoint
    Query params: type=mechanic|driver|merchant|bank|wallet|transaction|primary_user
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get account data (mechanic, driver, merchant, bank, wallet, transaction, primary_user)",
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description="Type of data (mechanic, driver, merchant, bank, wallet, transaction, primary_user)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of items to return",
                type=openapi.TYPE_INTEGER,
                default=50,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Offset for pagination",
                type=openapi.TYPE_INTEGER,
                default=0,
            ),
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Search term",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "approved",
                openapi.IN_QUERY,
                description="Filter by approval status (true/false)",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={200: openapi.Response("Account data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        data_type = request.query_params.get("type")
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        search = request.query_params.get("search", "")
        approved = request.query_params.get("approved", "")

        if not data_type:
            return Response(
                api_response(
                    message="Query parameter 'type' is required (mechanic, driver, merchant, bank, wallet, transaction, primary_user)",  # noqa
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if data_type == "mechanic":
            return self._get_mechanic_profiles(limit, offset, search, approved)
        elif data_type == "driver":
            return self._get_driver_profiles(limit, offset, search, approved)
        elif data_type == "merchant":
            return self._get_merchant_profiles(limit, offset, search, approved)
        elif data_type == "bank":
            return self._get_bank_accounts(limit, offset, search)
        elif data_type == "wallet":
            return self._get_wallets(limit, offset, search)
        elif data_type == "transaction":
            return self._get_transactions(limit, offset, search)
        elif data_type == "primary_user":
            return self._get_primary_users(limit, offset, search, approved)
        else:
            return Response(
                api_response(
                    message="Invalid type. Use: mechanic, driver, merchant, bank, wallet, transaction, or primary_user",  # noqa
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

    def _get_mechanic_profiles(self, limit, offset, search, approved):
        """Get mechanic profiles"""
        queryset = MechanicProfile.objects.all()

        if approved:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_approved=is_approved)

        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(business_name__icontains=search)
            )

        total_count = queryset.count()
        profiles = queryset.select_related("user")[offset: offset + limit]

        serializer = MechanicProfileSerializer(profiles, many=True)

        return Response(
            api_response(
                message="Mechanic profiles retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "mechanics": serializer.data,
                },
            )
        )

    def _get_driver_profiles(self, limit, offset, search, approved):
        """Get driver profiles"""
        queryset = DriverProfile.objects.all()

        if approved:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_approved=is_approved)

        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(license_number__icontains=search)
            )

        total_count = queryset.count()
        profiles = queryset.select_related("user")[offset: offset + limit]

        serializer = DriverProfileSerializer(profiles, many=True)

        return Response(
            api_response(
                message="Driver profiles retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "drivers": serializer.data,
                },
            )
        )

    def _get_merchant_profiles(self, limit, offset, search, approved):
        """Get merchant profiles"""
        from users.serializers import MerchantProfileSerializer

        queryset = MerchantProfile.objects.all()

        if approved:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(user__is_active=is_approved)

        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(business_name__icontains=search)
            )

        total_count = queryset.count()
        profiles = queryset.select_related("user")[offset: offset + limit]

        serializer = MerchantProfileSerializer(profiles, many=True)

        return Response(
            api_response(
                message="Merchant profiles retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "merchants": serializer.data,
                },
            )
        )

    def _get_bank_accounts(self, limit, offset, search):
        """Get bank accounts"""
        from users.models import BankAccount

        queryset = BankAccount.objects.all()

        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(account_name__icontains=search)
                | Q(account_number__icontains=search)
                | Q(bank_name__icontains=search)
            )

        total_count = queryset.count()
        accounts = queryset.select_related("user")[offset: offset + limit]

        accounts_data = []
        for account in accounts:
            accounts_data.append(
                {
                    "id": str(account.id),
                    "user": {
                        "id": str(account.user.id),
                        "email": account.user.email,
                        "name": f"{account.user.first_name} {account.user.last_name}",  # noqa
                    },
                    "account_name": account.account_name,
                    "account_number": account.account_number,
                    "bank_name": account.bank_name,
                    "bank_code": account.bank_code,
                    "is_verified": account.is_verified,
                    "created_at": account.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Bank accounts retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "bank_accounts": accounts_data,
                },
            )
        )

    def _get_wallets(self, limit, offset, search):
        """Get wallets"""
        from users.models import Wallet

        queryset = Wallet.objects.all()

        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        total_count = queryset.count()
        wallets = queryset.select_related("user")[offset: offset + limit]

        wallets_data = []
        for wallet in wallets:
            wallets_data.append(
                {
                    "id": str(wallet.id),
                    "user": {
                        "id": str(wallet.user.id),
                        "email": wallet.user.email,
                        "name": f"{wallet.user.first_name} {wallet.user.last_name}",  # noqa
                    },
                    "balance": float(wallet.balance),
                    "currency": wallet.currency,
                    "is_active": wallet.is_active,
                    "created_at": wallet.created_at.isoformat(),
                    "updated_at": wallet.updated_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Wallets retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "wallets": wallets_data,
                },
            )
        )

    def _get_transactions(self, limit, offset, search):
        """Get transactions"""
        from users.models import Transaction

        queryset = Transaction.objects.all()

        if search:
            queryset = queryset.filter(
                Q(wallet__user__email__icontains=search)
                | Q(wallet__user__first_name__icontains=search)
                | Q(wallet__user__last_name__icontains=search)
                | Q(reference__icontains=search)
                | Q(transaction_type__icontains=search)
            )

        total_count = queryset.count()
        transactions = queryset.select_related(
            "wallet__user")[offset: offset + limit]

        transactions_data = []
        for transaction in transactions:
            transactions_data.append(
                {
                    "id": str(transaction.id),
                    "wallet": {
                        "id": str(transaction.wallet.id),
                        "user": {
                            "id": str(transaction.wallet.user.id),
                            "email": transaction.wallet.user.email,
                            "name": f"{transaction.wallet.user.first_name} {transaction.wallet.user.last_name}",
                        },
                        "balance": float(transaction.wallet.balance),
                    },
                    "amount": float(transaction.amount),
                    "transaction_type": transaction.transaction_type,
                    "reference": transaction.reference,
                    "description": transaction.description,
                    "status": transaction.status,
                    "fee": float(transaction.fee),
                    "metadata": transaction.metadata,
                    "created_at": transaction.created_at.isoformat(),
                    "updated_at": transaction.updated_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Transactions retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "transactions": transactions_data,
                },
            )
        )

    def _get_primary_users(self, limit, offset, search, approved):
        """Get primary users"""
        queryset = User.objects.filter(role="primary_user")

        if approved:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_active=is_approved)

        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone_number__icontains=search)
            )

        total_count = queryset.count()
        users = queryset[offset: offset + limit]

        users_data = []
        for user in users:
            users_data.append(
                {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "phone_number": user.phone_number,
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "date_joined": user.date_joined.isoformat(),
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                }
            )

        return Response(
            api_response(
                message="Primary users retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "primary_users": users_data,
                },
            )
        )


class MechanicManagementView(APIView):
    """
    Unified mechanic management endpoint
    Query params: type=repair|customer|expertise
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get mechanic data (repairs, customers, expertise)",
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description="Type of data (repair, customer, expertise)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of items to return",
                type=openapi.TYPE_INTEGER,
                default=50,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Offset for pagination",
                type=openapi.TYPE_INTEGER,
                default=0,
            ),
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Search term",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (for repairs)",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={200: openapi.Response("Mechanic management data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        data_type = request.query_params.get("type")
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        search = request.query_params.get("search", "")
        status_filter = request.query_params.get("status", "")

        if not data_type:
            return Response(
                api_response(
                    message="Query parameter 'type' is required (repair, customer, expertise)",  # noqa
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if data_type == "repair":
            return self._get_repair_requests(
                limit, offset, search, status_filter
            )  # noqa
        elif data_type == "customer":
            return self._get_mechanic_customers(limit, offset, search)
        elif data_type == "expertise":
            return self._get_vehicle_expertise(limit, offset, search)
        else:
            return Response(
                api_response(
                    message="Invalid type. Use: repair, customer, or expertise",
                    status=False,
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

    def _get_repair_requests(self, limit, offset, search, status_filter):
        """Get repair requests"""
        from mechanics.models import RepairRequest
        from mechanics.serializers import RepairRequestSerializer

        queryset = RepairRequest.objects.all()

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if search:
            queryset = queryset.filter(
                Q(customer__email__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
                | Q(mechanic__email__icontains=search)
                | Q(problem_description__icontains=search)
            )

        total_count = queryset.count()
        repairs = queryset.select_related("customer", "mechanic")[
            offset: offset + limit
        ]

        serializer = RepairRequestSerializer(
            repairs, many=True, context={"request": self.request}
        )

        return Response(
            api_response(
                message="Repair requests retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "repairs": serializer.data,
                },
            )
        )

    def _get_mechanic_customers(self, limit, offset, search):
        """Get customers who have used mechanic services"""
        from mechanics.models import RepairRequest

        queryset = User.objects.filter(
            repair_requests__isnull=False).distinct()

        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone_number__icontains=search)
            )

        total_count = queryset.count()
        customers = queryset.annotate(total_repairs=Count("repair_requests"))[
            offset: offset + limit
        ]

        customers_data = []
        for customer in customers:
            # Calculate total spent by summing repair costs
            total_spent = (
                RepairRequest.objects.filter(customer=customer).aggregate(
                    total=Sum("actual_cost")
                )["total"]
                or 0
            )

            customers_data.append(
                {
                    "id": str(customer.id),
                    "email": customer.email,
                    "name": f"{customer.first_name} {customer.last_name}",
                    "phone_number": customer.phone_number,
                    "total_repairs": customer.total_repairs,
                    "total_spent": float(total_spent),
                    "date_joined": customer.date_joined.isoformat(),
                    "is_active": customer.is_active,
                }
            )

        return Response(
            api_response(
                message="Mechanic customers retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "customers": customers_data,
                },
            )
        )

    def _get_vehicle_expertise(self, limit, offset, search):
        """Get mechanic vehicle expertise"""
        from mechanics.models import MechanicVehicleExpertise

        queryset = MechanicVehicleExpertise.objects.all()

        if search:
            queryset = queryset.filter(
                Q(mechanic__user__email__icontains=search)
                | Q(mechanic__user__first_name__icontains=search)
                | Q(mechanic__user__last_name__icontains=search)
                | Q(vehicle_make__name__icontains=search)
            )

        total_count = queryset.count()
        expertise = queryset.select_related("mechanic__user", "vehicle_make")[
            offset: offset + limit
        ]

        expertise_data = []
        for exp in expertise:
            expertise_data.append(
                {
                    "id": str(exp.id),
                    "mechanic": {
                        "id": str(exp.mechanic.id),
                        "user_id": str(exp.mechanic.user.id),
                        "email": exp.mechanic.user.email,
                        "name": f"{exp.mechanic.user.first_name} {exp.mechanic.user.last_name}",
                        "location": exp.mechanic.location,
                    },
                    "vehicle_make": {
                        "id": str(exp.vehicle_make.id),
                        "name": exp.vehicle_make.name,
                    },
                    "years_of_experience": exp.years_of_experience,
                    "certification_level": exp.certification_level,
                    "created_at": exp.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Vehicle expertise retrieved successfully",
                status=True,
                data={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "expertise": expertise_data,
                },
            )
        )


class AdminCategoryCreateView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Create a new category (admin only)",
        request_body=CategorySerializer,
        responses={201: CategorySerializer(), 400: "Bad Request",
                   403: "Forbidden"},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)
        serializer = CategorySerializer(data=data)
        if serializer.is_valid():
            category = serializer.save()
            return Response(
                api_response(
                    message="Category created successfully.",
                    status=True,
                    data=CategorySerializer(category).data,
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


class PendingVerificationsView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description=(
            "List all pending verifications (mechanics, drivers, merchants) "
            "on a request type bases."
        ),
        manual_parameters=[
            openapi.Parameter(
                "request_type",
                openapi.IN_QUERY,
                description=(
                    "Request type (mechanics, drivers, merchants) " "if requested."
                ),
                type=openapi.TYPE_STRING,
            )
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "pending_mechanics": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    "pending_drivers": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    "pending_merchants": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                },
            )
        },
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        request_type = request.query_params.get("request_type")
        if not request_type:
            return Response(
                api_response(
                    message="Request type not provided.", status=False),
                status=400,
            )

        pending_mechanics = MechanicProfile.objects.filter(is_approved=False)
        pending_drivers = DriverProfile.objects.filter(is_approved=False)
        pending_merchants = MerchantProfile.objects.filter(
            user__is_active=False
        )  # noqa

        if request_type == "mechanics":
            mechanics_data = [
                {
                    "id": m.id,
                    "user": m.user.email,
                    "created_at": m.created_at,
                }
                for m in pending_mechanics
            ]
            return Response(
                api_response(
                    message="Pending mechanics retrieved successfully.",
                    status=True,
                    data={"pending_mechanics": mechanics_data},
                )
            )
        elif request_type == "drivers":
            drivers_data = [
                {
                    "id": d.id,
                    "user": d.user.email,
                    "created_at": d.created_at,
                }
                for d in pending_drivers
            ]
            return Response(
                api_response(
                    message="Pending drivers retrieved successfully.",
                    status=True,
                    data={"pending_drivers": drivers_data},
                )
            )
        elif request_type == "merchants":
            merchants_data = [
                {
                    "id": m.id,
                    "user": m.user.email,
                    "created_at": m.created_at,
                }
                for m in pending_merchants
            ]
            return Response(
                api_response(
                    message="Pending merchants retrieved successfully.",
                    status=True,
                    data={"pending_merchants": merchants_data},
                )
            )
        else:
            return Response(
                api_response(
                    message="Invalid request type.",
                    status=False,
                ),
                status=400,
            )


class UserActivationView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Activate or deactivate a user account by role",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["user_id", "action"],
            properties={
                "user_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="ID of the user to activate/deactivate",
                ),
                "action": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["activate", "deactivate"],
                    description="Action to perform",
                ),
                "reason": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Reason for deactivation (optional, sent via email)",
                ),
                "send_email": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description="Whether to send email notification (default: true)",
                    default=True,
                ),
            },
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "message": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            400: "Bad Request",
            404: "User not found",
        },
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        user_id = data.get("user_id")
        action = data.get("action")
        reason = data.get("reason", "")
        send_email = data.get("send_email", True)

        if not user_id or action not in ["activate", "deactivate"]:
            return Response(
                api_response(
                    message="user_id and action (activate/deactivate) are required.",  # noqa
                    status=False,
                ),
                status=400,
            )

        try:
            user = User.objects.get(id=user_id)

            # Check if user has role-specific profiles
            user_profiles = []
            if user.roles.filter(name="merchant").exists():
                try:
                    user_profiles.append(("merchant", user.merchant_profile))
                except MerchantProfile.DoesNotExist:
                    pass

            if user.roles.filter(name="mechanic").exists():
                try:
                    user_profiles.append(("mechanic", user.mechanic_profile))
                except MechanicProfile.DoesNotExist:
                    pass

            if user.roles.filter(name="driver").exists():
                try:
                    user_profiles.append(("driver", user.driver_profile))
                except DriverProfile.DoesNotExist:
                    pass

            if action == "activate":
                user.is_active = True
                user.save()

                # Activate role-specific profiles
                for role_name, profile in user_profiles:
                    if hasattr(profile, "is_active"):
                        profile.is_active = True
                    if hasattr(profile, "is_approved"):
                        profile.is_approved = True
                    profile.save()

                # Create notification
                NotificationService.create_notification(
                    user=user,
                    title="Account Activated",
                    message="Your account has been activated by an administrator.",  # noqa
                    notification_type="success",
                )

                # Send email if requested
                if send_email:
                    from users.services import send_account_status_email

                    send_account_status_email.delay(str(user.id), "activated")

                # Prepare response data with profile information
                response_data = {
                    "user_id": str(user.id),
                    "is_active": True,
                    "profiles": [],
                }

                for role_name, profile in user_profiles:
                    response_data["profiles"].append(
                        {
                            "role": role_name,
                            "profile_id": str(profile.id),
                            "is_approved": getattr(profile, "is_approved", None),
                            "is_active": getattr(profile, "is_active", None),
                        }
                    )

                return Response(
                    api_response(
                        message="User activated successfully.",
                        status=True,
                        data=response_data,
                    ),
                    status=200,
                )

            elif action == "deactivate":
                user.is_active = False
                user.save()

                # Deactivate role-specific profiles
                for role_name, profile in user_profiles:
                    if hasattr(profile, "is_active"):
                        profile.is_active = False
                    if hasattr(profile, "is_approved"):
                        profile.is_approved = False
                    profile.save()

                # Create notification
                message = (
                    "Your account has been deactivated by an administrator."  # noqa
                )
                if reason:
                    message += f" Reason: {reason}"

                NotificationService.create_notification(
                    user=user,
                    title="Account Deactivated",
                    message=message,
                    notification_type="warning",
                )

                # Send email if requested
                if send_email:
                    from users.services import send_account_status_email

                    send_account_status_email.delay(
                        str(user.id), "deactivated", reason)

                # Prepare response data with profile information
                response_data = {
                    "user_id": str(user.id),
                    "is_active": False,
                    "profiles": [],
                }

                for role_name, profile in user_profiles:
                    response_data["profiles"].append(
                        {
                            "role": role_name,
                            "profile_id": str(profile.id),
                            "is_approved": getattr(profile, "is_approved", None),
                            "is_active": getattr(profile, "is_active", None),
                        }
                    )

                return Response(
                    api_response(
                        message="User deactivated successfully.",
                        status=True,
                        data=response_data,
                    ),
                    status=200,
                )

        except User.DoesNotExist:
            return Response(
                api_response(message="User not found.", status=False), status=404
            )
        except Exception as e:
            return Response(
                api_response(
                    message=f"An error occurred: {str(e)}", status=False),
                status=500,
            )


class AdminNotificationView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Send notification to all users (admin only)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["title", "message"],
            properties={
                "title": openapi.Schema(type=openapi.TYPE_STRING),
                "message": openapi.Schema(type=openapi.TYPE_STRING),
                "notification_type": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["info", "success", "warning", "error"],
                    default="info",
                ),
            },
        ),
        responses={201: openapi.Response("Notification sent successfully")},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        title = data.get("title")
        message = data.get("message")
        notification_type = data.get("notification_type", "info")

        if not title or not message:
            return Response(
                api_response(
                    message="Title and message are required", status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Import service here to avoid circular imports
        from users.services import NotificationService

        # Get all active users
        users = User.objects.filter(is_active=True)

        # Create notifications for all users
        notifications = NotificationService.create_bulk_notifications(
            users=users,
            title=title,
            message=message,
            notification_type=notification_type,
        )

        return Response(
            api_response(
                message=f"Notification sent to {len(notifications)} users",
                status=True,
                data={"sent_count": len(notifications)},
            ),
            status=http_status.HTTP_201_CREATED,
        )


class RoleNotificationView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Send notification to users with specific role (admin only)",  # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["role", "title", "message"],
            properties={
                "role": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["customer", "merchant", "driver", "mechanic"],
                ),
                "title": openapi.Schema(type=openapi.TYPE_STRING),
                "message": openapi.Schema(type=openapi.TYPE_STRING),
                "notification_type": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["info", "success", "warning", "error"],
                    default="info",
                ),
            },
        ),
        responses={201: openapi.Response("Notification sent successfully")},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        role = data.get("role")
        title = data.get("title")
        message = data.get("message")
        notification_type = data.get("notification_type", "info")

        if not role or not title or not message:
            return Response(
                api_response(
                    message="Role, title, and message are required", status=False
                ),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Import service here to avoid circular imports
        from users.services import NotificationService

        # Get users with specific role
        users = User.objects.filter(roles__name=role, is_active=True)

        # Create notifications for users with role
        notifications = NotificationService.create_bulk_notifications(
            users=users,
            title=title,
            message=message,
            notification_type=notification_type,
        )

        return Response(
            api_response(
                message=f"Notification sent to {len(notifications)} {role}s",
                status=True,
                data={"sent_count": len(notifications)},
            ),
            status=http_status.HTTP_201_CREATED,
        )


# ============================================================================
# ANALYTICS ENDPOINTS (Model-free, computed on-the-fly)
# ============================================================================


class DashboardOverviewView(APIView):
    """
    Get essential dashboard overview metrics (12+ key values)
    Optimized to avoid redundant data available in other endpoints
    Supports period filtering: 7d, 30d, 90d, 1y, or all data (no filter)
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get essential dashboard overview metrics",
        manual_parameters=[
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y, or omit for all data)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Essential dashboard overview metrics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "period": openapi.Schema(type=openapi.TYPE_STRING),
                        "total_revenue": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "total_users": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "active_users": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "total_orders": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "pending_tasks": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "conversion_rate": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "avg_rating": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "total_merchants": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "total_drivers": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "total_mechanics": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "commission_earned": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "cancellation_rate": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "revenue_breakdown": openapi.Schema(type=openapi.TYPE_OBJECT),
                    },
                ),
            )
        },
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Parse period filter
        period = request.query_params.get("period", None)
        start_date = None
        if period:
            days = self._parse_period(period)
            start_date = timezone.now() - timedelta(days=days)

        # Apply date filter helper
        def apply_date_filter(queryset, date_field="created_at"):
            if start_date:
                filter_kwargs = {f"{date_field}__gte": start_date}
                return queryset.filter(**filter_kwargs)
            return queryset

        # ====================================================================
        # 1. TOTAL REVENUE - All services combined
        # ====================================================================
        total_revenue = 0
        revenue_breakdown = {}

        # E-commerce revenue
        ecommerce_revenue = (
            apply_date_filter(
                Order.objects.filter(status__in=["paid", "shipped", "completed"])
            ).aggregate(total=Sum("total_amount"))["total"] or 0
        )
        revenue_breakdown["ecommerce"] = float(ecommerce_revenue)

        # Rides revenue
        rides_revenue = 0
        try:
            from rides.models import Ride
            rides_revenue = (
                apply_date_filter(Ride.objects.filter(status="completed"), "requested_at")
                .aggregate(total=Sum("fare"))["total"] or 0
            )
            revenue_breakdown["rides"] = float(rides_revenue)
        except ImportError:
            revenue_breakdown["rides"] = 0.0

        # Courier revenue
        courier_revenue = 0
        try:
            from couriers.models import DeliveryRequest
            courier_revenue = (
                apply_date_filter(DeliveryRequest.objects.filter(status="delivered"), "requested_at")
                .aggregate(total=Sum("total_fare"))["total"] or 0
            )
            revenue_breakdown["couriers"] = float(courier_revenue)
        except ImportError:
            revenue_breakdown["couriers"] = 0.0

        # Mechanic revenue
        mechanic_revenue = 0
        try:
            from mechanics.models import RepairRequest
            mechanic_revenue = (
                apply_date_filter(RepairRequest.objects.filter(status="completed"), "requested_at")
                .aggregate(total=Sum("actual_cost"))["total"] or 0
            )
            revenue_breakdown["mechanics"] = float(mechanic_revenue)
        except ImportError:
            revenue_breakdown["mechanics"] = 0.0

        # Rental revenue
        rental_revenue = 0
        try:
            from rentals.models import RentalBooking
            rental_revenue = (
                apply_date_filter(
                    RentalBooking.objects.filter(status__in=["completed", "active"]), "booked_at"
                ).aggregate(total=Sum("total_amount"))["total"] or 0
            )
            revenue_breakdown["rentals"] = float(rental_revenue)
        except ImportError:
            revenue_breakdown["rentals"] = 0.0

        total_revenue = sum(revenue_breakdown.values())

        # ====================================================================
        # 2. USER METRICS
        # ====================================================================
        total_users = User.objects.count()
        new_users = apply_date_filter(User.objects, "date_joined").count() if start_date else 0
        
        # Active users (logged in recently - last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        active_users = User.objects.filter(last_login__gte=thirty_days_ago).count()

        # ====================================================================
        # 3. SERVICE PROVIDER COUNTS
        # ====================================================================
        total_merchants = MerchantProfile.objects.count()
        total_mechanics = MechanicProfile.objects.count()
        total_drivers = DriverProfile.objects.count()

        # ====================================================================
        # 4. ORDERS/REQUESTS COUNT
        # ====================================================================
        total_orders = apply_date_filter(
            Order.objects.filter(status__in=["paid", "shipped", "completed"])
        ).count()

        # Add rides, deliveries, mechanics to total orders
        try:
            from rides.models import Ride
            total_orders += apply_date_filter(Ride.objects, "requested_at").count()
        except ImportError:
            pass

        try:
            from couriers.models import DeliveryRequest
            total_orders += apply_date_filter(DeliveryRequest.objects, "requested_at").count()
        except ImportError:
            pass

        try:
            from mechanics.models import RepairRequest
            total_orders += apply_date_filter(RepairRequest.objects, "requested_at").count()
        except ImportError:
            pass

        # ====================================================================
        # 5. PENDING TASKS
        # ====================================================================
        pending_tasks = 0

        # Pending orders
        pending_tasks += apply_date_filter(
            Order.objects.filter(status__in=["pending", "processing"])
        ).count()

        # Pending service requests
        try:
            from rides.models import Ride
            pending_tasks += apply_date_filter(
                Ride.objects.filter(status__in=["initiated", "requested", "accepted"]), "requested_at"
            ).count()
        except ImportError:
            pass

        try:
            from couriers.models import DeliveryRequest
            pending_tasks += apply_date_filter(
                DeliveryRequest.objects.filter(status__in=["pending", "assigned", "picked_up", "in_transit"]), "requested_at"
            ).count()
        except ImportError:
            pass

        try:
            from mechanics.models import RepairRequest
            pending_tasks += apply_date_filter(
                RepairRequest.objects.filter(status="pending"), "requested_at"
            ).count()
        except ImportError:
            pass

        # Pending approvals
        pending_tasks += MerchantProfile.objects.filter(is_approved=False).count()
        pending_tasks += DriverProfile.objects.filter(is_approved=False).count()
        pending_tasks += MechanicProfile.objects.filter(is_approved=False).count()

        # ====================================================================
        # 6. CONVERSION RATE
        # ====================================================================
        total_requests = 0
        completed_requests = 0

        # E-commerce conversion
        total_orders_all = apply_date_filter(Order.objects).count()
        completed_orders = apply_date_filter(
            Order.objects.filter(status__in=["paid", "shipped", "completed"])
        ).count()
        total_requests += total_orders_all
        completed_requests += completed_orders

        # Service conversions
        try:
            from rides.models import Ride
            rides_total = apply_date_filter(Ride.objects, "requested_at").count()
            rides_completed = apply_date_filter(Ride.objects.filter(status="completed"), "requested_at").count()
            total_requests += rides_total
            completed_requests += rides_completed
        except ImportError:
            pass

        try:
            from couriers.models import DeliveryRequest
            courier_total = apply_date_filter(DeliveryRequest.objects, "requested_at").count()
            courier_completed = apply_date_filter(DeliveryRequest.objects.filter(status="delivered"), "requested_at").count()
            total_requests += courier_total
            completed_requests += courier_completed
        except ImportError:
            pass

        conversion_rate = (completed_requests / total_requests * 100) if total_requests > 0 else 0

        # ====================================================================
        # 7. AVERAGE RATING
        # ====================================================================
        avg_rating = 0.0
        rating_count = 0

        # Product ratings
        product_ratings = (
            apply_date_filter(ProductReview.objects, "created_at")
            .aggregate(avg=Avg("rating"), count=Count("id"))
        )
        if product_ratings["count"]:
            avg_rating += float(product_ratings["avg"] or 0)
            rating_count += 1

        # Service ratings (ride ratings)
        try:
            from rides.models import RideRating
            ride_ratings = (
                apply_date_filter(RideRating.objects, "rated_at")
                .aggregate(avg=Avg("overall_rating"), count=Count("id"))
            )
            if ride_ratings["count"]:
                avg_rating += float(ride_ratings["avg"] or 0)
                rating_count += 1
        except (ImportError, AttributeError):
            pass

        avg_rating = avg_rating / rating_count if rating_count > 0 else 0

        # ====================================================================
        # 8. COMMISSION EARNED
        # ====================================================================
        COMMISSION_RATE = 0.1  # 10% commission
        commission_earned = round(total_revenue * COMMISSION_RATE, 2)

        # ====================================================================
        # 9. CANCELLATION RATE
        # ====================================================================
        total_cancelled = 0
        total_all_requests = 0

        # Order cancellations
        total_all_requests += apply_date_filter(Order.objects).count()
        total_cancelled += apply_date_filter(Order.objects.filter(status="cancelled")).count()

        # Service cancellations
        try:
            from rides.models import Ride
            rides_all = apply_date_filter(Ride.objects, "requested_at").count()
            rides_cancelled = apply_date_filter(Ride.objects.filter(status="cancelled"), "requested_at").count()
            total_all_requests += rides_all
            total_cancelled += rides_cancelled
        except ImportError:
            pass

        try:
            from couriers.models import DeliveryRequest
            courier_all = apply_date_filter(DeliveryRequest.objects, "requested_at").count()
            courier_cancelled = apply_date_filter(DeliveryRequest.objects.filter(status="cancelled"), "requested_at").count()
            total_all_requests += courier_all
            total_cancelled += courier_cancelled
        except ImportError:
            pass

        cancellation_rate = (total_cancelled / total_all_requests * 100) if total_all_requests > 0 else 0

        return Response(
            api_response(
                message="Dashboard overview retrieved successfully.",
                status=True,
                data={
                    "period": period or "all",
                    # Key Metrics (12+ essential values)
                    "total_revenue": round(total_revenue, 2),
                    "total_users": total_users,
                    "active_users": active_users,
                    "new_users": new_users,
                    "total_orders": total_orders,
                    "pending_tasks": pending_tasks,
                    "conversion_rate": round(conversion_rate, 2),
                    "avg_rating": round(avg_rating, 2),
                    "total_merchants": total_merchants,
                    "total_drivers": total_drivers,
                    "total_mechanics": total_mechanics,
                    "commission_earned": commission_earned,
                    "cancellation_rate": round(cancellation_rate, 2),
                    # Essential breakdown
                    "revenue_breakdown": revenue_breakdown,
                },
            )
        )

    def _parse_period(self, period):
        """Parse period string to days"""
        period_map = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365,
        }
        return period_map.get(period, 30)


class UserGrowthAnalyticsView(APIView):
    """Analytics focused on user growth over time"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get user growth analytics over time",
        manual_parameters=[
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y)",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
        ],
        responses={200: openapi.Response("User growth data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        period = request.query_params.get("period", "30d")
        days = self._parse_period(period)
        start_date = timezone.now() - timedelta(days=days)

        # Determine granularity based on period
        if period in ["7d", "30d"]:
            # Daily granularity for shorter periods
            user_growth = (
                User.objects.filter(date_joined__gte=start_date)
                .annotate(date=TruncDate("date_joined"))
                .values("date")
                .annotate(count=Count("id"))
                .order_by("date")
            )
        else:
            # Monthly granularity for longer periods
            user_growth = (
                User.objects.filter(date_joined__gte=start_date)
                .annotate(date=TruncMonth("date_joined"))
                .values("date")
                .annotate(count=Count("id"))
                .order_by("date")
            )

        return Response(
            api_response(
                message="User growth analytics retrieved successfully.",
                status=True,
                data={
                    "period": period,
                    "user_growth": list(user_growth),
                },
            )
        )

    def _parse_period(self, period):
        """Parse period string to days"""
        period_map = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365,
        }
        return period_map.get(period, 30)


class UserActivityAnalyticsView(APIView):
    """Analytics for tracking user activities over time with line chart data"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get user activity analytics with line chart data",
        manual_parameters=[
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y)",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
            openapi.Parameter(
                "action",
                openapi.IN_QUERY,
                description="Filter by specific action type",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "category",
                openapi.IN_QUERY,
                description="Filter by activity category",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "severity",
                openapi.IN_QUERY,
                description="Filter by severity level",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "period": openapi.Schema(type=openapi.TYPE_STRING),
                    "total_activities": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "activity_timeline": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "date": openapi.Schema(type=openapi.TYPE_STRING),
                                "count": openapi.Schema(type=openapi.TYPE_INTEGER),
                            }
                        )
                    ),
                    "action_breakdown": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        additional_properties=openapi.Schema(type=openapi.TYPE_INTEGER)
                    ),
                    "category_breakdown": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        additional_properties=openapi.Schema(type=openapi.TYPE_INTEGER)
                    ),
                    "severity_breakdown": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        additional_properties=openapi.Schema(type=openapi.TYPE_INTEGER)
                    ),
                    "top_users": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                    ),
                },
            )
        },
    )
    def get(self, request):
        from users.models import UserActivityLog
        
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        period = request.query_params.get("period", "30d")
        action_filter = request.query_params.get("action")
        category_filter = request.query_params.get("category")
        severity_filter = request.query_params.get("severity")

        days = self._parse_period(period)
        start_date = timezone.now() - timedelta(days=days)

        # Base queryset
        queryset = UserActivityLog.objects.filter(timestamp__gte=start_date)

        # Apply filters
        if action_filter:
            queryset = queryset.filter(action__icontains=action_filter)
        if category_filter:
            queryset = queryset.filter(category__icontains=category_filter)
        if severity_filter:
            queryset = queryset.filter(severity__iexact=severity_filter)

        # Total activities
        total_activities = queryset.count()

        # Activity timeline for line chart (grouped by date)
        activity_timeline = (
            queryset
            .annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Action breakdown
        action_breakdown = (
            queryset
            .values("action")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )
        action_breakdown_dict = {
            item["action"]: item["count"] for item in action_breakdown
        }

        # Category breakdown
        category_breakdown = (
            queryset
            .values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        category_breakdown_dict = {
            item["category"]: item["count"] for item in category_breakdown
        }

        # Severity breakdown
        severity_breakdown = (
            queryset
            .values("severity")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        severity_breakdown_dict = {
            item["severity"]: item["count"] for item in severity_breakdown
        }

        # Top users by activity count
        # top_users = (
        #     queryset
        #     .values("user__id", "user__email", "user__first_name", "user__last_name")
        #     .annotate(activity_count=Count("id"))
        #     .order_by("-activity_count")[:10]
        # )
        # top_users_data = [
        #     {
        #         "user_id": user["user__id"],
        #         "email": user["user__email"],
        #         "name": f"{user['user__first_name']} {user['user__last_name']}".strip(),
        #         "activity_count": user["activity_count"],
        #     }
        #     for user in top_users
        # ]

        return Response(
            api_response(
                message="User activity analytics retrieved successfully.",
                status=True,
                data={
                    "period": period,
                    "total_activities": total_activities,
                    "activity_timeline": list(activity_timeline),
                    "action_breakdown": action_breakdown_dict,
                    "category_breakdown": category_breakdown_dict,
                    "severity_breakdown": severity_breakdown_dict,
                    # "top_users": top_users_data,
                },
            )
        )

    def _parse_period(self, period):
        period_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        return period_map.get(period, 30)


class ConsolidatedAnalyticsView(APIView):
    """Comprehensive analytics for sales, revenue, and merchant performance"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get comprehensive analytics including sales, revenue, and merchant performance",
        manual_parameters=[
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y)",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of top merchants/products to return",
                type=openapi.TYPE_INTEGER,
                default=10,
            ),
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description="Analytics type: sales, merchants, or all",
                type=openapi.TYPE_STRING,
                default="all",
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "sales_analytics": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "merchant_analytics": openapi.Schema(type=openapi.TYPE_OBJECT),
                },
            )
        },
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Get parameters
        period = request.query_params.get("period", "30d")
        limit = int(request.query_params.get("limit", 10))
        analytics_type = request.query_params.get("type", "all")

        days = self._parse_period(period)
        start_date = timezone.now() - timedelta(days=days)
        paid_statuses = ["paid", "shipped", "completed"]

        response_data = {}

        # Include sales analytics
        if analytics_type in ["sales", "all"]:
            response_data["sales_analytics"] = self._get_sales_analytics(
                start_date, period, paid_statuses
            )

        # Include merchant analytics
        if analytics_type in ["merchants", "all"]:
            response_data["merchant_analytics"] = self._get_merchant_analytics(
                limit, paid_statuses
            )

        return Response(
            api_response(
                message="Analytics retrieved successfully.",
                status=True,
                data=response_data,
            )
        )

    def _get_sales_analytics(self, start_date, period, paid_statuses):
        """Get sales and revenue analytics"""

        # Basic metrics
        total_sales = Order.objects.filter(
            status__in=paid_statuses, created_at__gte=start_date
        ).count()

        # total_order_revenue = (
        #     Order.objects.filter(
        #         status__in=paid_statuses, created_at__gte=start_date
        #     ).aggregate(total=Sum("total_amount"))["total"]
        #     or 0
        # )

        # Order status breakdown
        order_status_counts = (
            Order.objects.filter(status__in=paid_statuses,
                                 created_at__gte=start_date)
            .values("status")
            .annotate(count=Count("id"))
        )
        status_breakdown = {
            item["status"]: item["count"] for item in order_status_counts
        }

        # Top selling products
        top_products = (
            OrderItem.objects.filter(
                order__status__in=paid_statuses, order__created_at__gte=start_date
            )
            .values("product__id", "product__name")
            .annotate(
                quantity_sold=Sum("quantity"),
                revenue=Sum(
                    ExpressionWrapper(
                        F("price") * F("quantity"),
                        output_field=DecimalField(
                            max_digits=12, decimal_places=2),
                    )
                ),
            )
            .order_by("-revenue")[:10]
        )
        top_products_data = [
            {
                "product_id": b["product__id"],
                "product_name": b["product__name"],
                "total_quantity": b["quantity_sold"],
                "total_sales": float(b["revenue"]),
            }
            for b in top_products
        ]

        # Build sales response
        sales_data = {
            "period": period,
            "total_sales": total_sales,
            # "total_order_revenue": float(total_order_revenue),
            "order_status_breakdown": status_breakdown,
            "top_products": top_products_data,
        }

        return sales_data

    def _get_merchant_analytics(self, limit, paid_statuses):
        """Get merchant performance analytics"""
        # Total merchants
        # total_merchants = MerchantProfile.objects.count()
        # active_merchants = MerchantProfile.objects.filter(
        #     user__is_active=True).count()

        # Top merchants by sales
        top_merchants = (
            OrderItem.objects.filter(
                order__status__in=paid_statuses)
            .values(
                "product__merchant__id",
                "product__merchant__email",
                "product__merchant__first_name",
                "product__merchant__last_name",
            )
            .annotate(
                total_sales=Sum(
                    ExpressionWrapper(
                        F("price") * F("quantity"),
                        output_field=DecimalField(
                            max_digits=12, decimal_places=2),
                    )
                ),
                total_orders=Count("order__id", distinct=True),
                total_products_sold=Sum("quantity"),
            )
            .order_by("-total_sales")[:limit]
        )

        top_merchants_data = [
            {
                "merchant_id": m["product__merchant__id"],
                "email": m["product__merchant__email"],
                "name": f"{m['product__merchant__first_name']} {m['product__merchant__last_name']}".strip(),
                "total_sales": float(m["total_sales"]),
                "total_orders": m["total_orders"],
                "total_products_sold": m["total_products_sold"] or 0,
            }
            for m in top_merchants
        ]

        return {
            # "total_merchants": total_merchants,
            # "active_merchants": active_merchants,
            "top_merchants_by_sales": top_merchants_data,
        }

    def _parse_period(self, period):
        period_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        return period_map.get(period, 30)


class ServiceAnalyticsView(APIView):
    """Analytics for rides, couriers, rentals, and mechanic services"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get service analytics",
        manual_parameters=[
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y)",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
            openapi.Parameter(
                "service",
                openapi.IN_QUERY,
                description="Filter by specific service type (rides, couriers, rentals, mechanics)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response("Service analytics data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        period = request.query_params.get("period", "30d")
        service_type = request.query_params.get("service")
        days = self._parse_period(period)
        start_date = timezone.now() - timedelta(days=days)

        analytics_data = {
            "period": period,
        }

        # Only include requested service type
        if not service_type or service_type == "rides":
            analytics_data["rides"] = self._get_ride_analytics(start_date)
        
        if not service_type or service_type == "couriers":
            analytics_data["couriers"] = self._get_courier_analytics(start_date)
        
        if not service_type or service_type == "rentals":
            analytics_data["rentals"] = self._get_rental_analytics(start_date)
        
        if not service_type or service_type == "mechanics":
            analytics_data["mechanics"] = self._get_mechanic_analytics(start_date)

        # If specific service type requested, only return that
        if service_type and service_type in ["rides", "couriers", "rentals", "mechanics"]:
            # Return only the requested service
            filtered_data = {service_type: analytics_data[service_type]}
            return Response(
                api_response(
                    message=f"{service_type.capitalize()} analytics retrieved successfully.",
                    status=True,
                    data=filtered_data,
                )
            )

        return Response(
            api_response(
                message="Service analytics retrieved successfully.",
                status=True,
                data=analytics_data,
            )
        )

    def _get_ride_analytics(self, start_date):
        """Get ride service analytics"""
        try:
            from rides.models import Ride

            rides = Ride.objects.filter(requested_at__gte=start_date)
            completed_rides = rides.filter(status="completed")

            total_revenue = completed_rides.aggregate(
                total=Sum("fare"))["total"] or 0

            avg_fare = completed_rides.aggregate(avg=Avg("fare"))["avg"] or 0

            # Rides by status
            status_breakdown = rides.values(
                "status").annotate(count=Count("id"))

            return {
                "total_rides": rides.count(),
                "completed_rides": completed_rides.count(),
                "total_revenue": float(total_revenue),
                "average_fare": float(avg_fare),
                "status_breakdown": {
                    item["status"]: item["count"] for item in status_breakdown
                },
                "completion_rate": (
                    (completed_rides.count() / rides.count() * 100)
                    if rides.count() > 0
                    else 0
                ),
            }
        except ImportError:
            return {"error": "Rides module not available"}

    def _get_courier_analytics(self, start_date):
        """Get courier service analytics"""
        try:
            from couriers.models import DeliveryRequest

            deliveries = DeliveryRequest.objects.filter(
                requested_at__gte=start_date)
            completed = deliveries.filter(status="delivered")

            total_revenue = completed.aggregate(
                total=Sum("total_fare"))["total"] or 0

            avg_fare = completed.aggregate(avg=Avg("total_fare"))["avg"] or 0

            status_breakdown = deliveries.values(
                "status").annotate(count=Count("id"))

            return {
                "total_deliveries": deliveries.count(),
                "completed_deliveries": completed.count(),
                "total_revenue": float(total_revenue),
                "average_fare": float(avg_fare),
                "status_breakdown": {
                    item["status"]: item["count"] for item in status_breakdown
                },
                "completion_rate": (
                    (completed.count() / deliveries.count() * 100)
                    if deliveries.count() > 0
                    else 0
                ),
            }
        except ImportError:
            return {"error": "Couriers module not available"}

    def _get_rental_analytics(self, start_date):
        """Get rental service analytics"""
        try:
            from rentals.models import RentalBooking
            from django.db.models import F, ExpressionWrapper, fields

            rentals = RentalBooking.objects.filter(booked_at__gte=start_date)
            completed = rentals.filter(status="completed")

            total_revenue = (
                rentals.filter(status__in=["completed", "active"]).aggregate(
                    total=Sum("total_amount")
                )["total"]
                or 0
            )

            # Calculate duration as difference between end_date and start_date
            avg_duration = completed.annotate(
                duration=ExpressionWrapper(
                    F("end_date") - F("start_date"), output_field=fields.DurationField()
                )
            ).aggregate(avg=Avg("duration"))["avg"]

            # Convert timedelta to days if not None
            avg_duration_days = avg_duration.days if avg_duration else 0

            status_breakdown = rentals.values(
                "status").annotate(count=Count("id"))

            return {
                "total_rentals": rentals.count(),
                "completed_rentals": completed.count(),
                "active_rentals": rentals.filter(status="active").count(),
                "total_revenue": float(total_revenue),
                "average_duration_days": float(avg_duration_days),
                "status_breakdown": {
                    item["status"]: item["count"] for item in status_breakdown
                },
            }
        except ImportError:
            return {"error": "Rentals module not available"}

    def _get_mechanic_analytics(self, start_date):
        """Get mechanic service analytics"""
        try:
            from mechanics.models import (
                RepairRequest, 
                # TrainingSession
            )

            repairs = RepairRequest.objects.filter(
                requested_at__gte=start_date)
            # sessions = TrainingSession.objects.filter(
            #     created_at__gte=start_date)

            repair_status = repairs.values(
                "status").annotate(count=Count("id"))

            # session_status = sessions.values(
            #     "status").annotate(count=Count("id"))

            # Repair requests timeline for line chart (grouped by date)
            repair_timeline = (
                repairs
                .annotate(date=TruncDate("requested_at"))
                .values("date")
                .annotate(count=Count("id"))
                .order_by("date")
            )

            return {
                "total_repairs": repairs.count(),
                "completed_repairs": repairs.filter(status="completed").count(),
                "pending_repairs": repairs.filter(status="pending").count(),
                "repair_status_breakdown": {
                    item["status"]: item["count"] for item in repair_status
                },
                # "total_sessions": sessions.count(),
                # "active_sessions": sessions.filter(status="in_progress").count(),
                # "session_status_breakdown": {
                #     item["status"]: item["count"] for item in session_status
                # },
                "repair_timeline": list(repair_timeline),
            }
        except ImportError:
            return {"error": "Mechanics module not available"}

    def _parse_period(self, period):
        period_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        return period_map.get(period, 30)


class RevenueAnalyticsView(APIView):
    """Comprehensive revenue analytics across all services with individual breakdowns"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get comprehensive revenue analytics with individual service breakdowns",
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date (YYYY-MM-DD format)",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date (YYYY-MM-DD format)",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y) - ignored if start_date provided",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
        ],
        responses={200: openapi.Response("Revenue analytics data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Parse date range
        start_date, end_date = self._parse_date_range(request)
        
        # Validate date range
        if start_date and end_date and start_date > end_date:
            return Response(
                api_response(message="Start date cannot be after end date", status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Get individual revenue sources
        revenue_sources = self._get_revenue_by_source(start_date, end_date)
        
        # Get individual timelines for each service
        period = request.query_params.get("period", "30d")
        revenue_timelines = self._get_revenue_timelines(start_date, end_date, period)
        
        # Calculate total revenue
        total_revenue = sum(revenue_sources.values())

        return Response(
            api_response(
                message="Revenue analytics retrieved successfully.",
                status=True,
                data={
                    "date_range": {
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                    },
                    "total_revenue": round(total_revenue, 2),
                    "revenue_by_source": revenue_sources,
                    "revenue_timelines": revenue_timelines,
                },
            )
        )

    def _parse_date_range(self, request):
        """Parse date range from request parameters"""
        from datetime import datetime
        
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                start_date = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            except ValueError:
                return None, None
        else:
            # Use period-based calculation
            period = request.query_params.get("period", "30d")
            days = self._parse_period(period)
            start_date = timezone.now() - timedelta(days=days)
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
            except ValueError:
                return None, None
        else:
            end_date = timezone.now()
        
        return start_date, end_date

    def _get_revenue_by_source(self, start_date, end_date):
        """Get revenue breakdown by individual service sources"""
        revenue_sources = {}

        # Product sales revenue
        product_revenue = (
            Order.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date,
                status__in=["paid", "shipped", "completed"]
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )
        revenue_sources["products"] = float(product_revenue)

        # Rides revenue if available
        try:
            from rides.models import Ride
            rides_revenue = (
                Ride.objects.filter(
                    requested_at__gte=start_date,
                    requested_at__lte=end_date,
                    status="completed"
                ).aggregate(total=Sum("fare"))["total"]
                or 0
            )
            revenue_sources["rides"] = float(rides_revenue)
        except ImportError:
            revenue_sources["rides"] = 0.0

        # Courier revenue if available
        try:
            from couriers.models import DeliveryRequest
            courier_revenue = (
                DeliveryRequest.objects.filter(
                    requested_at__gte=start_date,
                    requested_at__lte=end_date,
                    status="delivered"
                ).aggregate(total=Sum("total_fare"))["total"]
                or 0
            )
            revenue_sources["couriers"] = float(courier_revenue)
        except ImportError:
            revenue_sources["couriers"] = 0.0

        # Rental revenue if available
        try:
            from rentals.models import RentalBooking
            rental_revenue = (
                RentalBooking.objects.filter(
                    booked_at__gte=start_date,
                    booked_at__lte=end_date,
                    status__in=["completed", "active"]
                ).aggregate(total=Sum("total_amount"))["total"]
                or 0
            )
            revenue_sources["rentals"] = float(rental_revenue)
        except ImportError:
            revenue_sources["rentals"] = 0.0

        return revenue_sources

    def _get_revenue_timelines(self, start_date, end_date, period):
        """Get individual revenue timelines for each service"""
        timelines = {}

        # Products timeline
        timelines["products"] = self._get_service_timeline(
            Order.objects.filter(status__in=["paid", "shipped", "completed"]),
            "created_at",
            "total_amount",
            start_date,
            end_date,
            period,
        )

        # Rides timeline if available
        try:
            from rides.models import Ride
            timelines["rides"] = self._get_service_timeline(
                Ride.objects.filter(status="completed"),
                "requested_at",
                "fare",
                start_date,
                end_date,
                period,
            )
        except ImportError:
            timelines["rides"] = []

        # Couriers timeline if available
        try:
            from couriers.models import DeliveryRequest
            timelines["couriers"] = self._get_service_timeline(
                DeliveryRequest.objects.filter(status="delivered"),
                "requested_at",
                "total_fare",
                start_date,
                end_date,
                period,
            )
        except ImportError:
            timelines["couriers"] = []

        # Rentals timeline if available
        try:
            from rentals.models import RentalBooking
            timelines["rentals"] = self._get_service_timeline(
                RentalBooking.objects.filter(status__in=["completed", "active"]),
                "booked_at",
                "total_amount",
                start_date,
                end_date,
                period,
            )
        except ImportError:
            timelines["rentals"] = []

        return timelines

    def _get_service_timeline(self, queryset, date_field, amount_field, start_date, end_date, period):
        """Generic method to get revenue timeline for any service"""
        filtered_queryset = queryset.filter(
            **{f'{date_field}__gte': start_date, f'{date_field}__lte': end_date}
        )

        # Determine granularity based on period
        if period in ['90d', '1y']:
            # Monthly granularity for longer periods
            timeline = (
                filtered_queryset.annotate(period=TruncMonth(date_field))
                .values("period")
                .annotate(revenue=Sum(amount_field))
                .order_by("period")
            )
        elif period == '7d':
            # Daily granularity for short period
            timeline = (
                filtered_queryset.annotate(period=TruncDate(date_field))
                .values("period")
                .annotate(revenue=Sum(amount_field))
                .order_by("period")
            )
        else:  # 30d default - daily granularity
            timeline = (
                filtered_queryset.annotate(period=TruncDate(date_field))
                .values("period")
                .annotate(revenue=Sum(amount_field))
                .order_by("period")
            )

        return [
            {
                "period": item["period"].isoformat(),
                "revenue": float(item["revenue"] or 0)
            }
            for item in timeline
        ]

    def _parse_period(self, period):
        period_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        return period_map.get(period, 30)


class TopPerformersView(APIView):
    """Analytics for top performing entities"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get top performers",
        manual_parameters=[
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of top items to return",
                type=openapi.TYPE_INTEGER,
                default=10,
            ),
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, all)",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
        ],
        responses={200: openapi.Response("Top performers data")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        limit = int(request.query_params.get("limit", 10))
        period = request.query_params.get("period", "30d")

        # Date filter
        if period != "all":
            days = self._parse_period(period)
            start_date = timezone.now() - timedelta(days=days)
            order_filter = Q(order__created_at__gte=start_date)
        else:
            order_filter = Q()

        # Top products by revenue
        top_products = (
            OrderItem.objects.filter(
                order__status__in=["paid", "shipped", "completed"])
            .filter(order_filter)
            .values("product__id", "product__name")
            .annotate(
                revenue=Sum(
                    ExpressionWrapper(
                        F("price") * F("quantity"),
                        output_field=DecimalField(
                            max_digits=12, decimal_places=2),
                    )
                ),
                quantity_sold=Sum("quantity"),
                order_count=Count("order__id", distinct=True),
            )
            .order_by("-revenue")[:limit]
        )

        # Top merchants
        top_merchants = (
            OrderItem.objects.filter(
                order__status__in=["paid", "shipped", "completed"])
            .filter(order_filter)
            .values(
                "product__merchant__id",
                "product__merchant__email",
                "product__merchant__first_name",
                "product__merchant__last_name",
            )
            .annotate(
                revenue=Sum(
                    ExpressionWrapper(
                        F("price") * F("quantity"),
                        output_field=DecimalField(
                            max_digits=12, decimal_places=2),
                    )
                ),
                order_count=Count("order__id", distinct=True),
            )
            .order_by("-revenue")[:limit]
        )

        # Top drivers (if available)
        top_drivers = []
        try:
            from rides.models import Ride

            driver_filter = Q(
                requested_at__gte=start_date) if period != "all" else Q()
            top_drivers = (
                Ride.objects.filter(status="completed")
                .filter(driver_filter)
                .values(
                    "driver__id",
                    "driver__email",
                    "driver__first_name",
                    "driver__last_name",
                )
                .annotate(total_rides=Count("id"), total_revenue=Sum("fare"))
                .order_by("-total_revenue")[:limit]
            )
            top_drivers = list(top_drivers)
        except ImportError:
            pass

        return Response(
            api_response(
                message="Top performers retrieved successfully.",
                status=True,
                data={
                    "period": period,
                    "top_products": list(top_products),
                    "top_merchants": list(top_merchants),
                    "top_drivers": top_drivers,
                },
            )
        )

    def _parse_period(self, period):
        period_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        return period_map.get(period, 30)


class GeographicHeatMapView(APIView):
    """
    Geographic heat map showing locations of all user roles:
    - Merchants
    - Mechanics  
    - Drivers
    - Active rides
    - Active deliveries
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get geographic data for map visualization with pagination",
        manual_parameters=[
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of items per role (10, 20, 30, 50, 100)",
                type=openapi.TYPE_INTEGER,
                default=20,
            ),
            openapi.Parameter(
                "role",
                openapi.IN_QUERY,
                description="Filter by role (merchant, mechanic, driver, rides, deliveries, all)",
                type=openapi.TYPE_STRING,
                default="all",
            ),
            openapi.Parameter(
                "active_only",
                openapi.IN_QUERY,
                description="Show only active items (true/false)",
                type=openapi.TYPE_BOOLEAN,
                default="false",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Geographic map data",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "merchants": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "mechanics": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "drivers": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "active_rides": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "active_deliveries": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "summary": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "total_locations": openapi.Schema(type=openapi.TYPE_INTEGER),
                                "role_counts": openapi.Schema(type=openapi.TYPE_OBJECT),
                            },
                        ),
                    },
                ),
            )
        },
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Parse parameters
        limit = self._parse_limit(request.query_params.get("limit", "20"))
        role_filter = request.query_params.get("role", "all").lower()
        active_only = request.query_params.get("active_only", "false").lower() == "true"

        result = {}
        role_counts = {}

        # Get data based on role filter
        if role_filter in ["all", "merchant"]:
            result["merchants"], merchant_count = self._get_merchants(limit, active_only)
            role_counts["merchants"] = merchant_count

        if role_filter in ["all", "mechanic"]:
            result["mechanics"], mechanic_count = self._get_mechanics(limit, active_only)
            role_counts["mechanics"] = mechanic_count

        if role_filter in ["all", "driver"]:
            result["drivers"], driver_count = self._get_drivers(limit, active_only)
            role_counts["drivers"] = driver_count

        if role_filter in ["all", "rides"]:
            result["active_rides"], ride_count = self._get_active_rides(limit)
            role_counts["active_rides"] = ride_count

        if role_filter in ["all", "deliveries"]:
            result["active_deliveries"], delivery_count = self._get_active_deliveries(limit)
            role_counts["active_deliveries"] = delivery_count

        # Calculate summary
        total_locations = sum(role_counts.values())

        return Response(
            api_response(
                message="Geographic map data retrieved successfully.",
                status=True,
                data={
                    **result,
                    "summary": {
                        "total_locations": total_locations,
                        "role_counts": role_counts,
                    },
                },
            )
        )

    def _parse_limit(self, limit_str):
        """Parse and validate limit parameter"""
        try:
            limit = int(limit_str)
            # Allowed limits: 10, 20, 30, 50, 100
            allowed_limits = [10, 20, 30, 50, 100]
            return limit if limit in allowed_limits else 20
        except (ValueError, TypeError):
            return 20

    def _get_merchants(self, limit, active_only=False):
        """Get merchant locations"""
        try:
            from users.models import MerchantProfile
            
            queryset = MerchantProfile.objects.all()
            
            if active_only:
                # Filter for merchants with recent activity
                queryset = queryset.filter(
                    user__is_active=True,
                    updated_at__gte=timezone.now() - timedelta(days=7)
                )
            
            merchants = queryset.select_related("user")[:limit]
            
            merchant_data = []
            for merchant in merchants:
                # MerchantProfile has location (text) but no latitude/longitude
                if merchant.location or merchant.business_address:
                    merchant_data.append({
                        "id": str(merchant.id),
                        "user_id": str(merchant.user.id),
                        "name": f"{merchant.user.first_name} {merchant.user.last_name}",
                        "email": merchant.user.email,
                        "business_name": getattr(merchant, 'business_name', 'N/A'),
                        "location": {
                            "address": merchant.location or merchant.business_address,
                            "latitude": None,
                            "longitude": None,
                        },
                        "is_active": merchant.user.is_active,
                        "last_updated": merchant.updated_at.isoformat(),
                    })
            
            return merchant_data, len(merchant_data)
        except ImportError:
            return [], 0

    def _get_mechanics(self, limit, active_only=False):
        """Get mechanic locations"""
        try:
            from users.models import MechanicProfile
            
            queryset = MechanicProfile.objects.all()
            
            if active_only:
                # Filter for approved and recently active mechanics
                queryset = queryset.filter(
                    is_approved=True,
                    user__is_active=True,
                    updated_at__gte=timezone.now() - timedelta(days=7)
                )
            
            mechanics = queryset.select_related("user")[:limit]
            
            mechanic_data = []
            for mechanic in mechanics:
                if mechanic.latitude and mechanic.longitude:
                    mechanic_data.append({
                        "id": str(mechanic.id),
                        "user_id": str(mechanic.user.id),
                        "name": f"{mechanic.user.first_name} {mechanic.user.last_name}",
                        "email": mechanic.user.email,
                        "location": {
                            "latitude": float(mechanic.latitude),
                            "longitude": float(mechanic.longitude),
                            "address": mechanic.location,
                        },
                        "is_approved": mechanic.is_approved,
                        "is_active": mechanic.user.is_active,
                        "specialization": getattr(mechanic, 'specialization', None),
                        "last_updated": mechanic.updated_at.isoformat(),
                    })
            
            return mechanic_data, len(mechanic_data)
        except ImportError:
            return [], 0

    def _get_drivers(self, limit, active_only=False):
        """Get driver locations"""
        try:
            from users.models import DriverProfile
            
            queryset = DriverProfile.objects.all()
            
            if active_only:
                # Filter for approved and recently active drivers
                queryset = queryset.filter(
                    is_approved=True,
                    user__is_active=True,
                    updated_at__gte=timezone.now() - timedelta(days=7)
                )
            
            drivers = queryset.select_related("user")[:limit]
            
            driver_data = []
            for driver in drivers:
                if driver.latitude and driver.longitude:
                    driver_data.append({
                        "id": str(driver.id),
                        "user_id": str(driver.user.id),
                        "name": f"{driver.user.first_name} {driver.user.last_name}",
                        "email": driver.user.email,
                        "location": {
                            "latitude": float(driver.latitude),
                            "longitude": float(driver.longitude),
                            "address": driver.location,
                        },
                        "is_approved": driver.is_approved,
                        "is_active": driver.user.is_active,
                        "vehicle_type": getattr(driver, 'vehicle_type', None),
                        "last_updated": driver.updated_at.isoformat(),
                    })
            
            return driver_data, len(driver_data)
        except ImportError:
            return [], 0

    def _get_active_rides(self, limit):
        """Get active ride locations"""
        try:
            from rides.models import Ride
            
            rides = Ride.objects.filter(
                status__in=["accepted", "in_progress"]
            ).select_related("driver", "customer")[:limit]
            
            ride_data = []
            for ride in rides:
                # Use current location if available, otherwise pickup location
                lat = ride.current_latitude if hasattr(ride, 'current_latitude') and ride.current_latitude else ride.pickup_latitude
                lng = ride.current_longitude if hasattr(ride, 'current_longitude') and ride.current_longitude else ride.pickup_longitude
                
                if lat and lng:
                    ride_data.append({
                        "id": str(ride.id),
                        "type": "ride",
                        "status": ride.status,
                        "driver": {
                            "id": str(ride.driver.id) if ride.driver else None,
                            "name": f"{ride.driver.first_name} {ride.driver.last_name}" if ride.driver else None,
                        },
                        "customer": {
                            "id": str(ride.customer.id) if ride.customer else None,
                            "name": f"{ride.customer.first_name} {ride.customer.last_name}" if ride.customer else None,
                        },
                        "location": {
                            "latitude": float(lat),
                            "longitude": float(lng),
                        },
                        "pickup_location": {
                            "latitude": float(ride.pickup_latitude) if ride.pickup_latitude else None,
                            "longitude": float(ride.pickup_longitude) if ride.pickup_longitude else None,
                            "address": ride.pickup_address,
                        },
                        "dropoff_location": {
                            "latitude": float(ride.dropoff_latitude) if ride.dropoff_latitude else None,
                            "longitude": float(ride.dropoff_longitude) if ride.dropoff_longitude else None,
                            "address": ride.dropoff_address,
                        },
                        "fare": float(ride.fare) if ride.fare else 0,
                        "requested_at": ride.requested_at.isoformat() if ride.requested_at else None,
                    })
            
            return ride_data, len(ride_data)
        except ImportError:
            return [], 0

    def _get_active_deliveries(self, limit):
        """Get active delivery locations"""
        try:
            from couriers.models import DeliveryRequest
            
            deliveries = DeliveryRequest.objects.filter(
                status__in=["assigned", "picked_up", "in_transit"]
            ).select_related("driver", "customer")[:limit]
            
            delivery_data = []
            for delivery in deliveries:
                # Use current location if available, otherwise pickup location
                lat = delivery.current_latitude if hasattr(delivery, 'current_latitude') and delivery.current_latitude else delivery.pickup_latitude
                lng = delivery.current_longitude if hasattr(delivery, 'current_longitude') and delivery.current_longitude else delivery.pickup_longitude
                
                if lat and lng:
                    delivery_data.append({
                        "id": str(delivery.id),
                        "type": "delivery",
                        "status": delivery.status,
                        "driver": {
                            "id": str(delivery.driver.id) if delivery.driver else None,
                            "name": f"{delivery.driver.first_name} {delivery.driver.last_name}" if delivery.driver else None,
                        },
                        "customer": {
                            "id": str(delivery.customer.id) if delivery.customer else None,
                            "name": f"{delivery.customer.first_name} {delivery.customer.last_name}" if delivery.customer else None,
                        },
                        "location": {
                            "latitude": float(lat),
                            "longitude": float(lng),
                        },
                        "pickup_location": {
                            "latitude": float(delivery.pickup_latitude) if delivery.pickup_latitude else None,
                            "longitude": float(delivery.pickup_longitude) if delivery.pickup_longitude else None,
                            "address": delivery.pickup_address,
                        },
                        "dropoff_location": {
                            "latitude": float(delivery.delivery_latitude) if delivery.delivery_latitude else None,
                            "longitude": float(delivery.delivery_longitude) if delivery.delivery_longitude else None,
                            "address": delivery.delivery_address,
                        },
                        "total_fare": float(delivery.total_fare) if delivery.total_fare else 0,
                        "requested_at": delivery.requested_at.isoformat() if delivery.requested_at else None,
                    })
            
            return delivery_data, len(delivery_data)
        except ImportError:
            return [], 0


class OngoingActivitiesFeedView(APIView):
    """
    Real-time feed of ongoing activities including:
    - Active rides
    - Deliveries in progress
    - Mechanic visits
    - Recent transactions
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get real-time feed of ongoing activities",
        manual_parameters=[
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of activities to return per category",
                type=openapi.TYPE_INTEGER,
                default=20,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Ongoing activities feed",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "activities": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "summary": openapi.Schema(type=openapi.TYPE_OBJECT),
                    },
                ),
            )
        },
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        limit = int(request.query_params.get("limit", 20))
        activities = []

        # ====================================================================
        # ACTIVE RIDES
        # ====================================================================
        try:
            from rides.models import Ride

            active_rides = (
                Ride.objects.filter(
                    status__in=["requested", "accepted", "in_progress"])
                .select_related("driver", "customer")
                .order_by("-requested_at")[:limit]
            )

            for ride in active_rides:
                activity = {
                    "id": str(ride.id),
                    "type": "ride",
                    "status": ride.status,
                    "title": f"Ride #{ride.id}",
                    "description": f"Ride {ride.status.replace('_', ' ')} by {ride.driver.first_name if ride.driver else 'Unassigned'}",
                    "driver": {
                        "id": str(ride.driver.id) if ride.driver else None,
                        "name": (
                            f"{ride.driver.first_name} {ride.driver.last_name}"
                            if ride.driver
                            else "Unassigned"
                        ),
                    },
                    "customer": {
                        "id": str(ride.customer.id) if ride.customer else None,
                        "name": (
                            f"{ride.customer.first_name} {ride.customer.last_name}"
                            if ride.customer
                            else None
                        ),
                    },
                    "pickup_address": ride.pickup_address,
                    "dropoff_address": ride.dropoff_address,
                    "fare": float(ride.fare) if ride.fare else 0,
                    "requested_at": (
                        ride.requested_at.isoformat() if ride.requested_at else None
                    ),
                    "accepted_at": (
                        ride.accepted_at.isoformat() if ride.accepted_at else None
                    ),
                    "timestamp": (
                        ride.requested_at.isoformat() if ride.requested_at else None
                    ),
                }
                activities.append(activity)
        except ImportError:
            pass

        # ====================================================================
        # ACTIVE DELIVERIES
        # ====================================================================
        try:
            from couriers.models import DeliveryRequest

            active_deliveries = (
                DeliveryRequest.objects.filter(
                    status__in=["pending", "assigned",
                                "picked_up", "in_transit"]
                )
                .select_related("driver", "customer")
                .order_by("-requested_at")[:limit]
            )
            for delivery in active_deliveries:
                activity = {
                    "id": str(delivery.id),
                    "type": "delivery",
                    "status": delivery.status,
                    "title": f"Delivery #{delivery.id}",
                    "description": f"Delivery {delivery.status.replace('_', ' ')} by {delivery.driver.first_name if delivery.driver else 'Unassigned'}",
                    "driver": {
                        "id": str(delivery.driver.id) if delivery.driver else None,
                        "name": (
                            f"{delivery.driver.first_name} {delivery.driver.last_name}"
                            if delivery.driver
                            else "Unassigned"
                        ),
                    },
                    "customer": {
                        "id": str(delivery.customer.id) if delivery.customer else None,
                        "name": (
                            f"{delivery.customer.first_name} {delivery.customer.last_name}"
                            if delivery.customer
                            else None
                        ),
                    },
                    "pickup_address": delivery.pickup_address,
                    "dropoff_address": delivery.dropoff_address,
                    "total_fare": (
                        float(delivery.total_fare) if delivery.total_fare else 0
                    ),
                    "requested_at": (
                        delivery.requested_at.isoformat()
                        if delivery.requested_at
                        else None
                    ),
                    "assigned_at": (
                        delivery.assigned_at.isoformat()
                        if delivery.assigned_at
                        else None
                    ),
                    "timestamp": (
                        delivery.requested_at.isoformat()
                        if delivery.requested_at
                        else None
                    ),
                }
                activities.append(activity)
        except ImportError:
            pass

        # ====================================================================
        # MECHANIC VISITS
        # ====================================================================
        try:
            from mechanics.models import RepairRequest

            active_repairs = (
                RepairRequest.objects.filter(
                    status__in=["pending", "accepted",
                                "in_transit", "in_progress"]
                )
                .select_related("mechanic", "customer")
                .order_by("-requested_at")[:limit]
            )

            for repair in active_repairs:
                # Get mechanic profile if available
                mechanic_profile = None
                mechanic_name = "Unassigned"
                mechanic_specialization = None

                if repair.mechanic:
                    mechanic_name = (
                        f"{repair.mechanic.first_name} {repair.mechanic.last_name}"
                    )
                    try:
                        mechanic_profile = repair.mechanic.mechanic_profile
                        if mechanic_profile and hasattr(
                            mechanic_profile, "specialization"
                        ):
                            mechanic_specialization = mechanic_profile.specialization
                    except:
                        pass

                activity = {
                    "id": str(repair.id),
                    "type": "mechanic_visit",
                    "status": repair.status,
                    "title": f"Mechanic Visit #{repair.id}",
                    "description": f"Repair {repair.status.replace('_', ' ')} by {mechanic_name}",
                    "mechanic": {
                        "id": str(repair.mechanic.id) if repair.mechanic else None,
                        "name": mechanic_name,
                        "specialization": mechanic_specialization,
                    },
                    "customer": {
                        "id": str(repair.customer.id) if repair.customer else None,
                        "name": (
                            f"{repair.customer.first_name} {repair.customer.last_name}"
                            if repair.customer
                            else None
                        ),
                    },
                    "service_type": repair.service_type,
                    "address": repair.service_address,
                    "estimated_cost": (
                        float(repair.estimated_cost) if repair.estimated_cost else 0
                    ),
                    "requested_at": (
                        repair.requested_at.isoformat() if repair.requested_at else None
                    ),
                    "accepted_at": (
                        repair.accepted_at.isoformat() if repair.accepted_at else None
                    ),
                    "timestamp": (
                        repair.requested_at.isoformat() if repair.requested_at else None
                    ),
                }
                activities.append(activity)
        except ImportError:
            pass

        # ====================================================================
        # RECENT ORDERS
        # ====================================================================
        recent_orders = (
            Order.objects.filter(status__in=["pending", "paid", "shipped"])
            .select_related("customer")
            .order_by("-created_at")[:limit]
        )

        for order in recent_orders:
            activity = {
                "id": str(order.id),
                "type": "order",
                "status": order.status,
                "title": f"Order #{order.id}",
                "description": f"Order {order.status} by {order.customer.first_name if order.customer else 'Guest'}",
                "customer": {
                    "id": str(order.customer.id) if order.customer else None,
                    "name": (
                        f"{order.customer.first_name} {order.customer.last_name}"
                        if order.customer
                        else "Guest"
                    ),
                },
                "total_amount": float(order.total_amount),
                "created_at": (
                    order.created_at.isoformat() if order.created_at else None
                ),
                "timestamp": order.created_at.isoformat() if order.created_at else None,
            }
            activities.append(activity)

        # ====================================================================
        # ACTIVE RENTALS
        # ====================================================================
        try:
            from rentals.models import RentalBooking

            active_rentals = (
                RentalBooking.objects.filter(
                    status__in=["pending", "confirmed", "active"]
                )
                .select_related("customer", "product")
                .order_by("-booked_at")[:limit]
            )
            for rental in active_rentals:
                activity = {
                    "id": str(rental.id),
                    "type": "rental",
                    "status": rental.status,
                    "title": f"Car Rental #{rental.id}",
                    "description": f"Rental {rental.status} by {rental.customer.first_name if rental.customer else 'Unknown'}",
                    "customer": {
                        "id": str(rental.customer.id) if rental.customer else None,
                        "name": (
                            f"{rental.customer.first_name} {rental.customer.last_name}"
                            if rental.customer
                            else None
                        ),
                    },
                    "car": {
                        "id": str(rental.car.id) if rental.car else None,
                        "name": (
                            f"{rental.car.make} {rental.car.model}"
                            if rental.car
                            else None
                        ),
                    },
                    "total_amount": (
                        float(rental.total_amount) if rental.total_amount else 0
                    ),
                    "start_date": (
                        rental.start_date.isoformat() if rental.start_date else None
                    ),
                    "end_date": (
                        rental.end_date.isoformat() if rental.end_date else None
                    ),
                    "booked_at": (
                        rental.booked_at.isoformat() if rental.booked_at else None
                    ),
                    "timestamp": (
                        rental.booked_at.isoformat() if rental.booked_at else None
                    ),
                }
                activities.append(activity)
        except ImportError:
            pass

        # Sort all activities by timestamp (most recent first)
        activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # ====================================================================
        # SUMMARY STATISTICS
        # ====================================================================
        summary = {
            "total_activities": len(activities),
            "active_rides": len([a for a in activities if a["type"] == "ride"]),
            "active_deliveries": len(
                [a for a in activities if a["type"] == "delivery"]
            ),
            "active_mechanic_visits": len(
                [a for a in activities if a["type"] == "mechanic_visit"]
            ),
            "recent_orders": len([a for a in activities if a["type"] == "order"]),
            "active_rentals": len([a for a in activities if a["type"] == "rental"]),
            "timestamp": timezone.now().isoformat(),
        }

        return Response(
            api_response(
                message="Ongoing activities feed retrieved successfully.",
                status=True,
                data={
                    # Return only the requested limit
                    "activities": activities[:limit],
                    "summary": summary,
                },
            )
        )


# ============================================================================
# FEEDBACK MANAGEMENT ENDPOINTS
# ============================================================================


class ProductReviewManagementView(APIView):
    """
    View for managing product reviews
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get all product reviews with filtering options",
        manual_parameters=[
            openapi.Parameter(
                "rating",
                openapi.IN_QUERY,
                description="Filter by rating (1-5)",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "approved",
                openapi.IN_QUERY,
                description="Filter by approval status",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of results to return",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Number of results to skip",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: "Product reviews retrieved successfully"},
    )
    def get(self, request):
        from products.models import ProductReview

        rating = request.query_params.get("rating")
        approved = request.query_params.get("approved")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        queryset = ProductReview.objects.all().select_related("user", "product")

        if rating:
            queryset = queryset.filter(rating=rating)
        if approved is not None:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_approved=is_approved)

        total_count = queryset.count()
        reviews = queryset[offset: offset + limit]

        # Serialize reviews
        review_data = []
        for review in reviews:
            review_data.append(
                {
                    "id": str(review.id),
                    "user": {
                        "id": str(review.user.id),
                        "email": review.user.email,
                        "full_name": review.user.get_full_name(),
                    },
                    "product": {
                        "id": str(review.product.id),
                        "name": review.product.name,
                    },
                    "rating": review.rating,
                    "comment": review.comment,
                    "is_approved": getattr(review, "is_approved", True),
                    "created_at": review.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Product reviews retrieved successfully",
                status=True,
                data={
                    "reviews": review_data,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

    @swagger_auto_schema(
        operation_description="Approve or reject product review",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["review_id", "approved"],
            properties={
                "review_id": openapi.Schema(type=openapi.TYPE_STRING),
                "approved": openapi.Schema(type=openapi.TYPE_BOOLEAN),
            },
        ),
        responses={200: "Review status updated successfully"},
    )
    def post(self, request):
        from products.models import ProductReview

        review_id = request.data.get("review_id")
        approved = request.data.get("approved")

        if not review_id or approved is None:
            return Response(
                api_response(
                    message="review_id and approved are required", status=False
                ),
                status=400,
            )

        try:
            review = ProductReview.objects.get(id=review_id)
            review.is_approved = approved
            review.save()

            action = "approved" if approved else "rejected"
            return Response(
                api_response(
                    message=f"Product review {action} successfully",
                    status=True,
                    data={
                        "review_id": str(review.id),
                        "is_approved": review.is_approved,
                    },
                )
            )
        except ProductReview.DoesNotExist:
            return Response(
                api_response(message="Review not found", status=False), status=404
            )


class MerchantReviewManagementView(APIView):
    """
    View for managing merchant reviews
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get all merchant reviews with filtering options",
        manual_parameters=[
            openapi.Parameter(
                "rating",
                openapi.IN_QUERY,
                description="Filter by rating (1-5)",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "approved",
                openapi.IN_QUERY,
                description="Filter by approval status",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of results to return",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Number of results to skip",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: "Mechanic reviews retrieved successfully"},
    )
    def get(self, request):
        # Assuming there's a MerchantReview model, adjust if needed
        from users.models import MechanicReview

        rating = request.query_params.get("rating")
        approved = request.query_params.get("approved")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        queryset = MechanicReview.objects.all().select_related("user", "mechanic")

        if rating:
            queryset = queryset.filter(rating=rating)
        if approved is not None:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_approved=is_approved)

        total_count = queryset.count()
        reviews = queryset[offset: offset + limit]

        review_data = []
        for review in reviews:
            review_data.append(
                {
                    "id": str(review.id),
                    "user": {
                        "id": str(review.user.id),
                        "email": review.user.email,
                        "full_name": review.user.get_full_name(),
                    },
                    "mechanic": {
                        "id": str(review.mechanic.id),
                        "name": review.mechanic.user.get_full_name()
                        or review.mechanic.user.email,
                    },
                    "rating": review.rating,
                    "comment": review.comment,
                    "is_approved": getattr(review, "is_approved", True),
                    "created_at": review.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Mechanic reviews retrieved successfully",
                status=True,
                data={
                    "reviews": review_data,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

    @swagger_auto_schema(
        operation_description="Approve or reject mechanic review",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["review_id", "approved"],
            properties={
                "review_id": openapi.Schema(type=openapi.TYPE_STRING),
                "approved": openapi.Schema(type=openapi.TYPE_BOOLEAN),
            },
        ),
        responses={200: "Review status updated successfully"},
    )
    def post(self, request):
        from users.models import MechanicReview

        review_id = request.data.get("review_id")
        approved = request.data.get("approved")

        if not review_id or approved is None:
            return Response(
                api_response(
                    message="review_id and approved are required", status=False
                ),
                status=400,
            )

        try:
            review = MechanicReview.objects.get(id=review_id)
            if hasattr(review, 'is_approved'):
                review.is_approved = approved
                review.save()

            action = "approved" if approved else "rejected"
            return Response(
                api_response(
                    message=f"Mechanic review {action} successfully",
                    status=True,
                    data={
                        'review_id': str(review.id),
                        'is_approved': getattr(review, 'is_approved', True)
                    }
                )
            )
        except MechanicReview.DoesNotExist:
            return Response(
                api_response(message="Review not found", status=False), status=404
            )


class MechanicReviewManagementView(APIView):
    """
    View for managing mechanic reviews
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get all mechanic reviews with filtering options",
        manual_parameters=[
            openapi.Parameter(
                "rating",
                openapi.IN_QUERY,
                description="Filter by rating (1-5)",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "approved",
                openapi.IN_QUERY,
                description="Filter by approval status",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of results to return",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Number of results to skip",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: "Mechanic reviews retrieved successfully"},
    )
    def get(self, request):
        from users.models import MechanicReview

        rating = request.query_params.get("rating")
        approved = request.query_params.get("approved")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        queryset = MechanicReview.objects.all().select_related("user", "mechanic__user")

        if rating:
            queryset = queryset.filter(rating=rating)
        if approved is not None:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_approved=is_approved)

        total_count = queryset.count()
        reviews = queryset[offset: offset + limit]

        review_data = []
        for review in reviews:
            review_data.append(
                {
                    "id": str(review.id),
                    "user": {
                        "id": str(review.user.id),
                        "email": review.user.email,
                        "full_name": review.user.get_full_name(),
                    },
                    "mechanic": {
                        "id": str(review.mechanic.id),
                        "name": review.mechanic.user.get_full_name()
                        or review.mechanic.user.email,
                    },
                    "rating": review.rating,
                    "comment": review.comment,
                    # MechanicReview might not have is_approved
                    "is_approved": getattr(review, "is_approved", True),
                    "created_at": review.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Mechanic reviews retrieved successfully",
                status=True,
                data={
                    "reviews": review_data,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

    @swagger_auto_schema(
        operation_description="Approve or reject mechanic review",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["review_id", "approved"],
            properties={
                "review_id": openapi.Schema(type=openapi.TYPE_STRING),
                "approved": openapi.Schema(type=openapi.TYPE_BOOLEAN),
            },
        ),
        responses={200: "Review status updated successfully"},
    )
    def post(self, request):
        from users.models import MechanicReview

        review_id = request.data.get("review_id")
        approved = request.data.get("approved")

        if not review_id or approved is None:
            return Response(
                api_response(
                    message="review_id and approved are required", status=False
                ),
                status=400,
            )

        try:
            review = MechanicReview.objects.get(id=review_id)
            if hasattr(review, "is_approved"):
                review.is_approved = approved
                review.save()

            action = "approved" if approved else "rejected"
            return Response(
                api_response(
                    message=f"Mechanic review {action} successfully",
                    status=True,
                    data={
                        "review_id": str(review.id),
                        "is_approved": getattr(review, "is_approved", True),
                    },
                )
            )
        except MechanicReview.DoesNotExist:
            return Response(
                api_response(message="Review not found", status=False), status=404
            )


class DriverReviewManagementView(APIView):
    """
    View for managing driver reviews
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get all driver reviews with filtering options",
        manual_parameters=[
            openapi.Parameter(
                "rating",
                openapi.IN_QUERY,
                description="Filter by rating (1-5)",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "approved",
                openapi.IN_QUERY,
                description="Filter by approval status",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of results to return",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Number of results to skip",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: "Driver reviews retrieved successfully"},
    )
    def get(self, request):
        # Assuming there's a DriverReview model, adjust if needed
        from users.models import DriverReview

        rating = request.query_params.get("rating")
        approved = request.query_params.get("approved")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        queryset = DriverReview.objects.all().select_related("user", "driver__user")

        if rating:
            queryset = queryset.filter(rating=rating)
        if approved is not None:
            is_approved = approved.lower() == "true"
            queryset = queryset.filter(is_approved=is_approved)

        total_count = queryset.count()
        reviews = queryset[offset: offset + limit]

        review_data = []
        for review in reviews:
            review_data.append(
                {
                    "id": str(review.id),
                    "user": {
                        "id": str(review.user.id),
                        "email": review.user.email,
                        "full_name": review.user.get_full_name(),
                    },
                    "driver": {
                        "id": str(review.driver.id),
                        "name": review.driver.user.get_full_name()
                        or review.driver.user.email,
                    },
                    "rating": review.rating,
                    "comment": review.comment,
                    "is_approved": getattr(review, "is_approved", True),
                    "created_at": review.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Driver reviews retrieved successfully",
                status=True,
                data={
                    "reviews": review_data,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

    @swagger_auto_schema(
        operation_description="Approve or reject driver review",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["review_id", "approved"],
            properties={
                "review_id": openapi.Schema(type=openapi.TYPE_STRING),
                "approved": openapi.Schema(type=openapi.TYPE_BOOLEAN),
            },
        ),
        responses={200: "Review status updated successfully"},
    )
    def post(self, request):
        from users.models import DriverReview

        review_id = request.data.get("review_id")
        approved = request.data.get("approved")

        if not review_id or approved is None:
            return Response(
                api_response(
                    message="review_id and approved are required", status=False
                ),
                status=400,
            )

        try:
            review = DriverReview.objects.get(id=review_id)
            if hasattr(review, 'is_approved'):
                review.is_approved = approved
                review.save()

            action = "approved" if approved else "rejected"
            return Response(
                api_response(
                    message=f"Driver review {action} successfully",
                    status=True,
                    data={
                        'review_id': str(review.id),
                        'is_approved': getattr(review, 'is_approved', True)
                    }
                )
            )
        except DriverReview.DoesNotExist:
            return Response(
                api_response(message="Review not found", status=False), status=404
            )


class AdminChatMessageView(APIView):
    """
    View for managing chat messages sent to admin
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get all chat messages sent to admin",
        manual_parameters=[
            openapi.Parameter(
                "room_id",
                openapi.IN_QUERY,
                description="Filter by specific chat room ID",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "read",
                openapi.IN_QUERY,
                description="Filter by read status",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of results to return",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description="Number of results to skip",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: "Chat messages retrieved successfully"},
    )
    def get(self, request):
        from communications.models import Message, ChatRoom
        from django.contrib.auth import get_user_model

        User = get_user_model()
        
        room_id = request.query_params.get("room_id")
        read_status = request.query_params.get("read")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        # Get admin users
        admin_users = User.objects.filter(is_staff=True)
        
        # Get chat rooms that include admin users
        admin_chat_rooms = ChatRoom.objects.filter(participants__in=admin_users).distinct()
        
        # Filter by specific room if provided
        if room_id:
            try:
                specific_room = ChatRoom.objects.get(id=room_id, participants__in=admin_users)
                admin_chat_rooms = ChatRoom.objects.filter(id=specific_room.id)
            except ChatRoom.DoesNotExist:
                return Response(
                    api_response(message="Chat room not found or not accessible", status=False),
                    status=404
                )
        
        # Get messages from these chat rooms
        queryset = Message.objects.filter(
            chat_room__in=admin_chat_rooms,
            message_type__in=["text", "image", "file"]
        ).select_related("sender").order_by("created_at")

        if read_status is not None:
            is_read = read_status.lower() == "true"
            if is_read:
                queryset = queryset.filter(read_at__isnull=False)
            else:
                queryset = queryset.filter(read_at__isnull=True)

        total_count = queryset.count()
        messages = queryset[offset: offset + limit]

        message_data = []
        for message in messages:
            message_data.append(
                {
                    "id": str(message.id),
                    "chat_room": {
                        "id": str(message.chat_room.id),
                        "participants": [
                            {
                                "id": str(participant.id),
                                "email": participant.email,
                                "full_name": participant.get_full_name(),
                            }
                            for participant in message.chat_room.participants.all()
                        ],
                    },
                    "sender": {
                        "id": str(message.sender.id),
                        "email": message.sender.email,
                        "full_name": message.sender.get_full_name(),
                    },
                    "message": message.content,
                    "message_type": message.message_type,
                    "is_read": message.is_read,
                    "created_at": message.created_at.isoformat(),
                }
            )

        return Response(
            api_response(
                message="Chat messages retrieved successfully",
                status=True,
                data={
                    "messages": message_data,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "room_id": room_id,
                },
            )
        )

    @swagger_auto_schema(
        operation_description="Mark chat message as read",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["message_id"],
            properties={
                "message_id": openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        responses={200: "Message marked as read successfully"},
    )
    def post(self, request):
        from communications.models import Message, ChatRoom
        from django.utils import timezone
        from django.contrib.auth import get_user_model

        User = get_user_model()

        message_id = request.data.get("message_id")

        if not message_id:
            return Response(
                api_response(message="message_id is required", status=False), status=400
            )

        try:
            # Get admin users
            admin_users = User.objects.filter(is_staff=True)

            # Get chat rooms that include admin users
            admin_chat_rooms = ChatRoom.objects.filter(
                participants__in=admin_users).distinct()

            message = Message.objects.get(
                id=message_id,
                chat_room__in=admin_chat_rooms,
                message_type__in=["text", "image", "file"]
            )
            message.read_at = timezone.now()
            message.save()

            return Response(
                api_response(
                    message="Message marked as read successfully",
                    status=True,
                    data={"message_id": str(message.id),
                          "is_read": message.is_read},
                )
            )
        except Message.DoesNotExist:
            return Response(
                api_response(message="Message not found", status=False), status=404
            )

    @swagger_auto_schema(
        operation_description="Reply to user chat message",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["message_id", "reply"],
            properties={
                "message_id": openapi.Schema(type=openapi.TYPE_STRING),
                "reply": openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        responses={200: "Reply sent successfully"},
    )
    def put(self, request):
        from communications.models import Message, ChatRoom
        from django.contrib.auth import get_user_model

        User = get_user_model()

        message_id = request.data.get("message_id")
        reply = request.data.get("reply")

        if not message_id or not reply:
            return Response(
                api_response(
                    message="message_id and reply are required", status=False),
                status=400,
            )

        try:
            # Get admin users
            admin_users = User.objects.filter(is_staff=True)

            # Get chat rooms that include admin users
            admin_chat_rooms = ChatRoom.objects.filter(
                participants__in=admin_users).distinct()

            original_message = Message.objects.get(
                id=message_id,
                chat_room__in=admin_chat_rooms,
                message_type__in=["text", "image", "file"]
            )

            # Create admin reply in the same chat room
            admin_user = request.user
            reply_message = Message.objects.create(
                chat_room=original_message.chat_room,
                sender=admin_user,
                content=reply,
                message_type="text",
            )

            return Response(
                api_response(
                    message="Reply sent successfully",
                    status=True,
                    data={
                        "original_message_id": str(original_message.id),
                        "reply_message_id": str(reply_message.id),
                        "reply": reply,
                    },
                )
            )
        except Message.DoesNotExist:
            return Response(
                api_response(
                    message="Original message not found", status=False),
                status=404,
            )


class ContactMessageListView(APIView):
    """
    API endpoint for admins to view and manage contact messages
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """Check if user is admin"""
        if self.request.method in ['GET', 'PUT', 'PATCH']:
            return [IsAuthenticated()]  # Allow authenticated users to view
        return [IsAuthenticated()]

    @swagger_auto_schema(
        operation_summary="List Contact Messages",
        operation_description="""
        **List all contact messages**

        This endpoint allows admins to view contact messages with filtering options.
        """,
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description="Filter by status (pending, in_progress, resolved, closed)",
                type=openapi.TYPE_STRING,
                enum=['pending', 'in_progress', 'resolved', 'closed']
            ),
            openapi.Parameter(
                'is_read',
                openapi.IN_QUERY,
                description="Filter by read status (true/false)",
                type=openapi.TYPE_BOOLEAN
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Search in name, email, or message content",
                type=openapi.TYPE_STRING
            ),
        ],
        responses={
            200: openapi.Response("Contact messages list", ContactMessageSerializer(many=True)),
            401: "Unauthorized",
        },
    )
    def get(self, request):
        """
        List contact messages with filtering
        """
        from users.models import ContactMessage

        queryset = ContactMessage.objects.all()

        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        is_read_filter = request.query_params.get('is_read')
        if is_read_filter is not None:
            is_read = is_read_filter.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_read=is_read)

        search_query = request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                models.Q(first_name__icontains=search_query) |
                models.Q(last_name__icontains=search_query) |
                models.Q(email__icontains=search_query) |
                models.Q(message__icontains=search_query) |
                models.Q(company_name__icontains=search_query)
            )

        # Order by creation date (newest first)
        queryset = queryset.order_by('-created_at')

        serializer = ContactMessageSerializer(queryset, many=True)
        return Response(
            api_response(
                message="Contact messages retrieved successfully",
                status=True,
                data=serializer.data
            )
        )

    # @swagger_auto_schema(
    #     operation_summary="Update Contact Message",
    #     operation_description="""
    #     **Update contact message status**

    #     This endpoint allows admins to update contact message status and response notes.
    #     """,
    #     request_body=ContactMessageAdminSerializer,
    #     responses={
    #         200: openapi.Response("Contact message updated", ContactMessageSerializer),
    #         400: "Bad Request",
    #         404: "Not Found",
    #         401: "Unauthorized",
    #     },
    # )
    # def patch(self, request, message_id=None):
        """
        Update a specific contact message (status, notes, etc.)
        """
        from users.models import ContactMessage

        if not message_id:
            return Response(
                api_response(message="Message ID is required", status=False),
                status=400
            )

        try:
            message = ContactMessage.objects.get(id=message_id)
        except ContactMessage.DoesNotExist:
            return Response(
                api_response(message="Contact message not found", status=False),
                status=404
            )

        serializer = ContactMessageAdminSerializer(
            message,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            updated_message = serializer.save()

            # Log the update
            logger.info(f"Contact message {message_id} updated by {request.user.email}")

            return Response(
                api_response(
                    message="Contact message updated successfully",
                    status=True,
                    data=ContactMessageSerializer(updated_message).data
                )
            )

        return Response(
            api_response(
                message="Validation failed",
                status=False,
                errors=serializer.errors
            ),
            status=400
        )


class ContactMessageDetailView(APIView):
    """
    API endpoint for admins to view and update individual contact messages
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Contact Message Details",
        operation_description="""
        **Get detailed contact message information**

        This endpoint allows admins to view detailed information about a specific contact message.
        """,
        responses={
            200: openapi.Response("Contact message details", ContactMessageSerializer),
            404: "Not Found",
            401: "Unauthorized",
        },
    )
    def get(self, request, message_id):
        """
        Get a specific contact message
        """
        from users.models import ContactMessage

        try:
            message = ContactMessage.objects.get(id=message_id)
        except ContactMessage.DoesNotExist:
            return Response(
                api_response(message="Contact message not found", status=False),
                status=404
            )

        # Mark as read if not already read
        if not message.is_read:
            message.is_read = True
            message.save()

        serializer = ContactMessageSerializer(message)
        return Response(
            api_response(
                message="Contact message retrieved successfully",
                status=True,
                data=serializer.data
            )
        )


class EmailSubscriptionListView(APIView):
    """API endpoint for admins to view email subscribers"""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List Email Subscribers",
        operation_description="""
        **List all email subscribers**

        This endpoint allows admins to view email subscriptions with optional filtering.
        """,
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description="Filter by status (active, unsubscribed)",
                type=openapi.TYPE_STRING,
                enum=['active', 'unsubscribed']
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Search by email, first name, or last name",
                type=openapi.TYPE_STRING
            ),
        ],
        responses={
            200: openapi.Response("Subscribers list", EmailSubscriptionSerializer(many=True)),
            401: "Unauthorized",
        },
    )
    def get(self, request):
        from users.models import EmailSubscription

        queryset = EmailSubscription.objects.all()

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        search_query = request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                models.Q(email__icontains=search_query) |
                models.Q(first_name__icontains=search_query) |
                models.Q(last_name__icontains=search_query)
            )

        queryset = queryset.order_by('-subscribed_at')
        serializer = EmailSubscriptionSerializer(queryset, many=True)

        return Response(
            api_response(
                message="Subscribers retrieved successfully",
                status=True,
                data=serializer.data,
            )
        )

    # @swagger_auto_schema(
    #     operation_summary="Update Contact Message",
    #     operation_description="""
    #     **Update contact message details**

    #     This endpoint allows admins to update contact message status, response notes, etc.
    #     """,
    #     request_body=ContactMessageAdminSerializer,
    #     responses={
    #         200: openapi.Response("Contact message updated", ContactMessageSerializer),
    #         400: "Bad Request",
    #         404: "Not Found",
    #         401: "Unauthorized",
    #     },
    # )
    # def put(self, request, message_id):
        """
        Update a contact message
        """
        from users.models import ContactMessage

        try:
            message = ContactMessage.objects.get(id=message_id)
        except ContactMessage.DoesNotExist:
            return Response(
                api_response(message="Contact message not found", status=False),
                status=404
            )

        serializer = ContactMessageAdminSerializer(message, data=request.data)

        if serializer.is_valid():
            updated_message = serializer.save()

            # Log the update
            logger.info(f"Contact message {message_id} updated by {request.user.email}")

            return Response(
                api_response(
                    message="Contact message updated successfully",
                    status=True,
                    data=ContactMessageSerializer(updated_message).data
                )
            )

        return Response(
            api_response(
                message="Validation failed",
                status=False,
                errors=serializer.errors
            ),
            status=400
        )
