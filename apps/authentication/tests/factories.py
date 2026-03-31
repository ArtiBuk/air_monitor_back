import itertools

from apps.users.models import User

_auth_sequence = itertools.count(1)


def build_auth_payload(**overrides) -> dict:
    idx = next(_auth_sequence)
    payload = {
        "email": f"user{idx}@example.com",
        "password": "pass12345",
        "first_name": "Air",
        "last_name": "Monitor",
    }
    payload.update(overrides)
    return payload


def create_auth_user(**overrides) -> User:
    payload = build_auth_payload(**overrides)
    return User.objects.create_user(
        email=payload["email"],
        password=payload["password"],
        first_name=payload["first_name"],
        last_name=payload["last_name"],
    )
