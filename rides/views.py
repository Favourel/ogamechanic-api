from rest_framework.views import APIView
from rest_framework import permissions
from rest_framework.response import Response
from .models import Ride
from .serializers import RideSerializer
from ogamechanic.modules.utils import (
    api_response,
    get_incoming_request_checks,
    incoming_request_checks,
)
from ogamechanic.modules.location_service import LocationService, MapIntegrationService # noqa
from users.models import User
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils import timezone
from django.db import models
from couriers.serializers import CourierRequestSerializer
from django.db.models import Count, Sum, F, DecimalField, ExpressionWrapper, Func # noqa
from django.db import transaction
from couriers.models import DeliveryRequest
from couriers.serializers import CourierRequestListSerializer

from rest_framework import status
import logging
from math import radians, sin, cos, sqrt, atan2
from .tasks import notify_drivers_task, notify_user_of_ride_status_task
from .serializers import WaypointSerializer, WaypointUpdateSerializer, RideCreateSerializer # noqa
from .models import Waypoint # noqa
from ogamechanic.modules.idempotency import (
    get_cached_response,
    store_response,
    IdempotencyConflict,
)

logger = logging.getLogger(__name__)


class RideListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "List rides for the authenticated user (customer or driver)"
        ),
        responses={200: RideSerializer(many=True)},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=status.HTTP_400_BAD_REQUEST
            )
        user = request.user
        rides = Ride.objects.filter(
            models.Q(customer=user) | models.Q(driver=user)
        ).order_by("-requested_at")
        serializer = RideSerializer(rides, many=True)
        return Response(
            api_response(
                message="Rides retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    def _calculate_fare(self, distance_km, duration_min):
        """Calculate fare based on distance and duration"""
        base_fare = 500  # Base fare in NGN
        per_km_rate = 100  # Rate per kilometer
        per_min_rate = 2  # Rate per minute

        distance_fare = distance_km * per_km_rate
        time_fare = duration_min * per_min_rate
        total_fare = base_fare + distance_fare + time_fare

        return round(total_fare, 2)

    @swagger_auto_schema(
        operation_description=(
            "Book a ride (customer only, with geolocation and driver selection)"
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
                    required=[
                        "pickup_address",
                        "pickup_latitude",
                        "pickup_longitude",
                        "dropoff_address",
                        "dropoff_latitude",
                        "dropoff_longitude",
                    ],
                    properties={
                        "pickup_address": openapi.Schema(
                            type=openapi.TYPE_STRING
                        ),
                        "pickup_latitude": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                        "pickup_longitude": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                        "dropoff_address": openapi.Schema(
                            type=openapi.TYPE_STRING
                        ),
                        "dropoff_latitude": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                        "dropoff_longitude": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                    },
                ),
            },
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "suggested_fare": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "distance_km": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "duration_min": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "drivers": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    "route_info": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "polyline": openapi.Schema(type=openapi.TYPE_STRING),
                            "bounds": openapi.Schema(type=openapi.TYPE_OBJECT),
                        }
                    ),
                },
            )
        },
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=status.HTTP_400_BAD_REQUEST
            )

        # Extract data
        data = request.data.get('data', {})
        pickup_address = data.get('pickup_address')
        pickup_lat = float(data.get('pickup_latitude'))
        pickup_lon = float(data.get('pickup_longitude'))
        dropoff_address = data.get('dropoff_address')
        dropoff_lat = float(data.get('dropoff_latitude'))
        dropoff_lon = float(data.get('dropoff_longitude'))

        # Validate coordinates
        if not LocationService.validate_coordinates(pickup_lat, pickup_lon):
            return Response(
                api_response(
                    message="Invalid pickup coordinates",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        if not LocationService.validate_coordinates(dropoff_lat, dropoff_lon):
            return Response(
                api_response(
                    message="Invalid dropoff coordinates",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get route information using LocationService
        route_info = LocationService.get_directions(
            pickup_lat, pickup_lon, dropoff_lat, dropoff_lon
        )

        if route_info:
            distance_km = route_info['distance_km']
            duration_min = route_info['duration_min']
        else:
            # Fallback to haversine calculation
            distance_km = LocationService.haversine_distance(
                pickup_lat, pickup_lon, dropoff_lat, dropoff_lon
            )
            duration_min = distance_km * 2  # Rough estimate: 2 min per km

        # Calculate fare
        suggested_fare = self._calculate_fare(distance_km, duration_min)

        # Find nearby drivers using LocationService
        nearby_drivers = LocationService.find_nearby_drivers(
            pickup_lat, pickup_lon, radius_km=10.0, limit=10
        )

        # Prepare response data
        response_data = {
            "suggested_fare": suggested_fare,
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 2),
            "drivers": nearby_drivers,
            "route_info": {
                "polyline": route_info.get('polyline') if route_info else None,
                "bounds": route_info.get('bounds') if route_info else None,
            } if route_info else None,
            "map_url": MapIntegrationService.get_route_map_url(
                pickup_lat, pickup_lon, dropoff_lat, dropoff_lon
            )
        }

        return Response(
            api_response(
                message="Ride options calculated successfully.",
                status=True,
                data=response_data,
            )
        )


class RideConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Confirm a ride with selected driver and price",

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
                    required=[
                        # "pickup_address",
                        # "pickup_latitude",
                        # "pickup_longitude",
                        # "dropoff_address",
                        # "dropoff_latitude",
                        # "dropoff_longitude",
                        "ride_id",
                        "driver_id",
                        "fare",
                    ],
                    properties={
                        # "pickup_address": openapi.Schema(
                        #     type=openapi.TYPE_STRING
                        # ),
                        # "pickup_latitude": openapi.Schema(
                        #     type=openapi.TYPE_NUMBER, format="float"
                        # ),
                        # "pickup_longitude": openapi.Schema(
                        #     type=openapi.TYPE_NUMBER, format="float"
                        # ),
                        # "dropoff_address": openapi.Schema(
                        #     type=openapi.TYPE_STRING
                        # ),
                        # "dropoff_latitude": openapi.Schema(
                        #     type=openapi.TYPE_NUMBER, format="float"
                        # ),
                        # "dropoff_longitude": openapi.Schema(
                        #     type=openapi.TYPE_NUMBER, format="float"
                        # ),
                        "ride_id": openapi.Schema(
                            type=openapi.TYPE_STRING
                        ),
                        "driver_id": openapi.Schema(
                            type=openapi.TYPE_STRING
                        ),
                        "fare": openapi.Schema(
                            type=openapi.TYPE_NUMBER, format="float"
                        ),
                    },
                ),
            },
        ),
        responses={201: RideSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=status.HTTP_400_BAD_REQUEST
            )
        user = request.user
        if not user.roles.filter(name="rider").exists():
            return Response(
                api_response(
                    message="Only riders can confirm rides.", status=False
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        required_fields = [
            "ride_id",
            "driver_id",
            "fare",
        ]
        for field in required_fields:
            if field not in data or data[field] in [None, ""]:
                return Response(
                    api_response(
                        message=(
                            f"{field.replace('_', ' ').capitalize()} is required." # noqa
                        ),
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        # Fetch the initiated ride
        try:
            ride = Ride.objects.get(
                id=data["ride_id"],
                customer=user,
                status="initiated"
            )
        except Ride.DoesNotExist:
            return Response(
                api_response(
                    message="Initiated ride not found for confirmation.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        # Validate driver
        try:
            driver = User.objects.get(
                id=data["driver_id"],
                roles__name="driver",
                driver_profile__is_approved=True,
            )
        except User.DoesNotExist:
            return Response(
                api_response(
                    message="Selected driver not available.", status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Ensure driver is not already on a ride
        if Ride.objects.filter(
            driver=driver, status__in=["accepted", "in_progress"]
        ).exists():
            return Response(
                api_response(
                    message="Driver is no longer available.", status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the ride with confirmation details
        ride.driver = driver
        ride.status = "requested"
        ride.fare = data["fare"]

        # Optionally update pickup/dropoff if provided (for backward compatibility) # noqa
        for field in [
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_address",
            "dropoff_latitude",
            "dropoff_longitude",
        ]:
            if field in data and data[field] not in [None, ""]:
                setattr(ride, field, data[field])

        ride.save()
        serializer = RideSerializer(ride)
        return Response(
            api_response(
                message="Ride confirmed successfully.",
                status=True,
                data=serializer.data,
            ),
            status=status.HTTP_200_OK,
        )


class RideStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Update ride status (accept, start, complete, cancel)"
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["status"],
            properties={
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=[
                        "accepted",
                        "in_progress",
                        "completed",
                        "cancelled",
                    ],
                    description="New ride status",
                )
            },
        ),
        responses={200: RideSerializer()},
    )
    def patch(self, request, ride_id):
        user = request.user
        idem_key = request.headers.get("Idempotency-Key") or request.META.get(
            "HTTP_IDEMPOTENCY_KEY"
        )
        request_payload = request.data
        if idem_key:
            try:
                cached, redis_key = get_cached_response(
                    user_id=str(user.id),
                    method=request.method,
                    path=request.path,
                    idempotency_key=idem_key,
                    request_payload=request_payload,
                )
                if cached is not None:
                    return Response(cached)
            except IdempotencyConflict as e:
                return Response(
                    api_response(message=str(e), status=False),
                    status=status.HTTP_409_CONFLICT,
                )
        try:
            with transaction.atomic():
                ride = Ride.objects.select_for_update().get(id=ride_id)

                # Translate legacy statuses to DeliveryRequest statuses
                new_status = request.data.get("status")
                status_map = {
                    "accepted": "assigned",
                    "in_progress": "in_transit",
                    "completed": "delivered",
                    "cancelled": "cancelled",
                }
                if new_status not in status_map:
                    resp = Response(
                        api_response(message="Invalid status.", status=False),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                # Only assigned driver or customer can update
                is_driver = ride.driver == user
                is_customer = ride.customer == user
                if not (is_driver or is_customer):
                    resp = Response(
                        api_response(message="Not allowed.", status=False),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                # Define allowed transitions
                valid_transitions = {
                    "requested": ["accepted", "cancelled"],
                    "accepted": ["in_progress", "cancelled"],
                    "in_progress": ["completed", "cancelled"],
                    "completed": [],
                    "cancelled": [],
                }
                if new_status not in valid_transitions.get(ride.status, []):
                    resp = Response(
                        api_response(
                            message="Invalid status transition.", status=False
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                # Only driver can accept/start/complete
                if (
                    new_status in ["accepted", "in_progress", "completed"]
                    and not is_driver
                ):
                    resp = Response(
                        api_response(
                            message="Only driver can update to this status.",
                            status=False,
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                # Accept only when driver is set to this user (prevents 3rd party accept)
                if new_status == "accepted" and ride.driver and ride.driver != user:
                    resp = Response(
                        api_response(
                            message="Ride already assigned to another driver.",
                            status=False,
                        ),
                        status=status.HTTP_409_CONFLICT,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp
                if new_status == "accepted" and not ride.driver:
                    ride.driver = user

                # Update status and timestamps
                ride.status = new_status
                notify_user = False
                if new_status == "accepted":
                    ride.accepted_at = timezone.now()
                    notify_user = True
                elif new_status == "in_progress":
                    ride.started_at = timezone.now()
                    notify_user = True
                elif new_status == "completed":
                    ride.completed_at = timezone.now()
                    notify_user = True
                elif new_status == "cancelled":
                    ride.cancelled_at = timezone.now()
                    notify_user = True

                ride.save()
        except Ride.DoesNotExist:
            return Response(
                api_response(
                    message="Ride not found.", status=False
                ),
                status=status.HTTP_404_NOT_FOUND    ,
            )
        # Re-fetch ride for serialization after transaction
        ride = Ride.objects.get(id=ride_id)
        new_status = ride.status
        is_driver = ride.driver == user
        notify_user = new_status in [
            "accepted",
            "in_progress",
            "completed",
            "cancelled",
        ]

        # Notify the user asynchronously if the driver updated the status
        if notify_user and is_driver:
            try:
                notify_user_of_ride_status_task.delay(
                    user_id=str(ride.customer.id),
                    ride_id=str(ride.id),
                    new_status=new_status
                )
            except Exception as e:
                logger.error(
                    "Failed to queue user notification task for ride %s: %s",
                    ride.id,
                    e,
                )
        serializer = RideSerializer(ride)
        resp = Response(
            api_response(
                message=f"Ride status updated to {new_status}.",
                status=True,
                data=serializer.data,
            )
        )
        if idem_key:
            store_response(
                redis_key=redis_key,
                request_payload=request_payload,
                response_payload=resp.data,
            )
        return resp


class CourierRequestOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get courier request options (suggested fare, drivers)", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=[
                "pickup_address", "pickup_latitude", "pickup_longitude",
                "dropoff_address", "dropoff_latitude", "dropoff_longitude",
                "item_description"
            ],
            properties={
                "pickup_address": openapi.Schema(type=openapi.TYPE_STRING),
                "pickup_latitude": openapi.Schema(type=openapi.TYPE_NUMBER,
                                                  format="float"),
                "pickup_longitude": openapi.Schema(type=openapi.TYPE_NUMBER,
                                                   format="float"),
                "dropoff_address": openapi.Schema(type=openapi.TYPE_STRING),
                "dropoff_latitude": openapi.Schema(type=openapi.TYPE_NUMBER,
                                                   format="float"),
                "dropoff_longitude": openapi.Schema(type=openapi.TYPE_NUMBER,
                                                    format="float"),
                "item_description": openapi.Schema(type=openapi.TYPE_STRING),
                "item_weight": openapi.Schema(type=openapi.TYPE_NUMBER,
                                              format="float"),
            },
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "suggested_fare": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "distance_km": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "duration_min": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "drivers": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                },
            )
        },
    )
    def post(self, request):
        import random

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        if not user.roles.filter(name="rider").exists():
            return Response(
                api_response(
                    message="Only customers can request courier options.",
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        required_fields = [
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_address",
            "dropoff_latitude",
            "dropoff_longitude",
            "item_description",
        ]
        for field in required_fields:
            if field not in data or data[field] in [None, ""]:
                return Response(
                    api_response(
                        message=f"{field.replace('_', ' ').capitalize()} is required.", # noqa
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        pickup_lat = float(data["pickup_latitude"])
        pickup_lon = float(data["pickup_longitude"])
        dropoff_lat = float(data["dropoff_latitude"])
        dropoff_lon = float(data["dropoff_longitude"])
        route_info = LocationService.get_directions(
            origin_lat=pickup_lat,
            origin_lon=pickup_lon,
            dest_lat=dropoff_lat,
            dest_lon=dropoff_lon,
        )
        distance_km = float(route_info.get("distance_km") or 0)
        duration_min = float(route_info.get("duration_min") or 0)
        # Fare calculation (can be customized for courier)
        base_fare = 700  # NGN
        per_km_rate = 250  # NGN per km
        weight_fee = (
            float(data.get("item_weight", 0)) * 50 if data.get("item_weight") else 0 # noqa
        )
        suggested_fare = base_fare + (per_km_rate * distance_km) + weight_fee

        def haversine(lat1, lon1, lat2, lon2):
            R = 6371
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = (
                sin(dlat / 2) ** 2
                + cos(radians(lat1))
                * cos(radians(lat2))
                * sin(dlon / 2) ** 2
            )
            c = 2 * atan2(sqrt(a), sqrt(1 - a))
            return R * c

        available_drivers = (
            User.objects.filter(
                roles__name="driver", driver_profile__is_approved=True
            )
            .exclude(
                assigned_delivery_requests__status__in=[
                    "assigned",
                    "picked_up",
                    "in_transit",
                ]
            )
        )
        driver_list = []
        for driver in available_drivers:
            profile = getattr(driver, "driver_profile", None)
            if (
                not profile
                or not hasattr(profile, "latitude")
                or not hasattr(profile, "longitude")
            ):
                continue
            driver_lat = float(profile.latitude)
            driver_lon = float(profile.longitude)
            straight_distance = haversine(
                pickup_lat, pickup_lon, driver_lat, driver_lon
            )
            if straight_distance > 7.0:
                continue
            price_multiplier = random.uniform(0.9, 1.2)
            driver_fare = round(suggested_fare * price_multiplier, 2)
            driver_list.append(
                {
                    "driver_id": str(driver.id),
                    "driver_email": driver.email,
                    "distance_to_pickup_km": round(straight_distance, 2),
                    "price": driver_fare,
                }
            )
        return Response(
            api_response(
                message="Courier options retrieved successfully.",
                status=True,
                data={
                    "suggested_fare": round(suggested_fare, 2),
                    "distance_km": round(distance_km, 2),
                    "duration_min": round(duration_min, 1),
                    "drivers": driver_list,
                },
            )
        )


class CourierRequestConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Confirm a courier request with selected driver and price", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=[
                "pickup_address",
                "pickup_latitude",
                "pickup_longitude",
                "dropoff_address",
                "dropoff_latitude",
                "dropoff_longitude",
                "item_description",
                "driver_id",
                "fare",
            ],
            properties={
                "pickup_address": openapi.Schema(type=openapi.TYPE_STRING),
                "pickup_latitude": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
                "pickup_longitude": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
                "dropoff_address": openapi.Schema(type=openapi.TYPE_STRING),
                "dropoff_latitude": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
                "dropoff_longitude": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
                "item_description": openapi.Schema(type=openapi.TYPE_STRING),
                "item_weight": openapi.Schema(
                    type=openapi.TYPE_NUMBER, format="float"
                ),
                "driver_id": openapi.Schema(type=openapi.TYPE_STRING),
                "fare": openapi.Schema(type=openapi.TYPE_NUMBER, format="float"), # noqa
            },
        ),
        responses={201: CourierRequestSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=400)
        user = request.user
        if not user.roles.filter(name="rider").exists():
            return Response(
                api_response(
                    message="Only customers can confirm courier requests.",
                    status=False,
                ),
                status=403,
            )
        required_fields = [
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_address",
            "dropoff_latitude",
            "dropoff_longitude",
            "item_description",
            "driver_id",
            "fare",
        ]
        for field in required_fields:
            if field not in data or data[field] in [None, ""]:
                return Response(
                    api_response(
                        message=f"{field.replace('_', ' ').capitalize()} is required.", # noqa
                        status=False,
                    ),
                    status=400,
                )
        try:
            driver = User.objects.get(
                id=data["driver_id"],
                roles__name="driver",
                driver_profile__is_approved=True,
            )
        except User.DoesNotExist:
            return Response(
                api_response(
                    message="Selected driver not available.",
                    status=False),
                status=400,
            )
        # Ensure driver is not already on a courier delivery (source of truth)
        if DeliveryRequest.objects.filter(
            driver=driver,
            status__in=["assigned", "picked_up", "in_transit"],
        ).exists():
            return Response(
                api_response(
                    message="Driver is no longer available.",
                    status=False),
                status=400,
            )

        # Create DeliveryRequest in couriers app as source of truth
        courier = DeliveryRequest.objects.create(
            customer=user,
            driver=driver,
            pickup_address=data["pickup_address"],
            pickup_latitude=data["pickup_latitude"],
            pickup_longitude=data["pickup_longitude"],
            delivery_address=data["dropoff_address"],
            delivery_latitude=data["dropoff_latitude"],
            delivery_longitude=data["dropoff_longitude"],
            package_description=data["item_description"],
            package_weight=data.get("item_weight"),
            base_fare=0,
            distance_fare=0,
            total_fare=data["fare"],
            status="pending",
        )
        serializer = CourierRequestListSerializer(courier)
        return Response(
            api_response(
                message="Courier request confirmed and created successfully.",
                status=True,
                data=serializer.data,
            ),
            status=201,
        )


class CourierRequestStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update courier request status (accept, in_progress, completed, cancelled)", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["status"],
            properties={
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["accepted", "in_progress", "completed", "cancelled"],
                    description="New courier request status",
                )
            },
        ),
        responses={200: CourierRequestSerializer()},
    )
    def patch(self, request, courier_id):
        from django.utils import timezone

        user = request.user
        idem_key = request.headers.get("Idempotency-Key") or request.META.get(
            "HTTP_IDEMPOTENCY_KEY"
        )
        request_payload = request.data
        if idem_key:
            try:
                cached, redis_key = get_cached_response(
                    user_id=str(user.id),
                    method=request.method,
                    path=request.path,
                    idempotency_key=idem_key,
                    request_payload=request_payload,
                )
                if cached is not None:
                    return Response(cached)
            except IdempotencyConflict as e:
                return Response(
                    api_response(message=str(e), status=False),
                    status=status.HTTP_409_CONFLICT,
                )
        try:
            with transaction.atomic():
                courier = DeliveryRequest.objects.select_for_update().get(
                    id=courier_id
                )

                status_map = {
                    "accepted": "assigned",
                    "in_progress": "in_transit",
                    "completed": "delivered",
                    "cancelled": "cancelled",
                }
                new_status = request.data.get("status")
                if new_status not in [
                    "accepted",
                    "in_progress",
                    "completed",
                    "cancelled",
                ]:
                    resp = Response(
                        api_response(message="Invalid status.", status=False),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                is_driver = courier.driver == user
                is_customer = courier.customer == user
                if not (is_driver or is_customer):
                    resp = Response(
                        api_response(message="Not allowed.", status=False),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                translated_status = status_map[new_status]

                if new_status in ["accepted", "in_progress", "completed"] and not is_driver:
                    resp = Response(
                        api_response(
                            message="Only driver can update to this status.",
                            status=False,
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                if new_status == "accepted" and courier.driver and courier.driver != user:
                    resp = Response(
                        api_response(
                            message="Courier request already assigned to another driver.",
                            status=False,
                        ),
                        status=status.HTTP_409_CONFLICT,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp
                if new_status == "accepted" and not courier.driver:
                    courier.driver = user

                courier.status = translated_status
                if translated_status == "assigned":
                    courier.assigned_at = timezone.now()
                elif translated_status == "picked_up":
                    courier.picked_up_at = timezone.now()
                elif translated_status == "delivered":
                    courier.delivered_at = timezone.now()
                elif translated_status == "cancelled":
                    courier.cancelled_at = timezone.now()
                courier.save()
        except DeliveryRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Courier request not found.", status=False),
                status=404,
            )
        courier = DeliveryRequest.objects.get(id=courier_id)
        serializer = CourierRequestListSerializer(courier)
        resp = Response(
            api_response(
                message=f"Courier request status updated to {new_status}.",
                status=True,
                data=serializer.data,
            )
        )
        if idem_key:
            store_response(
                redis_key=redis_key,
                request_payload=request_payload,
                response_payload=resp.data,
            )
        return resp


class CourierRequestListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List courier requests for the authenticated user (admin, driver, or customer)", # noqa
        responses={200: CourierRequestSerializer(many=True)},
    )
    def get(self, request):
        user = request.user
        if user.is_staff:
            queryset = DeliveryRequest.objects.all()
        elif user.roles.filter(name="driver").exists():
            queryset = DeliveryRequest.objects.filter(driver=user)
        else:
            queryset = DeliveryRequest.objects.filter(customer=user)
        queryset = queryset.order_by("-requested_at")
        serializer = CourierRequestListSerializer(queryset, many=True)
        return Response(
            api_response(
                message="Courier requests retrieved successfully.",
                status=True,
                data={"results": serializer.data},
            )
        )


class RideCourierAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get analytics for rides and courier requests (admin: all, driver/customer: own)", # noqa
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "total_rides": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "total_couriers": openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                    "completed_rides": openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                    "completed_couriers": openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                    "cancelled_rides": openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                    "cancelled_couriers": openapi.Schema(type=openapi.TYPE_INTEGER), # noqa
                    "total_ride_revenue": openapi.Schema(type=openapi.TYPE_NUMBER), # noqa
                    "total_courier_revenue": openapi.Schema(type=openapi.TYPE_NUMBER), # noqa
                    "rides_by_month": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "couriers_by_month": openapi.Schema(type=openapi.TYPE_OBJECT), # noqa
                    "top_drivers": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                    "top_customers": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT),
                    ),
                },
            )
        },
    )
    def get(self, request):
        user = request.user
        if user.is_staff:
            rides = Ride.objects.all()
            couriers = DeliveryRequest.objects.all()
        elif user.roles.filter(name="driver").exists():
            rides = Ride.objects.filter(driver=user)
            couriers = DeliveryRequest.objects.filter(driver=user)
        else:
            rides = Ride.objects.filter(customer=user)
            couriers = DeliveryRequest.objects.filter(customer=user)
        # Totals
        total_rides = rides.count()
        total_couriers = couriers.count()
        completed_rides = rides.filter(status="completed").count()
        completed_couriers = couriers.filter(status="delivered").count()
        cancelled_rides = rides.filter(status="cancelled").count()
        cancelled_couriers = couriers.filter(status="cancelled").count()
        total_ride_revenue = (
            rides.filter(status="completed").aggregate(total=Sum("fare"))["total"] or 0 # noqa
        )
        total_courier_revenue = (
            couriers.filter(status="delivered").aggregate(total=Sum("total_fare"))["total"] # noqa
            or 0
        )

        from django.db.models.functions import TruncMonth

        # class TruncMonth(Func):
        #     function = "DATE_TRUNC"
        #     template = "%(function)s('month', %(expressions)s)"

        rides_by_month = (
            rides.filter(status="completed")
            .annotate(month=TruncMonth("completed_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        couriers_by_month = (
            couriers.filter(status="delivered")
            .annotate(month=TruncMonth("delivered_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        rides_by_month_dict = {
            str(item["month"].date()): item["count"]
            for item in rides_by_month
            if item["month"]
        }
        couriers_by_month_dict = {
            str(item["month"].date()): item["count"]
            for item in couriers_by_month
            if item["month"]
        }
        # Top drivers (by completed rides/couriers)
        top_drivers_qs = (
            rides.filter(status="completed")
            .values("driver__email")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        top_drivers = [
            {"driver_email": d["driver__email"], "completed_rides": d["count"]}
            for d in top_drivers_qs
            if d["driver__email"]
        ]
        # Top customers (by completed rides/couriers)
        top_customers_qs = (
            rides.filter(status="completed")
            .values("customer__email")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        top_customers = [
            {"customer_email": c["customer__email"], "completed_rides": c["count"]} # noqa
            for c in top_customers_qs
            if c["customer__email"]
        ]
        return Response(
            api_response(
                message="Analytics retrieved successfully.",
                status=True,
                data={
                    "total_rides": total_rides,
                    "total_couriers": total_couriers,
                    "completed_rides": completed_rides,
                    "completed_couriers": completed_couriers,
                    "cancelled_rides": cancelled_rides,
                    "cancelled_couriers": cancelled_couriers,
                    "total_ride_revenue": float(total_ride_revenue),
                    "total_courier_revenue": float(total_courier_revenue),
                    "rides_by_month": rides_by_month_dict,
                    "couriers_by_month": couriers_by_month_dict,
                    "top_drivers": top_drivers,
                    "top_customers": top_customers,
                },
            )
        )


class LocationTrackingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get real-time location tracking for a ride",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "ride_id": openapi.Schema(type=openapi.TYPE_STRING),
                    "driver_location": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "accuracy": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "timestamp": openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    ),
                    "eta": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "total_duration_min": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "driver_to_pickup_eta_min": openapi.Schema(type=openapi.TYPE_NUMBER),
                            "total_distance_km": openapi.Schema(type=openapi.TYPE_NUMBER),
                        }
                    ),
                    "route_polyline": openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        }
    )
    def get(self, request, ride_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        try:
            ride = Ride.objects.get(id=ride_id)

            # Check if user has access to this ride
            if not (request.user == ride.customer or
                   request.user == ride.driver or
                   request.user.is_staff):
                return Response(
                    api_response(
                        message="You don't have permission to track this ride",
                        status=False
                    ),
                    status=403
                )

            # Get driver location
            driver_location = None
            if ride.driver and ride.driver.driver_profile:
                profile = ride.driver.driver_profile
                if profile.latitude and profile.longitude:
                    driver_location = {
                        'latitude': float(profile.latitude),
                        'longitude': float(profile.longitude),
                        'accuracy': None,  # Could be added to driver profile
                        'timestamp': profile.updated_at.isoformat()
                    }

            # Calculate ETA
            eta_data = None
            if driver_location:
                eta_data = LocationService.calculate_route_eta(
                    float(ride.pickup_latitude), float(ride.pickup_longitude),
                    float(ride.dropoff_latitude), float(ride.dropoff_longitude),
                    driver_location['latitude'], driver_location['longitude']
                )

            # Get route polyline
            route_info = LocationService.get_directions(
                float(ride.pickup_latitude), float(ride.pickup_longitude),
                float(ride.dropoff_latitude), float(ride.dropoff_longitude)
            )

            response_data = {
                'ride_id': str(ride.id),
                'ride_status': ride.status,
                'driver_location': driver_location,
                'eta': eta_data,
                'route_polyline': route_info.get('polyline') if route_info else None,
                'pickup_location': {
                    'latitude': float(ride.pickup_latitude),
                    'longitude': float(ride.pickup_longitude),
                    'address': ride.pickup_address
                },
                'dropoff_location': {
                    'latitude': float(ride.dropoff_latitude),
                    'longitude': float(ride.dropoff_longitude),
                    'address': ride.dropoff_address
                }
            }

            return Response(
                api_response(
                    message="Location tracking data retrieved successfully",
                    status=True,
                    data=response_data
                )
            )

        except Ride.DoesNotExist:
            return Response(
                api_response(
                    message="Ride not found",
                    status=False
                ),
                status=404
            )


class DriverLocationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update driver's current location",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['latitude', 'longitude'],
            properties={
                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, format="float"),
                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, format="float"),
                'accuracy': openapi.Schema(type=openapi.TYPE_NUMBER, format="float"),
            }
        ),
        responses={200: openapi.Response("Location updated successfully")}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        # Check if user is a driver
        if not request.user.roles.filter(name='driver').exists():
            return Response(
                api_response(
                    message="Only drivers can update location",
                    status=False
                ),
                status=403
            )

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        accuracy = request.data.get('accuracy')

        if not latitude or not longitude:
            return Response(
                api_response(
                    message="Latitude and longitude are required",
                    status=False
                ),
                status=400
            )

        # Validate coordinates
        if not LocationService.validate_coordinates(latitude, longitude):
            return Response(
                api_response(
                    message="Invalid coordinates",
                    status=False
                ),
                status=400
            )

        # Update driver location
        success = LocationService.update_driver_location(
            str(request.user.id), latitude, longitude, accuracy
        )

        if success:
            return Response(
                api_response(
                    message="Location updated successfully",
                    status=True,
                    data={
                        'latitude': latitude,
                        'longitude': longitude,
                        'accuracy': accuracy,
                        'timestamp': timezone.now().isoformat()
                    }
                )
            )
        else:
            return Response(
                api_response(
                    message="Failed to update location",
                    status=False
                ),
                status=500
            )


class NearbyDriversView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Find nearby drivers",
        manual_parameters=[
            openapi.Parameter(
                'latitude', openapi.IN_QUERY, description="Pickup latitude",
                type=openapi.TYPE_NUMBER, format="float", required=True
            ),
            openapi.Parameter(
                'longitude', openapi.IN_QUERY, description="Pickup longitude",
                type=openapi.TYPE_NUMBER, format="float", required=True
            ),
            openapi.Parameter(
                'radius', openapi.IN_QUERY, description="Search radius in km",
                type=openapi.TYPE_NUMBER, format="float", default=10.0
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "drivers": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "driver_id": openapi.Schema(type=openapi.TYPE_STRING),
                                "driver_name": openapi.Schema(type=openapi.TYPE_STRING),
                                "distance_km": openapi.Schema(type=openapi.TYPE_NUMBER),
                                "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                                "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                                "vehicle_type": openapi.Schema(type=openapi.TYPE_STRING),
                                "rating": openapi.Schema(type=openapi.TYPE_NUMBER),
                            }
                        )
                    )
                }
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

        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        radius = float(request.query_params.get('radius', 10.0))

        if not latitude or not longitude:
            return Response(
                api_response(
                    message="Latitude and longitude are required",
                    status=False
                ),
                status=400
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response(
                api_response(
                    message="Invalid coordinates",
                    status=False
                ),
                status=400
            )

        # Validate coordinates
        if not LocationService.validate_coordinates(latitude, longitude):
            return Response(
                api_response(
                    message="Invalid coordinates",
                    status=False
                ),
                status=400
            )

        # Find nearby drivers
        nearby_drivers = LocationService.find_nearby_drivers(
            latitude, longitude, radius, limit=20
        )

        return Response(
            api_response(
                message=f"Found {len(nearby_drivers)} nearby drivers",
                status=True,
                data={
                    'drivers': nearby_drivers,
                    'search_center': {
                        'latitude': latitude,
                        'longitude': longitude
                    },
                    'radius_km': radius
                }
            )
        )


class GeocodingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Geocode an address to coordinates",
        manual_parameters=[
            openapi.Parameter(
                'address', openapi.IN_QUERY, description="Address to geocode",
                type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "formatted_address": openapi.Schema(type=openapi.TYPE_STRING),
                }
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

        address = request.query_params.get('address')
        if not address:
            return Response(
                api_response(
                    message="Address is required",
                    status=False
                ),
                status=400
            )

        # Geocode the address
        result = LocationService.geocode_address(address)

        if result:
            return Response(
                api_response(
                    message="Address geocoded successfully",
                    status=True,
                    data=result
                )
            )
        else:
            return Response(
                api_response(
                    message="Failed to geocode address",
                    status=False
                ),
                status=400
            )


class ReverseGeocodingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Reverse geocode coordinates to address",
        manual_parameters=[
            openapi.Parameter(
                'latitude', openapi.IN_QUERY, description="Latitude",
                type=openapi.TYPE_NUMBER, format="float", required=True
            ),
            openapi.Parameter(
                'longitude', openapi.IN_QUERY, description="Longitude",
                type=openapi.TYPE_NUMBER, format="float", required=True
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "formatted_address": openapi.Schema(type=openapi.TYPE_STRING),
                    "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                    "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                }
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

        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')

        if not latitude or not longitude:
            return Response(
                api_response(
                    message="Latitude and longitude are required",
                    status=False
                ),
                status=400
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response(
                api_response(
                    message="Invalid coordinates",
                    status=False
                ),
                status=400
            )

        # Validate coordinates
        if not LocationService.validate_coordinates(latitude, longitude):
            return Response(
                api_response(
                    message="Invalid coordinates",
                    status=False
                ),
                status=400
            )

        # Reverse geocode the coordinates
        address = LocationService.reverse_geocode(latitude, longitude)

        if address:
            return Response(
                api_response(
                    message="Coordinates reverse geocoded successfully",
                    status=True,
                    data={
                        'formatted_address': address,
                        'latitude': latitude,
                        'longitude': longitude
                    }
                )
            )
        else:
            return Response(
                api_response(
                    message="Failed to reverse geocode coordinates",
                    status=False
                ),
                status=400
            )


class WaypointListView(APIView):
    """List waypoints for a ride."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List waypoints for a specific ride",
        responses={200: WaypointSerializer(many=True)}
    )
    def get(self, request, ride_id):
        """Get waypoints for a ride."""
        try:
            ride = Ride.objects.get(id=ride_id)

            # Check if user has access to this ride
            if ride.customer != request.user and ride.driver != request.user:
                return Response(
                    api_response(message="Access denied", status=False),
                    status=403
                )

            waypoints = ride.waypoints.all().order_by('sequence_order')
            serializer = WaypointSerializer(waypoints, many=True)

            return Response(
                api_response(
                    message="Waypoints retrieved successfully",
                    status=True,
                    data=serializer.data
                )
            )
        except Ride.DoesNotExist:
            return Response(
                api_response(message="Ride not found", status=False),
                status=404
            )


class WaypointUpdateView(APIView):
    """Update waypoint completion status."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update waypoint completion status",
        request_body=WaypointUpdateSerializer,
        responses={200: WaypointSerializer()}
    )
    def patch(self, request, ride_id, waypoint_id):
        """Update waypoint completion status."""
        try:
            user = request.user
            idem_key = request.headers.get("Idempotency-Key") or request.META.get(
                "HTTP_IDEMPOTENCY_KEY"
            )
            request_payload = request.data
            if idem_key:
                try:
                    cached, redis_key = get_cached_response(
                        user_id=str(user.id),
                        method=request.method,
                        path=request.path,
                        idempotency_key=idem_key,
                        request_payload=request_payload,
                    )
                    if cached is not None:
                        return Response(cached)
                except IdempotencyConflict as e:
                    return Response(
                        api_response(message=str(e), status=False),
                        status=status.HTTP_409_CONFLICT,
                    )

            with transaction.atomic():
                ride = Ride.objects.select_for_update().get(id=ride_id)
                waypoint = Waypoint.objects.select_for_update().get(
                    id=waypoint_id, rides=ride
                )

                # Check if user has access to this ride
                if ride.customer != request.user and ride.driver != request.user:
                    resp = Response(
                        api_response(message="Access denied", status=False),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                # Only driver can complete waypoints
                if ride.driver != request.user:
                    resp = Response(
                        api_response(
                            message="Only driver can update waypoints",
                            status=False,
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                if ride.status not in ["accepted", "in_progress"]:
                    resp = Response(
                        api_response(
                            message="Ride is not active for waypoint updates",
                            status=False,
                        ),
                        status=status.HTTP_409_CONFLICT,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                next_wp = (
                    ride.waypoints.filter(is_completed=False)
                    .order_by("sequence_order")
                    .first()
                )
                if next_wp and waypoint.id != next_wp.id:
                    resp = Response(
                        api_response(
                            message="Waypoints must be completed in order",
                            status=False,
                        ),
                        status=status.HTTP_409_CONFLICT,
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                serializer = WaypointUpdateSerializer(
                    waypoint, data=request.data, partial=True
                )
                if serializer.is_valid():
                    waypoint = serializer.save()

                    if (
                        request.data.get("is_completed") is True
                        and not waypoint.completed_at
                    ):
                        waypoint.completed_at = timezone.now()
                        waypoint.save(update_fields=["completed_at"])

                    if waypoint.is_completed:
                        ride.current_waypoint_index = max(
                            ride.current_waypoint_index,
                            waypoint.sequence_order,
                        )

                    if ride.is_route_completed():
                        ride.status = "completed"
                        ride.completed_at = timezone.now()
                    ride.save()

                    response_serializer = WaypointSerializer(waypoint)
                    resp = Response(
                        api_response(
                            message="Waypoint updated successfully",
                            status=True,
                            data=response_serializer.data,
                        )
                    )
                    if idem_key:
                        store_response(
                            redis_key=redis_key,
                            request_payload=request_payload,
                            response_payload=resp.data,
                        )
                    return resp

                resp = Response(
                    api_response(message=serializer.errors, status=False),
                    status=status.HTTP_400_BAD_REQUEST,
                )
                if idem_key:
                    store_response(
                        redis_key=redis_key,
                        request_payload=request_payload,
                        response_payload=resp.data,
                    )
                return resp
        except (Ride.DoesNotExist, Waypoint.DoesNotExist):
            return Response(
                api_response(message="Ride or waypoint not found", status=False),
                status=404
            )


class MultiWaypointRideCreateView(APIView):
    """Create a ride with multiple waypoints."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Create a ride with multiple waypoints",
        request_body=RideCreateSerializer,
        responses={201: RideSerializer()}
    )
    def post(self, request):
        """Create a ride with multiple waypoints."""
        serializer = RideCreateSerializer(data=request.data)
        if serializer.is_valid():
            ride = serializer.save(customer=request.user)

            # Calculate total distance and duration
            total_distance = ride.calculate_total_distance_km()
            total_duration = total_distance * 2  # Rough estimate: 2 min per km

            # Update ride with calculated values
            ride.total_distance_km = total_distance
            ride.total_duration_min = total_duration
            ride.save()

            # Calculate fare
            fare = self._calculate_fare(total_distance, total_duration)
            ride.fare = fare
            ride.save()

            response_serializer = RideSerializer(ride)
            return Response(
                api_response(
                    message="Ride with multiple waypoints created successfully",
                    status=True,
                    data=response_serializer.data
                ),
                status=201
            )

        return Response(
            api_response(message=serializer.errors, status=False),
            status=400
        )

    def _calculate_fare(self, distance_km, duration_min):
        """Calculate fare based on distance and duration."""
        base_fare = 500  # Base fare in NGN
        per_km_rate = 100  # Rate per kilometer
        per_min_rate = 2  # Rate per minute

        distance_fare = distance_km * per_km_rate
        time_fare = duration_min * per_min_rate
        total_fare = base_fare + distance_fare + time_fare

        return round(total_fare, 2)


class RouteOptimizationView(APIView):
    """Optimize route for multiple waypoints."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Optimize route for multiple waypoints",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['waypoints'],
            properties={
                'waypoints': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'address': openapi.Schema(type=openapi.TYPE_STRING),
                            'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'waypoint_type': openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    )
                )
            }
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'optimized_route': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Items(type=openapi.TYPE_OBJECT)
                    ),
                    'total_distance': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'total_duration': openapi.Schema(type=openapi.TYPE_NUMBER),
                }
            )
        }
    )
    def post(self, request):
        """Optimize route for multiple waypoints."""
        waypoints_data = request.data.get('waypoints', [])

        if len(waypoints_data) < 2:
            return Response(
                api_response(
                    message="At least 2 waypoints are required for route optimization",
                    status=False
                ),
                status=400
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
                min_distance = float('inf')

                for waypoint in other_waypoints:
                    distance = LocationService.haversine_distance(
                        float(current_waypoint['latitude']),
                        float(current_waypoint['longitude']),
                        float(waypoint['latitude']),
                        float(waypoint['longitude'])
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
                    float(wp1['latitude']), float(wp1['longitude']),
                    float(wp2['latitude']), float(wp2['longitude'])
                )
                total_distance += distance

            total_duration = total_distance * 2  # Rough estimate

            return Response(
                api_response(
                    message="Route optimized successfully",
                    status=True,
                    data={
                        'optimized_route': optimized_waypoints,
                        'total_distance': round(total_distance, 2),
                        'total_duration': round(total_duration, 2)
                    }
                )
            )
        except Exception as e:
            return Response(
                api_response(
                    message=f"Route optimization failed: {str(e)}",
                    status=False
                ),
                status=500
            )

