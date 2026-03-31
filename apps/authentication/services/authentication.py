import logging

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from apps.users.models import User
from apps.users.services import create_user

from .context import AuthContext
from .errors import AuthenticationError
from .tokens import issue_token_pair

logger = logging.getLogger(__name__)


def register_user(*, email: str, password: str, first_name: str = "", last_name: str = "", auth_context: AuthContext):
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError("User with this email already exists.")

    user = create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    logger.info("registered user email=%s ip=%s", user.email, auth_context.ip_address)
    return user, issue_token_pair(user=user, auth_context=auth_context)


def login_user(*, email: str, password: str, auth_context: AuthContext):
    user = authenticate(username=email, password=password)
    if user is None:
        logger.warning("login failed email=%s ip=%s", email, auth_context.ip_address)
        raise AuthenticationError("Invalid credentials.")

    logger.info("login success email=%s ip=%s", user.email, auth_context.ip_address)
    return user, issue_token_pair(user=user, auth_context=auth_context)
