from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from users.models import UserActivityLog
from rest_framework.authentication import SessionAuthentication


User = get_user_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # override to skip CSRF check


class LockoutBackend(ModelBackend):
    def authenticate(self, request, username=None, email=None, phone_number=None, password=None, **kwargs): # noqa
        # Use email, phone_number, or username for authentication
        auth_identifier = email or phone_number or username

        if not auth_identifier or not password:
            return None

        try:
            # Try to find user by email or phone number
            user = None
            if '@' in auth_identifier:
                # Looks like an email
                user = User.objects.get(email=auth_identifier)
            else:
                # Try phone number
                user = User.objects.get(phone_number=auth_identifier)

            if user and user.check_password(password):
                # Check if account is locked
                if user.is_locked():
                    return None

                # Login successful - reset failed attempts
                if user.failed_login_attempts > 0:
                    user.failed_login_attempts = 0
                    user.locked_until = None
                    user.save()

                return user
        except User.DoesNotExist:
            pass

        # Login failed - increment failed attempts
        try:
            user_obj = None
            if '@' in auth_identifier:
                # Looks like an email
                user_obj = User.objects.get(email=auth_identifier)
            else:
                # Try phone number
                user_obj = User.objects.get(phone_number=auth_identifier)

            if user_obj:
                user_obj.failed_login_attempts += 1
                user_obj.last_failed_login = timezone.now()

                # Lock account after 3 failed attempts
                if user_obj.failed_login_attempts >= 3:
                    user_obj.locked_until = timezone.now() + timedelta(hours=1)

                user_obj.save()

                # Log failed attempt
                ip_address = None
                if request and hasattr(request, 'META'):
                    ip_address = request.META.get('REMOTE_ADDR')

                UserActivityLog.objects.create(
                    user=user_obj,
                    action='login_failed',
                    description=(
                        f"Failed login attempt "
                        f"(identifier: {auth_identifier}, "
                        f"attempts: {user_obj.failed_login_attempts})"
                    ),
                    ip_address=ip_address,
                    object_type='User',
                    object_id=user_obj.id if user_obj else None,
                    severity='medium'
                )
        except User.DoesNotExist:
            pass

        return None
