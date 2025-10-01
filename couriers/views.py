from rest_framework.views import APIView
from rest_framework import permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from ogamechanic.modules.utils import (
    api_response,
    get_incoming_request_checks,
    incoming_request_checks,
)
from ogamechanic.modules.location_service import LocationService
from users.models import User
from .models import DeliveryRequest, DeliveryTracking, DeliveryWaypoint
from .serializers import (
    DeliveryRequestSerializer,
    DeliveryRequestCreateSerializer,
    DeliveryTrackingSerializer,
    CourierRatingSerializer,
    DeliveryWaypointSerializer,
    # DeliveryWaypointCreateSerializer,
    DeliveryWaypointUpdateSerializer,
    CourierRequestCreateSerializer,
    CourierRequestListSerializer,
    CourierRequestStatusUpdateSerializer,
    DriverLocationUpdateSerializer,
    CourierRequestSerializer,
)


class DeliveryWaypointListView(APIView):
    """List waypoints for a delivery request."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List waypoints for a specific delivery request",
        responses={200: DeliveryWaypointSerializer(many=True)},
    )
    def get(self, request, delivery_id):
        """Get waypoints for a delivery request."""
        try:
            delivery = DeliveryRequest.objects.get(id=delivery_id)

            # Check if user has access to this delivery
            if delivery.customer != request.user and delivery.driver != request.user:
                return Response(
                    api_response(message="Access denied", status=False), status=403
                )

            waypoints = delivery.waypoints.all().order_by("sequence_order")
            serializer = DeliveryWaypointSerializer(waypoints, many=True)

            return Response(
                api_response(
                    message="Delivery waypoints retrieved successfully",
                    status=True,
                    data=serializer.data,
                )
            )
        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Delivery request not found", status=False),
                status=404,
            )


class DeliveryWaypointUpdateView(APIView):
    """Update delivery waypoint completion status."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update delivery waypoint completion status",
        request_body=DeliveryWaypointUpdateSerializer,
        responses={200: DeliveryWaypointSerializer()},
    )
    def patch(self, request, delivery_id, waypoint_id):
        """Update delivery waypoint completion status."""
        try:
            delivery = DeliveryRequest.objects.get(id=delivery_id)
            waypoint = DeliveryWaypoint.objects.get(
                id=waypoint_id, delivery_requests=delivery
            )

            # Check if user has access to this delivery
            if delivery.customer != request.user and delivery.driver != request.user:
                return Response(
                    api_response(message="Access denied", status=False), status=403
                )

            serializer = DeliveryWaypointUpdateSerializer(
                waypoint, data=request.data, partial=True
            )
            if serializer.is_valid():
                waypoint = serializer.save()

                # Check if all waypoints are completed
                if delivery.is_route_completed():
                    delivery.status = "delivered"
                    delivery.delivered_at = timezone.now()
                    delivery.save()

                response_serializer = DeliveryWaypointSerializer(waypoint)
                return Response(
                    api_response(
                        message="Delivery waypoint updated successfully",
                        status=True,
                        data=response_serializer.data,
                    )
                )

            return Response(
                api_response(message=serializer.errors, status=False), status=400
            )
        except (DeliveryRequest.DoesNotExist, DeliveryWaypoint.DoesNotExist):
            return Response(
                api_response(
                    message="Delivery request or waypoint not found", status=False
                ),
                status=404,
            )


