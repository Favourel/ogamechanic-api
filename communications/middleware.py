"""
JWT Authentication Middleware for Django Channels WebSocket connections.

Usage:
    Connect with: ws://host/ws/path/?token=<JWT_ACCESS_TOKEN>

The middleware extracts the JWT token from the query string, validates it
using simplejwt, and attaches the authenticated user to the scope.
"""

from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_str):
    """Validate JWT token and return the associated user."""
    try:
        token = AccessToken(token_str)
        user_id = token.get("user_id")
        return User.objects.get(id=user_id, is_active=True)
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Middleware that authenticates WebSocket connections via JWT token
    passed as a query parameter: ?token=<access_token>
    """

    async def __call__(self, scope, receive, send):
        # Parse query string for token
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token_list = query_params.get("token", [])

        if token_list:
            scope["user"] = await get_user_from_token(token_list[0])
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
