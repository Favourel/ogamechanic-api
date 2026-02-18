from rest_framework import serializers
from .models import Ride, CourierRequest, Waypoint


class WaypointSerializer(serializers.ModelSerializer):
    """Serializer for Waypoint model."""
    waypoint_type_display = serializers.CharField(source='get_waypoint_type_display', read_only=True)

    class Meta:
        model = Waypoint
        fields = [
            'id', 'address', 'latitude', 'longitude', 'waypoint_type',
            'waypoint_type_display', 'sequence_order', 'contact_name',
            'contact_phone', 'instructions', 'is_completed', 'completed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_completed', 'completed_at', 'created_at', 'updated_at']


class WaypointCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating waypoints."""

    class Meta:
        model = Waypoint
        fields = [
            'address', 'latitude', 'longitude', 'waypoint_type',
            'sequence_order', 'contact_name', 'contact_phone', 'instructions'
        ]

    def validate_sequence_order(self, value):
        """Validate sequence order is positive."""
        if value <= 0:
            raise serializers.ValidationError("Sequence order must be positive")
        return value


class RideSerializer(serializers.ModelSerializer):
    """Enhanced serializer for Ride model with waypoints."""
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    waypoints = WaypointSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Ride
        fields = [
            'id', 'customer', 'driver', 'pickup_address', 'pickup_latitude',
            'pickup_longitude', 'dropoff_address', 'dropoff_latitude',
            'dropoff_longitude', 'waypoints', 'current_waypoint_index',
            'total_distance_km', 'total_duration_min', 'route_polyline',
            'status', 'status_display', 'fare', 'distance_km', 'duration_min',
            'requested_at', 'accepted_at', 'started_at', 'completed_at', 'cancelled_at'
        ]
        read_only_fields = [
            'id', 'customer', 'driver', 'current_waypoint_index',
            'total_distance_km', 'total_duration_min', 'route_polyline',
            'fare', 'distance_km', 'duration_min', 'requested_at',
            'accepted_at', 'started_at', 'completed_at', 'cancelled_at'
        ]


class RideCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating rides with multiple waypoints."""
    waypoints = WaypointCreateSerializer(many=True, required=False)

    class Meta:
        model = Ride
        fields = [
            'pickup_address', 'pickup_latitude', 'pickup_longitude',
            'dropoff_address', 'dropoff_latitude', 'dropoff_longitude',
            'waypoints'
        ]

    def create(self, validated_data):
        waypoints_data = validated_data.pop('waypoints', [])
        ride = Ride.objects.create(**validated_data)

        # Create waypoints if provided
        if waypoints_data:
            for waypoint_data in waypoints_data:
                waypoint = Waypoint.objects.create(**waypoint_data)
                ride.waypoints.add(waypoint)
        else:
            # Create default pickup and dropoff waypoints from legacy fields
            if validated_data.get('pickup_address'):
                pickup_waypoint = Waypoint.objects.create(
                    address=validated_data['pickup_address'],
                    latitude=validated_data['pickup_latitude'],
                    longitude=validated_data['pickup_longitude'],
                    waypoint_type='pickup',
                    sequence_order=1
                )
                ride.waypoints.add(pickup_waypoint)

            if validated_data.get('dropoff_address'):
                dropoff_waypoint = Waypoint.objects.create(
                    address=validated_data['dropoff_address'],
                    latitude=validated_data['dropoff_latitude'],
                    longitude=validated_data['dropoff_longitude'],
                    waypoint_type='dropoff',
                    sequence_order=2
                )
                ride.waypoints.add(dropoff_waypoint)

        return ride


class CourierRequestSerializer(serializers.ModelSerializer):
    """Enhanced serializer for CourierRequest model with waypoints."""
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    waypoints = WaypointSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CourierRequest
        fields = [
            'id', 'customer', 'driver', 'pickup_address', 'pickup_latitude',
            'pickup_longitude', 'dropoff_address', 'dropoff_latitude',
            'dropoff_longitude', 'waypoints', 'current_waypoint_index',
            'total_distance_km', 'total_duration_min', 'route_polyline',
            'item_description', 'item_weight', 'status', 'status_display',
            'fare', 'requested_at', 'accepted_at', 'started_at',
            'completed_at', 'cancelled_at'
        ]
        read_only_fields = [
            'id', 'customer', 'driver', 'current_waypoint_index',
            'total_distance_km', 'total_duration_min', 'route_polyline',
            'fare', 'requested_at', 'accepted_at', 'started_at',
            'completed_at', 'cancelled_at'
        ]


class CourierRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating courier requests with multiple waypoints."""
    waypoints = WaypointCreateSerializer(many=True, required=False)

    class Meta:
        model = CourierRequest
        fields = [
            'pickup_address', 'pickup_latitude', 'pickup_longitude',
            'dropoff_address', 'dropoff_latitude', 'dropoff_longitude',
            'item_description', 'item_weight', 'waypoints'
        ]

    def create(self, validated_data):
        waypoints_data = validated_data.pop('waypoints', [])
        courier_request = CourierRequest.objects.create(**validated_data)

        # Create waypoints if provided
        if waypoints_data:
            for waypoint_data in waypoints_data:
                waypoint = Waypoint.objects.create(**waypoint_data)
                courier_request.waypoints.add(waypoint)
        else:
            # Create default pickup and dropoff waypoints from legacy fields
            if validated_data.get('pickup_address'):
                pickup_waypoint = Waypoint.objects.create(
                    address=validated_data['pickup_address'],
                    latitude=validated_data['pickup_latitude'],
                    longitude=validated_data['pickup_longitude'],
                    waypoint_type='pickup',
                    sequence_order=1
                )
                courier_request.waypoints.add(pickup_waypoint)

            if validated_data.get('dropoff_address'):
                dropoff_waypoint = Waypoint.objects.create(
                    address=validated_data['dropoff_address'],
                    latitude=validated_data['dropoff_latitude'],
                    longitude=validated_data['dropoff_longitude'],
                    waypoint_type='dropoff',
                    sequence_order=2
                )
                courier_request.waypoints.add(dropoff_waypoint)

        return courier_request


class WaypointUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating waypoint completion status."""

    class Meta:
        model = Waypoint
        fields = ['is_completed']

    def update(self, instance, validated_data):
        from django.utils import timezone

        is_completed = validated_data.get('is_completed', False)
        if is_completed and not instance.is_completed:
            instance.completed_at = timezone.now()

        instance.is_completed = is_completed
        instance.save()
        return instance