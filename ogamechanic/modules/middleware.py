from django.utils.deprecation import MiddlewareMixin
import time
from django.db import connection
from asgiref.sync import iscoroutinefunction, markcoroutinefunction


# --- NGROK BYPASS MIDDLEWARE ---
class NgrokBypassMiddleware:
    """
    Middleware to bypass the ngrok browser warning page by setting the
    'ngrok-skip-browser-warning' header in the response if not present in the request.
    """
    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)

        response = self.get_response(request)
        if 'ngrok-skip-browser-warning' not in request.headers:
            response['ngrok-skip-browser-warning'] = 'true'
        return response

    async def __acall__(self, request):
        response = await self.get_response(request)
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
                f"{duration:.3f}s - Status: {response.status_code}"
            )

            # Add response time header
            response['X-Response-Time'] = f"{duration:.3f}s"

            # Log slow requests (> 1 second)
            if duration > 1.0:
                print(
                    f"Slow Request: {request.method} {request.path} - "
                    f"{duration:.3f}s - Status: {response.status_code}"
                )

        return response


class DatabaseQueryLoggingMiddleware(MiddlewareMixin):
    """Database query logging middleware for development"""

    def process_response(self, request, response):
        """Log database queries in development"""
        if connection.queries:
            query_count = len(connection.queries)
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

    def process_request(self, request):
        """Log incoming request details (sync portion via MiddlewareMixin)"""
        if request.path in ['/health/', '/metrics/', '/admin/']:
            return None

        user_str = "Anonymous"
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            user_str = getattr(user, "username", None) or getattr(user, "email", None) or str(user)

        print(
            f"Request: {request.method} {request.path} - "
            f"IP: {self.get_client_ip(request)} - "
            f"User: {user_str}"
        )
        return None

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

