import itertools

from apps.users.models import User

_user_sequence = itertools.count(1)


def build_user_payload(**overrides) -> dict:
    idx = next(_user_sequence)
    payload = {
        "email": f"user{idx}@example.com",
        "password": "pass12345",
        "first_name": "Test",
        "last_name": "User",
    }
    payload.update(overrides)
    return payload


def create_user(**overrides) -> User:
    payload = build_user_payload(**overrides)
    return User.objects.create_user(
        email=payload["email"],
        password=payload["password"],
        first_name=payload["first_name"],
        last_name=payload["last_name"],
    )
