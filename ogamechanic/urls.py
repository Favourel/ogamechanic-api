"""
URL configuration for ogamechanic project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework.permissions import BasePermission, AllowAny
from django.conf.urls.static import static
import os
from dotenv import load_dotenv
load_dotenv()
# from ogamechanic.health_views import (
#     health_check, readiness_check)


class DocsAccessPermission(BasePermission):
    """
    Allow access to staff, superusers, and users with 'admin' or 'developer' role. # noqa
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        # Check for role name 'admin' or 'developer'
        if user.role and user.role.name in [
            'admin', 'developer'
        ]:
            return True
        return False


if os.getenv('env', 'dev') == 'prod':
    # Determine the URL and schemes based on environment
    if 'api.ogamechanic.org' in settings.ALLOWED_HOSTS: # noqa
        # Production configuration
        API_URL = 'https://api.ogamechanic.org'
        API_SCHEMES = ['https']
    else:
        # Development configuration
        API_URL = 'http://127.0.0.1:2340'
        API_SCHEMES = ['http']


# API_URL = 'http://127.0.0.1:2340'
# API_SCHEMES = ['http']

if 'untrustingly-vicennial-herlinda.ngrok-free.dev' in settings.ALLOWED_HOSTS: # noqa
    # Production configuration
    API_URL = 'https://untrustingly-vicennial-herlinda.ngrok-free.dev'
    API_SCHEMES = ['https']
else:
    # Development configuration
    API_URL = 'http://127.0.0.1:2340'
    API_SCHEMES = ['http']

schema_view = get_schema_view(
    openapi.Info(
        title="OGAMECHANIC API",
        default_version='v1',
        description=(
            "API documentation for OGAMECHANIC"
        ),
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=settings.DEBUG,
    permission_classes=(AllowAny,) if settings.DEBUG else (DocsAccessPermission,), # noqa
    url=API_URL,
)

urlpatterns = [
    # Health check endpoints
    # path('api/health/', health_check, name='health-check'),
    # path('api/readiness/', readiness_check, name='readiness-check'),

    path('admin/management/', admin.site.urls),
    path('api/v1/users/', include('users.urls')),
    path('api/v1/admin/', include('adminpanel.urls', namespace='adminpanel')), # noqa
    path('api/v1/products/', include('products.urls', namespace='products')),
    # path('api/v1/rides/', include('rides.urls', namespace='rides')),
    # path('api/v1/communications/',
    #      include('communications.urls', namespace='communications')),
    # path('api/v1/couriers/',
    #      include('couriers.urls', namespace='couriers')),
    path('api/v1/mechanics/',
         include('mechanics.urls', namespace='mechanics')),
    path('api/v1/rentals/',
         include('rentals.urls', namespace='rentals')),
    # path('api/v1/analytics/',
    #      include('analytics.urls', namespace='analytics')),

    # Swagger documentation URLs
    re_path(
        r'^swagger(?P<format>\.json|\.yaml)$',
        schema_view.without_ui(cache_timeout=0),
        name='schema-json'
    ),
    path(
        'swagger/',
        schema_view.with_ui('swagger', cache_timeout=0),
        name='schema-swagger-ui'
    ),
    path(
        'redoc/',
        schema_view.with_ui('redoc', cache_timeout=0),
        name='schema-redoc'
    ),
]

if settings.DEBUG:
    urlpatterns += [
        path('__debug__/', include('debug_toolbar.urls')),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # noqa
    urlpatterns += static(
        settings.STATIC_URL, document_root=settings.STATIC_ROOT
    )  # noqa
