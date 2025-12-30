import os
from pathlib import Path
from datetime import timedelta
from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

LOG_DIR = os.path.join('logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_yasg',
    'corsheaders',
    'django_filters',
    "django_celery_beat",

    # Local apps
    'users.apps.UsersConfig',
    'adminpanel',
    'products',
    'rides',
    'communications',
    'couriers',
    'mechanics',
    'rentals',
]

MIDDLEWARE = [
    'ogamechanic.modules.middleware.NgrokBypassMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'ogamechanic.modules.middleware.ResponseTimeMiddleware',
    'ogamechanic.modules.middleware.DatabaseQueryLoggingMiddleware',
    'ogamechanic.modules.middleware.RequestLoggingMiddleware'
]

AUTHENTICATION_BACKENDS = [
    'users.authentication.LockoutBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'ogamechanic.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ogamechanic.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', # noqa
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', # noqa
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', # noqa
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', # noqa
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Ensure the static directory exists
os.makedirs(STATIC_ROOT, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'static'), exist_ok=True)

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': [
        # 'users.authentication.CsrfExemptSessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': (
        'rest_framework.pagination.PageNumberPagination'
    ),
    'PAGE_SIZE': 10,
    'DEFAULT_THROTTLE_CLASSES': [
        'users.throttling.AuthRateThrottle',
        'users.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'auth': '10/minute',
        'user': '100/minute',
    },
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    # Disable slash redirects
    'APPEND_SLASH': True,
}
APPEND_SLASH = True
SITE_DOMAIN = 'https://ogamechanic.twopikin.com'

# Swagger settings for drf_yasg
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': (
                'JWT Authorization header using the Bearer scheme. '
                'Example: "Authorization: Bearer {token}"'
            ),
        },
        'ApiKeyAuth': {
            'type': 'apiKey',
            'name': 'X-Api-Key',
            'in': 'header',
            'description': (
                'Custom API Key header: "X-Api-Key: {api_key}"'
            ),
        },
        # 'RequestId': {
        #     'type': 'apiKey',
        #     'name': 'X-Request-ID',
        #     'in': 'header',
        #     'description': (
        #         'Custom X-Request-ID header: "X-Request-ID: {api_key}"'
        #     ),
        # },
    },
    'USE_SESSION_AUTH': True,
    'JSON_EDITOR': True,
    'PERSIST_AUTH': True,
    'VALIDATOR_URL': None,
    'OPERATIONS_SORTER': None,
    'TAGS_SORTER': None,
    'DOC_EXPANSION': 'none',
    'DEFAULT_MODEL_RENDERING': 'model',
    'DEFAULT_INFO': None,
    'SECURITY': [],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
    },
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

# JWT settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=45),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule', # noqa

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',
}

# Add this setting for django.contrib.sites
SITE_ID = 1

# Custom user model
AUTH_USER_MODEL = 'users.User'

# Django Channels Configuration
# ASGI_APPLICATION = 'ogamechanic.asgi.application'

# Channel Layers for WebSocket support
# CHANNEL_LAYERS = {
#     'default': {
#         'BACKEND': 'channels_redis.core.RedisChannelLayer',
#         'CONFIG': {
#             "hosts": [('127.0.0.1', 6379)],
#         },
#     },
# }

# Database Configuration
# Choose your database backend based on environment

# SQLite with SpatiaLite (Development)
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.contrib.gis.db.backends.spatialite',
#         'NAME': BASE_DIR / 'db.sqlite3',
#         'OPTIONS': {
#             'timeout': 20,
#         },
#     }
# }

# # PostgreSQL with PostGIS (Production)
# # Uncomment and configure for production
# # DATABASES = {
# #     'default': {
# #         'ENGINE': 'django.contrib.gis.db.backends.postgis',
# #         'NAME': 'ogamechanic_db',
# #         'USER': 'ogamechanic_user',
# #         'PASSWORD': 'your_secure_password',
# #         'HOST': 'localhost',
# #         'PORT': '5432',
# #         'OPTIONS': {
# #             'sslmode': 'require',
# #         },
# #     }
# # }

# # GeoDjango Configuration
# SPATIALITE_LIBRARY_PATH = 'mod_spatialite'

# print(DATABASES)

# File upload settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# File Upload Settings
FILE_UPLOAD_PERMISSIONS = 0o644

# Limit the number of data upload fields to prevent DoS via massive POST/GET field counts. # noqa
# See: https://docs.djangoproject.com/en/stable/ref/settings/#data-upload-max-number-fields # noqa
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000  # Default is 1000; adjust as needed for your forms/APIs # noqa

DATA_UPLOAD_MAX_NUMBER_FILES = 100  # Adjust as per your application's needs; default is 100 # noqa

ADMINS = [
    # ("IT Support", "it-support@example.com"),
    ("Favour", "favourelodimuor16@gmail.com"),
]

CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-tokens': {
        'task': 'cleanup_expired_tokens',
        'schedule': crontab(hour=0, minute=0),  # Run daily at midnight
    },

    'unlock-expired-accounts': {
        'task': 'users.tasks.unlock_expired_accounts',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    # Add more periodic tasks here

    'delete-expired-pending-rides': {
        'task': 'rides.tasks.delete_expired_pending_rides',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
}

