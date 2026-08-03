"""WebSocket authentication.

The REST API authenticates with JWT bearer tokens, but browsers cannot set
custom headers on a WebSocket handshake. Channels' stock AuthMiddlewareStack
only understands session cookies, which a token-based frontend never sends, so
this middleware additionally accepts an access token from the query string:

    wss://<host>/ws/chat/alice__bob/?token=<access_token>

Session authentication still works, so the Django admin and the browsable API
are unaffected.
"""

from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


@database_sync_to_async
def get_user_from_token(raw_token):
    try:
        token = AccessToken(raw_token)
        return User.objects.get(id=token['user_id'])
    except (InvalidToken, TokenError, KeyError, User.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Only consult the token when the wrapped session middleware has not
        # already resolved a user.
        if not scope.get('user') or scope['user'].is_anonymous:
            query = parse_qs(scope.get('query_string', b'').decode())
            token = (query.get('token') or [None])[0]
            if token:
                scope['user'] = await get_user_from_token(token)

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
