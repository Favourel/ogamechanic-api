from rest_framework import status, permissions
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
from .models import (
    RepairRequest, TrainingSession, VehicleMake
)
from .serializers import (
    RepairRequestSerializer,
    RepairRequestListSerializer,
    RepairRequestStatusUpdateSerializer,
    TrainingSessionSerializer,
    VehicleMakeSerializer,
    TrainingSessionListSerializer,
    TrainingSessionParticipantSerializer,
    TrainingSessionParticipantListSerializer,
)
from .tasks import find_and_notify_mechanics_task
from users.serializers import MechanicProfileSerializer
from users.models import User
from users.services import NotificationService
from django.db import models
from django.contrib.auth import get_user_model


class RepairRequestListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List repair requests for the authenticated user",  # noqa
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "priority",
                openapi.IN_QUERY,
                description="Filter by priority",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: RepairRequestListSerializer(many=True)},
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
            repair_requests = RepairRequest.objects.filter(
                customer=request.user)
        elif request.user.roles.filter(name="mechanic").exists():
            # Mechanics can see:
            # 1. Requests assigned to them
            # 2. Requests they were notified about (pending, no mechanic)
            repair_requests = RepairRequest.objects.filter(
                models.Q(mechanic=request.user) |
                models.Q(
                    notified_mechanics=request.user,
                    status="pending",
                    mechanic__isnull=True
                )
            ).distinct()
        else:
            repair_requests = RepairRequest.objects.none()

        # Apply filters
        status_filter = request.query_params.get("status")
        if status_filter:
            repair_requests = repair_requests.filter(status=status_filter)

        priority_filter = request.query_params.get("priority")
        if priority_filter:
            repair_requests = repair_requests.filter(priority=priority_filter)

        # Paginate
        paginator = self.pagination_class()
        paginated_requests = paginator.paginate_queryset(
            repair_requests, request)
        serializer = RepairRequestListSerializer(paginated_requests, many=True, context={'request': self.request})# noqa

        return Response(
            api_response(
                message="Repair requests retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Create a new repair request. You can use `/api/v1/mechanics/vehicle-makes/` to get the vehicle makes.", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (e.g., 'inbound', 'outbound')"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=[
                        'service_type',
                        'vehicle_make',
                        'vehicle_model',
                        'vehicle_year',
                        'service_address',
                        'service_latitude',
                        'service_longitude',
                        'preferred_date',
                        'preferred_time_slot',
                        'problem_description',
                    ],
                    properties={
                        'mechanic_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='uuid',
                            description="UUID of the mechanic (optional)"
                        ),
                        'service_type': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Type of service requested"
                        ),
                        # 'vehicle_make': openapi.Schema(
                        #     type=openapi.TYPE_STRING,
                        #     description="Vehicle make"
                        # ),
                        'vehicle_model': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Vehicle model"
                        ),
                        'vehicle_year': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Vehicle year"
                        ),
                        # 'vehicle_registration': openapi.Schema(
                        #     type=openapi.TYPE_STRING,
                        #     description="Vehicle registration (optional)"
                        # ),
                        'problem_description': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Description of the problem"
                        ),
                        # 'symptoms': openapi.Schema(
                        #     type=openapi.TYPE_STRING,
                        #     description="Symptoms (optional)"
                        # ),
                        # 'estimated_cost': openapi.Schema(
                        #     type=openapi.TYPE_NUMBER,
                        #     format='decimal',
                        #     description="Estimated cost (optional)"
                        # ),
                        'service_address': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Service address"
                        ),
                        'service_latitude': openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format='decimal',
                            description="Latitude"
                        ),
                        'service_longitude': openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format='decimal',
                            description="Longitude"
                        ),
                        'preferred_date': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='date',
                            description="Preferred date"
                        ),
                        'preferred_time_slot': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Preferred time slot",
                            enum=["morning", "afternoon", "evening"]
                        ),
                        # 'status': openapi.Schema(
                        #     type=openapi.TYPE_STRING,
                        #     description="Status (optional)"
                        # ),
                        'priority': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Priority (optional)"
                        ),
                        'notes': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Additional notes (optional)"
                        ),
                        'cancellation_reason': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Cancellation reason (optional)"
                        ),
                        # 'actual_cost': openapi.Schema(
                        #     type=openapi.TYPE_NUMBER,
                        #     format='decimal',
                        #     description="Actual cost (optional)"
                        # ),
                    }
                )
            },
        ),
        responses={201: RepairRequestSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RepairRequestSerializer(
            data=data, context={'request': request}
        )
        if serializer.is_valid():
            repair_request = serializer.save()

            # If mechanic_id is provided, assign directly (old flow)
            mechanic_id = data.get('mechanic_id')
            if mechanic_id:
                try:
                    mechanic = User.objects.get(id=mechanic_id)
                    if repair_request.assign_mechanic(mechanic):
                        return Response(
                            api_response(
                                message=(
                                    "Repair request created and "
                                    "mechanic assigned successfully."
                                ),
                                status=True,
                                data=RepairRequestSerializer(repair_request).data,
                            ),
                            status=status.HTTP_201_CREATED,
                        )
                except User.DoesNotExist:
                    pass
            
            # New flow: Automatically find and notify mechanics within 5km
            # Only if no mechanic was manually assigned
            if not repair_request.mechanic:
                # Trigger async task to find and notify mechanics
                find_and_notify_mechanics_task.delay(
                    str(repair_request.id),
                    radius_km=5.0
                )

                message = (
                    "Repair request created successfully. "
                    "Searching for mechanics within 5km radius. "
                    "You will be notified when mechanics respond."
                )
            else:
                message = (
                    "Repair request created and "
                    "mechanic assigned successfully."
                )
            
            return Response(
                api_response(
                    message=message,
                    status=True,
                    data=RepairRequestSerializer(repair_request).data,
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class RepairRequestDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get details of a repair request",
        responses={200: RepairRequestSerializer()},
    )
    def get(self, request, repair_id):
        repair_request = get_object_or_404(RepairRequest, id=repair_id)

        # Check permissions
        is_customer = repair_request.customer == request.user
        is_assigned_mechanic = repair_request.mechanic == request.user
        is_notified_mechanic = (
            request.user.roles.filter(name="mechanic").exists() and
            repair_request.notified_mechanics.filter(
                id=request.user.id
            ).exists() and
            repair_request.status == "pending" and
            repair_request.mechanic is None
        )

        if not (is_customer or is_assigned_mechanic or is_notified_mechanic):
            return Response(
                api_response(message="Access denied.", status=False),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RepairRequestSerializer(
            repair_request, context={'request': request}
        )
        return Response(
            api_response(
                message="Repair request details retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Update repair request status",
        request_body=RepairRequestStatusUpdateSerializer,
        responses={200: RepairRequestSerializer()},
    )
    def patch(self, request, repair_id):
        repair_request = get_object_or_404(RepairRequest, id=repair_id)

        # Check permissions
        if (
            repair_request.customer != request.user
            and repair_request.mechanic != request.user
        ):
            return Response(
                api_response(message="Access denied.", status=False),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RepairRequestStatusUpdateSerializer(
            repair_request, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                api_response(
                    message="Repair request updated successfully.",
                    status=True,
                    data=RepairRequestSerializer(
                        repair_request, context={'request': request}
                    ).data,
                )
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class AvailableMechanicsView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get list of available approved mechanics",
        responses={200: MechanicProfileSerializer(many=True)},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        from users.models import MechanicProfile

        mechanics = MechanicProfile.objects.filter(is_approved=True)
        serializer = MechanicProfileSerializer(mechanics, many=True, context={'request': self.request}) # noqa

        return Response(
            api_response(
                message="Available mechanics retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )


class AssignMechanicView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Assign a mechanic to a repair request. "
            "Customers can manually assign a mechanic, or mechanics can "
            "accept requests they were notified about."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "mechanic_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description=(
                        "Mechanic ID (required for customer assignment, "
                        "ignored if mechanic is accepting)"
                    ),
                ),
            },
        ),
        responses={200: RepairRequestSerializer()},
    )
    def post(self, request, repair_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        repair_request = get_object_or_404(RepairRequest, id=repair_id)

        # Check if user is a mechanic trying to accept
        if request.user.roles.filter(name="mechanic").exists():
            # Mechanic is accepting the request
            if repair_request.can_mechanic_accept(request.user):
                if repair_request.assign_mechanic(request.user):
                    # Notify customer
                    mechanic_name = (
                        request.user.get_full_name() or request.user.email
                    )
                    NotificationService.create_notification(
                        user=repair_request.customer,
                        title="Mechanic Accepted Your Request",
                        message=(
                            f"{mechanic_name} has accepted your repair request. " # noqa
                            f"They will contact you soon."
                        ),
                        notification_type='success',
                        related_object=repair_request,
                        related_object_type='RepairRequest'
                    )

                    return Response(
                        api_response(
                            message="Request accepted successfully.",
                            status=True,
                            data=RepairRequestSerializer(
                                repair_request,
                                context={'request': request}
                            ).data,
                        )
                    )
                else:
                    return Response(
                        api_response(
                            message="Failed to accept request.",
                            status=False
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    api_response(
                        message=(
                            "You cannot accept this request. It may have "
                            "already been assigned or you were not notified "
                            "about it."
                        ),
                        status=False
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Customer manually assigning a mechanic
        if repair_request.customer != request.user:
            return Response(
                api_response(
                    message="Only the customer can assign mechanics.",
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        mechanic_id = data.get("mechanic_id")
        if not mechanic_id:
            return Response(
                api_response(message="Mechanic ID is required.", status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserModel = get_user_model()
        mechanic = get_object_or_404(UserModel, id=mechanic_id)

        # Customer manual assignment - skip notification check
        if repair_request.assign_mechanic(
            mechanic, skip_notification_check=True
        ):
            return Response(
                api_response(
                    message="Mechanic assigned successfully.",
                    status=True,
                    data=RepairRequestSerializer(
                        repair_request, context={'request': request}
                    ).data,
                )
            )
        else:
            return Response(
                api_response(
                    message="Failed to assign mechanic.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


class TrainingSessionListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List training sessions",
        manual_parameters=[
            openapi.Parameter(
                "session_type",
                openapi.IN_QUERY,
                description="Filter by session type",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: TrainingSessionListSerializer(many=True)},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        training_sessions = TrainingSession.objects.all()

        # Apply filters
        session_type = request.query_params.get("session_type")
        if session_type:
            training_sessions = training_sessions.filter(
                session_type=session_type)

        status_filter = request.query_params.get("status")
        if status_filter:
            training_sessions = training_sessions.filter(status=status_filter)

        # Paginate
        paginator = self.pagination_class()
        paginated_sessions = paginator.paginate_queryset(
            training_sessions, request)
        serializer = TrainingSessionListSerializer(
            paginated_sessions, many=True)

        return Response(
            api_response(
                message="Training sessions retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Create a new training session",
        request_body=TrainingSessionSerializer,
        responses={201: TrainingSessionSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only approved mechanics can create training sessions
        if not request.user.roles.filter(name="mechanic").exists():
            return Response(
                api_response(
                    message="Only mechanics can create training sessions.", status=False  # noqa
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TrainingSessionSerializer(data=request.data)
        if serializer.is_valid():
            training_session = serializer.save(instructor=request.user)
            return Response(
                api_response(
                    message="Training session created successfully.",
                    status=True,
                    data=TrainingSessionSerializer(training_session).data,
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class TrainingSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get details of a training session",
        responses={200: TrainingSessionSerializer()},
    )
    def get(self, request, session_id):
        training_session = get_object_or_404(TrainingSession, id=session_id)
        serializer = TrainingSessionSerializer(training_session)
        return Response(
            api_response(
                message="Training session details retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )


class TrainingSessionParticipantListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List participants for a training session",
        responses={200: TrainingSessionParticipantListSerializer(many=True)},
    )
    def get(self, request, session_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        training_session = get_object_or_404(TrainingSession, id=session_id)
        participants = training_session.participants.all()

        # Paginate
        paginator = self.pagination_class()
        paginated_participants = paginator.paginate_queryset(
            participants, request)
        serializer = TrainingSessionParticipantListSerializer(
            paginated_participants, many=True
        )

        return Response(
            api_response(
                message="Training session participants retrieved successfully.",  # noqa
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Register for a training session",
        request_body=TrainingSessionParticipantSerializer,
        responses={201: TrainingSessionParticipantSerializer()},
    )
    def post(self, request, session_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        training_session = get_object_or_404(TrainingSession, id=session_id)

        # Check if registration is open
        if not training_session.is_registration_open:
            return Response(
                api_response(
                    message="Registration for this session is closed.", status=False  # noqa
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if session is full
        if training_session.is_full:
            return Response(
                api_response(
                    message="This training session is full.", status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user is already registered
        if training_session.participants.filter(participant=request.user).exists():  # noqa
            return Response(
                api_response(
                    message="You are already registered for this session.", status=False  # noqa    
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TrainingSessionParticipantSerializer(data=request.data)
        if serializer.is_valid():
            participant = serializer.save(
                participant=request.user, session=training_session
            )
            return Response(
                api_response(
                    message="Successfully registered for training session.",
                    status=True,
                    data=TrainingSessionParticipantSerializer(
                        participant).data,
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class VehicleMakeListView(APIView):
    """
    API endpoint to get all available vehicle makes and models for mechanic registration. # noqa

    - GET: List all active vehicle makes (parent_make is null) and their models. # noqa
    - POST: Create a new vehicle make or model (admin only).
    - PATCH: Update a vehicle make or model (admin only).
    - DELETE: Delete a vehicle make or model (admin only).
    """
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Get Available Vehicle Makes and Models",
        operation_description=(
            "Get a list of all available vehicle makes and their models "
            "that mechanics can specialize in. This endpoint is used during "
            "mechanic registration to show available options. Each make includes " # noqa
            "its models as a nested list."
        ),
        responses={
            200: openapi.Response(
                description="List of vehicle makes and models",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Vehicle makes retrieved successfully"),
                        'data': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(
                                        type=openapi.TYPE_INTEGER, example=1),
                                    'name': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="Toyota"),
                                    'parent_make': openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        nullable=True,
                                        example=None,
                                        description=(
                                            "ID of parent make if this is a model, else null" # noqa
                                        )
                                    ),
                                    'description': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="Vehicle make: Toyota"),
                                    'is_active': openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN,
                                        example=True),
                                    'models': openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        items=openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            properties={
                                                'id': openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=10),
                                                'name': openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    example="Corolla"),
                                                'parent_make': openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=1),
                                                'description': openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    example="Toyota Corolla"),
                                                'is_active': openapi.Schema(
                                                    type=openapi.TYPE_BOOLEAN,
                                                    example=True),
                                            }
                                        ),
                                        description="List of models for this make" # noqa
                                    ),
                                }
                            )
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """
        Get all active vehicle makes (parent_make is null) and their active models. # noqa
        Uses caching to improve performance.
        """
        from django.core.cache import cache

        CACHE_KEY = "active_vehicle_makes_with_models"
        CACHE_TIMEOUT = 60 * 10  # 10 minutes

        cached_data = cache.get(CACHE_KEY)
        if cached_data is not None:
            return Response(
                api_response(
                    message="Vehicle makes retrieved successfully (cached)",
                    status=True,
                    data=cached_data
                )
            )

        makes = VehicleMake.objects.filter(
            is_active=True, parent_make__isnull=True
        ).order_by('name').prefetch_related('models')
        serializer = VehicleMakeSerializer(makes, many=True)
        cache.set(CACHE_KEY, serializer.data, CACHE_TIMEOUT)
        return Response(
            api_response(
                message="Vehicle makes retrieved successfully",
                status=True,
                data=serializer.data
            )
        )

    @swagger_auto_schema(
        operation_summary="Create a Vehicle Make or Model",
        request_body=VehicleMakeSerializer,
        responses={
            201: VehicleMakeSerializer(),
            400: "Bad Request",
            403: "Forbidden"
        }
    )
    def post(self, request):
        """
        Create a new vehicle make or model. Admin only.
        """
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response(
                api_response(
                    message="You do not have permission to perform this action.", # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VehicleMakeSerializer(data=request.data)
        if serializer.is_valid():
            vehicle_make = serializer.save()
            return Response(
                api_response(
                    message="Vehicle make/model created successfully.",
                    status=True,
                    data=VehicleMakeSerializer(vehicle_make).data
                ),
                status=status.HTTP_201_CREATED
            )
        return Response(
            api_response(
                message=serializer.errors,
                status=False
            ),
            status=status.HTTP_400_BAD_REQUEST
        )

    @swagger_auto_schema(
        operation_summary="Update a Vehicle Make or Model",
        request_body=VehicleMakeSerializer,
        manual_parameters=[
            openapi.Parameter(
                'id', openapi.IN_QUERY, description="ID of the vehicle make/model to update", # noqa
                type=openapi.TYPE_INTEGER, required=True
            )
        ],
        responses={
            200: VehicleMakeSerializer(),
            400: "Bad Request",
            403: "Forbidden",
            404: "Not Found"
        }
    )
    def patch(self, request):
        """
        Update a vehicle make or model. Admin only.
        """
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response(
                api_response(
                    message="You do not have permission to perform this action.", # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        vehicle_make_id = request.query_params.get('id')
        if not vehicle_make_id:
            return Response(
                api_response(
                    message="Vehicle make/model ID is required.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            vehicle_make = VehicleMake.objects.get(id=vehicle_make_id)
        except VehicleMake.DoesNotExist:
            return Response(
                api_response(
                    message="Vehicle make/model not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = VehicleMakeSerializer(
            vehicle_make, data=request.data, partial=True)
        if serializer.is_valid():
            vehicle_make = serializer.save()
            return Response(
                api_response(
                    message="Vehicle make/model updated successfully.",
                    status=True,
                    data=VehicleMakeSerializer(vehicle_make).data
                ),
                status=status.HTTP_200_OK
            )
        return Response(
            api_response(
                message=serializer.errors,
                status=False
            ),
            status=status.HTTP_400_BAD_REQUEST
        )

    @swagger_auto_schema(
        operation_summary="Delete a Vehicle Make or Model",
        manual_parameters=[
            openapi.Parameter(
                'id', openapi.IN_QUERY, description="ID of the vehicle make/model to delete", # noqa
                type=openapi.TYPE_INTEGER, required=True
            )
        ],
        responses={
            204: "No Content",
            403: "Forbidden",
            404: "Not Found"
        }
    )
    def delete(self, request):
        """
        Delete a vehicle make or model. Admin only.
        """
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response(
                api_response(
                    message="You do not have permission to perform this action.", # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        vehicle_make_id = request.query_params.get('id')
        if not vehicle_make_id:
            return Response(
                api_response(
                    message="Vehicle make/model ID is required.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            vehicle_make = VehicleMake.objects.get(id=vehicle_make_id)
        except VehicleMake.DoesNotExist:
            return Response(
                api_response(
                    message="Vehicle make/model not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        vehicle_make.delete()
        return Response(
            api_response(
                message="Vehicle make/model deleted successfully.",
                status=True
            ),
            status=status.HTTP_204_NO_CONTENT
        )


class MechanicDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve mechanic details by mechanic user ID",
        responses={
            200: MechanicProfileSerializer(),
            404: openapi.Response(
                description="Mechanic not found",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "status": openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, example=False
                        ),
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Mechanic not found."
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="User does not have a mechanic profile",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "status": openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, example=False
                        ),
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="User does not have a mechanic profile.",
                        ),
                    },
                ),
            ),
        },
    )
    def get(self, request, mechanic_id):
        """
        Retrieve mechanic details by passing the mechanic's user ID.
        """
        user = get_object_or_404(User, id=mechanic_id)
        if not user.roles.filter(name="mechanic").exists():
            return Response(
                api_response(
                    message="User is not a mechanic.",
                    status=False,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        mechanic_profile = getattr(user, "mechanic_profile", None)
        if not mechanic_profile:
            return Response(
                api_response(
                    message="User does not have a mechanic profile.",
                    status=False,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = MechanicProfileSerializer(
            mechanic_profile, context={"request": request}
        )
        return Response(
            api_response(
                message="Mechanic details retrieved successfully.",
                status=True,
                data=serializer.data,
            ),
            status=status.HTTP_200_OK,
        )


class MechanicAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Mechanic Analytics",
        operation_description=(
            "Returns analytics data for mechanics, including:\n"
            "  - Total number of repair requests handled\n"
            "  - Number of completed repair requests\n"
            "  - Number of pending repair requests\n"
            "  - Average mechanic rating\n"
            "  - Most common vehicle makes serviced\n"
            "  - Total number of distinct customers served"
        ),
        responses={
            200: openapi.Response(
                description="Analytics payload",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "status": openapi.Schema(
                            type=openapi.TYPE_BOOLEAN,
                            example=True
                        ),
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example=(
                                "Mechanic analytics retrieved successfully."
                            ),
                        ),
                        "data": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "total_repair_requests": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=42
                                ),
                                "completed_repair_requests": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=30
                                ),
                                "pending_repair_requests": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=6
                                ),
                                "avg_rating": openapi.Schema(
                                    type=openapi.TYPE_NUMBER,
                                    format="float",
                                    example=4.7
                                ),
                                "common_vehicle_makes": openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Items(
                                        type=openapi.TYPE_STRING
                                    ),
                                    example=["Toyota", "Honda"]
                                ),
                                "distinct_customers": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=18
                                ),
                            },
                        ),
                    },
                ),
            )
        },
    )
    def get(self, request):
        user = request.user
        # Must be mechanic
        if not user.roles.filter(name="mechanic").exists():
            return Response(
                api_response(
                    message="Only mechanics can access their analytics.",
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        from users.models import MechanicProfile, MechanicReview
        from django.db.models import Avg
        from django.db import models

        try:
            mechanic_profile = MechanicProfile.objects.get(user=user)
        except MechanicProfile.DoesNotExist:
            return Response(
                api_response(
                    message="Mechanic profile not found for this user.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        total_repair_requests = RepairRequest.objects.filter(
            mechanic=user
        ).count()
        completed_repair_requests = RepairRequest.objects.filter(
            mechanic=user, status="completed"
        ).count()
        pending_repair_requests = RepairRequest.objects.filter(
            mechanic=user, status__in=["pending", "in_progress"]
        ).count()

        reviews = MechanicReview.objects.filter(mechanic=mechanic_profile)
        avg_rating = reviews.aggregate(avg=Avg('rating')).get('avg')
        avg_rating = round(avg_rating, 1) if avg_rating is not None else None

        # Use 'vehicle_make' field instead of non-existent related field
        make_counts = (
            RepairRequest.objects.filter(mechanic=user)
            .values('vehicle_make')
            .annotate(count=models.Count('id'))
            .order_by('-count')
        )
        common_vehicle_makes = [
            item['vehicle_make']
            for item in make_counts[:3]
            if item['vehicle_make']
        ]

        distinct_customers = (
            RepairRequest.objects.filter(mechanic=user)
            .values('customer')
            .distinct()
            .count()
        )

        data = {
            "total_repair_requests": total_repair_requests,
            "completed_repair_requests": completed_repair_requests,
            "pending_repair_requests": pending_repair_requests,
            "avg_rating": avg_rating,
            "common_vehicle_makes": common_vehicle_makes,
            "distinct_customers": distinct_customers,
        }

        return Response(
            api_response(
                message="Mechanic analytics retrieved successfully.",
                status=True,
                data=data
            ),
            status=status.HTTP_200_OK,
        )


