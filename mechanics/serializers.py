from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    RepairRequest, TrainingSession, TrainingSessionParticipant,
    VehicleMake, MechanicVehicleExpertise, RepairProblemResolve,
    ServiceType, Settlement
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
    can_accept = serializers.SerializerMethodField()

    class Meta:
        model = RepairRequest
        fields = [
            'id', 'customer', 'mechanic', 'mechanic_id',
            'service_category', 'service_type',
            'vehicle_make',
            'vehicle_model', 'vehicle_year',
            'vehicle_registration',
            'vehicle_vin',
            'problem_description',
            'problem_resolutions',
            # 'symptoms',
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
        # Ensure either service_category (FK) or service_type (String) is provided
        if not attrs.get('service_category') and not attrs.get('service_type'):
            raise serializers.ValidationError(
                "Either 'service_category' or 'service_type' must be provided."
            )
        return attrs

    def create(self, validated_data):
        # The authenticated user is always the customer
        request = self.context.get('request')
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated: # noqa
            raise serializers.ValidationError(
                "Authenticated user required to create a repair request."
            )

        customer = request.user

        mechanic_id = validated_data.pop('mechanic_id', None)
        mechanic = None
        if mechanic_id:
            try:
                mechanic = User.objects.get(id=mechanic_id)
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"mechanic_id": "Mechanic not found."})

        validated_data['customer'] = customer
        if mechanic:
            validated_data['mechanic'] = mechanic

        return super().create(validated_data)

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

    class Meta:
        model = RepairRequest
        fields = [
            'id',
            'customer',
            'mechanic',
            'notified_mechanics',
            'service_category',
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
            'is_otp_verified'
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

