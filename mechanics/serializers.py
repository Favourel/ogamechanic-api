from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    RepairRequest, TrainingSession, TrainingSessionParticipant,
    VehicleMake, MechanicVehicleExpertise
)
from users.models import MechanicProfile, MechanicReview

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for nested representations"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number']
        ref_name = "MechanicsUserSerializer"


class RepairRequestSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    mechanic = UserSerializer(read_only=True)
    mechanic_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True)

    class Meta:
        model = RepairRequest
        fields = [
            'id', 'customer', 'mechanic', 'mechanic_id',
            'service_type', 
            'vehicle_make', 
            'vehicle_model', 'vehicle_year',
            'vehicle_registration', 
            'problem_description',
            # 'symptoms',
            'estimated_cost', 'service_address', 'service_latitude',
            'service_longitude', 'preferred_date', 'preferred_time_slot',
            'status', 
            'priority', 'requested_at', 'accepted_at',
            'started_at', 'completed_at', 'cancelled_at', 'notes',
            'cancellation_reason', 'actual_cost', 'is_active',
            'can_be_cancelled'
        ]
        read_only_fields = [
            'id', 'customer', 'mechanic', 'requested_at', 'accepted_at',
            'started_at', 'completed_at', 'cancelled_at', 'is_active',
            'can_be_cancelled'
        ]

    def validate_mechanic_id(self, value):
        if value is not None and not User.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "Mechanic with this ID does not exist.")
        return value

    def create(self, validated_data):
        # The authenticated user is always the customer
        request = self.context.get('request')
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated: # noqa
            raise serializers.ValidationError(
                "Authenticated user required to create a repair request.")

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


class RepairRequestListSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    mechanic = UserSerializer(read_only=True)

    class Meta:
        model = RepairRequest
        fields = [
            'id', 'customer', 'mechanic', 'service_type', 'vehicle_make',
            'vehicle_model', 'status', 'priority', 'requested_at',
            'estimated_cost', 'is_active'
        ]


class RepairRequestStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairRequest
        fields = ['status', 'notes', 'actual_cost', 'cancellation_reason']


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


class MechanicProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    average_rating = serializers.ReadOnlyField()

    class Meta:
        model = MechanicProfile
        fields = [
            'id', 'user', 'government_id', 'is_approved', 'created_at',
            'updated_at', 'average_rating'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
        ref_name = (
            "MechanicsMechanicProfileSerializer"
        )


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
    
    class Meta:
        model = VehicleMake
        fields = ['id', 'name', 'description', 'is_active']
        read_only_fields = ['id']


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

    """Serializer for creating mechanic 
    vehicle expertise during registration"""
    vehicle_make_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of vehicle make IDs the mechanic is expert in"
    )
    expertise_details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Optional details for each vehicle make expertise"
    )
    
    def validate_vehicle_make_ids(self, value):
        """Validate that all vehicle make IDs exist and are active"""
        from .models import VehicleMake
        
        vehicle_makes = VehicleMake.objects.filter(
            id__in=value, is_active=True
        )
        
        if len(vehicle_makes) != len(value):
            invalid_ids = set(value) - set(vehicle_makes.values_list('id', flat=True))  # noqa
            raise serializers.ValidationError(
                f"Invalid or inactive vehicle make IDs: {list(invalid_ids)}"
            )
        
        return value
    
    def validate_expertise_details(self, value):
        """Validate expertise details if provided"""
        if not value:
            return value
            
        # Check that each detail has required fields
        for detail in value:
            if 'vehicle_make_id' not in detail:
                raise serializers.ValidationError(
                    "Each expertise detail must include 'vehicle_make_id'"
                )
            
            if 'years_of_experience' in detail:
                years = detail['years_of_experience']
                if not isinstance(years, int) or years < 0:
                    raise serializers.ValidationError(
                        "Years of experience must be a non-negative integer"
                    )
            
            if 'certification_level' in detail:
                valid_levels = [
                    'basic', 'intermediate', 'advanced', 'expert', 'certified']  
                if detail['certification_level'] not in valid_levels:
                    raise serializers.ValidationError(
                        f"Invalid certification level. Must be one of: {valid_levels}"  # noqa
                    )
        
        return value 