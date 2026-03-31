import logging
import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from apps.users.models import User

from .context import AuthContext
from .errors import AuthenticationError

logger = logging.getLogger(__name__)


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
        )
    except jwt.PyJWTError as exc:  # pragma: no cover
        raise AuthenticationError("Token is invalid or expired.") from exc


def _access_expiry():
    return timezone.now() + timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES)


def _refresh_expiry():
    return timezone.now() + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)


def _build_access_token(user: User) -> tuple[str, timezone.datetime]:
    issued_at = timezone.now()
    expires_at = _access_expiry()
    payload = {
        "iss": settings.JWT_ISSUER,
        "jti": uuid.uuid4().hex,
        "sub": str(user.id),
        "ver": user.token_version,
        "type": "access",
        "email": user.email,
        "exp": expires_at,
        "iat": issued_at,
    }
    return _encode(payload), expires_at


def _build_refresh_token(user: User) -> tuple[str, timezone.datetime]:
    expires_at = _refresh_expiry()
    payload = {
        "iss": settings.JWT_ISSUER,
        "jti": uuid.uuid4().hex,
        "sub": str(user.id),
        "ver": user.token_version,
        "type": "refresh",
        "email": user.email,
        "exp": expires_at,
        "iat": timezone.now(),
    }
    return _encode(payload), expires_at


def issue_token_pair(*, user: User, auth_context: AuthContext) -> dict:
    access_token, access_expires_at = _build_access_token(user)
    refresh_token, refresh_expires_at = _build_refresh_token(user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_at": access_expires_at,
        "refresh_expires_at": refresh_expires_at,
    }


def _get_user_from_payload(payload: dict) -> User:
    try:
        user = User.objects.get(id=payload["sub"], is_active=True)
    except User.DoesNotExist as exc:
        raise AuthenticationError("User not found.") from exc

    if payload.get("ver") != user.token_version:
        raise AuthenticationError("Token version is stale.")

    return user


def authenticate_access_token(token: str) -> User:
    payload = _decode(token)
    if payload.get("type") != "access":
        raise AuthenticationError("Unexpected token type.")

    return _get_user_from_payload(payload)


def rotate_refresh_token(*, raw_token: str, auth_context: AuthContext) -> tuple[User, dict]:
    payload = _decode(raw_token)
    if payload.get("type") != "refresh":
        raise AuthenticationError("Unexpected token type.")

    user = _get_user_from_payload(payload)
    logger.info("refresh success email=%s ip=%s", user.email, auth_context.ip_address)
    return user, issue_token_pair(user=user, auth_context=auth_context)


def revoke_refresh_token(raw_token: str) -> None:
    payload = _decode(raw_token)
    if payload.get("type") != "refresh":
        raise AuthenticationError("Unexpected token type.")

    updated = User.objects.filter(id=payload["sub"], token_version=payload.get("ver")).update(
        token_version=F("token_version") + 1
    )
    if not updated:
        raise AuthenticationError("Token is already invalidated.")
    logger.info("logout invalidated user_id=%s", payload["sub"])
