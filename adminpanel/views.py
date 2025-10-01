from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from django.utils import timezone
from users.models import (User, MechanicProfile, MerchantProfile, 
                          DriverProfile)
from products.models import Order, OrderItem
from users.serializers import (MechanicProfileSerializer, 
                               DriverProfileSerializer)
from django.db.models import (Sum, Count, F, DecimalField, 
                              ExpressionWrapper)
from drf_yasg import openapi
from ogamechanic.modules.utils import (
    api_response, incoming_request_checks, get_incoming_request_checks)
from django.db.models.functions import TruncMonth
from users.models import Role
from products.serializers import CategorySerializer
from django.db.models import Avg
from rest_framework import status as http_status


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
                status=http_status.HTTP_400_BAD_REQUEST
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
                status=http_status.HTTP_400_BAD_REQUEST
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
            status=http_status.HTTP_201_CREATED
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
                status=http_status.HTTP_400_BAD_REQUEST
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
                status=http_status.HTTP_400_BAD_REQUEST
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
            status=http_status.HTTP_201_CREATED
        )

