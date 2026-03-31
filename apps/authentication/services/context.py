from dataclasses import dataclass


@dataclass
class AuthContext:
    ip_address: str | None
    user_agent: str


def build_auth_context(request) -> AuthContext:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded_for.split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    return AuthContext(
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent", ""),
    )
