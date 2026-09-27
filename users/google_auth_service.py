import logging
import requests
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework.exceptions import PermissionDenied, ValidationError

from users.models import Role, User

logger = logging.getLogger(__name__)

VALID_ROLES = [
    Role.PRIMARY_USER,
    Role.DRIVER,
    Role.RIDER,
    Role.MECHANIC,
    Role.MERCHANT,
    Role.VEHICLE_RENTAL,
]


def verify_google_token(token_str: str) -> dict:
    """
    Verifies a Google token (ID token or OAuth2 Access token) and extracts user profile.

    Supports:
    1. Google ID Token (JWT) verified locally/cryptographically with Google's public keys.
    2. Google OAuth2 Access Token verified via Google UserInfo API endpoint as fallback.

    Returns:
        dict: Normalized user profile containing:
            - sub: Google unique user ID
            - email: User's verified email address (lowercase)
            - email_verified: Boolean
            - first_name: Given name
            - last_name: Family name
            - picture: Avatar/picture URL
            - raw: Original claims/payload
    Raises:
        ValidationError: If token is invalid, expired, or missing required email.
    """
    if not token_str or not isinstance(token_str, str):
        raise ValidationError("Token must be a non-empty string.")

    token_str = token_str.strip()
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", None)

    # 1. Primary: Verify as Google ID token (JWT)
    try:
        request = google_requests.Request()
        idinfo = id_token.verify_oauth2_token(token_str, request, audience=client_id)

        email = idinfo.get("email")
        if not email:
            raise ValidationError("Google token does not contain an email address.")

        name = idinfo.get("name", "")
        given_name = idinfo.get("given_name") or (
            name.split()[0] if name else ""
        )
        family_name = idinfo.get("family_name") or (
            " ".join(name.split()[1:]) if len(name.split()) > 1 else ""
        )

        return {
            "sub": str(idinfo.get("sub", "")),
            "email": email.lower().strip(),
            "email_verified": bool(idinfo.get("email_verified", True)),
            "first_name": given_name,
            "last_name": family_name,
            "picture": idinfo.get("picture", ""),
            "raw": idinfo,
        }
    except ValidationError:
        raise
    except Exception as id_err:
        logger.debug(
            f"ID token verification failed ({id_err}), falling back to userinfo endpoint"
        )

    # 2. Fallback: Verify as OAuth2 Access Token via Google userinfo endpoint
    try:
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        resp = requests.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {token_str}"},
            timeout=10,
        )
        if resp.status_code == 200:
            userinfo = resp.json()
            email = userinfo.get("email")
            if not email:
                raise ValidationError(
                    "Google user info does not contain an email address."
                )

            name = userinfo.get("name", "")
            given_name = userinfo.get("given_name") or (
                name.split()[0] if name else ""
            )
            family_name = userinfo.get("family_name") or (
                " ".join(name.split()[1:]) if len(name.split()) > 1 else ""
            )

            return {
                "sub": str(userinfo.get("sub", "")),
                "email": email.lower().strip(),
                "email_verified": bool(userinfo.get("email_verified", True)),
                "first_name": given_name,
                "last_name": family_name,
                "picture": userinfo.get("picture", ""),
                "raw": userinfo,
            }
        else:
            logger.debug(
                f"Google userinfo request failed with status {resp.status_code}: {resp.text}"
            )
    except ValidationError:
        raise
    except Exception as access_err:
        logger.debug(f"Userinfo endpoint check failed: {access_err}")

    raise ValidationError("Invalid or expired Google authentication token.")


def exchange_code_for_tokens(code: str, redirect_uri: str = None) -> dict:
    """
    Exchanges an OAuth2 authorization code for Google tokens.
    """
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", None)
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", None)

    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
    }
    if redirect_uri:
        data["redirect_uri"] = redirect_uri

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data=data,
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()

    logger.error(f"Failed to exchange Google auth code: {resp.text}")
    raise ValidationError("Failed to exchange Google authorization code.")


