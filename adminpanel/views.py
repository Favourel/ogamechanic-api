from rest_framework import status as http_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper, Avg, Q
from django.db.models.functions import TruncMonth, TruncDate
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
)
from products.models import Order, OrderItem
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
    Get high-level dashboard overview metrics with comprehensive analytics
    Supports period filtering: 7d, 30d, 90d, 1y, or all data (no filter)
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get comprehensive dashboard overview with key metrics and analytics",
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
                description="Comprehensive dashboard overview metrics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "period": openapi.Schema(type=openapi.TYPE_STRING),
                        "revenue": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "users": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "orders_rides_requests": openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                        "pending_tasks": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "conversion_rates": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "ratings": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "commission_fees": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "performance_metrics": openapi.Schema(type=openapi.TYPE_OBJECT),
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
        # REVENUE METRICS - Total and breakdown by service
        # ====================================================================

        # E-commerce revenue
        ecommerce_orders = apply_date_filter(
            Order.objects.filter(status__in=["paid", "shipped", "completed"])
        )
        ecommerce_revenue = (
            ecommerce_orders.aggregate(total=Sum("total_amount"))["total"] or 0
        )
        ecommerce_count = ecommerce_orders.count()

        # Rides revenue
        rides_revenue = 0
        rides_count = 0
        rides_completed = 0
        rides_pending = 0
        rides_cancelled = 0
        try:
            from rides.models import Ride

            rides_qs = apply_date_filter(Ride.objects, "requested_at")
            rides_completed_qs = rides_qs.filter(status="completed")
            rides_revenue = (
                rides_completed_qs.aggregate(total=Sum("fare"))["total"] or 0
            )
            rides_count = rides_qs.count()
            rides_completed = rides_completed_qs.count()
            rides_pending = rides_qs.filter(
                status__in=["initiated", "requested", "accepted"]
            ).count()
            rides_cancelled = rides_qs.filter(status="cancelled").count()
        except ImportError:
            pass

        # Courier/Delivery revenue
        courier_revenue = 0
        courier_count = 0
        courier_completed = 0
        courier_pending = 0
        courier_cancelled = 0
        try:
            from couriers.models import DeliveryRequest

            courier_qs = apply_date_filter(
                DeliveryRequest.objects, "requested_at")
            courier_completed_qs = courier_qs.filter(status="delivered")
            courier_revenue = (
                courier_completed_qs.aggregate(
                    total=Sum("total_fare"))["total"] or 0
            )
            courier_count = courier_qs.count()
            courier_completed = courier_completed_qs.count()
            courier_pending = courier_qs.filter(
                status__in=["pending", "assigned", "picked_up", "in_transit"]
            ).count()
            courier_cancelled = courier_qs.filter(status="cancelled").count()
        except ImportError:
            pass

        # Mechanic bookings revenue
        mechanic_revenue = 0
        mechanic_count = 0
        mechanic_completed = 0
        mechanic_pending = 0
        mechanic_cancelled = 0
        try:
            from mechanics.models import RepairRequest

            mechanic_qs = apply_date_filter(
                RepairRequest.objects, "requested_at")
            mechanic_completed_qs = mechanic_qs.filter(status="completed")
            mechanic_revenue = (
                mechanic_completed_qs.aggregate(
                    total=Sum("actual_cost"))["total"] or 0
            )
            mechanic_count = mechanic_qs.count()
            mechanic_completed = mechanic_completed_qs.count()
            mechanic_pending = mechanic_qs.filter(status="pending").count()
            mechanic_cancelled = mechanic_qs.filter(status="cancelled").count()
        except ImportError:
            pass

        # Car rental revenue
        rental_revenue = 0
        rental_count = 0
        rental_completed = 0
        rental_active = 0
        rental_pending = 0
        rental_cancelled = 0
        try:
            from rentals.models import RentalBooking

            rental_qs = apply_date_filter(RentalBooking.objects, "booked_at")
            rental_completed_qs = rental_qs.filter(status="completed")
            rental_revenue = (
                rental_qs.filter(status__in=["completed", "active"]).aggregate(
                    total=Sum("total_amount")
                )["total"]
                or 0
            )
            rental_count = rental_qs.count()
            rental_completed = rental_completed_qs.count()
            rental_active = rental_qs.filter(status="active").count()
            rental_pending = rental_qs.filter(status="pending").count()
            rental_cancelled = rental_qs.filter(status="cancelled").count()
        except ImportError:
            pass

        # Total revenue
        total_revenue = (
            float(ecommerce_revenue)
            + float(rides_revenue)
            + float(courier_revenue)
            + float(mechanic_revenue)
            + float(rental_revenue)
        )

        # ====================================================================
        # USER METRICS - Active users by role
        # ====================================================================

        # Total users
        total_users_qs = apply_date_filter(User.objects, "date_joined")
        total_users = User.objects.count()
        new_users = total_users_qs.count() if start_date else 0

        # Active users (logged in recently - last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        active_users = User.objects.filter(
            last_login__gte=thirty_days_ago).count()

        # Users by role
        customers_count = (
            User.objects.filter(roles__name="primary_user").distinct().count()
        )

        # Vendors/Merchants
        merchants_total = MerchantProfile.objects.count()
        merchants_active = MerchantProfile.objects.filter(
            user__is_active=True, is_approved=True
        ).count()
        merchants_unverified = MerchantProfile.objects.filter(
            Q(is_approved=False) | Q(user__is_active=False)
        ).count()

        # Drivers
        drivers_total = DriverProfile.objects.count()
        drivers_approved = DriverProfile.objects.filter(
            is_approved=True).count()
        drivers_online = DriverProfile.objects.filter(
            is_approved=True, is_online=True
        ).count()
        drivers_offline = DriverProfile.objects.filter(
            is_approved=True, is_online=False
        ).count()
        drivers_unverified = DriverProfile.objects.filter(
            is_approved=False).count()

        # Mechanics
        mechanics_total = MechanicProfile.objects.count()
        mechanics_approved = MechanicProfile.objects.filter(
            is_approved=True).count()
        mechanics_unverified = MechanicProfile.objects.filter(
            is_approved=False).count()

        # ====================================================================
        # ORDERS/RIDES/REQUESTS BREAKDOWN
        # ====================================================================

        total_transactions = (
            ecommerce_count
            + rides_count
            + courier_count
            + mechanic_count
            + rental_count
        )
        total_completed = (
            ecommerce_orders.filter(status="completed").count()
            + rides_completed
            + courier_completed
            + mechanic_completed
            + rental_completed
        )
        total_pending = (
            ecommerce_orders.filter(status="pending").count()
            + rides_pending
            + courier_pending
            + mechanic_pending
            + rental_pending
        )
        total_cancelled = (
            ecommerce_orders.filter(status="cancelled").count()
            + rides_cancelled
            + courier_cancelled
            + mechanic_cancelled
            + rental_cancelled
        )

        # Today's counts
        today = timezone.now().date()
        today_orders = Order.objects.filter(created_at__date=today).count()
        today_rides = 0
        today_couriers = 0
        today_mechanics = 0
        today_rentals = 0

        try:
            from rides.models import Ride

            today_rides = Ride.objects.filter(requested_at__date=today).count()
        except ImportError:
            pass

        try:
            from couriers.models import DeliveryRequest

            today_couriers = DeliveryRequest.objects.filter(
                requested_at__date=today
            ).count()
        except ImportError:
            pass

        try:
            from mechanics.models import RepairRequest

            today_mechanics = RepairRequest.objects.filter(
                requested_at__date=today
            ).count()
        except ImportError:
            pass

        try:
            from rentals.models import RentalBooking

            today_rentals = RentalBooking.objects.filter(
                booked_at__date=today).count()
        except ImportError:
            pass

        # ====================================================================
        # PENDING TASKS
        # ====================================================================

        pending_tasks = {
            "mechanic_requests_awaiting_assignment": mechanic_pending,
            "couriers_in_queue": courier_pending,
            "rides_waiting_for_drivers": rides_pending,
            "rental_bookings_pending_approval": rental_pending,
            "total_pending_tasks": (
                mechanic_pending + courier_pending + rides_pending + rental_pending
            ),
        }

        # ====================================================================
        # CONVERSION RATES
        # ====================================================================

        # Ride request to completion rate
        ride_conversion_rate = 0
        if rides_count > 0:
            ride_conversion_rate = round(
                (rides_completed / rides_count) * 100, 2)

        # Cart to purchase conversion (using orders as proxy)
        cart_conversion_rate = 0
        try:
            from products.models import Cart

            total_carts = Cart.objects.count()
            if total_carts > 0:
                cart_conversion_rate = round(
                    (ecommerce_count / total_carts) * 100, 2)
        except ImportError:
            pass

        # Courier completion rate
        courier_conversion_rate = 0
        if courier_count > 0:
            courier_conversion_rate = round(
                (courier_completed / courier_count) * 100, 2
            )

        # Mechanic completion rate
        mechanic_conversion_rate = 0
        if mechanic_count > 0:
            mechanic_conversion_rate = round(
                (mechanic_completed / mechanic_count) * 100, 2
            )

        # Rental completion rate
        rental_conversion_rate = 0
        if rental_count > 0:
            rental_conversion_rate = round(
                (rental_completed / rental_count) * 100, 2)

        # ====================================================================
        # RATINGS - Platform-wide and per service
        # ====================================================================

        # Product ratings
        product_avg_rating = 0
        product_total_reviews = 0
        try:
            from products.models import ProductReview

            product_reviews = ProductReview.objects.all()
            if start_date:
                product_reviews = product_reviews.filter(
                    created_at__gte=start_date)
            product_total_reviews = product_reviews.count()
            product_avg_rating = (
                product_reviews.aggregate(avg=Avg("rating"))["avg"] or 0
            )
            if product_avg_rating:
                product_avg_rating = round(float(product_avg_rating), 2)
        except ImportError:
            pass

        # Driver ratings
        driver_avg_rating = 0
        driver_total_reviews = 0
        try:
            from users.models import DriverReview

            driver_reviews = DriverReview.objects.all()
            if start_date:
                driver_reviews = driver_reviews.filter(
                    created_at__gte=start_date)
            driver_total_reviews = driver_reviews.count()
            driver_avg_rating = driver_reviews.aggregate(avg=Avg("rating"))[
                "avg"] or 0
            if driver_avg_rating:
                driver_avg_rating = round(float(driver_avg_rating), 2)
        except ImportError:
            pass

        # Mechanic ratings
        mechanic_avg_rating = 0
        mechanic_total_reviews = 0
        try:
            from users.models import MechanicReview

            mechanic_reviews = MechanicReview.objects.all()
            if start_date:
                mechanic_reviews = mechanic_reviews.filter(
                    created_at__gte=start_date)
            mechanic_total_reviews = mechanic_reviews.count()
            mechanic_avg_rating = (
                mechanic_reviews.aggregate(avg=Avg("rating"))["avg"] or 0
            )
            if mechanic_avg_rating:
                mechanic_avg_rating = round(float(mechanic_avg_rating), 2)
        except ImportError:
            pass

        # Courier ratings
        courier_avg_rating = 0
        courier_total_reviews = 0
        try:
            from couriers.models import CourierRating

            courier_reviews = CourierRating.objects.all()
            if start_date:
                courier_reviews = courier_reviews.filter(
                    created_at__gte=start_date)
            courier_total_reviews = courier_reviews.count()
            courier_avg_rating = (
                courier_reviews.aggregate(
                    avg=Avg("overall_rating"))["avg"] or 0
            )
            if courier_avg_rating:
                courier_avg_rating = round(float(courier_avg_rating), 2)
        except ImportError:
            pass

        # Rental ratings
        rental_avg_rating = 0
        rental_total_reviews = 0
        try:
            from rentals.models import RentalReview

            rental_reviews = RentalReview.objects.all()
            if start_date:
                rental_reviews = rental_reviews.filter(
                    created_at__gte=start_date)
            rental_total_reviews = rental_reviews.count()
            rental_avg_rating = rental_reviews.aggregate(avg=Avg("rating"))[
                "avg"] or 0
            if rental_avg_rating:
                rental_avg_rating = round(float(rental_avg_rating), 2)
        except ImportError:
            pass

        # Platform-wide average rating
        total_reviews = (
            product_total_reviews
            + driver_total_reviews
            + mechanic_total_reviews
            + courier_total_reviews
            + rental_total_reviews
        )
        platform_avg_rating = 0
        if total_reviews > 0:
            weighted_sum = (
                (product_avg_rating * product_total_reviews)
                + (driver_avg_rating * driver_total_reviews)
                + (mechanic_avg_rating * mechanic_total_reviews)
                + (courier_avg_rating * courier_total_reviews)
                + (rental_avg_rating * rental_total_reviews)
            )
            platform_avg_rating = round(weighted_sum / total_reviews, 2)

        # ====================================================================
        # COMMISSION/FEES EARNED
        # ====================================================================

        # Calculate commission (assuming 10% commission rate as example)
        COMMISSION_RATE = Decimal("0.10")  # 10%

        ecommerce_commission = float(
            ecommerce_revenue) * float(COMMISSION_RATE)
        rides_commission = float(rides_revenue) * float(COMMISSION_RATE)
        courier_commission = float(courier_revenue) * float(COMMISSION_RATE)
        mechanic_commission = float(mechanic_revenue) * float(COMMISSION_RATE)
        rental_commission = float(rental_revenue) * float(COMMISSION_RATE)

        total_commission = (
            ecommerce_commission
            + rides_commission
            + courier_commission
            + mechanic_commission
            + rental_commission
        )

        # ====================================================================
        # PERFORMANCE METRICS
        # ====================================================================

        # Response time for requests/deliveries (average time to accept)
        avg_ride_response_time = 0
        try:
            from rides.models import Ride

            rides_with_response = Ride.objects.filter(
                accepted_at__isnull=False)
            if start_date:
                rides_with_response = rides_with_response.filter(
                    requested_at__gte=start_date
                )
            if rides_with_response.exists():
                response_times = []
                for ride in rides_with_response:
                    if ride.accepted_at and ride.requested_at:
                        delta = (
                            ride.accepted_at - ride.requested_at
                        ).total_seconds() / 60
                        response_times.append(delta)
                if response_times:
                    avg_ride_response_time = round(
                        sum(response_times) / len(response_times), 2
                    )
        except ImportError:
            pass

        avg_courier_response_time = 0
        try:
            from couriers.models import DeliveryRequest

            couriers_with_response = DeliveryRequest.objects.filter(
                assigned_at__isnull=False
            )
            if start_date:
                couriers_with_response = couriers_with_response.filter(
                    requested_at__gte=start_date
                )
            if couriers_with_response.exists():
                response_times = []
                for courier in couriers_with_response:
                    if courier.assigned_at and courier.requested_at:
                        delta = (
                            courier.assigned_at - courier.requested_at
                        ).total_seconds() / 60
                        response_times.append(delta)
                if response_times:
                    avg_courier_response_time = round(
                        sum(response_times) / len(response_times), 2
                    )
        except ImportError:
            pass

        avg_mechanic_response_time = 0
        try:
            from mechanics.models import RepairRequest

            mechanics_with_response = RepairRequest.objects.filter(
                accepted_at__isnull=False
            )
            if start_date:
                mechanics_with_response = mechanics_with_response.filter(
                    requested_at__gte=start_date
                )
            if mechanics_with_response.exists():
                response_times = []
                for mechanic in mechanics_with_response:
                    if mechanic.accepted_at and mechanic.requested_at:
                        delta = (
                            mechanic.accepted_at - mechanic.requested_at
                        ).total_seconds() / 60
                        response_times.append(delta)
                if response_times:
                    avg_mechanic_response_time = round(
                        sum(response_times) / len(response_times), 2
                    )
        except ImportError:
            pass

        # GMV (Gross Merchandise Value) for e-commerce
        gmv = float(ecommerce_revenue)

        # On-time delivery rate (%)
        on_time_delivery_rate = 0
        try:
            from couriers.models import DeliveryRequest

            completed_deliveries = DeliveryRequest.objects.filter(
                status="delivered")
            if start_date:
                completed_deliveries = completed_deliveries.filter(
                    requested_at__gte=start_date
                )
            total_delivered = completed_deliveries.count()
            if total_delivered > 0:
                # Consider on-time if delivered within estimated duration + 30 min buffer
                on_time_count = 0
                for delivery in completed_deliveries:
                    if (
                        delivery.delivered_at
                        and delivery.requested_at
                        and delivery.estimated_duration
                    ):
                        actual_duration = (
                            delivery.delivered_at - delivery.requested_at
                        ).total_seconds() / 60
                        expected_duration = (
                            delivery.estimated_duration + 30
                        )  # 30 min buffer
                        if actual_duration <= expected_duration:
                            on_time_count += 1
                on_time_delivery_rate = round(
                    (on_time_count / total_delivered) * 100, 2
                )
        except ImportError:
            pass

        # Cancellation rate (%)
        cancellation_rate = 0
        if total_transactions > 0:
            cancellation_rate = round(
                (total_cancelled / total_transactions) * 100, 2)

        # ====================================================================
        # RESPONSE DATA
        # ====================================================================

        return Response(
            api_response(
                message="Dashboard overview retrieved successfully.",
                status=True,
                data={
                    "period": period if period else "all_time",
                    "period_description": (
                        f"Last {period}" if period else "All time data"
                    ),
                    # Revenue breakdown
                    "revenue": {
                        "total_revenue": round(total_revenue, 2),
                        "breakdown": {
                            "ecommerce_sales": round(float(ecommerce_revenue), 2),
                            "ride_fares": round(float(rides_revenue), 2),
                            "courier_fees": round(float(courier_revenue), 2),
                            "mechanic_bookings": round(float(mechanic_revenue), 2),
                            "car_rental_income": round(float(rental_revenue), 2),
                        },
                    },
                    # User metrics
                    "users": {
                        "total_users": total_users,
                        "new_users": new_users,
                        "active_users": active_users,
                        "customers": customers_count,
                        "vendors_merchants": {
                            "total": merchants_total,
                            "active": merchants_active,
                            "unverified": merchants_unverified,
                        },
                        "drivers": {
                            "total": drivers_total,
                            "approved": drivers_approved,
                            "online": drivers_online,
                            "offline": drivers_offline,
                            "unverified": drivers_unverified,
                        },
                        "mechanics": {
                            "total": mechanics_total,
                            "approved": mechanics_approved,
                            "unverified": mechanics_unverified,
                        },
                    },
                    # Orders/Rides/Requests breakdown
                    "orders_rides_requests": {
                        "total_transactions": total_transactions,
                        "today_count": today_orders
                        + today_rides
                        + today_couriers
                        + today_mechanics
                        + today_rentals,
                        "breakdown": {
                            "completed": total_completed,
                            "pending": total_pending,
                            "cancelled": total_cancelled,
                        },
                        "by_service": {
                            "ecommerce_orders": {
                                "total": ecommerce_count,
                                "completed": ecommerce_orders.filter(
                                    status="completed"
                                ).count(),
                                "pending": ecommerce_orders.filter(
                                    status="pending"
                                ).count(),
                                "cancelled": ecommerce_orders.filter(
                                    status="cancelled"
                                ).count(),
                                "today": today_orders,
                            },
                            "rides": {
                                "total": rides_count,
                                "completed": rides_completed,
                                "pending": rides_pending,
                                "cancelled": rides_cancelled,
                                "today": today_rides,
                            },
                            "courier_deliveries": {
                                "total": courier_count,
                                "completed": courier_completed,
                                "pending": courier_pending,
                                "cancelled": courier_cancelled,
                                "today": today_couriers,
                            },
                            "mechanic_requests": {
                                "total": mechanic_count,
                                "completed": mechanic_completed,
                                "pending": mechanic_pending,
                                "cancelled": mechanic_cancelled,
                                "today": today_mechanics,
                            },
                            "car_rentals": {
                                "total": rental_count,
                                "completed": rental_completed,
                                "active": rental_active,
                                "pending": rental_pending,
                                "cancelled": rental_cancelled,
                                "today": today_rentals,
                            },
                        },
                    },
                    # Pending tasks
                    "pending_tasks": pending_tasks,
                    # Conversion rates
                    "conversion_rates": {
                        "ride_requests_to_completions": f"{ride_conversion_rate}%",
                        "cart_adds_to_purchases": f"{cart_conversion_rate}%",
                        "courier_completion_rate": f"{courier_conversion_rate}%",
                        "mechanic_completion_rate": f"{mechanic_conversion_rate}%",
                        "rental_completion_rate": f"{rental_conversion_rate}%",
                    },
                    # Ratings
                    "ratings": {
                        "platform_wide_average": platform_avg_rating,
                        "total_reviews": total_reviews,
                        "by_service": {
                            "products": {
                                "average_rating": product_avg_rating,
                                "total_reviews": product_total_reviews,
                            },
                            "drivers": {
                                "average_rating": driver_avg_rating,
                                "total_reviews": driver_total_reviews,
                            },
                            "mechanics": {
                                "average_rating": mechanic_avg_rating,
                                "total_reviews": mechanic_total_reviews,
                            },
                            "couriers": {
                                "average_rating": courier_avg_rating,
                                "total_reviews": courier_total_reviews,
                            },
                            "rentals": {
                                "average_rating": rental_avg_rating,
                                "total_reviews": rental_total_reviews,
                            },
                        },
                    },
                    # Commission/Fees
                    "commission_fees": {
                        "total_commission_earned": round(total_commission, 2),
                        "commission_rate": f"{float(COMMISSION_RATE) * 100}%",
                        "breakdown": {
                            "ecommerce": round(ecommerce_commission, 2),
                            "rides": round(rides_commission, 2),
                            "couriers": round(courier_commission, 2),
                            "mechanics": round(mechanic_commission, 2),
                            "rentals": round(rental_commission, 2),
                        },
                    },
                    # Performance metrics
                    "performance_metrics": {
                        "response_time_minutes": {
                            "rides": avg_ride_response_time,
                            "couriers": avg_courier_response_time,
                            "mechanics": avg_mechanic_response_time,
                        },
                        "gmv_gross_merchandise_value": round(gmv, 2),
                        "on_time_delivery_rate": f"{on_time_delivery_rate}%",
                        "cancellation_rate": f"{cancellation_rate}%",
                    },
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
    """Comprehensive revenue analytics across all services"""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get comprehensive revenue analytics",
        manual_parameters=[
            openapi.Parameter(
                "period",
                openapi.IN_QUERY,
                description="Time period (7d, 30d, 90d, 1y)",
                type=openapi.TYPE_STRING,
                default="30d",
            ),
            openapi.Parameter(
                "group_by",
                openapi.IN_QUERY,
                description="Group by (day, week, month)",
                type=openapi.TYPE_STRING,
                default="day",
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

        period = request.query_params.get("period", "30d")
        group_by = request.query_params.get("group_by", "day")
        days = self._parse_period(period)
        start_date = timezone.now() - timedelta(days=days)

        # Product sales revenue
        product_revenue = (
            Order.objects.filter(
                created_at__gte=start_date, status__in=[
                    "paid", "shipped", "completed"]
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        # Revenue breakdown by source
        revenue_sources = {
            "products": float(product_revenue),
        }

        # Add rides revenue if available
        try:
            from rides.models import Ride

            rides_revenue = (
                Ride.objects.filter(
                    requested_at__gte=start_date, status="completed"
                ).aggregate(total=Sum("fare"))["total"]
                or 0
            )
            revenue_sources["rides"] = float(rides_revenue)
        except ImportError:
            pass

        # Add courier revenue if available
        try:
            from couriers.models import DeliveryRequest

            courier_revenue = (
                DeliveryRequest.objects.filter(
                    requested_at__gte=start_date, status="delivered"
                ).aggregate(total=Sum("total_fare"))["total"]
                or 0
            )
            revenue_sources["couriers"] = float(courier_revenue)
        except ImportError:
            pass

        # Add rental revenue if available
        try:
            from rentals.models import RentalBooking

            rental_revenue = (
                RentalBooking.objects.filter(
                    booked_at__gte=start_date, status__in=[
                        "completed", "active"]
                ).aggregate(total=Sum("total_amount"))["total"]
                or 0
            )
            revenue_sources["rentals"] = float(rental_revenue)
        except ImportError:
            pass

        # Total revenue
        total_revenue = sum(revenue_sources.values())

        # Revenue over time (grouped)
        revenue_timeline = self._get_revenue_timeline(start_date, group_by)

        return Response(
            api_response(
                message="Revenue analytics retrieved successfully.",
                status=True,
                data={
                    "period": period,
                    "total_revenue": round(total_revenue, 2),
                    "revenue_by_source": revenue_sources,
                    "revenue_timeline": revenue_timeline,
                },
            )
        )

    def _get_revenue_timeline(self, start_date, group_by):
        """Get revenue timeline grouped by day/week/month"""
        orders = Order.objects.filter(
            created_at__gte=start_date, status__in=[
                "paid", "shipped", "completed"]
        )

        if group_by == "month":
            timeline = (
                orders.annotate(period=TruncMonth("created_at"))
                .values("period")
                .annotate(revenue=Sum("total_amount"))
                .order_by("period")
            )
        else:  # day
            timeline = (
                orders.annotate(period=TruncDate("created_at"))
                .values("period")
                .annotate(revenue=Sum("total_amount"))
                .order_by("period")
            )

        return list(timeline)

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
    Real-time geographic heat map showing current positions of:
    - Active rides
    - Mechanic locations
    - Courier routes
    - Delivery progress
    """

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get real-time geographic data for heat map visualization",
        responses={
            200: openapi.Response(
                description="Geographic heat map data",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "active_rides": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "mechanic_locations": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "courier_routes": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                        "delivery_progress": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
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

        # ====================================================================
        # ACTIVE RIDES - Current ride positions
        # ====================================================================
        active_rides = []
        try:
            from rides.models import Ride

            rides = Ride.objects.filter(
                status__in=["accepted", "in_progress"]
            ).select_related("driver", "customer")

            for ride in rides:
                ride_data = {
                    "ride_id": str(ride.id),
                    "status": ride.status,
                    "driver": {
                        "id": str(ride.driver.id) if ride.driver else None,
                        "name": (
                            f"{ride.driver.first_name} {ride.driver.last_name}"
                            if ride.driver
                            else None
                        ),
                        "phone": ride.driver.phone_number if ride.driver else None,
                    },
                    "customer": {
                        "id": str(ride.customer.id) if ride.customer else None,
                        "name": (
                            f"{ride.customer.first_name} {ride.customer.last_name}"
                            if ride.customer
                            else None
                        ),
                    },
                    "pickup_location": {
                        "latitude": (
                            float(ride.pickup_latitude)
                            if ride.pickup_latitude
                            else None
                        ),
                        "longitude": (
                            float(ride.pickup_longitude)
                            if ride.pickup_longitude
                            else None
                        ),
                        "address": ride.pickup_address,
                    },
                    "dropoff_location": {
                        "latitude": (
                            float(ride.dropoff_latitude)
                            if ride.dropoff_latitude
                            else None
                        ),
                        "longitude": (
                            float(ride.dropoff_longitude)
                            if ride.dropoff_longitude
                            else None
                        ),
                        "address": ride.dropoff_address,
                    },
                    "current_location": {
                        "latitude": (
                            float(ride.current_latitude)
                            if hasattr(ride, "current_latitude")
                            and ride.current_latitude
                            else (
                                float(ride.pickup_latitude)
                                if ride.pickup_latitude
                                else None
                            )
                        ),
                        "longitude": (
                            float(ride.current_longitude)
                            if hasattr(ride, "current_longitude")
                            and ride.current_longitude
                            else (
                                float(ride.pickup_longitude)
                                if ride.pickup_longitude
                                else None
                            )
                        ),
                    },
                    "fare": float(ride.fare) if ride.fare else 0,
                    "requested_at": (
                        ride.requested_at.isoformat() if ride.requested_at else None
                    ),
                    "accepted_at": (
                        ride.accepted_at.isoformat() if ride.accepted_at else None
                    ),
                }
                active_rides.append(ride_data)
        except ImportError:
            pass

        # ====================================================================
        # MECHANIC LOCATIONS - Active mechanics
        # ====================================================================
        mechanic_locations = []
        try:
            from mechanics.models import RepairRequest

            # Get active mechanics with ongoing requests
            active_requests = RepairRequest.objects.filter(
                status__in=["accepted", "in_transit", "in_progress"]
            ).select_related("mechanic", "customer")

            for repair_request in active_requests:
                # Get mechanic profile if available
                mechanic_profile = None
                if repair_request.mechanic:
                    try:
                        mechanic_profile = repair_request.mechanic.mechanic_profile
                    except:
                        pass

                mechanic_data = {
                    "request_id": str(repair_request.id),
                    "status": repair_request.status,
                    "mechanic": {
                        "id": (
                            str(repair_request.mechanic.id)
                            if repair_request.mechanic
                            else None
                        ),
                        "name": (
                            f"{repair_request.mechanic.first_name} {repair_request.mechanic.last_name}"
                            if repair_request.mechanic
                            else None
                        ),
                        "phone": (
                            repair_request.mechanic.phone_number
                            if repair_request.mechanic
                            else None
                        ),
                        "specialization": (
                            mechanic_profile.specialization
                            if mechanic_profile
                            and hasattr(mechanic_profile, "specialization")
                            else None
                        ),
                    },
                    "customer": {
                        "id": (
                            str(repair_request.customer.id)
                            if repair_request.customer
                            else None
                        ),
                        "name": (
                            f"{repair_request.customer.first_name} {repair_request.customer.last_name}"
                            if repair_request.customer
                            else None
                        ),
                    },
                    "location": {
                        "latitude": (
                            float(repair_request.service_latitude)
                            if repair_request.service_latitude
                            else None
                        ),
                        "longitude": (
                            float(repair_request.service_longitude)
                            if repair_request.service_longitude
                            else None
                        ),
                        "address": repair_request.service_address,
                    },
                    "service_type": repair_request.service_type,
                    "estimated_cost": (
                        float(repair_request.estimated_cost)
                        if repair_request.estimated_cost
                        else 0
                    ),
                    "requested_at": (
                        repair_request.requested_at.isoformat()
                        if repair_request.requested_at
                        else None
                    ),
                    "accepted_at": (
                        repair_request.accepted_at.isoformat()
                        if repair_request.accepted_at
                        else None
                    ),
                }
                mechanic_locations.append(mechanic_data)
        except ImportError:
            pass

        # ====================================================================
        # COURIER ROUTES - Active deliveries
        # ====================================================================
        courier_routes = []
        try:
            from couriers.models import DeliveryRequest

            active_deliveries = DeliveryRequest.objects.filter(
                status__in=["assigned", "picked_up", "in_transit"]
            ).select_related("driver", "customer")

            for delivery in active_deliveries:
                courier_data = {
                    "delivery_id": str(delivery.id),
                    "status": delivery.status,
                    "driver": {
                        "id": str(delivery.driver.id) if delivery.driver else None,
                        "name": (
                            f"{delivery.driver.first_name} {delivery.driver.last_name}"
                            if delivery.driver
                            else None
                        ),
                        "phone": (
                            delivery.driver.phone_number if delivery.driver else None
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
                    "pickup_location": {
                        "latitude": (
                            float(delivery.pickup_latitude)
                            if delivery.pickup_latitude
                            else None
                        ),
                        "longitude": (
                            float(delivery.pickup_longitude)
                            if delivery.pickup_longitude
                            else None
                        ),
                        "address": delivery.pickup_address,
                    },
                    "dropoff_location": {
                        "latitude": (
                            float(delivery.dropoff_latitude)
                            if delivery.dropoff_latitude
                            else None
                        ),
                        "longitude": (
                            float(delivery.dropoff_longitude)
                            if delivery.dropoff_longitude
                            else None
                        ),
                        "address": delivery.dropoff_address,
                    },
                    "current_location": {
                        "latitude": (
                            float(delivery.current_latitude)
                            if hasattr(delivery, "current_latitude")
                            and delivery.current_latitude
                            else None
                        ),
                        "longitude": (
                            float(delivery.current_longitude)
                            if hasattr(delivery, "current_longitude")
                            and delivery.current_longitude
                            else None
                        ),
                    },
                    "package_type": (
                        delivery.package_type
                        if hasattr(delivery, "package_type")
                        else None
                    ),
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
                    "picked_up_at": (
                        delivery.picked_up_at.isoformat()
                        if hasattr(delivery, "picked_up_at") and delivery.picked_up_at
                        else None
                    ),
                }
                courier_routes.append(courier_data)
        except ImportError:
            pass

        # ====================================================================
        # DELIVERY PROGRESS - Summary statistics
        # ====================================================================
        delivery_progress = {
            "total_active_rides": len(active_rides),
            "total_active_mechanics": len(mechanic_locations),
            "total_active_couriers": len(courier_routes),
            "total_active_services": len(active_rides)
            + len(mechanic_locations)
            + len(courier_routes),
        }

        return Response(
            api_response(
                message="Geographic heat map data retrieved successfully.",
                status=True,
                data={
                    "active_rides": active_rides,
                    "mechanic_locations": mechanic_locations,
                    "courier_routes": courier_routes,
                    "delivery_progress": delivery_progress,
                    "timestamp": timezone.now().isoformat(),
                },
            )
        )


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
                    "description": f"Delivery {delivery.status.replace('_', ' ')} by {delivery.courier.first_name if delivery.courier else 'Unassigned'}",
                    "courier": {
                        "id": str(delivery.courier.id) if delivery.courier else None,
                        "name": (
                            f"{delivery.courier.first_name} {delivery.courier.last_name}"
                            if delivery.courier
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
