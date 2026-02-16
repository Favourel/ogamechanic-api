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
    rate = '300/minute'  # 300 requests per minute
    scope = 'user'
