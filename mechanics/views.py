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
from .models import RepairRequest, TrainingSession, VehicleMake
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
from users.serializers import MechanicProfileSerializer
from users.models import User


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
            repair_requests = RepairRequest.objects.filter(
                mechanic=request.user)
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

        serializer = RepairRequestSerializer(data=request.data)
        if serializer.is_valid():
            repair_request = serializer.save(customer=request.user)
            return Response(
                api_response(
                    message="Repair request created successfully.",
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
        if (
            repair_request.customer != request.user
            and repair_request.mechanic != request.user
        ):
            return Response(
                api_response(message="Access denied.", status=False),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RepairRequestSerializer(repair_request)
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
                    data=RepairRequestSerializer(repair_request).data,
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
        operation_description="Assign a mechanic to a repair request",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "mechanic_id": openapi.Schema(type=openapi.TYPE_STRING),
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

        # Only customers can assign mechanics
        if repair_request.customer != request.user:
            return Response(
                api_response(
                    message="Only the customer can assign mechanics.", status=False  # noqa
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        mechanic_id = request.data.get("mechanic_id")
        if not mechanic_id:
            return Response(
                api_response(message="Mechanic ID is required.", status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        mechanic = get_object_or_404(User, id=mechanic_id)

        if repair_request.assign_mechanic(mechanic):
            return Response(
                api_response(
                    message="Mechanic assigned successfully.",
                    status=True,
                    data=RepairRequestSerializer(repair_request).data,
                )
            )
        else:
            return Response(
                api_response(
                    message="Failed to assign mechanic.", status=False),
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
    API endpoint to get all available vehicle makes for mechanic registration
    """
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Get Available Vehicle Makes",
        operation_description="""
        Get a list of all available vehicle makes 
        that mechanics can specialize in.
        This endpoint is used during mechanic 
        registration to show available options.
        """,
        responses={
            200: openapi.Response(
                description="List of vehicle makes",
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
                                    'description': openapi.Schema(
                                        type=openapi.TYPE_STRING, 
                                        example="Vehicle make: Toyota"),
                                    'is_active': openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN, 
                                        example=True)
                                }
                            )
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """Get all active vehicle makes"""
        vehicle_makes = VehicleMake.objects.filter(
            is_active=True).order_by('name')
        serializer = VehicleMakeSerializer(vehicle_makes, many=True)
        
        return Response(
            api_response(
                message="Vehicle makes retrieved successfully",
                status=True,
                data=serializer.data
            )
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
