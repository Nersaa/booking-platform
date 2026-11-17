from django.db import transaction

from apps.users.models import User


@transaction.atomic
def user_register(*, email: str, password: str, first_name: str, last_name: str = "") -> User:
    return User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name
    )


def user_become_host(*, user: User) -> User:
    if not user.is_host:
        user.is_host = True
        user.save(update_fields=["is_host"])
    return user


def user_change_password(*, user: User, new_password: str) -> User:
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return user
