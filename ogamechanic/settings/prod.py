from .base import * # noqa
import ssl

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY') # noqa

DEBUG = False

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',') # noqa

X_API_KEY = os.environ.get('X_API_KEY') # noqa

# Database with PostGIS for spatial support
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ.get('DB_NAME'), # noqa
        'USER': os.environ.get('DB_USER'), # noqa
        'PASSWORD': os.environ.get('DB_PASSWORD'), # noqa
        'HOST': os.environ.get('DB_HOST'), # noqa
        'PORT': os.environ.get('DB_PORT', '5432'), # noqa
        # 'OPTIONS': {
        #     'sslmode': 'require',
        # },
    }
}

# Redis settings
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost') # noqa
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379)) # noqa
REDIS_DB = int(os.environ.get('REDIS_DB', 0)) # noqa

# Cache settings
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'RETRY_ON_TIMEOUT': True,
            'MAX_CONNECTIONS': 1000,
            'CONNECTION_POOL_KWARGS': {'max_connections': 100},
        }
    }
}

# Cache timeouts
CACHE_TIMEOUT_SHORT = os.environ.get('CACHE_TIMEOUT_SHORT') # noqa
CACHE_TIMEOUT_MEDIUM = os.environ.get('CACHE_TIMEOUT_MEDIUM') # noqa
CACHE_TIMEOUT_LONG = os.environ.get('CACHE_TIMEOUT_LONG') # noqa
CACHE_TIMEOUT_VERY_LONG = os.environ.get('CACHE_TIMEOUT_VERY_LONG') # noqa

# Use Redis for session storage
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Celery Configuration Options
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

CELERY_BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/6'
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}/6'
CELERY_ACCEPT_CONTENT = ['application/json']

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# CORS settings
CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS').split(',') # noqa
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-api-key',
    'cache-control',
    'pragma',
    "ipAddress", "browser", "os", "device"
]
# Allow common HTTP methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
# CORS response headers (override/extend base settings if needed)
CORS_EXPOSE_HEADERS = [
    'content-type',
    'x-csrf-token',
    'x-total-count',
    'x-page-count',
    'x-page-size',
]

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': ('[{asctime}] {levelname} {module} '
                       '{thread:d} - {message}'),
            'style': '{',
            'datefmt': '%d-%m-%Y %H:%M:%S'
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'ogamechanic.log'), # noqa
            'when': 'midnight',
            'interval': 1,  # daily
            'backupCount': 7,  # Keep logs for 7 days
            'formatter': 'verbose',
        }
    },
    'root': {
        'handlers': ['file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.server': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Email settings
EMAIL_BACKEND = 'ogamechanic.email_config.CustomEmailBackend'

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com') # noqa
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587)) # noqa
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER') # noqa
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD') # noqa
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER) # noqa

EMAIL_SSL_CONTEXT = ssl._create_unverified_context()

# Frontend URL for password reset
FRONTEND_URL = os.environ.get('FRONTEND_URL') # noqa

# Password reset timeout (in seconds)
PASSWORD_RESET_TIMEOUT = 3600  # 1 hour

# For Ride
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY') # noqa
FARE_CONFIG = {
    "BASE_FARE": os.environ.get('BASE_FARE'), # noqa
    "PER_KM_RATE": os.environ.get('PER_KM_RATE'), # noqa
    "PER_MIN_RATE": os.environ.get('PER_MIN_RATE'), # noqa
}

FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH") # noqa
FIREBASE_INITIALIZED = False

# Payment integration
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '') # noqa
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', '') # noqa
PAYSTACK_API_URL = 'https://api.paystack.co'
PAYSTACK_CALLBACK_URL = os.getenv('PAYSTACK_CALLBACK_URL', '') # noqa

# =============================================================================
# RENDER.COM SPECIFIC CONFIGURATIONS
# =============================================================================

# WhiteNoise configuration for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# =============================================================================
# SECURITY HARDENING SETTINGS
# =============================================================================

# HTTPS/SSL Settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie Security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Content Security Policy
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# X-Frame-Options
X_FRAME_OPTIONS = 'DENY'

# Additional Security Headers
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SECURE_PERMISSIONS_POLICY = {
    'accelerometer': [],
    'ambient-light-sensor': [],
    'autoplay': [],
    'battery': [],
    'camera': [],
    'cross-origin-isolated': [],
    'display-capture': [],
    'document-domain': [],
    'encrypted-media': [],
    'execution-while-not-rendered': [],
    'execution-while-out-of-viewport': [],
    'fullscreen': [],
    'geolocation': [],
    'gyroscope': [],
    'keyboard-map': [],
    'magnetometer': [],
    'microphone': [],
    'midi': [],
    'navigation-override': [],
    'payment': [],
    'picture-in-picture': [],
    'publickey-credentials-get': [],
    'screen-wake-lock': [],
    'sync-xhr': [],
    'usb': [],
    'web-share': [],
    'xr-spatial-tracking': [],
}

# Session Security
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# CSRF Protection
# CSRF_FAILURE_VIEW = 'users.views.csrf_failure'

# Rate Limiting
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'

# Channel Layers for WebSocket support (updated for production)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [f'redis://{REDIS_HOST}:{REDIS_PORT}/1'],
        },
    },
}