class MultiWaypointDeliveryCreateView(APIView):
    """Create a delivery request with multiple waypoints."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Create a delivery request with multiple waypoints",
        request_body=DeliveryRequestCreateSerializer,
        responses={201: DeliveryRequestSerializer()},
    )
    def post(self, request):
        """Create a delivery request with multiple waypoints."""
        serializer = DeliveryRequestCreateSerializer(data=request.data)
        if serializer.is_valid():
            delivery = serializer.save(customer=request.user)

            # Calculate total distance and duration
            total_distance = delivery.calculate_total_distance_km()
            total_duration = total_distance * 2  # Rough estimate: 2 min per km

            # Update delivery with calculated values
            delivery.total_distance_km = total_distance
            delivery.total_duration_min = total_duration
            delivery.save()

            # Calculate fare
            fare = self._calculate_fare(total_distance, total_duration)
            delivery.total_fare = fare
            delivery.save()

            response_serializer = DeliveryRequestSerializer(delivery)
            return Response(
                api_response(
                    message="Delivery request with multiple waypoints created successfully",
                    status=True,
                    data=response_serializer.data,
                ),
                status=201,
            )

        return Response(
            api_response(message=serializer.errors, status=False), status=400
        )

    def _calculate_fare(self, distance_km, duration_min):
        """Calculate fare based on distance and duration."""
        base_fare = 700  # Base fare in NGN
        per_km_rate = 150  # Rate per kilometer
        per_min_rate = 3  # Rate per minute

        distance_fare = distance_km * per_km_rate
        time_fare = duration_min * per_min_rate
        total_fare = base_fare + distance_fare + time_fare

        return round(total_fare, 2)


class DeliveryRouteOptimizationView(APIView):
    """Optimize route for multiple delivery waypoints."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Optimize route for multiple delivery waypoints",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["waypoints"],
            properties={
                "waypoints": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "address": openapi.Schema(type=openapi.TYPE_STRING),
                            "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "waypoint_type": openapi.Schema(type=openapi.TYPE_STRING),
                            "package_description": openapi.Schema(
                                type=openapi.TYPE_STRING
                            ),
                            "package_weight": openapi.Schema(type=openapi.TYPE_NUMBER),
                        },
                    ),
                )
            },
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "optimized_route": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    "total_distance": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "total_duration": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "estimated_fare": openapi.Schema(type=openapi.TYPE_NUMBER),
                },
            )
        },
    )
    def post(self, request):
        """Optimize route for multiple delivery waypoints."""
        waypoints_data = request.data.get("waypoints", [])

        if len(waypoints_data) < 2:
            return Response(
                api_response(
                    message="At least 2 waypoints are required for route optimization",
                    status=False,
                ),
                status=400,
            )

        try:
            # Simple optimization: sort by distance from first waypoint
            # In production, use more sophisticated algorithms
            first_waypoint = waypoints_data[0]
            other_waypoints = waypoints_data[1:]

            # Calculate distances from first waypoint
            optimized_waypoints = [first_waypoint]

            while other_waypoints:
                current_waypoint = optimized_waypoints[-1]
                nearest_waypoint = None
                min_distance = float("inf")

                for waypoint in other_waypoints:
                    distance = LocationService.haversine_distance(
                        float(current_waypoint["latitude"]),
                        float(current_waypoint["longitude"]),
                        float(waypoint["latitude"]),
                        float(waypoint["longitude"]),
                    )

                    if distance < min_distance:
                        min_distance = distance
                        nearest_waypoint = waypoint

                if nearest_waypoint:
                    optimized_waypoints.append(nearest_waypoint)
                    other_waypoints.remove(nearest_waypoint)

            # Calculate total distance and duration
            total_distance = 0
            for i in range(len(optimized_waypoints) - 1):
                wp1 = optimized_waypoints[i]
                wp2 = optimized_waypoints[i + 1]
                distance = LocationService.haversine_distance(
                    float(wp1["latitude"]),
                    float(wp1["longitude"]),
                    float(wp2["latitude"]),
                    float(wp2["longitude"]),
                )
                total_distance += distance

            total_duration = total_distance * 2  # Rough estimate

            # Calculate estimated fare
            base_fare = 700
            per_km_rate = 150
            per_min_rate = 3
            distance_fare = total_distance * per_km_rate
            time_fare = total_duration * per_min_rate
            estimated_fare = base_fare + distance_fare + time_fare

            return Response(
                api_response(
                    message="Delivery route optimized successfully",
                    status=True,
                    data={
                        "optimized_route": optimized_waypoints,
                        "total_distance": round(total_distance, 2),
                        "total_duration": round(total_duration, 2),
                        "estimated_fare": round(estimated_fare, 2),
                    },
                )
            )
        except Exception as e:
            return Response(
                api_response(
                    message=f"Route optimization failed: {str(e)}", status=False
                ),
                status=500,
            )