def _create_role_profile(user: User, role_name: str):
    """
    Instantiates the initial role-specific profile when a new user signs up.
    """
    try:
        if role_name == "merchant":
            from users.models import MerchantProfile

            MerchantProfile.objects.get_or_create(user=user)
        elif role_name == "mechanic":
            from users.models import MechanicProfile

            MechanicProfile.objects.get_or_create(user=user)
        elif role_name == "driver":
            from users.models import DriverProfile

            DriverProfile.objects.get_or_create(user=user)
        elif role_name == "rider":
            from users.models import RiderProfile

            RiderProfile.objects.get_or_create(user=user)
        elif role_name == "vehicle_rental":
            from users.models import VehicleRentalProfile

            VehicleRentalProfile.objects.get_or_create(user=user)
    except Exception as e:
        logger.error(f"Failed to create profile for role '{role_name}': {e}")


def _sync_allauth_social_account(user: User, google_info: dict):
    """
    Synchronizes the authenticated Google user with django-allauth's SocialAccount table.
    """
    try:
        from allauth.socialaccount.models import SocialAccount

        uid = str(google_info.get("sub") or google_info.get("email"))
        SocialAccount.objects.get_or_create(
            user=user,
            provider="google",
            uid=uid,
            defaults={"extra_data": google_info.get("raw", {})},
        )
    except Exception as e:
        logger.debug(f"Could not link allauth SocialAccount: {e}")


def authenticate_or_register_google_user(
    google_info: dict,
    role_name: str = "primary_user",
    phone_number: str = None,
) -> tuple[User, bool]:
    """
    Authenticates an existing user or creates a new user via Google.

    Args:
        google_info: Dict containing email, first_name, last_name, sub, etc.
        role_name: Target role (defaults to 'primary_user')
        phone_number: Optional phone number

    Returns:
        tuple[User, bool]: (user, is_new_user)
    """
    if not role_name:
        role_name = "primary_user"
    role_name = role_name.lower().strip()

    if role_name not in VALID_ROLES:
        raise ValidationError(f"Role must be one of: {', '.join(VALID_ROLES)}")

    email = google_info["email"]
    user = User.objects.filter(email__iexact=email).first()

    if user:
        is_new_user = False
        if not user.is_active:
            raise PermissionDenied("User account is disabled.")

        needs_save = False

        # Google email is verified
        if not user.is_verified:
            user.is_verified = True
            needs_save = True

        # Ensure user has an active_role
        if not user.active_role:
            role_obj = user.roles.first()
            if not role_obj:
                role_obj, _ = Role.objects.get_or_create(name=role_name)
                user.roles.add(role_obj)
            user.active_role = role_obj
            needs_save = True

        # Backfill names if blank
        if not user.first_name and google_info.get("first_name"):
            user.first_name = google_info["first_name"][:30]
            needs_save = True
        if not user.last_name and google_info.get("last_name"):
            user.last_name = google_info["last_name"][:30]
            needs_save = True

        # Reset failed login attempts on successful social login
        if hasattr(user, "failed_login_attempts") and user.failed_login_attempts > 0:
            user.failed_login_attempts = 0
            user.locked_until = None
            needs_save = True

        if needs_save:
            user.save()
    else:
        is_new_user = True
        role_obj, _ = Role.objects.get_or_create(name=role_name)

        formatted_phone = ""
        if phone_number:
            try:
                from ogamechanic.modules.utils import format_phone_number

                formatted_phone = format_phone_number(phone_number)
            except Exception:
                formatted_phone = phone_number

        user = User.objects.create_user(
            email=email,
            password=None,
            first_name=google_info.get("first_name", "")[:30],
            last_name=google_info.get("last_name", "")[:30],
            phone_number=formatted_phone,
            is_active=True,
            is_verified=True,  # Verified by Google
        )
        user.set_unusable_password()
        user.roles.add(role_obj)
        user.active_role = role_obj
        user.save()

        # Create role profile if applicable
        _create_role_profile(user, role_name)

    # Link allauth SocialAccount if available
    _sync_allauth_social_account(user, google_info)

    return user, is_new_user
