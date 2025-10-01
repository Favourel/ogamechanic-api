from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import models
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncMonth, TruncDate
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

from ogamechanic.modules.utils import (
    get_incoming_request_checks, incoming_request_checks, api_response
)
from ogamechanic.modules.paginations import CustomLimitOffsetPagination
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
            )

        if not request.user.is_staff:
            return Response(
                api_response(
                    message="Only admin users can access platform analytics.",
                    status=False
                ), status=status.HTTP_403_FORBIDDEN
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
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
                ), status=status.HTTP_201_CREATED
            )
        return Response(
            api_response(
                message=serializer.errors,
                status=False
            ), status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
            )

        cache_key = request.query_params.get('key')
        if not cache_key:
            return Response(
                api_response(
                    message="Cache key is required.",
                    status=False
                ), status=status.HTTP_400_BAD_REQUEST
            )

        try:
            cache_entry = AnalyticsCache.objects.get(key=cache_key)
            if cache_entry.is_expired:
                cache_entry.delete()
                return Response(
                    api_response(
                        message="Cache entry has expired.",
                        status=False
                    ), status=status.HTTP_404_NOT_FOUND
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
                ), status=status.HTTP_404_NOT_FOUND
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
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AnalyticsCacheSerializer(data=request.data)
        if serializer.is_valid():
            cache_entry = serializer.save()
            return Response(
                api_response(
                    message="Analytics data cached successfully.",
                    status=True,
                    data=AnalyticsCacheSerializer(cache_entry).data
                ), status=status.HTTP_201_CREATED
            )
        return Response(
            api_response(
                message=serializer.errors,
                status=False
            ), status=status.HTTP_400_BAD_REQUEST
        )