class DeliveryRequestListView(APIView):
    """List delivery requests."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List delivery requests for the authenticated user",
        responses={200: DeliveryRequestSerializer(many=True)},
    )
    def get(self, request):
        """List delivery requests."""
        user = request.user

        if user.roles.filter(name="admin").exists():
            # Admin can see all delivery requests
            deliveries = DeliveryRequest.objects.all().order_by("-requested_at")
        elif user.roles.filter(name="driver").exists():
            # Driver can see assigned deliveries and available ones
            deliveries = DeliveryRequest.objects.filter(
                Q(driver=user) | Q(driver__isnull=True, status="pending")
            ).order_by("-requested_at")
        else:
            # Customer can only see their own deliveries
            deliveries = DeliveryRequest.objects.filter(customer=user).order_by(
                "-requested_at"
            )

        serializer = DeliveryRequestSerializer(deliveries, many=True)
        return Response(
            api_response(
                message="Delivery requests retrieved successfully",
                status=True,
                data=serializer.data,
            )
        )


class DeliveryRequestDetailView(APIView):
    """Get delivery request details."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get delivery request details",
        responses={200: DeliveryRequestSerializer()},
    )
    def get(self, request, delivery_id):
        """Get delivery request details."""
        try:
            delivery = DeliveryRequest.objects.get(id=delivery_id)

            # Check if user has access to this delivery
            if delivery.customer != request.user and delivery.driver != request.user:
                return Response(
                    api_response(message="Access denied", status=False), status=403
                )

            serializer = DeliveryRequestSerializer(delivery)
            return Response(
                api_response(
                    message="Delivery request details retrieved successfully",
                    status=True,
                    data=serializer.data,
                )
            )
        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Delivery request not found", status=False),
                status=404,
            )


