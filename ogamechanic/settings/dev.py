from .base import * # noqa
import ssl

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY') # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true' # noqa

ALLOWED_HOSTS = ['ogamechanic.twopikin.com', '127.0.0.1'] # noqa
X_API_KEY = os.environ.get('X_API_KEY') # noqa

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# SECURE_HSTS_SECONDS = 31536000  # 1 year
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# WhiteNoise configuration
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Database (Development)
# Note: For full spatial support, use PostgreSQL with PostGIS in production
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3', # noqa
        'OPTIONS': {
            'check_same_thread': False,
        }
    }
}

# CORS settings for development
# Allow specific origins for better security even in development
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:8080",  # Vue.js development server
    "http://127.0.0.1:8080",
    "http://localhost:4200",  # Angular development server
    "http://127.0.0.1:4200",
    "http://localhost:5173",  # Vite development server
    "https://localhost:5173",  # Vite development server
    "http://127.0.0.1:5173",
    "https://*.ngrok-free.dev",  # ngrok tunnel,
    "https://ogamechanic.twopikin.com"
]

# Allow localhost with any port for development flexibility
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost:\d+$",
    r"^http://127\.0\.0\.1:\d+$",
    r"^https://.*\.ngrok-free\.app$",  # Allow any ngrok tunnel
]

# For development, you can temporarily enable this if needed
# CORS_ALLOW_ALL_ORIGINS = True  # Only use this if absolutely necessary

CORS_ALLOW_CREDENTIALS = True

# CSRF trusted origins for development (to allow ngrok and local testing)
CSRF_TRUSTED_ORIGINS = [
    f"http://{host}" for host in ALLOWED_HOSTS if not host.startswith("http")
] + [
    f"https://{host}" for host in ALLOWED_HOSTS if not host.startswith("http")
]

# Email settings for development
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# include allowed headers
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
    "ngrok-skip-browser-warning",
]

# Email settings for development
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Debug toolbar settings
INSTALLED_APPS += ['debug_toolbar'] # noqa
MIDDLEWARE += [ # noqa
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

INTERNAL_IPS = ['127.0.0.1']

# Debug Toolbar Configuration
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: True,
    'INTERCEPT_REDIRECTS': False,
    'IS_RUNNING_TESTS': False,
}

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Celery Configuration Options
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

CELERY_BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/5'
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}/5'
CELERY_ACCEPT_CONTENT = ['application/json']

# CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# CELERY_BROKER_CONNECTION_MAX_RETRIES = 5

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

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

# Cache settings
# CACHES = {
#     'default': {
#         'BACKEND': 'django_redis.cache.RedisCache',
#         'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#             'SOCKET_CONNECT_TIMEOUT': 5,
#             'SOCKET_TIMEOUT': 5,
#             'RETRY_ON_TIMEOUT': True,
#             'MAX_CONNECTIONS': 1000,
#             'CONNECTION_POOL_KWARGS': {'max_connections': 100},
#         }
#     }
# }

# # Cache timeouts
# CACHE_TIMEOUT_SHORT = os.environ.get('CACHE_TIMEOUT_SHORT') # noqa
# CACHE_TIMEOUT_MEDIUM = os.environ.get('CACHE_TIMEOUT_MEDIUM') # noqa
# CACHE_TIMEOUT_LONG = os.environ.get('CACHE_TIMEOUT_LONG') # noqa
# CACHE_TIMEOUT_VERY_LONG = os.environ.get('CACHE_TIMEOUT_VERY_LONG') # noqa

# Use Redis for session storage
# SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
# SESSION_CACHE_ALIAS = 'default'

# Email Validation API Keys
DISPOSABLE_EMAIL_API_KEY = 'your_key_here'  # For disposable-email-detector.com
EMAIL_VALIDATOR_API_KEY = 'your_key_here'   # For email-validator.net
ABSTRACT_API_KEY = '4cbeb26b4cf74042aea95af2bd399f5e'  # For abstractapi.com

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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "file": {
            "class": "logging.FileHandler",
            "filename": "debug.log",
        },
    },
    "loggers": {
        "drf_yasg": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}