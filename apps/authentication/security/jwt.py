from django.conf import settings
from ninja.security.base import AuthBase

from apps.authentication.services.errors import AuthenticationError
from apps.authentication.services.tokens import authenticate_access_token


class JWTAuth(AuthBase):
    openapi_type = "apiKey"
    openapi_in = "cookie"

    def __init__(self):
        self.openapi_name = settings.JWT_ACCESS_COOKIE_NAME
        super().__init__()

    @staticmethod
    def _get_token_from_header(request):
        auth_value = request.headers.get("Authorization")
        if not auth_value:
            return None

        parts = auth_value.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        return parts[1].strip() or None

    def __call__(self, request):
        token = self._get_token_from_header(request) or request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if not token:
            return None

        try:
            return authenticate_access_token(token)
        except AuthenticationError:
            return None
