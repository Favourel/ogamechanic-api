"""
Health check views for monitoring and load balancer health checks.
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.db import connection
import redis
import os

# Swagger imports
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.decorators import (
    api_view, permission_classes)
from rest_framework.permissions import AllowAny


@swagger_auto_schema(
    method='get',
    operation_summary="Health/Readiness Check",
    operation_description="""
    Consolidated health and readiness check endpoint.

    - Returns 200 if the service is healthy/ready, 500 otherwise.
    - Query param `type` can be `readiness` or `health` (default: `health`).
    - Checks:
        - Database connection
        - Redis connection
        - Cache backend
    """,
    manual_parameters=[
        openapi.Parameter(
            'type',
            openapi.IN_QUERY,
            description=(
                "Type of check: 'readiness' or 'health' (default: 'health')"
            ),
            type=openapi.TYPE_STRING,
            required=False
        )
    ],
    responses={
        200: openapi.Response(
            description="Service is healthy/ready",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(
                        type=openapi.TYPE_STRING, example="healthy"
                    ),
                    "database": openapi.Schema(
                        type=openapi.TYPE_STRING, example="connected"
                    ),
                    "redis": openapi.Schema(
                        type=openapi.TYPE_STRING, example="connected"
                    ),
                    "cache": openapi.Schema(
                        type=openapi.TYPE_STRING, example="working"
                    ),
                }
            )
        ),
        500: openapi.Response(
            description="Service is unhealthy/not ready",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(
                        type=openapi.TYPE_STRING, example="unhealthy"
                    ),
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        example="Cache backend is not working properly."
                    ),
                }
            )
        ),
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
# @renderer_classes([JSONRenderer])
@csrf_exempt
# @require_http_methods(["GET"])
def health_or_readiness_check(request):
    """
    Consolidated health and readiness check endpoint.
    Returns 200 if the service is healthy/ready, 500 otherwise.
    Query param 'type' can be 'readiness' or 'health' (default: 'health').
    Checks:
      - Database connection
      - Redis connection
      - Cache backend
    """
    check_type = request.GET.get("type", "health").lower()
    try:
        # Check database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Check Redis connection
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))
        redis_db = int(os.environ.get("REDIS_DB", 0))
        r = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        r.ping()

        # Check cache backend
        cache_key = (
            "readiness_check" if check_type == "readiness" else "health_check"
        )
        cache.set(cache_key, "ok", 10)
        cache_value = cache.get(cache_key)
        if check_type == "readiness" and cache_value != "ok":
            raise Exception("Cache backend is not working properly.")

        status_map = {
            "health": ("healthy", 200),
            "readiness": ("ready", 200)
        }
        status, code = status_map.get(check_type, ("healthy", 200))

        return JsonResponse(
            {
                "status": status,
                "database": "connected",
                "redis": "connected",
                "cache": "working",
            },
            status=code,
        )

    except Exception as e:
        error_status_map = {
            "health": ("unhealthy", 500),
            "readiness": ("not_ready", 500),
        }
        error_status, error_code = error_status_map.get(
            check_type, ("unhealthy", 500))
        return JsonResponse(
            {"status": error_status, "error": str(e)}, status=error_code
        )


# For backward compatibility, alias the old names
health_check = health_or_readiness_check
readiness_check = health_or_readiness_check