class DeliveryStatusUpdateView(APIView):
    """Update delivery status."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update delivery status",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["status"],
            properties={
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=[
                        "assigned",
                        "picked_up",
                        "in_transit",
                        "delivered",
                        "cancelled",
                    ],
                    description="New delivery status",
                )
            },
        ),
        responses={200: DeliveryRequestSerializer()},
    )
    def patch(self, request, delivery_id):
        """Update delivery status."""
        try:
            delivery = DeliveryRequest.objects.get(id=delivery_id)

            # Check if user has access to this delivery
            if delivery.customer != request.user and delivery.driver != request.user:
                return Response(
                    api_response(message="Access denied", status=False), status=403
                )

            new_status = request.data.get("status")
            if not new_status:
                return Response(
                    api_response(message="Status is required", status=False), status=400
                )

            # Update status based on current status
            if new_status == "assigned" and delivery.status == "pending":
                delivery.status = "assigned"
                delivery.assigned_at = timezone.now()
            elif new_status == "picked_up" and delivery.status == "assigned":
                delivery.status = "picked_up"
                delivery.picked_up_at = timezone.now()
            elif new_status == "in_transit" and delivery.status == "picked_up":
                delivery.status = "in_transit"
            elif new_status == "delivered" and delivery.status in [
                "picked_up",
                "in_transit",
            ]:
                delivery.status = "delivered"
                delivery.delivered_at = timezone.now()
            elif new_status == "cancelled" and delivery.status in [
                "pending",
                "assigned",
            ]:
                delivery.status = "cancelled"
                delivery.cancelled_at = timezone.now()
            else:
                return Response(
                    api_response(
                        message="Invalid status transition", status=False),
                    status=400,
                )

            delivery.save()
            serializer = DeliveryRequestSerializer(delivery)
            return Response(
                api_response(
                    message="Delivery status updated successfully",
                    status=True,
                    data=serializer.data,
                )
            )
        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Delivery request not found", status=False),
                status=404,
            )


class CourierRequestCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Create a new courier request",
        request_body=CourierRequestCreateSerializer,
        responses={201: CourierRequestListSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        # Check if user is a customer
        if not request.user.roles.filter(name="customer").exists():
            return Response(
                api_response(
                    message="Only customers can create courier requests", status=False
                ),
                status=403,
            )

        serializer = CourierRequestCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Validate coordinates
            pickup_lat = serializer.validated_data["pickup_latitude"]
            pickup_lon = serializer.validated_data["pickup_longitude"]
            delivery_lat = serializer.validated_data["delivery_latitude"]
            delivery_lon = serializer.validated_data["delivery_longitude"]

            if not LocationService.validate_coordinates(pickup_lat, pickup_lon):
                return Response(
                    api_response(
                        message="Invalid pickup coordinates", status=False),
                    status=400,
                )

            if not LocationService.validate_coordinates(delivery_lat, delivery_lon):
                return Response(
                    api_response(
                        message="Invalid delivery coordinates", status=False),
                    status=400,
                )

            # Calculate distance and duration using LocationService
            route_info = LocationService.get_directions(
                pickup_lat, pickup_lon, delivery_lat, delivery_lon
            )

            if route_info:
                distance_km = route_info["distance_km"]
                duration_min = route_info["duration_min"]
            else:
                # Fallback to haversine calculation
                distance_km = LocationService.haversine_distance(
                    pickup_lat, pickup_lon, delivery_lat, delivery_lon
                )
                duration_min = distance_km * 2  # Rough estimate

            # Calculate fare
            base_fare = 1000  # Base fare in NGN
            per_km_rate = 150  # Rate per kilometer
            per_min_rate = 3  # Rate per minute

            distance_fare = distance_km * per_km_rate
            time_fare = duration_min * per_min_rate
            total_fare = base_fare + distance_fare + time_fare

            # Create the delivery request
            delivery_request = serializer.save(
                customer=request.user,
                estimated_distance=distance_km,
                estimated_duration=int(duration_min),
                base_fare=base_fare,
                distance_fare=distance_fare,
                total_fare=total_fare,
            )

            # Find nearby drivers
            nearby_drivers = LocationService.find_nearby_drivers(
                pickup_lat, pickup_lon, radius_km=10.0, limit=5
            )

            return Response(
                api_response(
                    message="Courier request created successfully",
                    status=True,
                    data={
                        "delivery_request": CourierRequestSerializer(
                            delivery_request
                        ).data,
                        "nearby_drivers": nearby_drivers,
                        "route_info": {
                            "distance_km": round(distance_km, 2),
                            "duration_min": round(duration_min, 2),
                            "polyline": (
                                route_info.get(
                                    "polyline") if route_info else None
                            ),
                        },
                        "map_url": MapIntegrationService.get_route_map_url(
                            pickup_lat, pickup_lon, delivery_lat, delivery_lon
                        ),
                    },
                ),
                status=201,
            )
        else:
            return Response(
                api_response(
                    message="Invalid data provided",
                    status=False,
                    data=serializer.errors,
                ),
                status=400,
            )


class CourierRequestDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get courier request details",
        responses={200: CourierRequestListSerializer()},
    )
    def get(self, request, request_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        try:
            delivery_request = DeliveryRequest.objects.get(id=request_id)

            # Check if user has access to this request
            if not (
                request.user == delivery_request.customer
                or request.user == delivery_request.driver
                or request.user.is_staff
            ):
                return Response(
                    api_response(
                        message="You don't have permission to view this request",
                        status=False,
                    ),
                    status=403,
                )

            serializer = CourierRequestListSerializer(delivery_request)
            return Response(
                api_response(
                    message="Courier request details retrieved successfully",
                    status=True,
                    data=serializer.data,
                )
            )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Courier request not found", status=False),
                status=404,
            )


class CourierRequestStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update courier request status",
        request_body=CourierRequestStatusUpdateSerializer,
        responses={200: CourierRequestListSerializer()},
    )
    def patch(self, request, request_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        # Check if user is a driver
        if not request.user.roles.filter(name="driver").exists():
            return Response(
                api_response(
                    message="Only drivers can update courier request status",
                    status=False,
                ),
                status=403,
            )

        try:
            delivery_request = DeliveryRequest.objects.get(
                id=request_id, driver=request.user
            )

            serializer = CourierRequestStatusUpdateSerializer(
                delivery_request, data=request.data, partial=True
            )

            if serializer.is_valid():
                # Handle status transitions
                new_status = request.data.get("status")
                if new_status:
                    if new_status == "picked_up":
                        delivery_request.mark_as_picked_up()
                    elif new_status == "in_transit":
                        delivery_request.mark_as_in_transit()
                    elif new_status == "delivered":
                        delivery_request.mark_as_delivered()
                    else:
                        delivery_request.status = new_status
                        delivery_request.save()

                # Update notes if provided
                if "notes" in request.data:
                    delivery_request.notes = request.data["notes"]
                    delivery_request.save()

                return Response(
                    api_response(
                        message="Courier request status updated successfully",
                        status=True,
                        data=CourierRequestListSerializer(
                            delivery_request).data,
                    )
                )
            else:
                return Response(
                    api_response(
                        message="Invalid data provided",
                        status=False,
                        data=serializer.errors,
                    ),
                    status=400,
                )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Courier request not found", status=False),
                status=404,
            )


class CourierRequestCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Cancel a courier request",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "reason": openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        responses={200: openapi.Response("Request cancelled successfully")},
    )
    def post(self, request, request_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        # Check if user is a customer
        if not request.user.roles.filter(name="customer").exists():
            return Response(
                api_response(
                    message="Only customers can cancel courier requests", status=False
                ),
                status=403,
            )

        try:
            delivery_request = DeliveryRequest.objects.get(
                id=request_id, customer=request.user
            )

            if not delivery_request.can_be_cancelled:
                return Response(
                    api_response(
                        message="This courier request cannot be cancelled", status=False
                    ),
                    status=400,
                )

            reason = request.data.get("reason", "")
            if delivery_request.cancel_request(reason):
                return Response(
                    api_response(
                        message="Courier request cancelled successfully",
                        status=True,
                        data={},
                    )
                )
            else:
                return Response(
                    api_response(
                        message="Failed to cancel courier request", status=False
                    ),
                    status=400,
                )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Courier request not found", status=False),
                status=404,
            )


class AvailableDriversView(APIView):
    """Get available drivers for a courier request"""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get available drivers for courier request",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["pickup_latitude", "pickup_longitude"],
            properties={
                "pickup_latitude": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
                "pickup_longitude": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
            },
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "driver_id": openapi.Schema(type=openapi.TYPE_STRING),
                        "driver_email": openapi.Schema(type=openapi.TYPE_STRING),
                        "driver_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "distance_to_pickup": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                        "estimated_arrival": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "current_rating": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                        "vehicle_info": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            )
        },
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        pickup_lat = float(data.get("pickup_latitude"))
        pickup_lon = float(data.get("pickup_longitude"))

        # Get available drivers (not currently assigned to active requests)
        available_drivers = LocationService.find_nearby_drivers(
            pickup_lat, pickup_lon, radius_km=10.0, limit=5
        )

        # Sort by distance
        available_drivers.sort(key=lambda x: x["distance_to_pickup"])

        return Response(
            api_response(
                message="Available drivers retrieved successfully.",
                status=True,
                data=available_drivers,
            )
        )


class AssignDriverView(APIView):
    """Assign a driver to a courier request"""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Assign driver to courier request",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["driver_id"],
            properties={
                "driver_id": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Driver UUID"
                )
            },
        ),
        responses={200: CourierRequestListSerializer()},
    )
    def post(self, request, request_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        # Only customers can assign drivers
        if not request.user.roles.filter(name="customer").exists():
            return Response(
                api_response(
                    message="Only customers can assign drivers.", status=False
                ),
                status=403,
            )

        try:
            courier_request = DeliveryRequest.objects.get(
                id=request_id, customer=request.user
            )

            if courier_request.status != "pending":
                return Response(
                    api_response(
                        message="Can only assign driver to pending requests.",
                        status=False,
                    ),
                    status=400,
                )

            driver_id = data.get("driver_id")
            try:
                driver = User.objects.get(id=driver_id, roles__name="driver")
            except User.DoesNotExist:
                return Response(
                    api_response(
                        message="Driver not found or not a valid driver.", status=False
                    ),
                    status=404,
                )

            if courier_request.assign_driver(driver):
                return Response(
                    api_response(
                        message="Driver assigned successfully.",
                        status=True,
                        data=CourierRequestListSerializer(
                            courier_request).data,
                    )
                )
            else:
                return Response(
                    api_response(
                        message="Failed to assign driver.", status=False),
                    status=400,
                )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Courier request not found", status=False),
                status=404,
            )


class DriverLocationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update driver location for courier request",
        request_body=DriverLocationUpdateSerializer,
        responses={200: DriverLocationUpdateSerializer()},
    )
    def post(self, request, request_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        # Check if user is a driver
        if not request.user.roles.filter(name="driver").exists():
            return Response(
                api_response(
                    message="Only drivers can update location", status=False),
                status=403,
            )

        try:
            delivery_request = DeliveryRequest.objects.get(id=request_id)

            # Check if driver is assigned to this request
            if delivery_request.driver != request.user:
                return Response(
                    api_response(
                        message="You can only update location for your assigned deliveries",
                        status=False,
                    ),
                    status=403,
                )

            serializer = DriverLocationUpdateSerializer(
                delivery_request, data=request.data
            )

            if serializer.is_valid():
                # Validate coordinates
                latitude = serializer.validated_data["driver_latitude"]
                longitude = serializer.validated_data["driver_longitude"]

                if not LocationService.validate_coordinates(latitude, longitude):
                    return Response(
                        api_response(
                            message="Invalid coordinates", status=False),
                        status=400,
                    )

                # Update location using LocationService
                LocationService.update_driver_location(
                    str(request.user.id), latitude, longitude
                )

                # Save the delivery request
                serializer.save()

                return Response(
                    api_response(
                        message="Location updated successfully",
                        status=True,
                        data=serializer.data,
                    )
                )
            else:
                return Response(
                    api_response(
                        message="Invalid data provided",
                        status=False,
                        data=serializer.errors,
                    ),
                    status=400,
                )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Delivery request not found", status=False),
                status=404,
            )


class DeliveryTrackingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get delivery tracking information",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "delivery_request": CourierRequestSerializer(),
                    "tracking_updates": DeliveryTrackingSerializer(many=True),
                    "driver_location": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "timestamp": openapi.Schema(type=openapi.TYPE_STRING),
                        },
                    ),
                    "eta": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "total_duration_min": openapi.Schema(
                                type=openapi.TYPE_NUMBER
                            ),
                            "driver_to_pickup_eta_min": openapi.Schema(
                                type=openapi.TYPE_NUMBER
                            ),
                            "total_distance_km": openapi.Schema(
                                type=openapi.TYPE_NUMBER
                            ),
                        },
                    ),
                },
            )
        },
    )
    def get(self, request, request_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        try:
            delivery_request = DeliveryRequest.objects.get(id=request_id)

            # Check if user has access to this delivery
            if not (
                request.user == delivery_request.customer
                or request.user == delivery_request.driver
                or request.user.is_staff
            ):
                return Response(
                    api_response(
                        message="You don't have permission to track this delivery",
                        status=False,
                    ),
                    status=403,
                )

            # Get tracking updates
            tracking_updates = DeliveryTracking.objects.filter(
                delivery_request=delivery_request
            ).order_by("-timestamp")

            # Get driver location
            driver_location = None
            if delivery_request.driver and delivery_request.driver.driver_profile:
                profile = delivery_request.driver.driver_profile
                if profile.latitude and profile.longitude:
                    driver_location = {
                        "latitude": float(profile.latitude),
                        "longitude": float(profile.longitude),
                        "timestamp": profile.updated_at.isoformat(),
                    }

            # Calculate ETA
            eta_data = None
            if driver_location:
                eta_data = LocationService.calculate_route_eta(
                    float(delivery_request.pickup_latitude),
                    float(delivery_request.pickup_longitude),
                    float(delivery_request.delivery_latitude),
                    float(delivery_request.delivery_longitude),
                    driver_location["latitude"],
                    driver_location["longitude"],
                )

            # Get route polyline
            route_info = LocationService.get_directions(
                float(delivery_request.pickup_latitude),
                float(delivery_request.pickup_longitude),
                float(delivery_request.delivery_latitude),
                float(delivery_request.delivery_longitude),
            )

            response_data = {
                "delivery_request": CourierRequestSerializer(delivery_request).data,
                "tracking_updates": DeliveryTrackingSerializer(
                    tracking_updates, many=True
                ).data,
                "driver_location": driver_location,
                "eta": eta_data,
                "route_polyline": route_info.get("polyline") if route_info else None,
                "map_url": MapIntegrationService.get_route_map_url(
                    float(delivery_request.pickup_latitude),
                    float(delivery_request.pickup_longitude),
                    float(delivery_request.delivery_latitude),
                    float(delivery_request.delivery_longitude),
                ),
            }

            return Response(
                api_response(
                    message="Delivery tracking data retrieved successfully",
                    status=True,
                    data=response_data,
                )
            )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Delivery request not found", status=False),
                status=404,
            )


class CourierRatingView(APIView):
    """Rate courier service"""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Rate courier service (customers only)",
        request_body=CourierRatingSerializer,
        responses={201: CourierRatingSerializer()},
    )
    def post(self, request, request_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(api_response(message=data, status=False), status=400)

        # Only customers can rate
        if not request.user.roles.filter(name="customer").exists():
            return Response(
                api_response(
                    message="Only customers can rate courier services.", status=False
                ),
                status=403,
            )

        try:
            courier_request = DeliveryRequest.objects.get(
                id=request_id, customer=request.user
            )

            # Check if already rated
            if hasattr(courier_request, "rating"):
                return Response(
                    api_response(
                        message="This courier request has already been rated.",
                        status=False,
                    ),
                    status=400,
                )

            # Check if delivery is completed
            if courier_request.status != "delivered":
                return Response(
                    api_response(
                        message="Can only rate completed deliveries.", status=False
                    ),
                    status=400,
                )

            # Add courier request and user data
            data["courier_request"] = request_id
            data["customer"] = str(request.user.id)
            data["driver"] = str(courier_request.driver.id)

            serializer = CourierRatingSerializer(data=data)

            if serializer.is_valid():
                rating = serializer.save()
                return Response(
                    api_response(
                        message="Rating submitted successfully.",
                        status=True,
                        data=serializer.data,
                    ),
                    status=201,
                )
            else:
                return Response(
                    api_response(
                        message="Invalid data provided",
                        status=False,
                        data=serializer.errors,
                    ),
                    status=400,
                )

        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Courier request not found", status=False),
                status=404,
            )
