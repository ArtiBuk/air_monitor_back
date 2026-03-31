import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db


def test_register_sets_http_only_auth_cookies(json_post, auth_payload):
    response = json_post("/api/auth/register", auth_payload)

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == auth_payload["email"]
    assert "access_token" not in data
    assert "refresh_token" not in data

    access_cookie = response.cookies[settings.JWT_ACCESS_COOKIE_NAME]
    refresh_cookie = response.cookies[settings.JWT_REFRESH_COOKIE_NAME]
    assert access_cookie.value
    assert refresh_cookie.value
    assert access_cookie["httponly"]
    assert refresh_cookie["httponly"]


def test_login_sets_cookie_session(json_post, auth_user_factory):
    user = auth_user_factory(email="auth@example.com", password="pass12345")

    response = json_post(
        "/api/auth/login",
        {
            "email": user.email,
            "password": "pass12345",
        },
    )

    assert response.status_code == 200
    assert response.cookies[settings.JWT_ACCESS_COOKIE_NAME].value
    assert response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value


def test_refresh_uses_refresh_cookie_when_body_is_empty(json_post, auth_payload):
    register_response = json_post("/api/auth/register", auth_payload)
    old_refresh_token = register_response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value

    response = json_post("/api/auth/refresh", {})

    assert response.status_code == 200
    assert response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value != old_refresh_token


def test_logout_revokes_session_and_clears_cookies(client, json_post, auth_payload):
    json_post("/api/auth/register", auth_payload)

    response = json_post("/api/auth/logout", {})

    assert response.status_code == 200
    assert response.cookies[settings.JWT_ACCESS_COOKIE_NAME].value == ""
    assert response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value == ""

    me_response = client.get("/api/users/me")
    assert me_response.status_code == 401
