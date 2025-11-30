from rest_framework import status as http_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import models
from django.db.models import (Sum, Count, F, DecimalField, 
                              ExpressionWrapper, Avg, Q)
from django.db.models.functions import TruncMonth, TruncDate
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

from ogamechanic.modules.utils import (
    api_response, incoming_request_checks, get_incoming_request_checks
)
from ogamechanic.modules.paginations import CustomLimitOffsetPagination
from users.models import (User, MechanicProfile, MerchantProfile, 
                          DriverProfile, Role)
from users.serializers import (MechanicProfileSerializer, 
                               DriverProfileSerializer)
from products.models import Order, OrderItem
from products.serializers import CategorySerializer
from .models import (
    AnalyticsDashboard, AnalyticsWidget, AnalyticsCache,
    UserAnalytics, AnalyticsReport
)
from .serializers import (
    AnalyticsDashboardSerializer, AnalyticsWidgetSerializer,
    AnalyticsWidgetListSerializer, AnalyticsCacheSerializer,
    UserAnalyticsSerializer, AnalyticsReportSerializer,
    AnalyticsReportCreateSerializer, DashboardDataSerializer,
    AnalyticsSummarySerializer
)


class AdminCategoryCreateView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Create a new category (admin only)",
        request_body=CategorySerializer,
        responses={
            201: CategorySerializer(),
            400: "Bad Request",
            403: "Forbidden"
        }
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        serializer = CategorySerializer(data=request.data)
        if serializer.is_valid():
            category = serializer.save()
            return Response(
                api_response(
                    message="Category created successfully.",
                    status=True,
                    data=CategorySerializer(category).data
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


class ApproveMechanicProfileView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Approve a mechanic profile (admin only)",
        responses={
            200: MechanicProfileSerializer(),
            404: "Not found",
            403: "Forbidden"
        }
    )
    def post(self, request, profile_id):
        try:
            profile = MechanicProfile.objects.get(pk=profile_id)
        except MechanicProfile.DoesNotExist:
            return Response(
                api_response(
                    message="Mechanic profile not found.",
                    status=False
                ),
                status=404
            )
        if profile.is_approved:
            return Response(
                api_response(
                    message="Mechanic profile already approved.",
                    status=False
                ),
                status=400
            )
        profile.is_approved = True
        profile.save(update_fields=["is_approved"])
        return Response(
            api_response(
                message="Mechanic profile approved.",
                status=True,
                data=MechanicProfileSerializer(profile).data
            )
        )


class ApproveDriverProfileView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Approve a driver profile (admin only)",
        responses={
            200: DriverProfileSerializer(),
            404: "Not found",
            403: "Forbidden"
        }
    )
    def post(self, request, profile_id):
        try:
            profile = DriverProfile.objects.get(pk=profile_id)
        except DriverProfile.DoesNotExist:
            return Response(
                api_response(
                    message="Driver profile not found.",
                    status=False
                ),
                status=404
            )
        if profile.is_approved:
            return Response(
                api_response(
                    message="Driver profile already approved.",
                    status=False
                ),
                status=400
            )
        profile.is_approved = True
        profile.approved_at = timezone.now()
        profile.save(update_fields=["is_approved", "approved_at"])
        return Response(
            api_response(
                message="Driver profile approved.",
                status=True,
                data=DriverProfileSerializer(profile).data
            )
        )


class SalesAnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Sales analytics: total sales, revenue, sales by month, best sellers", # noqa
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'total_sales': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'total_revenue': openapi.Schema(type=openapi.TYPE_NUMBER, format='float'), # noqa
                    'sales_by_month': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    'best_sellers': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                },
            )
        }
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        paid_statuses = ['paid', 'shipped', 'completed']
        total_sales = Order.objects.filter(status__in=paid_statuses).count()
        total_revenue = (
            Order.objects.filter(status__in=paid_statuses)
            .aggregate(total=Sum('total_amount'))['total'] or 0
        )
        # Sales by month
        sales_by_month = (
            Order.objects.filter(status__in=paid_statuses)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(sales=Sum('total_amount'))
            .order_by('month')
        )
        # Best sellers
        best_sellers = (
            OrderItem.objects.filter(order__status__in=paid_statuses)
            .values('product__id', 'product__name')
            .annotate(total_quantity=Sum('quantity'), total_sales=Sum('price'))
            .order_by('-total_quantity')[:10]
        )
        best_sellers_data = [
            {
                'product_id': b['product__id'],
                'product_name': b['product__name'],
                'total_quantity': b['total_quantity'],
                'total_sales': b['total_sales'],
            }
            for b in best_sellers
        ]
        return Response(
            api_response(
                message="Sales analytics.",
                status=True,
                data={
                    'total_sales': total_sales,
                    'total_revenue': total_revenue,
                    'sales_by_month': list(sales_by_month),
                    'best_sellers': best_sellers_data,
                },
            )
        )


