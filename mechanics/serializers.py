from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    RepairRequest, TrainingSession, TrainingSessionParticipant,
    VehicleMake, MechanicVehicleExpertise, RepairProblemResolve,
    ServiceType, Settlement, RepairRequestService
)
from users.models import MechanicReview
from users.serializers import MechanicProfileSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for nested representations"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number']
        ref_name = "MechanicsUserSerializer"


class RepairProblemResolveSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairProblemResolve
        fields = ['id', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class RepairRequestSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    mechanic = UserSerializer(read_only=True)
    mechanic_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True)
    notified_mechanics = UserSerializer(many=True, read_only=True)
    problem_resolutions = RepairProblemResolveSerializer(many=True, required=False)
    service_categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ServiceType.objects.all(), required=False
    )
    can_accept = serializers.SerializerMethodField()

    class Meta:
        model = RepairRequest
        fields = [
            'id', 'customer', 'mechanic', 'mechanic_id',
            'service_categories', 'service_type',
            'vehicle_make',
            'vehicle_model', 'vehicle_year',
            'vehicle_registration',
            'vehicle_vin',
            'problem_description',
            'problem_resolutions',
            'estimated_cost', 'service_address', 'service_latitude',
            'service_longitude', 'schedule', 'preferred_date', 'preferred_time_slot',
            'status',
            'priority',
            'requested_at', 'accepted_at',
            'started_at', 'completed_at', 'cancelled_at',
            'rejected_at',
            'arrived_at',
            'in_transit_at',
            'in_progress_at',
            'user_vehicle',
            'created_at',
            'updated_at',
            'verify_completed_at',
            'notes',
            'cancellation_reason', 'actual_cost', 'is_active',
            'can_be_cancelled', 'notified_mechanics', 'can_accept', 'otp_code',
            'is_otp_verified'
        ]
        read_only_fields = [
            'id', 'customer', 'mechanic',
            'requested_at',
            'accepted_at',
            'started_at',
            'completed_at',
            'cancelled_at',
            'rejected_at',
            'arrived_at',
            'in_transit_at',
            'in_progress_at',
            'created_at',
            'updated_at',
            'verify_completed_at',
            'is_active',
            'can_be_cancelled', 'notified_mechanics', 'can_accept',
            'is_otp_verified'
        ]

    def get_can_accept(self, obj):
        """Check if current user (mechanic) can accept this request"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if request.user.roles.filter(name="mechanic").exists():
                return obj.can_mechanic_accept(request.user)
        return False

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        # Only reveal OTP if the authenticated user is the customer
        if not (request and request.user.is_authenticated and instance.customer_id == request.user.id):
            ret.pop('otp_code', None)
        return ret

    def validate_mechanic_id(self, value):
        if value is not None and not User.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "Mechanic with this ID does not exist.")
        return value

    def validate(self, attrs):
        # Ensure either service_categories or service_type (String) is provided
        if not attrs.get('service_categories') and not attrs.get('service_type'):
            raise serializers.ValidationError(
                "Either 'service_categories' (IDs) or 'service_type' (name) must be provided."
            )
        return attrs

    def create(self, validated_data):
        from django.db import transaction
        
        # The authenticated user is always the customer
        request = self.context.get('request')
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authenticated user required to create a repair request."
            )

        customer = request.user
        service_categories = validated_data.pop('service_categories', [])
        mechanic_id = validated_data.pop('mechanic_id', None)
        
        mechanic = None
        if mechanic_id:
            try:
                mechanic = User.objects.get(id=mechanic_id)
            except User.DoesNotExist:
                raise serializers.ValidationError({"mechanic_id": "Mechanic not found."})

        validated_data['customer'] = customer
        if mechanic:
            validated_data['mechanic'] = mechanic

        # Auto-fill vehicle details from user_vehicle or last repair request
        user_vehicle = validated_data.get('user_vehicle')
        if user_vehicle:
            # If user_vehicle is provided, populate missing fields
            if not validated_data.get('vehicle_make'):
                validated_data['vehicle_make'] = user_vehicle.make
            if not validated_data.get('vehicle_model'):
                validated_data['vehicle_model'] = user_vehicle.model
            if not validated_data.get('vehicle_year'):
                validated_data['vehicle_year'] = user_vehicle.year
            if not validated_data.get('vehicle_vin'):
                validated_data['vehicle_vin'] = user_vehicle.vin
            if not validated_data.get('vehicle_registration'):
                validated_data['vehicle_registration'] = user_vehicle.license_plate
        elif not any([validated_data.get('vehicle_make'), validated_data.get('vehicle_model'), validated_data.get('vehicle_vin')]):
            # If no vehicle info provided, try to fetch the last repair request by this user
            last_request = RepairRequest.objects.filter(customer=customer).order_by('-requested_at').first()
            if last_request:
                validated_data['vehicle_make'] = last_request.vehicle_make
                validated_data['vehicle_model'] = last_request.vehicle_model
                validated_data['vehicle_year'] = last_request.vehicle_year
                validated_data['vehicle_vin'] = last_request.vehicle_vin
                validated_data['vehicle_registration'] = last_request.vehicle_registration
                if not validated_data.get('user_vehicle'):
                    validated_data['user_vehicle'] = last_request.user_vehicle

        # Automatically calculate estimated_cost as the sum of base_price of all selected services
        # if estimated_cost was not explicitly provided by the user.
        if not validated_data.get('estimated_cost') and service_categories:
            total_base_price = sum(service.base_price for service in service_categories)
            validated_data['estimated_cost'] = total_base_price

        # Populate service_type charfield for easy reference and notification
        if service_categories and not validated_data.get('service_type'):
            validated_data['service_type'] = ", ".join([s.name for s in service_categories[:3]])
            if len(service_categories) > 3:
                validated_data['service_type'] += "..."

        with transaction.atomic():
            # Create the RepairRequest
            repair_request = RepairRequest.objects.create(**validated_data)
            
            # Create the many-to-many relationships through the through model
            repair_request_services = [
                RepairRequestService(repair_request=repair_request, service_type=service)
                for service in service_categories
            ]
            RepairRequestService.objects.bulk_create(repair_request_services)

        return repair_request

    def update(self, instance, validated_data):
        # Optionally support updating mechanic if mechanic_id provided (write_only) # noqa
        mechanic_id = validated_data.pop('mechanic_id', None)
        if mechanic_id is not None:
            try:
                mechanic = User.objects.get(id=mechanic_id)
                instance.mechanic = mechanic
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"mechanic_id": "Mechanic not found."})

        resolutions_data = validated_data.pop('problem_resolutions', None)

        # Remove otp_code from validated_data to prevent manual overwriting via generic updates
        validated_data.pop('otp_code', None)

        # Handle normal update for other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Handle problem_resolutions if provided
        if resolutions_data is not None:
            # Delete existing resolutions and create new ones
            instance.problem_resolutions.all().delete()
            for res_data in resolutions_data:
                RepairProblemResolve.objects.create(repair_request=instance, **res_data)

        return instance


class RepairRequestListSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    mechanic = UserSerializer(read_only=True)
    is_active = serializers.ReadOnlyField()
    can_be_cancelled = serializers.ReadOnlyField()
    problem_resolutions = RepairProblemResolveSerializer(many=True, read_only=True)
    notified_mechanics = UserSerializer(many=True, read_only=True)
    service_categories = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = RepairRequest
        fields = [
            'id',
            'customer',
            'mechanic',
            'notified_mechanics',
            'service_categories',
            'service_type',
            'vehicle_make',
            'vehicle_model',
            'vehicle_year',
            'vehicle_registration',
            'vehicle_vin',
            'problem_description',
            'problem_resolutions',
            'estimated_cost',
            'service_address',
            'service_latitude',
            'service_longitude',
            'schedule',
            'preferred_date',
            'preferred_time_slot',
            'status',
            'priority',
            'requested_at',
            'accepted_at',
            'started_at',
            'completed_at',
            'cancelled_at',
            'verify_completed_at',
            'notes',
            'cancellation_reason',
            'actual_cost',
            'is_active',
            'can_be_cancelled',
            'otp_code',
            'is_otp_verified',
            'user_vehicle',
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        # Only reveal OTP if the authenticated user is the customer
        if not (request and request.user.is_authenticated and instance.customer_id == request.user.id):
            ret.pop('otp_code', None)
        return ret


class RepairRequestStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairRequest
        fields = [
            'status', 'notes', 'actual_cost', 
            'cancellation_reason',]


class TrainingSessionSerializer(serializers.ModelSerializer):
    instructor = UserSerializer(read_only=True)
    instructor_id = serializers.UUIDField(write_only=True, required=True)
    current_participants_count = serializers.ReadOnlyField()
    is_registration_open = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    available_spots = serializers.ReadOnlyField()

    class Meta:
        model = TrainingSession
        fields = [
            'id', 'title', 'description', 'session_type', 'instructor',
            'instructor_id', 'max_participants', 'start_date', 'end_date',
            'start_time', 'end_time', 'venue', 'venue_address',
            'venue_latitude', 'venue_longitude', 'cost', 'is_free',
            'registration_deadline', 'status', 'created_at', 'updated_at',
            'materials_provided', 'prerequisites', 'certificate_offered',
            'current_participants_count', 'is_registration_open',
            'is_full', 'available_spots'
        ]
        read_only_fields = [
            'id', 'instructor', 'created_at', 'updated_at',
            'current_participants_count', 'is_registration_open',
            'is_full', 'available_spots'
        ]

    def create(self, validated_data):
        instructor_id = validated_data.pop('instructor_id')
        validated_data['instructor_id'] = instructor_id
        return super().create(validated_data)


class TrainingSessionListSerializer(serializers.ModelSerializer):
    instructor = UserSerializer(read_only=True)
    current_participants_count = serializers.ReadOnlyField()
    is_registration_open = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    available_spots = serializers.ReadOnlyField()

    class Meta:
        model = TrainingSession
        fields = [
            'id', 'title', 'session_type', 'instructor', 'start_date',
            'end_date', 'start_time', 'end_time', 'venue', 'cost',
            'is_free', 'status', 'current_participants_count',
            'is_registration_open', 'is_full', 'available_spots'
        ]


class TrainingSessionParticipantSerializer(serializers.ModelSerializer):
    participant = UserSerializer(read_only=True)
    session = TrainingSessionListSerializer(read_only=True)
    participant_id = serializers.UUIDField(write_only=True, required=True)
    session_id = serializers.UUIDField(write_only=True, required=True)

    class Meta:
        model = TrainingSessionParticipant
        fields = [
            'id', 'participant', 'session', 'participant_id', 'session_id',
            'status', 'payment_status', 'payment_amount', 'registered_at',
            'attended_at', 'completed_at', 'certificate_issued',
            'certificate_issued_at', 'rating', 'feedback'
        ]
        read_only_fields = [
            'id', 'participant', 'session', 'registered_at', 'attended_at',
            'completed_at', 'certificate_issued', 'certificate_issued_at'
        ]

    def create(self, validated_data):
        participant_id = validated_data.pop('participant_id')
        session_id = validated_data.pop('session_id')

        validated_data['participant_id'] = participant_id
        validated_data['session_id'] = session_id

        return super().create(validated_data)


class TrainingSessionParticipantListSerializer(serializers.ModelSerializer):
    participant = UserSerializer(read_only=True)
    session = TrainingSessionListSerializer(read_only=True)

    class Meta:
        model = TrainingSessionParticipant
        fields = [
            'id', 'participant', 'session', 'status', 'payment_status',
            'registered_at', 'certificate_issued', 'rating'
        ]


class MechanicReviewSerializer(serializers.ModelSerializer):
    mechanic = MechanicProfileSerializer(read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = MechanicReview
        fields = [
            'id', 'mechanic', 'user', 'rating', 'comment',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'mechanic', 'user', 'created_at', 'updated_at']  # noqa
        ref_name = (
            "MechanicsMechanicReviewSerializer"
        )


class VehicleMakeSerializer(serializers.ModelSerializer):
    """Serializer for VehicleMake model"""
    # models = serializers.StringRelatedField(many=True, read_only=True)
    models = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = VehicleMake
        fields = [
            "id", "name", "parent_make", "description",
            "is_active", "models"
        ]

    def get_models(self, obj):
        if obj.parent_make is None:
            return VehicleMakeSerializer(
                obj.models.filter(is_active=True), many=True
            ).data
        return []


class MechanicVehicleExpertiseSerializer(serializers.ModelSerializer):
    """Serializer for MechanicVehicleExpertise model"""
    vehicle_make = VehicleMakeSerializer(read_only=True)
    vehicle_make_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = MechanicVehicleExpertise
        fields = [
            'id', 'vehicle_make', 'vehicle_make_id', 'years_of_experience',
            'certification_level', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ServiceTypeSerializer(serializers.ModelSerializer):
    vehicle_make_name = serializers.CharField(source='vehicle_make.name', read_only=True)
    vehicle_model_name = serializers.CharField(source='vehicle_model.name', read_only=True)

    class Meta:
        model = ServiceType
        fields = '__all__'


class SettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settlement
        fields = '__all__'
        read_only_fields = ['id', 'total_payable', 'created_at', 'updated_at']

