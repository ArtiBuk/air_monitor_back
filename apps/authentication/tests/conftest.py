import json

import pytest

from .factories import build_auth_payload, create_auth_user


@pytest.fixture
def auth_payload():
    return build_auth_payload()


@pytest.fixture
def json_post(client):
    def sender(path: str, payload: dict):
        return client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    return sender


@pytest.fixture
def auth_user_factory(db):
    return create_auth_user
