import math
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models import Extent
from django.contrib.gis.measure import D
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Q
import requests
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

logger = logging.getLogger(__name__)

class LocationService:
    """
    Enhanced location service with GeoDjango spatial operations
    """

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees)
        """
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        # Radius of earth in kilometers
        r = 6371
        return c * r

    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the bearing between two points
        """
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.atan2(y, x)
        return math.degrees(bearing)

    @staticmethod
    def create_point(lat: float, lon: float) -> Point:
        """
        Create a GeoDjango Point from latitude and longitude
        """
        return Point(lon, lat, srid=4326)

    @staticmethod
    def validate_coordinates(lat: float, lon: float) -> bool:
        """
        Validate latitude and longitude coordinates
        """
        return -90 <= lat <= 90 and -180 <= lon <= 180

    @staticmethod
    def get_directions(origin_lat: float, origin_lon: float,
                      dest_lat: float, dest_lon: float) -> Dict[str, Any]:
        """
        Get directions from Google Maps API with enhanced spatial data
        """
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if not api_key:
            # Fallback to Haversine calculation
            distance = LocationService.haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
            return {
                'distance_km': round(distance, 2),
                'duration_min': int(distance * 2),  # Rough estimate: 2 min per km
                'polyline': None,
                'bounds': None,
                'route_points': [
                    {'lat': origin_lat, 'lng': origin_lon},
                    {'lat': dest_lat, 'lng': dest_lon}
                ]
            }

        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            'origin': f"{origin_lat},{origin_lon}",
            'destination': f"{dest_lat},{dest_lon}",
            'key': api_key
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'OK' and data['routes']:
                route = data['routes'][0]
                leg = route['legs'][0]

                # Extract polyline points
                polyline = route['overview_polyline']['points']
                route_points = LocationService._decode_polyline(polyline)

                return {
                    'distance_km': round(leg['distance']['value'] / 1000, 2),
                    'duration_min': int(leg['duration']['value'] / 60),
                    'polyline': polyline,
                    'bounds': route['bounds'],
                    'route_points': route_points,
                    'steps': leg.get('steps', [])
                }
            else:
                # Fallback to Haversine
                distance = LocationService.haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
                return {
                    'distance_km': round(distance, 2),
                    'duration_min': int(distance * 2),
                    'polyline': None,
                    'bounds': None,
                    'route_points': [
                        {'lat': origin_lat, 'lng': origin_lon},
                        {'lat': dest_lat, 'lng': dest_lon}
                    ]
                }
        except Exception as e:
            logger.error(f"Error getting directions: {e}")
            # Fallback to Haversine
            distance = LocationService.haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
            return {
                'distance_km': round(distance, 2),
                'duration_min': int(distance * 2),
                'polyline': None,
                'bounds': None,
                'route_points': [
                    {'lat': origin_lat, 'lng': origin_lon},
                    {'lat': dest_lat, 'lng': dest_lon}
                ]
            }

    @staticmethod
    def _decode_polyline(polyline: str) -> List[Dict[str, float]]:
        """
        Decode Google Maps polyline into coordinate points
        """
        points = []
        index = 0
        lat = 0
        lng = 0

        while index < len(polyline):
            # Decode latitude
            shift = 0
            result = 0

            while True:
                byte = ord(polyline[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if not byte >= 0x20:
                    break

            lat += (~(result >> 1) if (result & 1) else (result >> 1))

            # Decode longitude
            shift = 0
            result = 0

            while True:
                byte = ord(polyline[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if not byte >= 0x20:
                    break

            lng += (~(result >> 1) if (result & 1) else (result >> 1))

            points.append({'lat': lat * 1e-5, 'lng': lng * 1e-5})

        return points

    @staticmethod
    def geocode_address(address: str) -> Optional[Dict[str, float]]:
        """
        Geocode an address to coordinates using Google Maps API
        """
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if not api_key:
            return None

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': address,
            'key': api_key
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'OK' and data['results']:
                location = data['results'][0]['geometry']['location']
                return {
                    'lat': location['lat'],
                    'lng': location['lng']
                }
        except Exception as e:
            logger.error(f"Error geocoding address: {e}")

        return None

    @staticmethod
    def reverse_geocode(lat: float, lon: float) -> Optional[str]:
        """
        Reverse geocode coordinates to address using Google Maps API
        """
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if not api_key:
            return None

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'latlng': f"{lat},{lon}",
            'key': api_key
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'OK' and data['results']:
                return data['results'][0]['formatted_address']
        except Exception as e:
            logger.error(f"Error reverse geocoding: {e}")

        return None

    @staticmethod
    def find_nearby_drivers(lat: float, lon: float, radius_km: float = 5.0) -> List[Dict[str, Any]]:
        """
        Find nearby drivers using spatial queries
        """
        from users.models import User, DriverProfile

        if not LocationService.validate_coordinates(lat, lon):
            return []

        try:
            # Create a point for the search location
            search_point = LocationService.create_point(lat, lon)

            # Find drivers within radius using spatial query
            nearby_drivers = DriverProfile.objects.filter(
                location__distance_lte=(search_point, D(km=radius_km))
            ).annotate(
                distance=Distance('location', search_point)
            ).order_by('distance')[:10]

            drivers = []
            for profile in nearby_drivers:
                if profile.user.is_active and profile.user.role.name == 'driver':
                    drivers.append({
                        'id': profile.user.id,
                        'name': profile.user.get_full_name(),
                        'email': profile.user.email,
                        'phone': profile.user.phone,
                        'distance_km': round(profile.distance.km, 2),
                        'rating': getattr(profile, 'rating', 0.0),
                        'vehicle_info': getattr(profile, 'vehicle_info', ''),
                        'is_available': getattr(profile, 'is_available', True)
                    })

            return drivers
        except Exception as e:
            logger.error(f"Error finding nearby drivers: {e}")
            return []

    @staticmethod
    def update_driver_location(driver_id: int, lat: float, lon: float) -> bool:
        """
        Update driver location with spatial data
        """
        from users.models import User, DriverProfile

        if not LocationService.validate_coordinates(lat, lon):
            return False

        try:
            driver = User.objects.get(id=driver_id, role__name='driver')
            profile, created = DriverProfile.objects.get_or_create(user=driver)

            # Update location with Point geometry
            profile.location = LocationService.create_point(lat, lon)
            profile.latitude = lat
            profile.longitude = lon
            profile.last_location_update = timezone.now()
            profile.save()

            # Send real-time update
            LocationService.send_location_update(driver_id, lat, lon)

            return True
        except Exception as e:
            logger.error(f"Error updating driver location: {e}")
            return False

    @staticmethod
    def send_location_update(user_id: int, lat: float, lon: float):
        """
        Send real-time location update via WebSocket
        """
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"location_{user_id}",
            {
                'type': 'location.update',
                'user_id': user_id,
                'lat': lat,
                'lon': lon,
                'timestamp': timezone.now().isoformat()
            }
        )

    @staticmethod
    def calculate_route_eta(origin_lat: float, origin_lon: float,
                           dest_lat: float, dest_lon: float,
                           current_lat: float = None, current_lon: float = None) -> Dict[str, Any]:
        """
        Calculate ETA and route details with spatial analysis
        """
        # Get route from origin to destination
        route_info = LocationService.get_directions(origin_lat, origin_lon, dest_lat, dest_lon)

        # If current location is provided, calculate remaining time
        if current_lat and current_lon:
            current_to_dest = LocationService.get_directions(current_lat, current_lon, dest_lat, dest_lon)
            eta_minutes = current_to_dest['duration_min']
        else:
            eta_minutes = route_info['duration_min']

        return {
            'eta_minutes': eta_minutes,
            'distance_km': route_info['distance_km'],
            'route_info': route_info,
            'estimated_arrival': timezone.now() + timezone.timedelta(minutes=eta_minutes)
        }

    @staticmethod
    def get_location_cache_key(lat: float, lon: float, radius: float = 1.0) -> str:
        """
        Generate cache key for location data
        """
        # Round coordinates to create cache zones
        lat_rounded = round(lat / radius) * radius
        lon_rounded = round(lon / radius) * radius
        return f"location_data_{lat_rounded}_{lon_rounded}_{radius}"

    @staticmethod
    def cache_location_data(lat: float, lon: float, data: Dict[str, Any],
                          radius: float = 1.0, timeout: int = 300) -> None:
        """
        Cache location data for performance
        """
        cache_key = LocationService.get_location_cache_key(lat, lon, radius)
        cache.set(cache_key, data, timeout)

    @staticmethod
    def get_cached_location(lat: float, lon: float, radius: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        Get cached location data
        """
        cache_key = LocationService.get_location_cache_key(lat, lon, radius)
        return cache.get(cache_key)

    @staticmethod
    def create_spatial_index(lat: float, lon: float, radius_km: float = 5.0) -> Dict[str, Any]:
        """
        Create spatial index for efficient location queries
        """
        center_point = LocationService.create_point(lat, lon)

        return {
            'center': center_point,
            'radius': D(km=radius_km),
            'bounds': {
                'min_lat': lat - (radius_km / 111.32),  # Approximate degrees per km
                'max_lat': lat + (radius_km / 111.32),
                'min_lon': lon - (radius_km / (111.32 * math.cos(math.radians(lat)))),
                'max_lon': lon + (radius_km / (111.32 * math.cos(math.radians(lat))))
            }
        }

    @staticmethod
    def calculate_spatial_metrics(points: List[Tuple[float, float]]) -> Dict[str, float]:
        """
        Calculate spatial metrics for a set of points
        """
        if len(points) < 2:
            return {'total_distance': 0, 'avg_speed': 0, 'max_speed': 0}

        total_distance = 0
        speeds = []

        for i in range(len(points) - 1):
            lat1, lon1 = points[i]
            lat2, lon2 = points[i + 1]
            distance = LocationService.haversine_distance(lat1, lon1, lat2, lon2)
            total_distance += distance

            # Calculate speed (assuming 1-minute intervals)
            if distance > 0:
                speed = distance * 60  # km/h
                speeds.append(speed)

        return {
            'total_distance': round(total_distance, 2),
            'avg_speed': round(sum(speeds) / len(speeds), 2) if speeds else 0,
            'max_speed': round(max(speeds), 2) if speeds else 0
        }


class RealTimeLocationTracker:
    """
    Real-time location tracking with spatial operations
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.tracking_points = []
        self.is_tracking = False

    @staticmethod
    def start_tracking(user_id: int) -> bool:
        """
        Start real-time location tracking
        """
        try:
            tracker = RealTimeLocationTracker(user_id)
            tracker.is_tracking = True
            # Store tracker in cache or database
            cache.set(f"tracker_{user_id}", tracker, 3600)
            return True
        except Exception as e:
            logger.error(f"Error starting tracking: {e}")
            return False

    @staticmethod
    def stop_tracking(user_id: int) -> bool:
        """
        Stop real-time location tracking
        """
        try:
            cache.delete(f"tracker_{user_id}")
            return True
        except Exception as e:
            logger.error(f"Error stopping tracking: {e}")
            return False

    @staticmethod
    def update_tracking_location(user_id: int, lat: float, lon: float,
                               timestamp: Optional[str] = None) -> bool:
        """
        Update tracking location with spatial validation
        """
        if not LocationService.validate_coordinates(lat, lon):
            return False

        try:
            # Update driver location
            LocationService.update_driver_location(user_id, lat, lon)

            # Store tracking point
            point = {
                'lat': lat,
                'lon': lon,
                'timestamp': timestamp or timezone.now().isoformat()
            }

            # Cache recent tracking points
            cache_key = f"tracking_points_{user_id}"
            points = cache.get(cache_key, [])
            points.append(point)

            # Keep only last 100 points
            if len(points) > 100:
                points = points[-100:]

            cache.set(cache_key, points, 3600)

            # Send real-time update
            RealTimeLocationTracker.send_tracking_update(user_id, point)

            return True
        except Exception as e:
            logger.error(f"Error updating tracking location: {e}")
            return False

    @staticmethod
    def send_tracking_update(user_id: int, point: Dict[str, Any]):
        """
        Send real-time tracking update via WebSocket
        """
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"tracking_{user_id}",
            {
                'type': 'tracking.update',
                'user_id': user_id,
                'point': point
            }
        )

    @staticmethod
    def get_tracking_history(user_id: int, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get tracking history with spatial analysis
        """
        try:
            cache_key = f"tracking_points_{user_id}"
            points = cache.get(cache_key, [])

            if not points:
                return []

            # Calculate spatial metrics
            coordinates = [(p['lat'], p['lon']) for p in points]
            metrics = LocationService.calculate_spatial_metrics(coordinates)

            return {
                'points': points,
                'metrics': metrics,
                'total_points': len(points)
            }
        except Exception as e:
            logger.error(f"Error getting tracking history: {e}")
            return []


class MapIntegrationService:
    """
    Enhanced map integration service with spatial features
    """

    @staticmethod
    def get_map_embed_url(lat: float, lon: float, zoom: int = 15) -> str:
        """
        Get Google Maps embed URL
        """
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if api_key:
            return f"https://www.google.com/maps/embed/v1/view?key={api_key}&center={lat},{lon}&zoom={zoom}"
        return f"https://www.google.com/maps?q={lat},{lon}&z={zoom}"

    @staticmethod
    def get_static_map_url(lat: float, lon: float, zoom: int = 15,
                          size: str = "600x400") -> str:
        """
        Get Google Maps static image URL
        """
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if api_key:
            return (f"https://maps.googleapis.com/maps/api/staticmap?"
                   f"center={lat},{lon}&zoom={zoom}&size={size}&key={api_key}")
        return f"https://www.google.com/maps?q={lat},{lon}&z={zoom}"

    @staticmethod
    def get_route_map_url(origin_lat: float, origin_lon: float,
                          dest_lat: float, dest_lon: float,
                          size: str = "600x400") -> str:
        """
        Get Google Maps static route image URL
        """
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if api_key:
            return (f"https://maps.googleapis.com/maps/api/staticmap?"
                   f"size={size}&key={api_key}"
                   f"&markers=color:red|label:O|{origin_lat},{origin_lon}"
                   f"&markers=color:green|label:D|{dest_lat},{dest_lon}"
                   f"&path=color:0x0000ff|weight:5|{origin_lat},{origin_lon}|{dest_lat},{dest_lon}")
        return f"https://www.google.com/maps/dir/{origin_lat},{origin_lon}/{dest_lat},{dest_lon}"

    @staticmethod
    def get_spatial_bounds(points: List[Dict[str, float]]) -> Dict[str, float]:
        """
        Calculate spatial bounds for a set of points
        """
        if not points:
            return {'min_lat': 0, 'max_lat': 0, 'min_lon': 0, 'max_lon': 0}

        lats = [p['lat'] for p in points]
        lons = [p['lon'] for p in points]

        return {
            'min_lat': min(lats),
            'max_lat': max(lats),
            'min_lon': min(lons),
            'max_lon': max(lons)
        }

    @staticmethod
    def create_heatmap_data(points: List[Dict[str, float]]) -> List[Dict[str, Any]]:
        """
        Create heatmap data for visualization
        """
        heatmap_data = []
        for point in points:
            heatmap_data.append({
                'lat': point['lat'],
                'lng': point['lon'],
                'weight': point.get('weight', 1)
            })
        return heatmap_data


# Celery tasks for background processing
@shared_task
def track_location(user_id: int, lat: float, lon: float):
    """
    Background task for location tracking
    """
    RealTimeLocationTracker.update_tracking_location(user_id, lat, lon)

@shared_task
def update_driver_location_task(driver_id: int, lat: float, lon: float):
    """
    Background task for updating driver location
    """
    LocationService.update_driver_location(driver_id, lat, lon)

@shared_task
def geocode_address_task(address: str):
    """
    Background task for geocoding addresses
    """
    return LocationService.geocode_address(address)

@shared_task
def calculate_spatial_metrics_task(points: List[Tuple[float, float]]):
    """
    Background task for calculating spatial metrics
    """
    return LocationService.calculate_spatial_metrics(points)
