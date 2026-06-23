from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Allow login with either the username or the email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None or password is None:
            return None

        try:
            user = UserModel.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except UserModel.DoesNotExist:
            # Run the hasher once to keep timing consistent (avoids user enumeration).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Same email on multiple accounts — fall back to an exact username match.
            user = UserModel.objects.filter(username__iexact=username).first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
