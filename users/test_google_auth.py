from unittest.mock import MagicMock, patch
from django.conf import settings
from django.test import TestCase, override_settings

from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from users.google_auth_service import (
    authenticate_or_register_google_user,
    verify_google_token,
)
from users.models import MechanicProfile, Role, User, UserActivityLog

TEST_MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    WHITENOISE_MANIFEST_STRICT=False,
    MIDDLEWARE=TEST_MIDDLEWARE,
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    },
)
class GoogleAuthTests(TestCase):


    """
    Test suite for Google Sign-Up and Login functionality.
    """

    def setUp(self):
        self.client = APIClient()
        self.google_url = reverse("users:google_login")
        self.google_auth_url = reverse("users:google_auth")

        # Ensure standard roles exist in test DB
        self.primary_role, _ = Role.objects.get_or_create(
            name=Role.PRIMARY_USER, defaults={"description": "Primary User"}
        )
        self.mechanic_role, _ = Role.objects.get_or_create(
            name=Role.MECHANIC, defaults={"description": "Mechanic"}
        )
        self.merchant_role, _ = Role.objects.get_or_create(
            name=Role.MERCHANT, defaults={"description": "Merchant"}
        )

        self.mock_google_info = {
            "sub": "google-uid-12345",
            "email": "newuser@example.com",
            "email_verified": True,
            "first_name": "John",
            "last_name": "Doe",
            "picture": "https://lh3.googleusercontent.com/a/photo",
            "raw": {"sub": "google-uid-12345", "email": "newuser@example.com"},
        }

    @patch("users.google_auth_service.verify_google_token")
    def test_google_signup_new_user_success(self, mock_verify):
        """
        Verify that a new user can sign up with a Google ID token.
        """
        mock_verify.return_value = self.mock_google_info

        payload = {"id_token": "valid_mock_google_id_token"}
        response = self.client.post(self.google_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["status"])
        self.assertEqual(response.data["message"], "Google sign up successful")
        self.assertTrue(response.data["data"]["is_new_user"])
        self.assertIn("access", response.data["data"])
        self.assertIn("refresh", response.data["data"])

        # Check DB
        user = User.objects.get(email="newuser@example.com")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertTrue(user.is_verified)
        self.assertEqual(user.active_role.name, Role.PRIMARY_USER)

        # Check activity log
        log_entry = UserActivityLog.objects.filter(
            user=user, action="google_signup"
        ).first()
        self.assertIsNotNone(log_entry)

    @patch("users.google_auth_service.verify_google_token")
    def test_google_signup_with_role_and_profile_creation(self, mock_verify):
        """
        Verify that signing up with a specific role creates the corresponding profile.
        """
        mock_verify.return_value = {
            "sub": "google-uid-mechanic",
            "email": "mechanic.joe@example.com",
            "email_verified": True,
            "first_name": "Joe",
            "last_name": "Fixer",
            "picture": "",
            "raw": {},
        }

        payload = {
            "id_token": "valid_token",
            "role": "mechanic",
            "phone_number": "08012345678",
        }
        response = self.client.post(self.google_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="mechanic.joe@example.com")
        self.assertEqual(user.active_role.name, Role.MECHANIC)
        self.assertTrue(hasattr(user, "mechanic_profile"))
        self.assertTrue(
            MechanicProfile.objects.filter(user=user).exists()
        )

    @patch("users.google_auth_service.verify_google_token")
    def test_google_login_existing_user(self, mock_verify):
        """
        Verify that an existing user is logged in (status 200, is_new_user=False).
        """
        existing_user = User.objects.create_user(
            email="existing@example.com",
            first_name="Jane",
            last_name="Smith",
            is_active=True,
            is_verified=False,
        )
        existing_user.roles.add(self.primary_role)
        existing_user.active_role = self.primary_role
        existing_user.save()

        mock_verify.return_value = {
            "sub": "google-uid-existing",
            "email": "existing@example.com",
            "email_verified": True,
            "first_name": "Jane",
            "last_name": "Smith",
            "picture": "",
            "raw": {},
        }

        payload = {"id_token": "valid_token_for_existing"}
        response = self.client.post(self.google_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])
        self.assertEqual(response.data["message"], "Google login successful")
        self.assertFalse(response.data["data"]["is_new_user"])
        self.assertIn("access", response.data["data"])

        # Email should now be marked verified
        existing_user.refresh_from_db()
        self.assertTrue(existing_user.is_verified)

        # Activity log should record login
        log_entry = UserActivityLog.objects.filter(
            user=existing_user, action="google_login"
        ).first()
        self.assertIsNotNone(log_entry)

    @patch("users.google_auth_service.verify_google_token")
    def test_google_auth_wrapped_payload(self, mock_verify):
        """
        Verify that wrapped request {"requestType": "inbound", "data": {...}} is handled properly.
        """
        mock_verify.return_value = self.mock_google_info

        payload = {
            "requestType": "inbound",
            "data": {
                "id_token": "valid_token",
                "role": "primary_user",
            },
        }
        response = self.client.post(self.google_auth_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["status"])

    @patch("users.google_auth_service.verify_google_token")
    def test_google_auth_with_credential_alias(self, mock_verify):
        """
        Verify that Google One Tap's 'credential' parameter works as an alias for id_token.
        """
        mock_verify.return_value = self.mock_google_info

        payload = {"credential": "one_tap_jwt_token"}
        response = self.client.post(self.google_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["status"])

    @patch("users.google_auth_service.verify_google_token")
    def test_google_auth_with_access_token(self, mock_verify):
        """
        Verify that an OAuth2 access_token is accepted.
        """
        mock_verify.return_value = self.mock_google_info

        payload = {"access_token": "valid_access_token_12345"}
        response = self.client.post(self.google_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["status"])

    @patch("users.google_auth_service.verify_google_token")
    def test_google_auth_invalid_token(self, mock_verify):
        """
        Verify that an invalid Google token returns a 400 Bad Request error.
        """
        mock_verify.side_effect = ValidationError("Invalid or expired Google authentication token.")

        payload = {"id_token": "invalid_fake_token"}
        response = self.client.post(self.google_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["status"])
        self.assertIn("Invalid Google token", response.data["message"])

    def test_google_auth_missing_token_fields(self):
        """
        Verify that omitting token fields returns 400 with validation errors.
        """
        response = self.client.post(self.google_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["status"])

    def test_google_auth_invalid_role(self):
        """
        Verify that submitting an unrecognized role returns 400 Bad Request.
        """
        payload = {"id_token": "token", "role": "superman_invalid_role"}
        response = self.client.post(self.google_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("users.google_auth_service.verify_google_token")
    def test_google_auth_disabled_user(self, mock_verify):
        """
        Verify that a deactivated user receives a 403 Forbidden.
        """
        User.objects.create_user(
            email="disabled@example.com",
            is_active=False,
            is_verified=True,
        )
        mock_verify.return_value = {
            "sub": "uid-disabled",
            "email": "disabled@example.com",
            "email_verified": True,
            "first_name": "Disabled",
            "last_name": "User",
            "picture": "",
            "raw": {},
        }

        payload = {"id_token": "valid_token"}
        response = self.client.post(self.google_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["status"])

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_verify_google_token_service_id_token(self, mock_verify_oauth):
        """
        Direct unit test for verify_google_token using an ID token.
        """
        mock_verify_oauth.return_value = {
            "sub": "11223344",
            "email": "Verified@Example.COM",
            "email_verified": True,
            "name": "Jane Developer",
            "given_name": "Jane",
            "family_name": "Developer",
            "picture": "https://example.com/avatar.jpg",
        }

        result = verify_google_token("valid_jwt")
        self.assertEqual(result["sub"], "11223344")
        self.assertEqual(result["email"], "verified@example.com")
        self.assertEqual(result["first_name"], "Jane")
        self.assertEqual(result["last_name"], "Developer")
        self.assertTrue(result["email_verified"])

    @patch("requests.get")
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_verify_google_token_service_access_token_fallback(
        self, mock_verify_oauth, mock_requests_get
    ):
        """
        Direct unit test for verify_google_token falling back to Google UserInfo endpoint.
        """
        mock_verify_oauth.side_effect = ValueError("Not an ID token")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sub": "55667788",
            "email": "accesstoken@example.com",
            "name": "Access User",
            "given_name": "Access",
            "family_name": "User",
        }
        mock_requests_get.return_value = mock_resp

        result = verify_google_token("access_token_str")
        self.assertEqual(result["email"], "accesstoken@example.com")
        self.assertEqual(result["sub"], "55667788")
        self.assertEqual(result["first_name"], "Access")
