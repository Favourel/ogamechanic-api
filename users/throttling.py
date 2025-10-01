from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    """
    Throttle for unauthenticated users attempting to authenticate.
    """
    rate = '5/minute'  # 7 attempts per minute
    scope = 'auth'


class UserRateThrottle(UserRateThrottle):
    """
    Throttle for authenticated users.
    """
    rate = '20/minute'  # 20 requests per minute
    scope = 'user'
