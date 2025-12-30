"""
Strategic Audit Trail Middleware
=================================
Production-grade middleware for logging business-critical events only.
Focuses on strategic activities rather than logging every request.
"""

import time
import json
import logging
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from users.models import UserActivityLog

logger = logging.getLogger(__name__)


class StrategicAuditMiddleware(MiddlewareMixin):
    """
    Middleware that logs only business-critical activities.
    Designed for multi-service platforms (ecommerce, rentals, rides, mechanics).
    """
    
    # Define business-critical endpoints that should be logged
    CRITICAL_PATTERNS = {
        # Authentication & Authorization
        '/api/v1/authentication/login/': {
            'category': 'authentication',
            'severity': 'medium',
            'action': 'user_login'
        },
        '/api/v1/authentication/logout/': {
            'category': 'authentication',
            'severity': 'low',
            'action': 'user_logout'
        },
        '/api/v1/authentication/register/': {
            'category': 'authentication',
            'severity': 'medium',
            'action': 'user_registration'
        },
        '/api/v1/authentication/password/reset/': {
            'category': 'security',
            'severity': 'high',
            'action': 'password_reset'
        },
        '/api/v1/authentication/password/change/': {
            'category': 'security',
            'severity': 'medium',
            'action': 'password_change'
        },
        
        # Transactions & Payments
        '/api/v1/payments/': {
            'category': 'transaction',
            'severity': 'critical',
            'action': 'payment_initiated'
        },
        '/api/v1/payments/verify/': {
            'category': 'transaction',
            'severity': 'critical',
            'action': 'payment_verified'
        },
        '/api/v1/wallet/withdraw/': {
            'category': 'transaction',
            'severity': 'critical',
            'action': 'wallet_withdrawal'
        },
        '/api/v1/wallet/deposit/': {
            'category': 'transaction',
            'severity': 'critical',
            'action': 'wallet_deposit'
        },
        
        # Orders & Purchases
        '/api/v1/orders/create/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'order_created'
        },
        '/api/v1/orders/cancel/': {
            'category': 'business_critical',
            'severity': 'medium',
            'action': 'order_cancelled'
        },
        
        # Rides
        '/api/v1/rides/request/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'ride_requested'
        },
        '/api/v1/rides/accept/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'ride_accepted'
        },
        '/api/v1/rides/complete/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'ride_completed'
        },
        '/api/v1/rides/cancel/': {
            'category': 'business_critical',
            'severity': 'medium',
            'action': 'ride_cancelled'
        },
        
        # Rentals
        '/api/v1/rentals/book/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'rental_booked'
        },
        '/api/v1/rentals/cancel/': {
            'category': 'business_critical',
            'severity': 'medium',
            'action': 'rental_cancelled'
        },
        
        # Mechanic Services
        '/api/v1/mechanics/request/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'mechanic_requested'
        },
        '/api/v1/mechanics/accept/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'mechanic_accepted'
        },
        '/api/v1/mechanics/complete/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'mechanic_completed'
        },
        
        # Courier/Delivery
        '/api/v1/couriers/request/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'delivery_requested'
        },
        '/api/v1/couriers/accept/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'delivery_accepted'
        },
        '/api/v1/couriers/complete/': {
            'category': 'business_critical',
            'severity': 'high',
            'action': 'delivery_completed'
        },
        
        # Profile & Account Changes
        '/api/v1/profile/update/': {
            'category': 'data_modification',
            'severity': 'medium',
            'action': 'profile_updated'
        },
        '/api/v1/profile/delete/': {
            'category': 'data_modification',
            'severity': 'critical',
            'action': 'account_deletion'
        },
        
        # Admin Actions
        '/api/v1/admin/approve/': {
            'category': 'authorization',
            'severity': 'high',
            'action': 'admin_approval'
        },
        '/api/v1/admin/reject/': {
            'category': 'authorization',
            'severity': 'high',
            'action': 'admin_rejection'
        },
        
        # Document Uploads (KYC/Verification)
        '/api/v1/documents/upload/': {
            'category': 'compliance',
            'severity': 'high',
            'action': 'document_uploaded'
        },
        '/api/v1/documents/verify/': {
            'category': 'compliance',
            'severity': 'high',
            'action': 'document_verified'
        },
    }
    
    # Patterns to match (for partial URL matching)
    CRITICAL_PATTERNS_PARTIAL = [
        'payment',
        'transaction',
        'withdraw',
        'deposit',
        'approve',
        'reject',
        'verify',
        'delete',
        'cancel',
    ]
    
    # HTTP methods that indicate state changes (worth logging)
    STATE_CHANGING_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
    
    # Paths to NEVER log (too noisy, low value)
    EXCLUDED_PATHS = [
        '/static/',
        '/media/',
        '/__debug__/',
        '/swagger/',
        '/redoc/',
        '/api/v1/products/list/',  # Read-only list
        '/api/v1/categories/',  # Read-only
        '/api/v1/health/',  # Health checks
        '/api/v1/ping/',  # Ping endpoints
    ]
    
    def process_request(self, request):
        """Mark the start time for response time calculation."""
        request._audit_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """
        Log business-critical activities based on request/response.
        Only logs strategic events, not every request.
        """
        # Skip if audit logging is disabled
        if not getattr(settings, 'ENABLE_AUDIT_LOGGING', True):
            return response
        
        # Calculate response time
        response_time_ms = None
        if hasattr(request, '_audit_start_time'):
            response_time_ms = int((time.time() - request._audit_start_time) * 1000)
        
        # Check if this request should be logged
        if not self._should_log_request(request, response):
            return response
        
        # Extract audit info
        audit_info = self._extract_audit_info(request, response, response_time_ms)
        
        # Log asynchronously (don't block the response)
        try:
            self._log_activity(audit_info)
        except Exception as e:
            logger.error(f"Failed to log audit activity: {e}")
        
        return response
    
    def _should_log_request(self, request, response):
        """
        Determine if this request should be logged.
        Returns True only for business-critical activities.
        """
        path = request.path
        method = request.method
        
        # Skip excluded paths
        for excluded in self.EXCLUDED_PATHS:
            if excluded in path:
                return False
        
        # Skip successful GET requests (read-only, not critical)
        if method == 'GET' and 200 <= response.status_code < 300:
            return False
        
        # Log all state-changing methods on critical endpoints
        if method in self.STATE_CHANGING_METHODS:
            # Check exact match
            if path in self.CRITICAL_PATTERNS:
                return True
            
            # Check partial match
            for pattern in self.CRITICAL_PATTERNS_PARTIAL:
                if pattern in path.lower():
                    return True
        
        # Log failed requests (4xx, 5xx) on any authenticated endpoint
        if response.status_code >= 400 and request.user.is_authenticated:
            return True
        
        return False
    
    def _extract_audit_info(self, request, response, response_time_ms):
        """Extract relevant information for audit logging."""
        path = request.path
        
        # Get predefined audit info or create default
        audit_config = self.CRITICAL_PATTERNS.get(path, {})
        
        # If not in exact patterns, try to infer from path
        if not audit_config:
            audit_config = self._infer_audit_config(path, request.method)
        
        # Extract user
        user = request.user if request.user.is_authenticated else None
        
        # Extract IP address
        ip_address = self._get_client_ip(request)
        
        # Extract user agent
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        # Extract session ID
        session_id = request.session.session_key if hasattr(request, 'session') else ''
        
        # Determine success
        success = 200 <= response.status_code < 400
        
        # Extract error message if failed
        error_message = ''
        if not success:
            try:
                if hasattr(response, 'data'):
                    error_message = str(response.data)[:500]
            except:
                error_message = f"HTTP {response.status_code}"
        
        # Build metadata
        metadata = {
            'request_body_size': len(request.body) if hasattr(request, 'body') else 0,
            'response_size': len(response.content) if hasattr(response, 'content') else 0,
        }
        
        # Add request data for critical transactions (sanitized)
        if audit_config.get('category') in ['transaction', 'business_critical']:
            try:
                if request.method in ['POST', 'PUT', 'PATCH']:
                    # Sanitize sensitive data
                    body_data = json.loads(request.body) if request.body else {}
                    sanitized_data = self._sanitize_data(body_data)
                    metadata['request_data'] = sanitized_data
            except:
                pass
        
        return {
            'user': user,
            'action': audit_config.get('action', f'{request.method.lower()}_{path.split("/")[-2]}'),
            'category': audit_config.get('category', 'business_critical'),
            'severity': audit_config.get('severity', 'medium'),
            'request_method': request.method,
            'request_path': path[:500],
            'response_status': response.status_code,
            'response_time_ms': response_time_ms,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'session_id': session_id,
            'success': success,
            'error_message': error_message,
            'metadata': metadata,
        }
    
    def _infer_audit_config(self, path, method):
        """Infer audit configuration from path and method."""
        config = {
            'category': 'business_critical',
            'severity': 'medium',
            'action': f'{method.lower()}_request'
        }
        
        # Adjust based on keywords in path
        path_lower = path.lower()
        
        if any(word in path_lower for word in ['payment', 'transaction', 'withdraw', 'deposit']):
            config['category'] = 'transaction'
            config['severity'] = 'critical'
        elif any(word in path_lower for word in ['login', 'logout', 'register']):
            config['category'] = 'authentication'
            config['severity'] = 'medium'
        elif any(word in path_lower for word in ['password', 'security']):
            config['category'] = 'security'
            config['severity'] = 'high'
        elif any(word in path_lower for word in ['approve', 'reject', 'admin']):
            config['category'] = 'authorization'
            config['severity'] = 'high'
        elif any(word in path_lower for word in ['document', 'verify', 'kyc']):
            config['category'] = 'compliance'
            config['severity'] = 'high'
        elif any(word in path_lower for word in ['delete', 'remove']):
            config['severity'] = 'high'
        
        return config
    
    def _get_client_ip(self, request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _sanitize_data(self, data):
        """Remove sensitive fields from data before logging."""
        sensitive_fields = [
            'password', 'token', 'secret', 'api_key', 'private_key',
            'card_number', 'cvv', 'pin', 'ssn', 'account_number'
        ]
        
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in sensitive_fields):
                    sanitized[key] = '***REDACTED***'
                elif isinstance(value, dict):
                    sanitized[key] = self._sanitize_data(value)
                elif isinstance(value, list):
                    sanitized[key] = [self._sanitize_data(item) if isinstance(item, dict) else item for item in value]
                else:
                    sanitized[key] = value
            return sanitized
        return data
    
    def _log_activity(self, audit_info):
        """
        Create audit log entry.
        This runs synchronously but could be made async with Celery.
        """
        try:
            UserActivityLog.objects.create(**audit_info)
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            # Don't raise - logging failures shouldn't break the app
