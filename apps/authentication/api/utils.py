from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.authentication.services.errors import AuthenticationError

from .schemas import LogoutPayload, RefreshPayload


def serialize_session(*, user, token_pair: dict) -> dict:
    """Собирает данные сессии для ответа API."""
    return {
        "access_expires_at": token_pair["access_expires_at"],
        "refresh_expires_at": token_pair["refresh_expires_at"],
        "user": user,
    }


def _cookie_kwargs(*, path: str) -> dict:
    return {
        "httponly": settings.JWT_COOKIE_HTTPONLY,
        "secure": settings.JWT_COOKIE_SECURE,
        "samesite": settings.JWT_COOKIE_SAMESITE,
        "domain": settings.JWT_COOKIE_DOMAIN,
        "path": path,
    }


def set_auth_cookies(response: HttpResponse, *, token_pair: dict) -> None:
    """Устанавливает access и refresh JWT в cookie."""
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        token_pair["access_token"],
        expires=token_pair["access_expires_at"],
        **_cookie_kwargs(path=settings.JWT_ACCESS_COOKIE_PATH),
    )
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        token_pair["refresh_token"],
        expires=token_pair["refresh_expires_at"],
        **_cookie_kwargs(path=settings.JWT_REFRESH_COOKIE_PATH),
    )


def clear_auth_cookies(response: HttpResponse) -> None:
    """Удаляет access и refresh JWT из cookie."""
    response.delete_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        path=settings.JWT_ACCESS_COOKIE_PATH,
        domain=settings.JWT_COOKIE_DOMAIN,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        domain=settings.JWT_COOKIE_DOMAIN,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )


def resolve_refresh_token(request: HttpRequest, payload: RefreshPayload | LogoutPayload) -> str:
    """Достает refresh-токен из payload или cookie."""
    token = payload.refresh_token or request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
    if not token:
        raise AuthenticationError("Refresh token is required.")
    return token