class PendingVerificationsView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="List all pending verifications (mechanics, drivers, merchants)", # noqa
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'pending_mechanics': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    'pending_drivers': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    'pending_merchants': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                },
            )
        }
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        pending_mechanics = MechanicProfile.objects.filter(is_approved=False)
        pending_drivers = DriverProfile.objects.filter(is_approved=False)
        pending_merchants = MerchantProfile.objects.filter(user__is_active=False) # noqa
        mechanics_data = [
            {
                'id': m.id,
                'user': m.user.email,
                'created_at': m.created_at,
            }
            for m in pending_mechanics
        ]
        drivers_data = [
            {
                'id': d.id,
                'user': d.user.email,
                'created_at': d.created_at,
            }
            for d in pending_drivers
        ]
        merchants_data = [
            {
                'id': m.id,
                'user': m.user.email,
                'created_at': m.created_at,
            }
            for m in pending_merchants
        ]
        return Response(
            api_response(
                message="Pending verifications retrieved successfully.",
                status=True,
                data={
                    'pending_mechanics': mechanics_data,
                    'pending_drivers': drivers_data,
                    'pending_merchants': merchants_data,
                },
            )
        )


class ApproveRejectVerificationView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Approve or reject a pending verification (mechanic, driver, merchant)", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['type', 'id', 'action'],
            properties={
                'type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['mechanic', 'driver', 'merchant'],
                ),
                'id': openapi.Schema(type=openapi.TYPE_STRING),
                'action': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['approve', 'reject'],
                ),
            },
        ),
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        vtype = data.get('type')
        vid = data.get('id')
        action = data.get('action')
        if vtype not in ['mechanic', 'driver', 'merchant'] or action not in ['approve', 'reject']: # noqa
            return Response(
                api_response(message="Invalid type or action.", 
                             status=False), status=400)
        if vtype == 'mechanic':
            try:
                profile = MechanicProfile.objects.get(id=vid)
                if action == 'approve':
                    profile.is_approved = True
                    profile.save()
                else:
                    profile.delete()
            except MechanicProfile.DoesNotExist:
                return Response(
                    api_response(
                        message="Mechanic not found.",
                        status=False
                    ),
                    status=404
                )
        elif vtype == 'driver':
            try:
                profile = DriverProfile.objects.get(id=vid)
                if action == 'approve':
                    profile.is_approved = True
                    profile.save()
                else:
                    profile.delete()
            except DriverProfile.DoesNotExist:
                return Response(
                    api_response(
                        message="Driver not found.",
                        status=False
                    ),
                    status=404
                )
        elif vtype == 'merchant':
            try:
                profile = MerchantProfile.objects.get(id=vid)
                if action == 'approve':
                    profile.user.is_active = True
                    profile.user.save()
                else:
                    profile.user.delete()
            except MerchantProfile.DoesNotExist:
                return Response(
                    api_response(
                        message="Merchant not found.",
                        status=False
                    ),
                    status=404
                )
        return Response(
            api_response(
                message=f"{vtype.capitalize()} {action}d successfully.",
                status=True,
                data={},
            )
        )


class AdminAnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Get comprehensive platform-wide analytics for admin dashboard",
        responses={
            200: openapi.Response(
                description="Admin analytics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'user_counts': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'total_sales': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'order_status_counts': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'revenue_by_month': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'pending_mechanic_verifications': openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        'pending_driver_verifications': openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        'pending_merchants': openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        'top_merchants': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_STRING)
                        ),
                        'ride_analytics': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'courier_analytics': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'rental_analytics': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'mechanic_analytics': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'platform_performance': openapi.Schema(type=openapi.TYPE_OBJECT),
                    }
                )
            )
        }
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        # User counts by role
        user_counts = {}
        for role in Role.objects.all():
            user_counts[role.name] = User.objects.filter(roles=role).count()

        # Total sales
        total_sales = (
            Order.objects.filter(
                status__in=['paid', 'shipped', 'completed']
            ).aggregate(total=Sum('total_amount'))['total'] or 0
        )

        # Order status counts
        order_status_counts = (
            Order.objects.values('status').annotate(count=Count('id'))
        )
        status_counts = {
            item['status']: item['count'] for item in order_status_counts
        }

        from django.db.models.functions import TruncMonth

        revenue_by_month = (
            Order.objects.filter(
                status__in=['paid', 'shipped', 'completed']
            )
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(revenue=Sum('total_amount'))
            .order_by('month')
        )
        revenue_by_month_dict = {
            str(item['month'].date()): float(item['revenue'])
            for item in revenue_by_month
        }

        # Pending verifications
        pending_mechanic_verifications = (
            MechanicProfile.objects.filter(is_approved=False).count()
        )
        pending_driver_verifications = (
            DriverProfile.objects.filter(is_approved=False).count()
        )
        pending_merchants = MerchantProfile.objects.filter(user__is_active=False).count()

        # Top merchants by sales
        top_merchants_qs = (
            OrderItem.objects.filter(
                order__status__in=['paid', 'shipped', 'completed']
            )
            .values('product__merchant__email')
            .annotate(
                total_sales=Sum(
                    ExpressionWrapper(
                        F('price') * F('quantity'),
                        output_field=DecimalField(
                            max_digits=12, decimal_places=2
                        )
                    )
                )
            )
            .order_by('-total_sales')[:5]
        )
        top_merchants = [
            item['product__merchant__email'] for item in top_merchants_qs
        ]

        # Additional analytics
        ride_analytics = self._get_ride_analytics()
        courier_analytics = self._get_courier_analytics()
        rental_analytics = self._get_rental_analytics()
        mechanic_analytics = self._get_mechanic_analytics()
        platform_performance = self._get_platform_performance()

        return Response(
            api_response(
                message="Admin analytics retrieved successfully.",
                status=True,
                data={
                    'user_counts': user_counts,
                    'total_sales': float(total_sales),
                    'order_status_counts': status_counts,
                    'revenue_by_month': revenue_by_month_dict,
                    'pending_mechanic_verifications': pending_mechanic_verifications,
                    'pending_driver_verifications': pending_driver_verifications,
                    'pending_merchants': pending_merchants,
                    'top_merchants': top_merchants,
                    'ride_analytics': ride_analytics,
                    'courier_analytics': courier_analytics,
                    'rental_analytics': rental_analytics,
                    'mechanic_analytics': mechanic_analytics,
                    'platform_performance': platform_performance,
                }
            )
        )

    def _get_ride_analytics(self):
        """Get ride analytics"""
        try:
            from rides.models import Ride
            
            total_rides = Ride.objects.count()
            completed_rides = Ride.objects.filter(status='completed').count()
            active_rides = Ride.objects.filter(status='active').count()
            cancelled_rides = Ride.objects.filter(status='cancelled').count()
            
            # Revenue from rides
            ride_revenue = Ride.objects.filter(
                status='completed'
            ).aggregate(total=Sum('fare'))['total'] or 0
            
            # Average ride fare
            avg_fare = Ride.objects.filter(
                status='completed'
            ).aggregate(avg=Avg('fare'))['avg'] or 0
            
            return {
                'total_rides': total_rides,
                'completed_rides': completed_rides,
                'active_rides': active_rides,
                'cancelled_rides': cancelled_rides,
                'ride_revenue': float(ride_revenue),
                'avg_fare': float(avg_fare),
                'completion_rate': (completed_rides / total_rides * 100) if total_rides > 0 else 0
            }
        except ImportError:
            return {}

    def _get_courier_analytics(self):
        """Get courier analytics"""
        try:
            from rides.models import CourierRequest
            
            total_couriers = CourierRequest.objects.count()
            completed_couriers = CourierRequest.objects.filter(status='completed').count()
            active_couriers = CourierRequest.objects.filter(status='active').count()
            cancelled_couriers = CourierRequest.objects.filter(status='cancelled').count()
            
            # Revenue from couriers
            courier_revenue = CourierRequest.objects.filter(
                status='completed'
            ).aggregate(total=Sum('fare'))['total'] or 0
            
            # Average courier fare
            avg_fare = CourierRequest.objects.filter(
                status='completed'
            ).aggregate(avg=Avg('fare'))['avg'] or 0
            
            return {
                'total_couriers': total_couriers,
                'completed_couriers': completed_couriers,
                'active_couriers': active_couriers,
                'cancelled_couriers': cancelled_couriers,
                'courier_revenue': float(courier_revenue),
                'avg_fare': float(avg_fare),
                'completion_rate': (completed_couriers / total_couriers * 100) if total_couriers > 0 else 0
            }
        except ImportError:
            return {}

    def _get_rental_analytics(self):
        """Get rental analytics"""
        try:
            from rentals.models import RentalBooking
            
            total_rentals = RentalBooking.objects.count()
            completed_rentals = RentalBooking.objects.filter(status='completed').count()
            active_rentals = RentalBooking.objects.filter(status='active').count()
            pending_rentals = RentalBooking.objects.filter(status='pending').count()
            
            # Revenue from rentals
            rental_revenue = RentalBooking.objects.filter(
                status__in=['completed', 'active']
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            
            # Average rental duration
            avg_duration = RentalBooking.objects.filter(
                status='completed'
            ).aggregate(avg=Avg('duration_days'))['avg'] or 0
            
            return {
                'total_rentals': total_rentals,
                'completed_rentals': completed_rentals,
                'active_rentals': active_rentals,
                'pending_rentals': pending_rentals,
                'rental_revenue': float(rental_revenue),
                'avg_duration': float(avg_duration),
                'completion_rate': (completed_rentals / total_rentals * 100) if total_rentals > 0 else 0
            }
        except ImportError:
            return {}

    def _get_mechanic_analytics(self):
        """Get mechanic analytics"""
        try:
            from mechanics.models import RepairRequest, TrainingSession
            
            total_repairs = RepairRequest.objects.count()
            completed_repairs = RepairRequest.objects.filter(status='completed').count()
            pending_repairs = RepairRequest.objects.filter(status='pending').count()
            
            total_sessions = TrainingSession.objects.count()
            active_sessions = TrainingSession.objects.filter(status='in_progress').count()
            completed_sessions = TrainingSession.objects.filter(status='completed').count()
            
            return {
                'total_repairs': total_repairs,
                'completed_repairs': completed_repairs,
                'pending_repairs': pending_repairs,
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'completed_sessions': completed_sessions,
                'repair_completion_rate': (completed_repairs / total_repairs * 100) if total_repairs > 0 else 0,
                'session_completion_rate': (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0
            }
        except ImportError:
            return {}

    def _get_platform_performance(self):
        """Get platform performance metrics"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        this_month = now.replace(day=1).date()
        
        # Today's metrics
        today_orders = Order.objects.filter(created_at__date=today).count()
        today_users = User.objects.filter(date_joined__date=today).count()
        today_revenue = Order.objects.filter(
            created_at__date=today,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Yesterday's metrics
        yesterday_orders = Order.objects.filter(created_at__date=yesterday).count()
        yesterday_users = User.objects.filter(date_joined__date=yesterday).count()
        yesterday_revenue = Order.objects.filter(
            created_at__date=yesterday,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # This month's metrics
        this_month_orders = Order.objects.filter(created_at__date__gte=this_month).count()
        this_month_users = User.objects.filter(date_joined__date__gte=this_month).count()
        this_month_revenue = Order.objects.filter(
            created_at__date__gte=this_month,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Growth rates
        order_growth = self._calculate_growth_rate(today_orders, yesterday_orders)
        user_growth = self._calculate_growth_rate(today_users, yesterday_users)
        revenue_growth = self._calculate_growth_rate(today_revenue, yesterday_revenue)
        
        return {
            'today_orders': today_orders,
            'today_users': today_users,
            'today_revenue': float(today_revenue),
            'yesterday_orders': yesterday_orders,
            'yesterday_users': yesterday_users,
            'yesterday_revenue': float(yesterday_revenue),
            'this_month_orders': this_month_orders,
            'this_month_users': this_month_users,
            'this_month_revenue': float(this_month_revenue),
            'order_growth_rate': order_growth,
            'user_growth_rate': user_growth,
            'revenue_growth_rate': revenue_growth
        }

    def _calculate_growth_rate(self, current, previous):
        """Calculate growth rate percentage"""
        if previous == 0:
            return 100 if current > 0 else 0
        return ((current - previous) / previous) * 100


class AdminNotificationView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Send notification to all users (admin only)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['title', 'message'],
            properties={
                'title': openapi.Schema(type=openapi.TYPE_STRING),
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'notification_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['info', 'success', 'warning', 'error'],
                    default='info'
                ),
            }
        ),
        responses={201: openapi.Response("Notification sent successfully")}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_http_status.HTTP_400_BAD_REQUEST
            )
        
        title = request.data.get('title')
        message = request.data.get('message')
        notification_type = request.data.get('notification_type', 'info')
        
        if not title or not message:
            return Response(
                api_response(
                    message="Title and message are required",
                    status=False
                ),
                status=http_http_status.HTTP_400_BAD_REQUEST
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
            notification_type=notification_type
        )
        
        return Response(
            api_response(
                message=f"Notification sent to {len(notifications)} users",
                status=True,
                data={'sent_count': len(notifications)}
            ),
            status=http_http_status.HTTP_201_CREATED
        )


class RoleNotificationView(APIView):
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        operation_description="Send notification to users with specific role (admin only)",  # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['role', 'title', 'message'],
            properties={
                'role': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['customer', 'merchant', 'driver', 'mechanic']
                ),
                'title': openapi.Schema(type=openapi.TYPE_STRING),
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'notification_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['info', 'success', 'warning', 'error'],
                    default='info'
                ),
            }
        ),
        responses={201: openapi.Response("Notification sent successfully")}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_http_status.HTTP_400_BAD_REQUEST
            )
        
        role = request.data.get('role')
        title = request.data.get('title')
        message = request.data.get('message')
        notification_type = request.data.get('notification_type', 'info')
        
        if not role or not title or not message:
            return Response(
                api_response(
                    message="Role, title, and message are required",
                    status=False
                ),
                status=http_http_status.HTTP_400_BAD_REQUEST
            )
        
        # Import service here to avoid circular imports
        from users.services import NotificationService
        
        # Get users with specific role
        users = User.objects.filter(
            roles__name=role,
            is_active=True
        )
        
        # Create notifications for users with role
        notifications = NotificationService.create_bulk_notifications(
            users=users,
            title=title,
            message=message,
            notification_type=notification_type
        )
        
        return Response(
            api_response(
                message=f"Notification sent to {len(notifications)} {role}s",
                status=True,
                data={'sent_count': len(notifications)}
            ),
            status=http_http_status.HTTP_201_CREATED
        )


# Analytics Views (moved from analytics app)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get role-based dashboard for the authenticated user",
        responses={200: DashboardDataSerializer()}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        user_roles = user.roles.values_list('name', flat=True)
        
        # Determine dashboard role
        dashboard_role = 'customer'  # default
        if user.is_staff:
            dashboard_role = 'admin'
        elif 'merchant' in user_roles:
            dashboard_role = 'merchant'
        elif 'driver' in user_roles:
            dashboard_role = 'driver'
        elif 'mechanic' in user_roles:
            dashboard_role = 'mechanic'

        # Get or create dashboard
        dashboard, created = AnalyticsDashboard.objects.get_or_create(
            role=dashboard_role,
            title=f"{dashboard_role.title()} Dashboard",
            defaults={
                'description': f"Analytics dashboard for {dashboard_role} users",
                'is_active': True
            }
        )

        # Get active widgets
        widgets = dashboard.widgets.filter(is_active=True).order_by('position')

        # Generate dashboard data based on role
        dashboard_data = self._generate_dashboard_data(user, dashboard_role)

        # Track dashboard view
        UserAnalytics.objects.create(
            user=user,
            data_type='dashboard_view',
            data={'dashboard_role': dashboard_role, 'widgets_count': widgets.count()}  # noqa
        )

        return Response(
            api_response(
                message="Dashboard data retrieved successfully.",
                status=True,
                data={
                    'dashboard': AnalyticsDashboardSerializer(dashboard).data,
                    'widgets': AnalyticsWidgetListSerializer(widgets, many=True).data,
                    'data': dashboard_data,
                }
            )
        )

    def _generate_dashboard_data(self, user, role):
        """Generate dashboard data based on user role"""
        if role == 'admin':
            return self._get_admin_dashboard_data()
        elif role == 'merchant':
            return self._get_merchant_dashboard_data(user)
        elif role == 'driver':
            return self._get_driver_dashboard_data(user)
        elif role == 'mechanic':
            return self._get_mechanic_dashboard_data(user)
        else:
            return self._get_customer_dashboard_data(user)

    def _get_admin_dashboard_data(self):
        """Get admin dashboard data"""
        from users.models import User
        from products.models import Order, OrderItem
        from rides.models import Ride
        from couriers.models import DeliveryRequest
        from mechanics.models import RepairRequest
        from rentals.models import RentalBooking

        # User counts
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        
        # Sales data
        paid_orders = Order.objects.filter(status__in=['paid', 'shipped', 'completed'])
        total_sales = paid_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Rides and couriers
        total_rides = Ride.objects.count()
        completed_rides = Ride.objects.filter(status='completed').count()
        total_couriers = DeliveryRequest.objects.count()
        completed_couriers = DeliveryRequest.objects.filter(status='completed').count()
        
        # Mechanics
        total_repairs = RepairRequest.objects.count()
        completed_repairs = RepairRequest.objects.filter(status='completed').count()
        
        # Rentals
        total_rentals = RentalBooking.objects.count()
        completed_rentals = RentalBooking.objects.filter(status='completed').count()

        # Revenue by month
        revenue_by_month = self._get_revenue_by_month()

        # Top performers
        top_merchants = self._get_top_merchants()
        top_drivers = self._get_top_drivers()

        return {
            'total_users': total_users,
            'active_users': active_users,
            'total_sales': float(total_sales),
            'total_rides': total_rides,
            'completed_rides': completed_rides,
            'total_couriers': total_couriers,
            'completed_couriers': completed_couriers,
            'total_repairs': total_repairs,
            'completed_repairs': completed_repairs,
            'total_rentals': total_rentals,
            'completed_rentals': completed_rentals,
            'revenue_by_month': revenue_by_month,
            'top_merchants': top_merchants,
            'top_drivers': top_drivers,
        }

    def _get_merchant_dashboard_data(self, user):
        """Get merchant dashboard data"""
        from products.models import Product, Order, OrderItem

        # Product data
        total_products = Product.objects.filter(merchant=user).count()
        rental_products = Product.objects.filter(merchant=user, is_rental=True).count()
        
        # Sales data
        order_items = OrderItem.objects.filter(product__merchant=user)
        order_ids = order_items.values_list('order_id', flat=True).distinct()
        orders = Order.objects.filter(id__in=order_ids)
        
        total_sales = order_items.filter(
            order__status__in=['paid', 'shipped', 'completed']  # noqa
        ).aggregate(
            total=Sum(models.ExpressionWrapper(
                models.F('price') * models.F('quantity'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)
            ))
        )['total'] or 0

        # Order status counts
        order_status_counts = orders.values('status').annotate(count=Count('id'))
        status_counts = {item['status']: item['count'] for item in order_status_counts}

        # Best selling products
        best_selling = order_items.values('product__name').annotate(
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')[:5]
        best_selling_products = [item['product__name'] for item in best_selling]

        return {
            'total_products': total_products,
            'rental_products': rental_products,
            'total_sales': float(total_sales),
            'total_orders': orders.count(),
            'order_status_counts': status_counts,
            'best_selling_products': best_selling_products,
        }

    def _get_driver_dashboard_data(self, user):
        """Get driver dashboard data"""
        from rides.models import Ride
        from couriers.models import DeliveryRequest

        # Rides data
        total_rides = Ride.objects.filter(driver=user).count()
        completed_rides = Ride.objects.filter(driver=user, status='completed').count()
        total_ride_revenue = Ride.objects.filter(
            driver=user, status='completed'
        ).aggregate(total=Sum('fare'))['total'] or 0

        # Couriers data
        total_couriers = DeliveryRequest.objects.filter(driver=user).count()
        completed_couriers = DeliveryRequest.objects.filter(
            driver=user, status='completed'
        ).count()
        total_courier_revenue = DeliveryRequest.objects.filter(
            driver=user, status='completed'
        ).aggregate(total=Sum('fare'))['total'] or 0

        return {
            'total_rides': total_rides,
            'completed_rides': completed_rides,
            'total_ride_revenue': float(total_ride_revenue),
            'total_couriers': total_couriers,
            'completed_couriers': completed_couriers,
            'total_courier_revenue': float(total_courier_revenue),
        }

    def _get_mechanic_dashboard_data(self, user):
        """Get mechanic dashboard data"""
        from mechanics.models import RepairRequest, TrainingSession

        # Repair requests
        total_repairs = RepairRequest.objects.filter(mechanic=user).count()
        completed_repairs = RepairRequest.objects.filter(
            mechanic=user, status='completed'
        ).count()
        pending_repairs = RepairRequest.objects.filter(
            mechanic=user, status='pending'
        ).count()

        # Training sessions
        total_sessions = TrainingSession.objects.filter(instructor=user).count()
        active_sessions = TrainingSession.objects.filter(
            instructor=user, status='in_progress'
        ).count()

        return {
            'total_repairs': total_repairs,
            'completed_repairs': completed_repairs,
            'pending_repairs': pending_repairs,
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
        }

    def _get_customer_dashboard_data(self, user):
        """Get customer dashboard data"""
        from products.models import Order
        from rides.models import Ride
        from rentals.models import RentalBooking

        # Orders
        total_orders = Order.objects.filter(customer=user).count()
        completed_orders = Order.objects.filter(
            customer=user, status='completed'
        ).count()

        # Rides
        total_rides = Ride.objects.filter(customer=user).count()
        completed_rides = Ride.objects.filter(
            customer=user, status='completed'
        ).count()

        # Rentals
        total_rentals = RentalBooking.objects.filter(customer=user).count()
        completed_rentals = RentalBooking.objects.filter(
            customer=user, status='completed'
        ).count()

        return {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'total_rides': total_rides,
            'completed_rides': completed_rides,
            'total_rentals': total_rentals,
            'completed_rentals': completed_rentals,
        }

    def _get_revenue_by_month(self):
        """Get revenue by month for the last 6 months"""
        from products.models import OrderItem
        from django.db.models.functions import TruncMonth

        six_months_ago = timezone.now() - timedelta(days=180)
        
        revenue_by_month = OrderItem.objects.filter(
            order__status__in=['paid', 'shipped', 'completed'],
            order__created_at__gte=six_months_ago
        ).annotate(
            month=TruncMonth('order__created_at')
        ).values('month').annotate(
            revenue=Sum(models.ExpressionWrapper(
                models.F('price') * models.F('quantity'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)
            ))
        ).order_by('month')

        return {
            str(item['month'].date()): float(item['revenue'])
            for item in revenue_by_month
        }

    def _get_top_merchants(self):
        """Get top merchants by sales"""
        from products.models import OrderItem

        top_merchants = OrderItem.objects.filter(
            order__status__in=['paid', 'shipped', 'completed']
        ).values('product__merchant__email').annotate(
            total_sales=Sum(models.ExpressionWrapper(
                models.F('price') * models.F('quantity'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)
            ))
        ).order_by('-total_sales')[:5]

        return [item['product__merchant__email'] for item in top_merchants]

    def _get_top_drivers(self):
        """Get top drivers by completed rides"""
        from rides.models import Ride

        top_drivers = Ride.objects.filter(status='completed').values(
            'driver__email'
        ).annotate(
            completed_rides=Count('id')
        ).order_by('-completed_rides')[:5]

        return [item['driver__email'] for item in top_drivers]


class AnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get platform-wide analytics summary (admin only)",
        responses={200: AnalyticsSummarySerializer()}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        if not request.user.is_staff:
            return Response(
                api_response(
                    message="Only admin users can access platform analytics.",
                    status=False
                ), status=http_status.HTTP_403_FORBIDDEN
            )

        from users.models import User
        from products.models import Order
        from rides.models import Ride
        from couriers.models import DeliveryRequest
        from rentals.models import RentalBooking

        # User counts
        total_users = User.objects.count()
        
        # Sales data
        paid_orders = Order.objects.filter(status__in=['paid', 'shipped', 'completed'])
        total_sales = paid_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Rides and couriers
        total_rides = Ride.objects.count()
        total_couriers = DeliveryRequest.objects.count()
        
        # Rentals
        total_rentals = RentalBooking.objects.count()
        
        # Mechanics (repair requests)
        from mechanics.models import RepairRequest
        total_mechanics = RepairRequest.objects.count()

        # Revenue by month
        revenue_by_month = self._get_revenue_by_month()

        # Top performers
        top_merchants = self._get_top_merchants()
        top_drivers = self._get_top_drivers()

        return Response(
            api_response(
                message="Analytics summary retrieved successfully.",
                status=True,
                data={
                    'total_users': total_users,
                    'total_sales': total_sales,
                    'total_rides': total_rides,
                    'total_couriers': total_couriers,
                    'total_rentals': total_rentals,
                    'total_mechanics': total_mechanics,
                    'revenue_by_month': revenue_by_month,
                    'top_merchants': top_merchants,
                    'top_drivers': top_drivers,
                }
            )
        )

    def _get_revenue_by_month(self):
        """Get revenue by month for the last 6 months"""
        from products.models import OrderItem
        from django.db.models.functions import TruncMonth

        six_months_ago = timezone.now() - timedelta(days=180)
        
        revenue_by_month = OrderItem.objects.filter(
            order__status__in=['paid', 'shipped', 'completed'],
            order__created_at__gte=six_months_ago
        ).annotate(
            month=TruncMonth('order__created_at')
        ).values('month').annotate(
            revenue=Sum(models.ExpressionWrapper(
                models.F('price') * models.F('quantity'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)
            ))
        ).order_by('month')

        return {
            str(item['month'].date()): float(item['revenue'])
            for item in revenue_by_month
        }

    def _get_top_merchants(self):
        """Get top merchants by sales"""
        from products.models import OrderItem

        top_merchants = OrderItem.objects.filter(
            order__status__in=['paid', 'shipped', 'completed']
        ).values('product__merchant__email').annotate(
            total_sales=Sum(models.ExpressionWrapper(
                models.F('price') * models.F('quantity'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)
            ))
        ).order_by('-total_sales')[:5]

        return [item['product__merchant__email'] for item in top_merchants]

    def _get_top_drivers(self):
        """Get top drivers by completed rides"""
        from rides.models import Ride

        top_drivers = Ride.objects.filter(status='completed').values(
            'driver__email'
        ).annotate(
            completed_rides=Count('id')
        ).order_by('-completed_rides')[:5]

        return [item['driver__email'] for item in top_drivers]


class AnalyticsReportView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List analytics reports for the authenticated user",
        responses={200: AnalyticsReportSerializer(many=True)}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        reports = AnalyticsReport.objects.filter(generated_by=request.user)
        
        # Paginate
        paginator = self.pagination_class()
        paginated_reports = paginator.paginate_queryset(reports, request)
        serializer = AnalyticsReportSerializer(paginated_reports, many=True)

        return Response(
            api_response(
                message="Analytics reports retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )

    @swagger_auto_schema(
        operation_description="Generate a new analytics report",
        request_body=AnalyticsReportCreateSerializer,
        responses={201: AnalyticsReportSerializer()}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = AnalyticsReportCreateSerializer(data=request.data)
        if serializer.is_valid():
            report_data = self._generate_report_data(
                serializer.validated_data['report_type'],
                serializer.validated_data['date_from'],
                serializer.validated_data['date_to']
            )
            
            report = AnalyticsReport.objects.create(
                title=serializer.validated_data['title'],
                report_type=serializer.validated_data['report_type'],
                generated_by=request.user,
                date_from=serializer.validated_data['date_from'],
                date_to=serializer.validated_data['date_to'],
                data=report_data
            )
            
            return Response(
                api_response(
                    message="Analytics report generated successfully.",
                    status=True,
                    data=AnalyticsReportSerializer(report).data
                ), status=http_status.HTTP_201_CREATED
            )
        return Response(
            api_response(
                message=serializer.errors,
                status=False
            ), status=http_status.HTTP_400_BAD_REQUEST
        )

    def _generate_report_data(self, report_type, date_from, date_to):
        """Generate report data based on type and date range"""
        if report_type == 'sales':
            return self._generate_sales_report(date_from, date_to)
        elif report_type == 'rides':
            return self._generate_rides_report(date_from, date_to)
        elif report_type == 'couriers':
            return self._generate_couriers_report(date_from, date_to)
        elif report_type == 'mechanics':
            return self._generate_mechanics_report(date_from, date_to)
        elif report_type == 'rentals':
            return self._generate_rentals_report(date_from, date_to)
        elif report_type == 'users':
            return self._generate_users_report(date_from, date_to)
        else:
            return {}

    def _generate_sales_report(self, date_from, date_to):
        """Generate sales report data"""
        from products.models import Order, OrderItem

        orders = Order.objects.filter(
            created_at__date__range=[date_from, date_to]
        )
        
        return {
            'total_orders': orders.count(),
            'total_revenue': float(orders.aggregate(
                total=Sum('total_amount')
            )['total'] or 0),
            'order_status_counts': dict(
                orders.values('status').annotate(count=Count('id'))
            ),
            'revenue_by_day': self._get_revenue_by_day(orders),
        }

    def _generate_rides_report(self, date_from, date_to):
        """Generate rides report data"""
        from rides.models import Ride

        rides = Ride.objects.filter(
            created_at__date__range=[date_from, date_to]
        )
        
        return {
            'total_rides': rides.count(),
            'completed_rides': rides.filter(status='completed').count(),
            'total_revenue': float(rides.filter(
                status='completed'
            ).aggregate(total=Sum('fare'))['total'] or 0),
            'status_counts': dict(
                rides.values('status').annotate(count=Count('id'))
            ),
        }

    def _generate_couriers_report(self, date_from, date_to):
        """Generate couriers report data"""
        from couriers.models import DeliveryRequest

        couriers = DeliveryRequest.objects.filter(
            requested_at__date__range=[date_from, date_to]
        )
        
        return {
            'total_couriers': couriers.count(),
            'completed_couriers': couriers.filter(status='completed').count(),
            'total_revenue': float(couriers.filter(
                status='completed'
            ).aggregate(total=Sum('fare'))['total'] or 0),
            'status_counts': dict(
                couriers.values('status').annotate(count=Count('id'))
            ),
        }

    def _generate_mechanics_report(self, date_from, date_to):
        """Generate mechanics report data"""
        from mechanics.models import RepairRequest

        repairs = RepairRequest.objects.filter(
            requested_at__date__range=[date_from, date_to]
        )
        
        return {
            'total_repairs': repairs.count(),
            'completed_repairs': repairs.filter(status='completed').count(),
            'status_counts': dict(
                repairs.values('status').annotate(count=Count('id'))
            ),
        }

    def _generate_rentals_report(self, date_from, date_to):
        """Generate rentals report data"""
        from rentals.models import RentalBooking

        rentals = RentalBooking.objects.filter(
            booked_at__date__range=[date_from, date_to]
        )
        
        return {
            'total_rentals': rentals.count(),
            'completed_rentals': rentals.filter(status='completed').count(),
            'total_revenue': float(rentals.filter(
                status='completed'
            ).aggregate(total=Sum('total_amount'))['total'] or 0),
            'status_counts': dict(
                rentals.values('status').annotate(count=Count('id'))
            ),
        }

    def _generate_users_report(self, date_from, date_to):
        """Generate users report data"""
        from users.models import User

        users = User.objects.filter(
            date_joined__date__range=[date_from, date_to]
        )
        
        return {
            'total_users': users.count(),
            'active_users': users.filter(is_active=True).count(),
            'verified_users': users.filter(is_verified=True).count(),
            'role_counts': dict(
                users.values('roles__name').annotate(count=Count('id'))
            ),
        }

    def _get_revenue_by_day(self, orders):
        """Get revenue by day for orders"""
        return dict(
            orders.values('created_at__date').annotate(
                revenue=Sum('total_amount')
            ).values_list('created_at__date', 'revenue')
        )


class RealTimeAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get real-time analytics data",
        manual_parameters=[
            openapi.Parameter(
                'type', openapi.IN_QUERY, description="Analytics type (sales, rides, users)",
                type=openapi.TYPE_STRING, required=False
            ),
        ],
        responses={200: openapi.Response("Real-time analytics data")}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        analytics_type = request.query_params.get('type', 'sales')
        
        if analytics_type == 'sales':
            data = self._get_real_time_sales()
        elif analytics_type == 'rides':
            data = self._get_real_time_rides()
        elif analytics_type == 'users':
            data = self._get_real_time_users()
        else:
            data = {}

        return Response(
            api_response(
                message="Real-time analytics retrieved successfully.",
                status=True,
                data=data
            )
        )

    def _get_real_time_sales(self):
        """Get real-time sales data"""
        from products.models import Order
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        this_month = now.replace(day=1).date()

        # Today's sales
        today_sales = Order.objects.filter(
            created_at__date=today,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        # Yesterday's sales
        yesterday_sales = Order.objects.filter(
            created_at__date=yesterday,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        # This month's sales
        this_month_sales = Order.objects.filter(
            created_at__date__gte=this_month,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        return {
            'today_sales': float(today_sales),
            'yesterday_sales': float(yesterday_sales),
            'this_month_sales': float(this_month_sales),
            'growth_rate': self._calculate_growth_rate(today_sales, yesterday_sales)
        }

    def _get_real_time_rides(self):
        """Get real-time rides data"""
        from rides.models import Ride
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)

        # Today's rides
        today_rides = Ride.objects.filter(created_at__date=today).count()
        completed_today = Ride.objects.filter(
            created_at__date=today, status='completed'
        ).count()

        # Yesterday's rides
        yesterday_rides = Ride.objects.filter(created_at__date=yesterday).count()
        completed_yesterday = Ride.objects.filter(
            created_at__date=yesterday, status='completed'
        ).count()

        return {
            'today_rides': today_rides,
            'completed_today': completed_today,
            'yesterday_rides': yesterday_rides,
            'completed_yesterday': completed_yesterday,
            'completion_rate': (completed_today / today_rides * 100) if today_rides > 0 else 0
        }

    def _get_real_time_users(self):
        """Get real-time users data"""
        from users.models import User
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)

        # Today's new users
        today_users = User.objects.filter(date_joined__date=today).count()
        yesterday_users = User.objects.filter(date_joined__date=yesterday).count()

        # Active users (logged in today)
        active_today = User.objects.filter(last_login__date=today).count()

        return {
            'today_new_users': today_users,
            'yesterday_new_users': yesterday_users,
            'active_today': active_today,
            'growth_rate': self._calculate_growth_rate(today_users, yesterday_users)
        }

    def _calculate_growth_rate(self, current, previous):
        """Calculate growth rate percentage"""
        if previous == 0:
            return 100 if current > 0 else 0
        return ((current - previous) / previous) * 100


class AnalyticsCacheView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get cached analytics data",
        manual_parameters=[
            openapi.Parameter(
                'key', openapi.IN_QUERY, description="Cache key",
                type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={200: AnalyticsCacheSerializer()}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        cache_key = request.query_params.get('key')
        if not cache_key:
            return Response(
                api_response(
                    message="Cache key is required.",
                    status=False
                ), status=http_status.HTTP_400_BAD_REQUEST
            )

        try:
            cache_entry = AnalyticsCache.objects.get(key=cache_key)
            if cache_entry.is_expired:
                cache_entry.delete()
                return Response(
                    api_response(
                        message="Cache entry has expired.",
                        status=False
                    ), status=http_status.HTTP_404_NOT_FOUND
                )
            
            serializer = AnalyticsCacheSerializer(cache_entry)
            return Response(
                api_response(
                    message="Cached analytics data retrieved successfully.",
                    status=True,
                    data=serializer.data
                )
            )
        except AnalyticsCache.DoesNotExist:
            return Response(
                api_response(
                    message="Cache entry not found.",
                    status=False
                ), status=http_status.HTTP_404_NOT_FOUND
            )

    @swagger_auto_schema(
        operation_description="Cache analytics data",
        request_body=AnalyticsCacheSerializer,
        responses={201: AnalyticsCacheSerializer()}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        serializer = AnalyticsCacheSerializer(data=request.data)
        if serializer.is_valid():
            cache_entry = serializer.save()
            return Response(
                api_response(
                    message="Analytics data cached successfully.",
                    status=True,
                    data=AnalyticsCacheSerializer(cache_entry).data
                ), status=http_status.HTTP_201_CREATED
            )
        return Response(
            api_response(
                message=serializer.errors,
                status=False
            ), status=http_status.HTTP_400_BAD_REQUEST
        )
