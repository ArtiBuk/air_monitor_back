import json

import pytest

from .factories import build_user_payload, create_user


@pytest.fixture
def user_payload():
    return build_user_payload()


@pytest.fixture
def user_factory(db):
    return create_user


@pytest.fixture
def authenticated_client(client, user_payload):
    response = client.post(
        "/api/auth/register",
        data=json.dumps(user_payload),
        content_type="application/json",
    )
    assert response.status_code == 201
    return client
