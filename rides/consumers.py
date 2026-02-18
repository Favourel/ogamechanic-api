import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rides.models import Ride
from ogamechanic.modules.location_service import LocationService, RealTimeLocationTracker

User = get_user_model()


class RideTrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time ride tracking
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Get user from scope
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Get ride_id from URL parameters
        self.ride_id = self.scope['url_route']['kwargs']['ride_id']

        # Verify user has access to this ride
        if not await self.can_access_ride():
            await self.close()
            return

        # Join ride tracking group
        self.tracking_group_name = f"ride_tracking_{self.ride_id}"
        await self.channel_layer.group_add(
            self.tracking_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial ride data
        ride_data = await self.get_ride_data()
        if ride_data:
            await self.send(text_data=json.dumps({
                'type': 'ride.data',
                'ride': ride_data
            }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave tracking group
        await self.channel_layer.group_discard(
            self.tracking_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'location_update':
                # Handle location update from driver
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                accuracy = data.get('accuracy')

                if latitude and longitude:
                    await self.update_location(latitude, longitude, accuracy)

            elif message_type == 'get_eta':
                # Get estimated time of arrival
                eta_data = await self.get_eta()
                await self.send(text_data=json.dumps({
                    'type': 'eta.update',
                    'eta': eta_data
                }))

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def tracking_update(self, event):
        """Send tracking update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'tracking.update',
            'data': event['message']
        }))

    async def location_update(self, event):
        """Send location update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'location.update',
            'data': event['message']
        }))

    async def eta_update(self, event):
        """Send ETA update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'eta.update',
            'data': event['message']
        }))

    @database_sync_to_async
    def can_access_ride(self):
        """Check if user can access this ride"""
        try:
            ride = Ride.objects.get(id=self.ride_id)
            return (self.user == ride.customer or
                   self.user == ride.driver or
                   self.user.is_staff)
        except Ride.DoesNotExist:
            return False

    @database_sync_to_async
    def get_ride_data(self):
        """Get ride data for the tracking session"""
        try:
            ride = Ride.objects.get(id=self.ride_id)
            return {
                'id': str(ride.id),
                'status': ride.status,
                'pickup_address': ride.pickup_address,
                'pickup_latitude': float(ride.pickup_latitude),
                'pickup_longitude': float(ride.pickup_longitude),
                'dropoff_address': ride.dropoff_address,
                'dropoff_latitude': float(ride.dropoff_latitude),
                'dropoff_longitude': float(ride.dropoff_longitude),
                'driver_id': str(ride.driver.id) if ride.driver else None,
                'driver_name': ride.driver.get_full_name() if ride.driver else None,
                'customer_id': str(ride.customer.id),
                'customer_name': ride.customer.get_full_name(),
                'fare': float(ride.fare) if ride.fare else None,
                'distance_km': float(ride.distance_km) if ride.distance_km else None,
                'duration_min': float(ride.duration_min) if ride.duration_min else None
            }
        except Ride.DoesNotExist:
            return None

    @database_sync_to_async
    def update_location(self, latitude, longitude, accuracy=None):
        """Update driver location for the ride"""
        try:
            ride = Ride.objects.get(id=self.ride_id)

            # Update driver location
            if ride.driver:
                LocationService.update_driver_location(
                    str(ride.driver.id), latitude, longitude, accuracy
                )

            # Update ride tracking
            RealTimeLocationTracker.update_tracking_location(
                self.ride_id, latitude, longitude, accuracy
            )

        except Ride.DoesNotExist:
            pass

    @database_sync_to_async
    def get_eta(self):
        """Get estimated time of arrival"""
        try:
            ride = Ride.objects.get(id=self.ride_id)

            # Get driver location
            driver_lat = None
            driver_lon = None
            if ride.driver and ride.driver.driver_profile:
                driver_lat = float(ride.driver.driver_profile.latitude)
                driver_lon = float(ride.driver.driver_profile.longitude)

            # Calculate ETA
            eta_data = LocationService.calculate_route_eta(
                float(ride.pickup_latitude), float(ride.pickup_longitude),
                float(ride.dropoff_latitude), float(ride.dropoff_longitude),
                driver_lat, driver_lon
            )

            return eta_data

        except Ride.DoesNotExist:
            return None


class DriverLocationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for driver location updates
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Get user from scope
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Verify user is a driver
        if not await self.is_driver():
            await self.close()
            return

        # Join driver location group
        self.location_group_name = f"location_updates_{self.user.id}"
        await self.channel_layer.group_add(
            self.location_group_name,
            self.channel_name
        )

        await self.accept()

        # Send current location
        current_location = await self.get_current_location()
        if current_location:
            await self.send(text_data=json.dumps({
                'type': 'current.location',
                'location': current_location
            }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave location group
        await self.channel_layer.group_discard(
            self.location_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'update_location':
                # Handle location update from driver app
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                accuracy = data.get('accuracy')

                if latitude and longitude:
                    success = await self.update_driver_location(latitude, longitude, accuracy)
                    await self.send(text_data=json.dumps({
                        'type': 'location.updated',
                        'success': success
                    }))

            elif message_type == 'get_nearby_rides':
                # Get nearby ride requests
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                radius = data.get('radius', 10.0)

                if latitude and longitude:
                    nearby_rides = await self.get_nearby_rides(latitude, longitude, radius)
                    await self.send(text_data=json.dumps({
                        'type': 'nearby.rides',
                        'rides': nearby_rides
                    }))

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def location_update(self, event):
        """Send location update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'location.update',
            'data': event['message']
        }))

    @database_sync_to_async
    def is_driver(self):
        """Check if user is a driver"""
        return self.user.roles.filter(name='driver').exists()

    @database_sync_to_async
    def get_current_location(self):
        """Get driver's current location"""
        if hasattr(self.user, 'driver_profile') and self.user.driver_profile:
            profile = self.user.driver_profile
            if profile.latitude and profile.longitude:
                return {
                    'latitude': float(profile.latitude),
                    'longitude': float(profile.longitude),
                    'timestamp': profile.updated_at.isoformat()
                }
        return None

    @database_sync_to_async
    def update_driver_location(self, latitude, longitude, accuracy=None):
        """Update driver's location"""
        return LocationService.update_driver_location(
            str(self.user.id), latitude, longitude, accuracy
        )

    @database_sync_to_async
    def get_nearby_rides(self, latitude, longitude, radius):
        """Get nearby ride requests"""
        from rides.models import Ride

        # Get pending rides
        pending_rides = Ride.objects.filter(
            status='requested',
            pickup_latitude__isnull=False,
            pickup_longitude__isnull=False
        )

        nearby_rides = []

        for ride in pending_rides:
            distance = LocationService.haversine_distance(
                latitude, longitude,
                float(ride.pickup_latitude), float(ride.pickup_longitude)
            )

            if distance <= radius:
                nearby_rides.append({
                    'ride_id': str(ride.id),
                    'pickup_address': ride.pickup_address,
                    'pickup_latitude': float(ride.pickup_latitude),
                    'pickup_longitude': float(ride.pickup_longitude),
                    'dropoff_address': ride.dropoff_address,
                    'dropoff_latitude': float(ride.dropoff_latitude),
                    'dropoff_longitude': float(ride.dropoff_longitude),
                    'distance_km': round(distance, 2),
                    'customer_name': ride.customer.get_full_name() or ride.customer.email,
                    'requested_at': ride.requested_at.isoformat()
                })

        # Sort by distance
        nearby_rides.sort(key=lambda x: x['distance_km'])
        return nearby_rides[:10]  # Limit to 10 nearby rides


class CourierTrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for courier delivery tracking
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Get user from scope
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Get delivery_id from URL parameters
        self.delivery_id = self.scope['url_route']['kwargs']['delivery_id']

        # Verify user has access to this delivery
        if not await self.can_access_delivery():
            await self.close()
            return

        # Join delivery tracking group
        self.tracking_group_name = f"delivery_tracking_{self.delivery_id}"
        await self.channel_layer.group_add(
            self.tracking_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial delivery data
        delivery_data = await self.get_delivery_data()
        if delivery_data:
            await self.send(text_data=json.dumps({
                'type': 'delivery.data',
                'delivery': delivery_data
            }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave tracking group
        await self.channel_layer.group_discard(
            self.tracking_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'location_update':
                # Handle location update from driver
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                accuracy = data.get('accuracy')

                if latitude and longitude:
                    await self.update_delivery_location(latitude, longitude, accuracy)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def tracking_update(self, event):
        """Send tracking update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'tracking.update',
            'data': event['message']
        }))

    @database_sync_to_async
    def can_access_delivery(self):
        """Check if user can access this delivery"""
        from couriers.models import DeliveryRequest

        try:
            delivery = DeliveryRequest.objects.get(id=self.delivery_id)
            return (self.user == delivery.customer or
                   self.user == delivery.driver or
                   self.user.is_staff)
        except DeliveryRequest.DoesNotExist:
            return False

    @database_sync_to_async
    def get_delivery_data(self):
        """Get delivery data for the tracking session"""
        from couriers.models import DeliveryRequest

        try:
            delivery = DeliveryRequest.objects.get(id=self.delivery_id)
            return {
                'id': str(delivery.id),
                'status': delivery.status,
                'pickup_address': delivery.pickup_address,
                'pickup_latitude': float(delivery.pickup_latitude),
                'pickup_longitude': float(delivery.pickup_longitude),
                'delivery_address': delivery.delivery_address,
                'delivery_latitude': float(delivery.delivery_latitude),
                'delivery_longitude': float(delivery.delivery_longitude),
                'driver_id': str(delivery.driver.id) if delivery.driver else None,
                'driver_name': delivery.driver.get_full_name() if delivery.driver else None,
                'customer_id': str(delivery.customer.id),
                'customer_name': delivery.customer.get_full_name(),
                'package_description': delivery.package_description,
                'total_fare': float(delivery.total_fare),
                'estimated_distance': float(delivery.estimated_distance) if delivery.estimated_distance else None,
                'estimated_duration': delivery.estimated_duration
            }
        except DeliveryRequest.DoesNotExist:
            return None

    @database_sync_to_async
    def update_delivery_location(self, latitude, longitude, accuracy=None):
        """Update driver location for the delivery"""
        from couriers.models import DeliveryRequest

        try:
            delivery = DeliveryRequest.objects.get(id=self.delivery_id)

            # Update driver location
            if delivery.driver:
                LocationService.update_driver_location(
                    str(delivery.driver.id), latitude, longitude, accuracy
                )

            # Update delivery tracking
            delivery.update_driver_location(latitude, longitude)

        except DeliveryRequest.DoesNotExist:
            pass
