from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404

from ogamechanic.modules.utils import (
    get_incoming_request_checks,
    incoming_request_checks,
    api_response,
)
from ogamechanic.modules.paginations import CustomLimitOffsetPagination
from .models import RentalBooking, RentalReview, RentalPeriod
from .serializers import (
    RentalBookingSerializer,
    RentalBookingListSerializer,
    RentalBookingStatusUpdateSerializer,
    RentalReviewSerializer,
    RentalReviewListSerializer,
    RentalPeriodSerializer,
    RentalPeriodListSerializer,
)


class RentalBookingListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List rental bookings for the authenticated user",  # noqa
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "product_id",
                openapi.IN_QUERY,
                description="Filter by product",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: RentalBookingListSerializer(many=True)},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Filter based on user role
        if request.user.roles.filter(name="primary_user").exists():
            rental_bookings = RentalBooking.objects.filter(customer=request.user)  # noqa
        elif request.user.roles.filter(name="merchant").exists():
            rental_bookings = RentalBooking.objects.filter(
                product__merchant=request.user
            )
        else:
            rental_bookings = RentalBooking.objects.none()

        # Apply filters
        status_filter = request.query_params.get("status")
        if status_filter:
            rental_bookings = rental_bookings.filter(status=status_filter)

        product_id = request.query_params.get("product_id")
        if product_id:
            rental_bookings = rental_bookings.filter(product_id=product_id)

        # Paginate
        paginator = self.pagination_class()
        paginated_bookings = paginator.paginate_queryset(rental_bookings, request)  # noqa
        serializer = RentalBookingListSerializer(paginated_bookings, many=True)

        return Response(
            api_response(
                message="Rental bookings retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Create a new rental booking",
        request_body=RentalBookingSerializer,
        responses={201: RentalBookingSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only customers can create rental bookings
        if not request.user.roles.filter(name="primary_user").exists():
            return Response(
                api_response(
                    message="Only customers can create rental bookings.", status=False  # noqa
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RentalBookingSerializer(data=request.data)
        if serializer.is_valid():
            rental_booking = serializer.save(customer=request.user)
            return Response(
                api_response(
                    message="Rental booking created successfully.",
                    status=True,
                    data=RentalBookingSerializer(rental_booking).data,
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class RentalBookingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get details of a rental booking",
        responses={200: RentalBookingSerializer()},
    )
    def get(self, request, booking_id):
        rental_booking = get_object_or_404(RentalBooking, id=booking_id)

        # Check permissions
        if (
            rental_booking.customer != request.user
            and rental_booking.product.merchant != request.user
        ):
            return Response(
                api_response(message="Access denied.", status=False),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RentalBookingSerializer(rental_booking)
        return Response(
            api_response(
                message="Rental booking details retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Update rental booking status",
        request_body=RentalBookingStatusUpdateSerializer,
        responses={200: RentalBookingSerializer()},
    )
    def patch(self, request, booking_id):
        rental_booking = get_object_or_404(RentalBooking, id=booking_id)

        # Check permissions
        if (
            rental_booking.customer != request.user
            and rental_booking.product.merchant != request.user
        ):
            return Response(
                api_response(message="Access denied.", status=False),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RentalBookingStatusUpdateSerializer(
            rental_booking, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                api_response(
                    message="Rental booking updated successfully.",
                    status=True,
                    data=RentalBookingSerializer(rental_booking).data,
                )
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class AvailableRentalsView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get list of available rental products",
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "category",
                openapi.IN_QUERY,
                description="Filter by category",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: openapi.Response("List of available rentals")},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        from products.models import Product

        # Get rental products
        rentals = Product.objects.filter(is_rental=True)

        # Apply filters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        category = request.query_params.get("category")

        if category:
            rentals = rentals.filter(category__name=category)

        # Filter by availability if dates provided
        if start_date and end_date:
            # Check for conflicting bookings
            conflicting_bookings = RentalBooking.objects.filter(
                product__in=rentals,
                status__in=["pending", "confirmed", "active"],
                start_date__lte=end_date,
                end_date__gte=start_date,
            ).values_list("product_id", flat=True)

            rentals = rentals.exclude(id__in=conflicting_bookings)

        # Serialize results
        from products.serializers import ProductSerializer

        serializer = ProductSerializer(rentals, many=True)

        return Response(
            api_response(
                message="Available rentals retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )


class RentalReviewListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List reviews for a rental booking",
        responses={200: RentalReviewListSerializer(many=True)},
    )
    def get(self, request, booking_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        rental_booking = get_object_or_404(RentalBooking, id=booking_id)
        reviews = RentalReview.objects.filter(rental=rental_booking)

        # Paginate
        paginator = self.pagination_class()
        paginated_reviews = paginator.paginate_queryset(reviews, request)
        serializer = RentalReviewListSerializer(paginated_reviews, many=True)

        return Response(
            api_response(
                message="Rental reviews retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Add a review for a rental booking",
        request_body=RentalReviewSerializer,
        responses={201: RentalReviewSerializer()},
    )
    def post(self, request, booking_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        rental_booking = get_object_or_404(RentalBooking, id=booking_id)

        # Only the customer can review their own booking
        if rental_booking.customer != request.user:
            return Response(
                api_response(
                    message="You can only review your own rental bookings.",
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if user already reviewed this rental
        if RentalReview.objects.filter(
            rental=rental_booking, customer=request.user
        ).exists():
            return Response(
                api_response(
                    message="You have already reviewed this rental.", 
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RentalReviewSerializer(data=request.data)
        if serializer.is_valid():
            review = serializer.save(rental=rental_booking, customer=request.user)  # noqa
            return Response(
                api_response(
                    message="Review added successfully.",
                    status=True,
                    data=RentalReviewSerializer(review).data,
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class RentalPeriodListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List rental periods for a product",
        responses={200: RentalPeriodListSerializer(many=True)},
    )
    def get(self, request, product_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        from products.models import Product

        product = get_object_or_404(Product, id=product_id, is_rental=True)
        periods = RentalPeriod.objects.filter(product=product)

        # Paginate
        paginator = self.pagination_class()
        paginated_periods = paginator.paginate_queryset(periods, request)
        serializer = RentalPeriodListSerializer(paginated_periods, many=True)

        return Response(
            api_response(
                message="Rental periods retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Create a rental period for a product",
        request_body=RentalPeriodSerializer,
        responses={201: RentalPeriodSerializer()},
    )
    def post(self, request, product_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        from products.models import Product

        product = get_object_or_404(Product, id=product_id, is_rental=True)

        # Only the product owner can create rental periods
        if product.merchant != request.user:
            return Response(
                api_response(
                    message="Only the product owner can create rental periods.",  # noqa
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RentalPeriodSerializer(data=request.data)
        if serializer.is_valid():
            period = serializer.save(product=product)
            return Response(
                api_response(
                    message="Rental period created successfully.",
                    status=True,
                    data=RentalPeriodSerializer(period).data,
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )
