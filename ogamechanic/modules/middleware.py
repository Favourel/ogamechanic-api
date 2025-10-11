from django.utils.deprecation import MiddlewareMixin
# from django.core.cache import cache
# from rest_framework.exceptions import APIException
import time
from django.db import connection


class PreventDuplicateSubmissionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # pass
        # Avoid duplicate submission protection for Django admin site
        if request.path.startswith('/admin/'):
            return  # Skip middleware for admin site

        # request_id = request.headers.get('X-Request-ID')
        # if request.method == "POST":
        #     if not request_id:
        #         raise APIException("Missing X-Request-ID header")
        #     cache_key = f"req-id:{request_id}"
        #     if cache.get(cache_key):
        #         raise APIException("Duplicate submission detected")
        #     cache.set(cache_key, True, timeout=60)  # prevent reuse for 60 seconds # noqa


# --- NGROK BYPASS MIDDLEWARE ---
class NgrokBypassMiddleware:
    """
    Middleware to bypass the ngrok browser warning page by setting the
    'ngrok-skip-browser-warning' header in the response if not present in the request. # noqa
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If the header is not present, set it in the response
        response = self.get_response(request)
        if 'ngrok-skip-browser-warning' not in request.headers:
            response['ngrok-skip-browser-warning'] = 'true'
        return response


class ResponseTimeMiddleware(MiddlewareMixin):
    """Middleware to track response times and log performance metrics"""
    
    def process_request(self, request):
        """Start timing the request"""
        request.start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Calculate and log response time"""
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            
            # Log response time for monitoring
            print(
                f"Response Time: {request.method} {request.path} - "
                f"{duration:.3f}s - Status: {response.status_code} - {request.method} {request.path}"  # noqa
            )  # noqa
            
            # Add response time header
            response['X-Response-Time'] = f"{duration:.3f}s {request.method} {request.path}"  # noqa
            
            # Log slow requests (> 1 second)
            if duration > 1.0:
                print(
                    f"Slow Request: {request.method} {request.path} - "
                    f"{duration:.3f}s - Status: {response.status_code} - {request.method} {request.path}"  # noqa
                )  # noqa
        
        return response


class DatabaseQueryLoggingMiddleware(MiddlewareMixin):
    """Database query logging middleware for development"""
    
    def process_response(self, request, response):
        """Log database queries in development"""
        if connection.queries:
            query_count = len(connection.queries)
            # print("query count", connection.queries)
            query_time = sum(float(q['time']) for q in connection.queries)
            
            print(
                f"Database queries for {request.path}: "
                f"Count: {query_count}, Time: {query_time:.3f}s"
            )
            
            # Log slow queries
            slow_queries = [
                q for q in connection.queries if float(q['time']) > 0.1]
            if slow_queries:
                print(f"Slow queries detected: {len(slow_queries)}")
                for query in slow_queries:
                    print(
                        f"Slow query ({query['time']}s): {query['sql']}")

        return response


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware to log request details for monitoring"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Log incoming request details"""
        # Skip logging for health checks and metrics
        if request.path in ['/health/', '/metrics/', '/admin/']:
            return self.get_response(request)

        response = self.get_response(request)

        # Log request details
        user_str = "Anonymous"
        user = getattr(request, "user", None)
        if user is not None and hasattr(user, "is_authenticated"):
            if callable(user.is_authenticated):
                is_authenticated = user.is_authenticated()
            else:
                is_authenticated = user.is_authenticated
            if is_authenticated:
                # Try to get username, email, or string representation
                user_str = getattr(user, "username", None) or getattr(user, "email", None) or str(user) # noqa
        print(
            f"Request: {request.method} {request.path} - "
            f"IP: {self.get_client_ip(request)} - "
            f"User: {user_str}"
        )

        return response

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
