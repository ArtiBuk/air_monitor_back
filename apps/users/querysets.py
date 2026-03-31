from django.db import models


class UserQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def by_email(self, email: str):
        return self.filter(email__iexact=email)
