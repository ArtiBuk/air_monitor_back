from django.core.exceptions import ValidationError
from django.http import HttpResponse
from ninja import Router
from ninja.responses import Status

from ..services.authentication import login_user, register_user
from ..services.context import build_auth_context
from ..services.errors import AuthenticationError
from ..services.tokens import revoke_refresh_token, rotate_refresh_token
from .schemas import AuthSessionSchema, LoginPayload, LogoutPayload, MessageSchema, RefreshPayload, RegisterPayload
from .utils import clear_auth_cookies, resolve_refresh_token, serialize_session, set_auth_cookies

router = Router(tags=["auth"])


@router.post("/register", response={201: AuthSessionSchema, 400: MessageSchema})
def register(request, response: HttpResponse, payload: RegisterPayload):
    """Регистрирует пользователя и выставляет auth-cookie."""
    try:
        user, token_pair = register_user(
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            auth_context=build_auth_context(request),
        )
    except ValidationError as exc:
        return Status(400, {"detail": str(exc)})

    set_auth_cookies(response, token_pair=token_pair)
    return Status(201, serialize_session(user=user, token_pair=token_pair))


@router.post("/login", response={200: AuthSessionSchema, 401: MessageSchema})
def login(request, response: HttpResponse, payload: LoginPayload):
    """Аутентифицирует пользователя и выставляет auth-cookie."""
    try:
        user, token_pair = login_user(
            email=payload.email,
            password=payload.password,
            auth_context=build_auth_context(request),
        )
    except AuthenticationError as exc:
        return Status(401, {"detail": str(exc)})

    set_auth_cookies(response, token_pair=token_pair)
    return Status(200, serialize_session(user=user, token_pair=token_pair))


@router.post("/refresh", response={200: AuthSessionSchema, 401: MessageSchema})
def refresh(request, response: HttpResponse, payload: RefreshPayload):
    """Обновляет refresh-токен и выдает новую сессию."""
    try:
        user, token_pair = rotate_refresh_token(
            raw_token=resolve_refresh_token(request, payload),
            auth_context=build_auth_context(request),
        )
    except AuthenticationError as exc:
        return Status(401, {"detail": str(exc)})

    set_auth_cookies(response, token_pair=token_pair)
    return Status(200, serialize_session(user=user, token_pair=token_pair))


@router.post("/logout", response={200: MessageSchema, 401: MessageSchema})
def logout(request, response: HttpResponse, payload: LogoutPayload):
    """Отзывает refresh-токен и очищает auth-cookie."""
    try:
        revoke_refresh_token(resolve_refresh_token(request, payload))
    except AuthenticationError as exc:
        return Status(401, {"detail": str(exc)})

    clear_auth_cookies(response)
    return Status(200, {"detail": "Logged out."})
