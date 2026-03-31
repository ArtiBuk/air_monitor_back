import pytest

pytestmark = pytest.mark.django_db


def test_me_returns_authenticated_user(authenticated_client, user_payload):
    response = authenticated_client.get("/api/users/me")

    assert response.status_code == 200
    assert response.json()["email"] == user_payload["email"]
