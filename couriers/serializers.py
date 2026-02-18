from rest_framework import serializers
from .models import DeliveryRequest, DeliveryTracking, CourierRating, DeliveryWaypoint


class DeliveryWaypointSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryWaypoint model."""
    waypoint_type_display = serializers.CharField(source='get_waypoint_type_display', read_only=True)

    class Meta:
        model = DeliveryWaypoint
        fields = [
            'id', 'address', 'latitude', 'longitude', 'waypoint_type',
            'waypoint_type_display', 'sequence_order', 'contact_name',
            'contact_phone', 'instructions', 'package_description',
            'package_weight', 'package_dimensions', 'is_fragile',
            'requires_signature', 'is_completed', 'completed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'is_completed', 'completed_at', 'created_at', 'updated_at'
        ]


class DeliveryWaypointCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating delivery waypoints."""

    class Meta:
        model = DeliveryWaypoint
        fields = [
            'address', 'latitude', 'longitude', 'waypoint_type',
            'sequence_order', 'contact_name', 'contact_phone', 'instructions',
            'package_description', 'package_weight', 'package_dimensions',
            'is_fragile', 'requires_signature'
        ]

    def validate_sequence_order(self, value):
        """Validate sequence order is positive."""
        if value <= 0:
            raise serializers.ValidationError("Sequence order must be positive")
        return value


class DeliveryRequestSerializer(serializers.ModelSerializer):
    """Enhanced serializer for DeliveryRequest model with waypoints."""
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    waypoints = DeliveryWaypointSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = DeliveryRequest
        fields = [
            'id', 'customer', 'driver', 'pickup_address', 'pickup_latitude',
            'pickup_longitude', 'pickup_contact_name', 'pickup_contact_phone',
            'pickup_instructions', 'delivery_address', 'delivery_latitude',
            'delivery_longitude', 'delivery_contact_name', 'delivery_contact_phone',
            'delivery_instructions', 'waypoints', 'current_waypoint_index',
            'total_distance_km', 'total_duration_min', 'route_polyline',
            'package_description', 'package_weight', 'package_dimensions',
            'is_fragile', 'requires_signature', 'estimated_distance',
            'estimated_duration', 'base_fare', 'distance_fare', 'total_fare',
            'payment_method', 'payment_method_display', 'payment_status',
            'payment_status_display', 'status', 'status_display', 'notes',
            'requested_at', 'assigned_at', 'picked_up_at', 'delivered_at',
            'cancelled_at', 'driver_latitude', 'driver_longitude',
            'last_location_update'
        ]
        read_only_fields = [
            'id', 'customer', 'driver', 'current_waypoint_index',
            'total_distance_km', 'total_duration_min', 'route_polyline',
            'estimated_distance', 'estimated_duration', 'base_fare',
            'distance_fare', 'total_fare', 'payment_status', 'requested_at',
            'assigned_at', 'picked_up_at', 'delivered_at', 'cancelled_at',
            'driver_latitude', 'driver_longitude', 'last_location_update'
        ]


class DeliveryRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating delivery requests with multiple waypoints."""
    waypoints = DeliveryWaypointCreateSerializer(many=True, required=False)

    class Meta:
        model = DeliveryRequest
        fields = [
            'pickup_address', 'pickup_latitude', 'pickup_longitude',
            'pickup_contact_name', 'pickup_contact_phone', 'pickup_instructions',
            'delivery_address', 'delivery_latitude', 'delivery_longitude',
            'delivery_contact_name', 'delivery_contact_phone', 'delivery_instructions',
            'package_description', 'package_weight', 'package_dimensions',
            'is_fragile', 'requires_signature', 'payment_method', 'waypoints'
        ]

    def create(self, validated_data):
        waypoints_data = validated_data.pop('waypoints', [])
        delivery_request = DeliveryRequest.objects.create(**validated_data)

        # Create waypoints if provided
        if waypoints_data:
            for waypoint_data in waypoints_data:
                waypoint = DeliveryWaypoint.objects.create(**waypoint_data)
                delivery_request.waypoints.add(waypoint)
        else:
            # Create default pickup and dropoff waypoints from legacy fields
            if validated_data.get('pickup_address'):
                pickup_waypoint = DeliveryWaypoint.objects.create(
                    address=validated_data['pickup_address'],
                    latitude=validated_data['pickup_latitude'],
                    longitude=validated_data['pickup_longitude'],
                    waypoint_type='pickup',
                    sequence_order=1,
                    contact_name=validated_data.get('pickup_contact_name', ''),
                    contact_phone=validated_data.get('pickup_contact_phone', ''),
                    instructions=validated_data.get('pickup_instructions', ''),
                    package_description=validated_data.get('package_description', ''),
                    package_weight=validated_data.get('package_weight'),
                    package_dimensions=validated_data.get('package_dimensions', ''),
                    is_fragile=validated_data.get('is_fragile', False),
                    requires_signature=validated_data.get('requires_signature', False)
                )
                delivery_request.waypoints.add(pickup_waypoint)

            if validated_data.get('delivery_address'):
                dropoff_waypoint = DeliveryWaypoint.objects.create(
                    address=validated_data['delivery_address'],
                    latitude=validated_data['delivery_latitude'],
                    longitude=validated_data['delivery_longitude'],
                    waypoint_type='dropoff',
                    sequence_order=2,
                    contact_name=validated_data.get('delivery_contact_name', ''),
                    contact_phone=validated_data.get('delivery_contact_phone', ''),
                    instructions=validated_data.get('delivery_instructions', '')
                )
                delivery_request.waypoints.add(dropoff_waypoint)

        return delivery_request


class DeliveryWaypointUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating delivery waypoint completion status."""

    class Meta:
        model = DeliveryWaypoint
        fields = ['is_completed']

    def update(self, instance, validated_data):
        from django.utils import timezone

        is_completed = validated_data.get('is_completed', False)
        if is_completed and not instance.is_completed:
            instance.completed_at = timezone.now()

        instance.is_completed = is_completed
        instance.save()
        return instance


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryTracking model."""
    delivery_request = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()

    class Meta:
        model = DeliveryTracking
        fields = [
            'id', 'delivery_request', 'driver', 'latitude', 'longitude',
            'accuracy', 'status', 'notes', 'timestamp'
        ]
        read_only_fields = ['id', 'delivery_request', 'driver', 'timestamp']


class CourierRatingSerializer(serializers.ModelSerializer):
    """Serializer for CourierRating model."""
    delivery_request = serializers.StringRelatedField()
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    average_rating = serializers.ReadOnlyField()

    class Meta:
        model = CourierRating
        fields = [
            'id', 'delivery_request', 'customer', 'driver', 'overall_rating',
            'delivery_speed_rating', 'service_quality_rating',
            'communication_rating', 'review', 'average_rating',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'delivery_request', 'customer', 'driver', 'created_at', 'updated_at']


class CourierRequestSerializer(serializers.ModelSerializer):
    """Legacy serializer for backward compatibility."""
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = DeliveryRequest
        fields = [
            'id', 'customer', 'driver', 'pickup_address', 'pickup_latitude',
            'pickup_longitude', 'delivery_address', 'delivery_latitude',
            'delivery_longitude', 'package_description', 'package_weight',
            'status', 'status_display', 'fare', 'requested_at', 'accepted_at',
            'started_at', 'completed_at', 'cancelled_at'
        ]
        read_only_fields = [
            'id', 'customer', 'driver', 'fare', 'requested_at', 'accepted_at',
            'started_at', 'completed_at', 'cancelled_at'
        ]
        ref_name = "CouriersCourierRequestSerializer"


class CourierRequestListSerializer(serializers.ModelSerializer):
    """Serializer for listing courier requests."""
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = DeliveryRequest
        fields = [
            'id', 'customer', 'driver', 'pickup_address', 'delivery_address',
            'package_description', 'status', 'status_display', 'total_fare',
            'requested_at'
        ]
        read_only_fields = ['id', 'customer', 'driver', 'total_fare', 'requested_at']


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryTracking model."""
    delivery_request = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()

    class Meta:
        model = DeliveryTracking
        fields = [
            'id', 'delivery_request', 'driver', 'latitude', 'longitude',
            'accuracy', 'status', 'notes', 'timestamp'
        ]
        read_only_fields = ['id', 'delivery_request', 'driver', 'timestamp']


class CourierRatingSerializer(serializers.ModelSerializer):
    """Serializer for CourierRating model."""
    delivery_request = serializers.StringRelatedField()
    customer = serializers.StringRelatedField()
    driver = serializers.StringRelatedField()
    average_rating = serializers.ReadOnlyField()

    class Meta:
        model = CourierRating
        fields = [
            'id', 'delivery_request', 'customer', 'driver', 'overall_rating',
            'delivery_speed_rating', 'service_quality_rating',
            'communication_rating', 'review', 'average_rating',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'delivery_request', 'customer', 'driver', 'created_at', 'updated_at']


class CourierRequestCreateSerializer(serializers.ModelSerializer):
    """Legacy serializer for creating courier requests."""

    class Meta:
        model = DeliveryRequest
        fields = [
            'pickup_address', 'pickup_latitude', 'pickup_longitude',
            'pickup_contact_name', 'pickup_contact_phone', 'pickup_instructions',
            'delivery_address', 'delivery_latitude', 'delivery_longitude',
            'delivery_contact_name', 'delivery_contact_phone', 'delivery_instructions',
            'package_description', 'package_weight', 'package_dimensions',
            'is_fragile', 'requires_signature', 'payment_method'
        ]


class CourierRequestStatusUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating courier request status."""

    class Meta:
        model = DeliveryRequest
        fields = ['status']

    def validate_status(self, value):
        """Validate status transition."""
        instance = self.instance
        if instance:
            valid_transitions = {
                'pending': ['assigned', 'cancelled'],
                'assigned': ['picked_up', 'cancelled'],
                'picked_up': ['in_transit', 'delivered'],
                'in_transit': ['delivered'],
                'delivered': [],
                'cancelled': [],
                'failed': []
            }

            current_status = instance.status
            if value not in valid_transitions.get(current_status, []):
                raise serializers.ValidationError(
                    f"Invalid status transition from {current_status} to {value}"
                )

        return value


class DriverLocationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating driver location."""

    class Meta:
        model = DeliveryRequest
        fields = ['driver_latitude', 'driver_longitude']

    def update(self, instance, validated_data):
        from django.utils import timezone

        instance.driver_latitude = validated_data.get('driver_latitude')
        instance.driver_longitude = validated_data.get('driver_longitude')
        instance.last_location_update = timezone.now()
        instance.save()
        return instance


class AvailableDriversSerializer(serializers.Serializer):
    """Serializer for available drivers response"""

    driver_id = serializers.UUIDField()
    driver_email = serializers.EmailField()
    driver_name = serializers.CharField()
    distance_to_pickup = serializers.DecimalField(max_digits=6, decimal_places=2) # noqa
    estimated_arrival = serializers.IntegerField()  # minutes
    current_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    vehicle_info = serializers.CharField()
