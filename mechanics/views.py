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
import logging

logger = logging.getLogger(__name__)


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

        # Filter based on user's active role
        active_role = getattr(request.user, 'active_role', None)
        active_role_name = active_role.name if active_role else None
        logger.info(f"Active role: {active_role_name} for user {request.user}")

        if active_role_name == "primary_user":
            # Customers see only their own requests
            repair_requests = RepairRequest.objects.filter(
                customer=request.user)
        elif active_role_name == "mechanic":
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
            # No active role or unsupported role
            repair_requests = RepairRequest.objects.none()

        logger.info(f"Repair requests: {repair_requests}")

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
                        'problem_description',
                        'service_address',
                        'service_latitude',
                        'service_longitude',
                    ],
                    properties={
                        'mechanic_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='uuid',
                            description="UUID of the mechanic (optional)",
                        ),
                        'service_type': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Type of service requested",
                        ),
                        'vehicle_make': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Vehicle make"
                        ),
                        'vehicle_model': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Vehicle model"
                        ),
                        'vehicle_year': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Vehicle year"
                        ),
                        'vehicle_registration': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Vehicle registration (optional)"
                        ),
                        'problem_description': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Description of the problem"
                        ),
                        # 'symptoms': openapi.Schema(
                        #     type=openapi.TYPE_STRING,
                        #     description="Symptoms (optional)"
                        # ),
                        'estimated_cost': openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format='decimal',
                            description="Estimated cost (optional)"
                        ),
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
                        'schedule': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN,
                            description="Whether customer wants to schedule the service"
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
                        'actual_cost': openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format='decimal',
                            description="Actual cost (optional)"
                        ),
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

        # If mechanic_id was provided, validate it early (fail fast)
        mechanic_id = data.get('mechanic_id')
        mechanic = None
        if mechanic_id:
            try:
                mechanic = User.objects.get(id=mechanic_id)
            except User.DoesNotExist:
                return Response(
                    api_response(
                        message="Provided mechanic_id does not exist.",
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Optional: ensure the selected user is actually a mechanic and approved
            if not mechanic.roles.filter(name="mechanic").exists():
                return Response(
                    api_response(
                        message="Provided user is not a mechanic.",
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # If using MechanicProfile/approval, ensure we fetch the correct profile
            from users.models import MechanicProfile

            mechanic_profile = None
            try:
                mechanic_profile = MechanicProfile.objects.get(user=mechanic)
            except MechanicProfile.DoesNotExist:
                return Response(
                    api_response(
                        message="Mechanic profile not found for the given user.",
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if mechanic_profile is None or mechanic_profile.is_approved is not True:
                return Response(
                    api_response(
                        message="Selected mechanic is not approved to receive requests.",
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = RepairRequestSerializer(
            data=data, context={'request': request}
        )
        if serializer.is_valid():
            repair_request = serializer.save()

            # If mechanic was provided and validated above, assign and return
            if mechanic:
                assigned = False
                try:
                    assigned = repair_request.assign_mechanic(mechanic)
                except Exception as e:
                    # Log error if assign_mechanic raises
                    logger.exception(f"Error assigning mechanic {mechanic.id}: {e}")
                    return Response(
                        api_response(
                            message="Failed to assign selected mechanic.",
                            status=False,
                        ),
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                if assigned:
                    # Ensure no other mechanics will see this request via notified_mechanics
                    # (this clears any accidental pre-populated entries)
                    repair_request.notified_mechanics.clear()

                    # If you keep track of notification jobs, cancel them here (if possible)
                    # e.g. revoke celery tasks if you stored task IDs on the model

                    return Response(
                        api_response(
                            message=(
                                "Repair request created and "
                                "mechanic assigned successfully."
                            ),
                            status=True,
                            data=RepairRequestSerializer(
                                repair_request,
                                context={'request': self.request}
                            ).data,
                        ),
                        status=status.HTTP_201_CREATED,
                    )
                else:
                    # assign_mechanic returned False (business rule prevented assignment)
                    return Response(
                        api_response(
                            message="Could not assign the selected mechanic.",
                            status=False,
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # New flow: no mechanic was manually assigned -> notify local mechanics
            if not repair_request.mechanic:
                find_and_notify_mechanics_task.delay(
                    str(repair_request.id),
                    radius_km=10.0
                )

                message = (
                    "Repair request created successfully. "
                    "Searching for mechanics within 10km radius. "
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
                    data=RepairRequestSerializer(
                        repair_request,
                        context={'request': self.request}
                    ).data,
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
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )
        repair_request = get_object_or_404(RepairRequest, id=repair_id)

        # Get user's active role
        active_role = getattr(request.user, 'active_role', None)
        active_role_name = active_role.name if active_role else None

        # Check permissions based on active role
        is_customer = (
            active_role_name == "primary_user" and
            repair_request.customer == request.user
        )
        is_assigned_mechanic = (
            active_role_name == "mechanic" and
            repair_request.mechanic == request.user
        )
        is_notified_mechanic = (
            active_role_name == "mechanic" and
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
        request_body=RepairRequestSerializer,
        responses={200: RepairRequestSerializer()},
    )
    def put(self, request, repair_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            repair_request = RepairRequest.objects.get(pk=repair_id)
        except RepairRequest.DoesNotExist:
            return Response(
                api_response(
                    message="Repair request not found.", status=False),
                status=status.HTTP_404_NOT_FOUND
            )

        # Get user's active role
        active_role = getattr(request.user, 'active_role', None)
        active_role_name = active_role.name if active_role else None
        logger.info(
            f"PUT request by user {request.user.id} with active_role: "
            f"{active_role_name}"
        )

        # Check permissions based on active role
        user_is_customer = (
            active_role_name == "primary_user" and
            repair_request.customer == request.user
        )
        user_is_mechanic = (
            active_role_name == "mechanic" and
            repair_request.mechanic == request.user
        )

        # Only customer or assigned mechanic can update
        if not (user_is_customer or user_is_mechanic):
            return Response(
                api_response(
                    message="You don't have permission to update this request.",
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        # Restrict customer updates based on status
        forbidden_statuses_for_customer = [
            "accepted",
            "in_transit",
            "in_progress",
            "completed",
            "cancelled",
            "rejected"
        ]
        if (
            user_is_customer
            and repair_request.status in forbidden_statuses_for_customer
        ):
            return Response(
                api_response(
                    message=(
                        "You cannot update this repair request in its "
                        "current status."
                    ),
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RepairRequestSerializer(
            repair_request, data=data, partial=False,
            context={'request': request}
        )

        if serializer.is_valid():
            logger.info(f"Serializer valid. Validated data: {serializer.validated_data}")
            updated_instance = serializer.save()  # <--- DRF calls update()
            logger.info(
                f"Updated instance status: {updated_instance.status}, "
                f"ID: {updated_instance.id}"
            )

            return Response(
                api_response(
                    message="Repair request updated successfully.",
                    status=True,
                    data=RepairRequestSerializer(
                        updated_instance, context={'request': request}).data
                ),
                status=status.HTTP_200_OK
            )
        else:
            logger.error(f"Serializer errors: {serializer.errors}")

        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, repair_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            repair_request = RepairRequest.objects.get(pk=repair_id)
        except RepairRequest.DoesNotExist:
            return Response(
                api_response(message="Repair request not found.", status=False),
                status=status.HTTP_404_NOT_FOUND
            )

        # Get user's active role
        active_role = getattr(request.user, 'active_role', None)
        active_role_name = active_role.name if active_role else None
        logger.info(
            f"PATCH request by user {request.user.id} with active_role: "
            f"{active_role_name}"
        )

        # Check permissions based on active role
        user_is_customer = (
            active_role_name == "primary_user" and
            repair_request.customer == request.user
        )
        user_is_mechanic = (
            active_role_name == "mechanic" and
            repair_request.mechanic == request.user
        )

        # Only customer or assigned mechanic can update
        if not (user_is_customer or user_is_mechanic):
            return Response(
                api_response(
                    message="You don't have permission to update this request.",
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        # Restrict customer updates based on status
        forbidden_statuses_for_customer = [
            "accepted",
            "in_transit",
            "in_progress",
            "completed",
            "cancelled",
            "rejected",
        ]
        if (
            user_is_customer
            and repair_request.status in forbidden_statuses_for_customer
        ):
            return Response(
                api_response(
                    message=(
                        "You cannot update this repair request in its "
                        "current status."
                    ),
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RepairRequestSerializer(
            repair_request, data=data, partial=True,
            context={'request': request}
        )

        if serializer.is_valid():
            logger.info(
                f"Serializer valid. Validated data: "
                f"{serializer.validated_data}"
            )
            updated_instance = serializer.save()   # <-- calls update()
            logger.info(
                f"Updated instance status: {updated_instance.status}, "
                f"ID: {updated_instance.id}"
            )

            return Response(
                api_response(
                    message="Repair request updated successfully.",
                    status=True,
                    data=RepairRequestSerializer(
                        updated_instance, context={'request': request}).data
                ),
                status=status.HTTP_200_OK
            )
        else:
            logger.error(f"Serializer errors: {serializer.errors}")

        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST
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
        from django.db.models import Exists, OuterRef

        mechanics = (
            MechanicProfile.objects
            .select_related('user')
            .filter(is_approved=True)
            .annotate(
                has_active_repair_request=Exists(
                    RepairRequest.objects.filter(
                        mechanic=OuterRef('user'),
                        status__in=['accepted', 'in_progress']
                    )
                )
            )
        )
        serializer = MechanicProfileSerializer(
            mechanics, many=True, context={'request': self.request}
        )

        return Response(
            api_response(
                message="Available mechanics retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )


class MechanicResponseView(APIView):
    """
    Consolidated view for mechanics to respond to repair requests.
    Supports both accepting and declining requests.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Mechanics can accept or decline repair requests they were "
            "notified about. Use 'action' field to specify 'accept' or "
            "'decline'. When declining, an optional 'reason' can be provided."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['action'],
            properties={
                'action': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Action to perform: 'accept' or 'decline'",
                    enum=['accept', 'decline'],
                ),
                'reason': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description=(
                        "Optional reason for declining the request "
                        "(only used when action is 'decline')"
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

        # Validate action parameter
        action = data.get('action')
        if action not in ['accept', 'decline']:
            return Response(
                api_response(
                    message=(
                        "Invalid action. Must be 'accept' or 'decline'."
                    ),
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        repair_request = get_object_or_404(RepairRequest, id=repair_id)

        # Only mechanics can respond to requests
        if not request.user.roles.filter(name="mechanic").exists():
            return Response(
                api_response(
                    message=(
                        "Only mechanics can respond to repair requests."
                    ),
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if mechanic can respond to this request
        # Allow if: mechanic was notified OR is the assigned mechanic
        is_notified = repair_request.notified_mechanics.filter(
            id=request.user.id
        ).exists()
        is_assigned = (
            repair_request.mechanic and
            repair_request.mechanic.id == request.user.id
        )

        if not (is_notified or is_assigned):
            return Response(
                api_response(
                    message=(
                        f"You cannot {action} this request. "
                        f"You were not notified about it."
                    ),
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if request is still pending and unassigned
        if (repair_request.status != "pending" or
                repair_request.mechanic is not None):
            return Response(
                api_response(
                    message=(
                        "This request has already been accepted by another "
                        "mechanic or is no longer pending."
                    ),
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        mechanic_name = request.user.get_full_name() or request.user.email

        # Handle accept action
        if action == 'accept':
            if repair_request.assign_mechanic(request.user):
                # Notify customer
                NotificationService.create_notification(
                    user=repair_request.customer,
                    title="Mechanic Accepted Your Request",
                    message=(
                        f"{mechanic_name} has accepted your repair request. "
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

        # Handle decline action
        elif action == 'decline':
            # Remove mechanic from notified list
            repair_request.notified_mechanics.remove(request.user)

            # Optional: Log the decline reason
            decline_reason = data.get('reason', '')
            if decline_reason:
                logger.info(
                    f"Mechanic {request.user.id} declined repair request "
                    f"{repair_request.id}. Reason: {decline_reason}"
                )

            # Notify customer that a mechanic declined
            NotificationService.create_notification(
                user=repair_request.customer,
                title="Mechanic Declined Request",
                message=(
                    f"{mechanic_name} is unable to accept your repair "
                    f"request. We are still searching for available "
                    f"mechanics."
                ),
                notification_type='info',
                related_object=repair_request,
                related_object_type='RepairRequest'
            )

            return Response(
                api_response(
                    message="Request declined successfully.",
                    status=True,
                    data=RepairRequestSerializer(
                        repair_request,
                        context={'request': request}
                    ).data,
                )
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

        # Annotate with active repair request status for optimization
        from django.db.models import Exists, OuterRef
        from users.models import MechanicProfile

        mechanic_profile = (
            MechanicProfile.objects
            .select_related('user')
            .filter(id=mechanic_profile.id)
            .annotate(
                has_active_repair_request=Exists(
                    RepairRequest.objects.filter(
                        mechanic=OuterRef('user'),
                        status__in=['accepted', 'in_progress']
                    )
                )
            )
        ).first()

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
            "Returns detailed analytics data for a mechanic, including:\n\n"
            "**High-level metrics**\n"
            "  - Total number of repair requests handled\n"
            "  - Number of completed / cancelled / failed repair requests\n"
            "  - Number of pending / in-progress repair requests\n"
            "  - Distinct customers served\n"
            "  - Distinct vehicle makes and models serviced\n\n"
            "**Ratings & reviews**\n"
            "  - Average rating\n"
            "  - Total number of reviews\n"
            "  - Rating distribution (1–5)\n\n"
            "**Revenue & pricing (if available on RepairRequest)**\n"
            "  - Total revenue\n"
            "  - Average revenue per job\n\n"
            "**Time-based metrics**\n"
            "  - Requests in the last 7 and 30 days\n"
            "  - Completion rate\n\n"
            "**Breakdowns**\n"
            "  - Top vehicle makes serviced\n"
            "  - Top vehicle models serviced\n"
            "  - Requests per status\n"
        ),
        responses={
            200: openapi.Response(
                description="Mechanic analytics payload",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "status": openapi.Schema(
                            type=openapi.TYPE_BOOLEAN,
                            example=True,
                        ),
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Mechanic analytics retrieved successfully.",
                        ),
                        "data": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "summary": openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        "total_repair_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=120,
                                        ),
                                        "completed_repair_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=90,
                                        ),
                                        "pending_repair_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=10,
                                        ),
                                        "in_progress_repair_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=5,
                                        ),
                                        "cancelled_repair_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=8,
                                        ),
                                        "failed_repair_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=7,
                                        ),
                                        "completion_rate": openapi.Schema(
                                            type=openapi.TYPE_NUMBER,
                                            format="float",
                                            example=0.75,
                                            description=(
                                                "Completed / Total, 0–1 float"
                                            ),
                                        ),
                                        "distinct_customers": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=60,
                                        ),
                                        "distinct_vehicle_makes": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=8,
                                        ),
                                        "distinct_vehicle_models": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=15,
                                        ),
                                    },
                                ),
                                "ratings": openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        "avg_rating": openapi.Schema(
                                            type=openapi.TYPE_NUMBER,
                                            format="float",
                                            example=4.6,
                                        ),
                                        "total_reviews": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=35,
                                        ),
                                        "rating_distribution": openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            properties={
                                                "1": openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=1,
                                                ),
                                                "2": openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=2,
                                                ),
                                                "3": openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=5,
                                                ),
                                                "4": openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=10,
                                                ),
                                                "5": openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    example=17,
                                                ),
                                            },
                                        ),
                                    },
                                ),
                                "time_window": openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        "last_7_days_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=12,
                                        ),
                                        "last_30_days_requests": openapi.Schema(
                                            type=openapi.TYPE_INTEGER,
                                            example=40,
                                        ),
                                    },
                                ),
                                "breakdown": openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        "requests_by_status": openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            additional_properties=openapi.Schema(
                                                type=openapi.TYPE_INTEGER
                                            ),
                                            example={
                                                "pending": 10,
                                                "in_progress": 5,
                                                "completed": 90,
                                            },
                                        ),
                                        "top_vehicle_makes": openapi.Schema(
                                            type=openapi.TYPE_ARRAY,
                                            items=openapi.Schema(
                                                type=openapi.TYPE_OBJECT,
                                                properties={
                                                    "make": openapi.Schema(
                                                        type=openapi.TYPE_STRING,
                                                        example="Toyota",
                                                    ),
                                                    "count": openapi.Schema(
                                                        type=openapi.TYPE_INTEGER,
                                                        example=40,
                                                    ),
                                                },
                                            ),
                                        ),
                                        "top_vehicle_models": openapi.Schema(
                                            type=openapi.TYPE_ARRAY,
                                            items=openapi.Schema(
                                                type=openapi.TYPE_OBJECT,
                                                properties={
                                                    "model": openapi.Schema(
                                                        type=openapi.TYPE_STRING,
                                                        example="Corolla",
                                                    ),
                                                    "count": openapi.Schema(
                                                        type=openapi.TYPE_INTEGER,
                                                        example=25,
                                                    ),
                                                },
                                            ),
                                        ),
                                    },
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

        # Authorization: must be a mechanic
        if not user.roles.filter(name="mechanic").exists():
            return Response(
                api_response(
                    message="Only mechanics can access mechanic analytics.",
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        from django.db import models
        from django.db.models import Avg, Count, Q
        from django.utils import timezone
        from users.models import MechanicProfile, MechanicReview

        try:
            mechanic_profile = MechanicProfile.objects.get(user=user)
        except MechanicProfile.DoesNotExist:
            return Response(
                api_response(
                    message="Mechanic profile not found for this user.",
                    status=False,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        # Base queryset for all analytics (centralize filters here)
        base_qs = RepairRequest.objects.filter(mechanic=user)

        # High-level counts
        total_repair_requests = base_qs.count()
        completed_repair_requests = base_qs.filter(status="completed").count()
        pending_repair_requests = base_qs.filter(status="pending").count()
        in_progress_repair_requests = base_qs.filter(
            status="in_progress"
        ).count()
        cancelled_repair_requests = base_qs.filter(status="cancelled").count()
        failed_repair_requests = base_qs.filter(status="failed").count()

        # Distinct entities
        distinct_customers = (
            base_qs.values("customer").distinct().count()
        )
        distinct_vehicle_makes = (
            base_qs.exclude(vehicle_make__isnull=True)
            .exclude(vehicle_make__exact="")
            .values("vehicle_make")
            .distinct()
            .count()
        )
        distinct_vehicle_models = (
            base_qs.exclude(vehicle_model__isnull=True)
            .exclude(vehicle_model__exact="")
            .values("vehicle_model")
            .distinct()
            .count()
        )

        # Completion rate
        completion_rate = (
            completed_repair_requests / total_repair_requests
            if total_repair_requests > 0
            else 0.0
        )

        # Ratings & reviews
        reviews_qs = MechanicReview.objects.filter(mechanic=mechanic_profile)
        rating_agg = reviews_qs.aggregate(
            avg=Avg("rating"),
            total=Count("id"),
        )
        raw_avg_rating = rating_agg.get("avg")
        avg_rating = (
            round(raw_avg_rating, 1) if raw_avg_rating is not None else None
        )
        total_reviews = rating_agg.get("total") or 0

        rating_distribution_raw = (
            reviews_qs.values("rating")
            .annotate(count=Count("id"))
            .order_by("rating")
        )
        # Normalize distribution for 1–5 keys
        rating_distribution = {str(i): 0 for i in range(1, 6)}
        for item in rating_distribution_raw:
            key = str(item.get("rating"))
            if key in rating_distribution:
                rating_distribution[key] = item.get("count") or 0

        # Time window metrics
        now = timezone.now()
        last_7_days = now - timezone.timedelta(days=7)
        last_30_days = now - timezone.timedelta(days=30)

        last_7_days_requests = base_qs.filter(
            created_at__gte=last_7_days
        ).count()
        last_30_days_requests = base_qs.filter(
            created_at__gte=last_30_days
        ).count()

        # Requests by status breakdown
        status_counts_qs = (
            base_qs.values("status")
            .annotate(count=Count("id"))
            .order_by()
        )
        requests_by_status = {
            item["status"]: item["count"] for item in status_counts_qs
        }

        # Top vehicle makes
        top_vehicle_makes_qs = (
            base_qs.exclude(vehicle_make__isnull=True)
            .exclude(vehicle_make__exact="")
            .values("vehicle_make")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        top_vehicle_makes = [
            {
                "make": item["vehicle_make"],
                "count": item["count"],
            }
            for item in top_vehicle_makes_qs
        ]

        # Top vehicle models
        top_vehicle_models_qs = (
            base_qs.exclude(vehicle_model__isnull=True)
            .exclude(vehicle_model__exact="")
            .values("vehicle_model")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        top_vehicle_models = [
            {
                "model": item["vehicle_model"],
                "count": item["count"],
            }
            for item in top_vehicle_models_qs
        ]

        # Assemble payload
        data = {
            "summary": {
                "total_repair_requests": total_repair_requests,
                "completed_repair_requests": completed_repair_requests,
                "pending_repair_requests": pending_repair_requests,
                "in_progress_repair_requests": in_progress_repair_requests,
                "cancelled_repair_requests": cancelled_repair_requests,
                "failed_repair_requests": failed_repair_requests,
                "completion_rate": round(completion_rate, 3),
                "distinct_customers": distinct_customers,
                "distinct_vehicle_makes": distinct_vehicle_makes,
                "distinct_vehicle_models": distinct_vehicle_models,
            },
            "ratings": {
                "avg_rating": avg_rating,
                "total_reviews": total_reviews,
                "rating_distribution": rating_distribution,
            },
            "time_window": {
                "last_7_days_requests": last_7_days_requests,
                "last_30_days_requests": last_30_days_requests,
            },
            "breakdown": {
                "requests_by_status": requests_by_status,
                "top_vehicle_makes": top_vehicle_makes,
                "top_vehicle_models": top_vehicle_models,
            },
        }

        return Response(
            api_response(
                message="Mechanic analytics retrieved successfully.",
                status=True,
                data=data,
            ),
            status=status.HTTP_200_OK,
        )
