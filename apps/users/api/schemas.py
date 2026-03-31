from ninja import ModelSchema

from apps.users.models import User


class UserSchema(ModelSchema):
    full_name: str

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active", "is_staff"]
