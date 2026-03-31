from datetime import datetime

from ninja import Schema

from apps.users.api.schemas import UserSchema


class RegisterPayload(Schema):
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""


class LoginPayload(Schema):
    email: str
    password: str


class RefreshPayload(Schema):
    refresh_token: str | None = None


class LogoutPayload(Schema):
    refresh_token: str | None = None


class AuthSessionSchema(Schema):
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: UserSchema


class MessageSchema(Schema):
    detail: str
