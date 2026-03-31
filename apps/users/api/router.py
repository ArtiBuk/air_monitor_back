from ninja import Router

from apps.authentication.security.jwt import JWTAuth

from .schemas import UserSchema

router = Router(tags=["users"], auth=JWTAuth())


@router.get("/me", response=UserSchema)
def me(request):
    """Возвращает профиль текущего пользователя."""
    return request.auth
