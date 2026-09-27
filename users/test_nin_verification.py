from unittest.mock import patch, MagicMock
from django.conf import settings
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from users.models import (
    Role,
    MechanicProfile,
    MerchantProfile,
    DriverProfile,
    NINVerification,
)
from users.didit_service import (
    clean_nin,
    validate_nin_format,
    DiditVerificationService,
)

User = get_user_model()


class NINValidationAndServiceTests(TestCase):
    def test_clean_nin(self):
        self.assertEqual(clean_nin(" 123-456-789-01 "), "12345678901")
        self.assertEqual(clean_nin("123 456 789 01"), "12345678901")
        self.assertEqual(clean_nin(""), "")
        self.assertEqual(clean_nin(None), "")
        self.assertEqual(clean_nin("123a456b78901"), "12345678901")

    def test_validate_nin_format(self):
        valid, result = validate_nin_format("12345678901")
        self.assertTrue(valid)
        self.assertEqual(result, "12345678901")

        valid, result = validate_nin_format("123-456-789-01")
        self.assertTrue(valid)
        self.assertEqual(result, "12345678901")

        valid, err = validate_nin_format("12345")
        self.assertFalse(valid)
        self.assertIn("11 numeric digits", err)

        valid, err = validate_nin_format("1234567890123")
        self.assertFalse(valid)
        self.assertIn("11 numeric digits", err)

        valid, err = validate_nin_format("")
        self.assertFalse(valid)

    @override_settings(DIDIT_MOCK_SUCCESS=True)
    def test_didit_mock_success_mode(self):
        res = DiditVerificationService.verify_nin(
            nin="12345678901",
            first_name="John",
            last_name="Doe",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "MATCH")
        self.assertEqual(res["source_data"]["national_id"], "12345678901")

    @override_settings(DIDIT_MOCK_SUCCESS=False, DIDIT_API_KEY="test-key")
    @patch("users.didit_service.requests.post")
    def test_didit_service_match_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "request_id": "req-12345",
            "database_validation": {
                "status": "Approved",
                "validations": [
                    {
                        "service_id": "nga_national_id",
                        "outcome_code": "MATCH",
                        "service_name": "Nigeria National ID (NIMC)",
                        "source_data": {"first_name": "John", "last_name": "Doe"},
                    }
                ],
            },
        }
        mock_post.return_value = mock_response

        res = DiditVerificationService.verify_nin(
            nin="12345678901",
            first_name="John",
            last_name="Doe",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "MATCH")
        self.assertEqual(res["request_id"], "req-12345")

    @override_settings(DIDIT_MOCK_SUCCESS=False, DIDIT_API_KEY="test-key")
    @patch("users.didit_service.requests.post")
    def test_didit_service_no_match_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "request_id": "req-99999",
            "database_validation": {
                "status": "Declined",
                "validations": [
                    {
                        "service_id": "nga_national_id",
                        "outcome_code": "NO_MATCH",
                    }
                ],
            },
        }
        mock_post.return_value = mock_response

        res = DiditVerificationService.verify_nin(
            nin="12345678901",
            first_name="Wrong",
            last_name="Name",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NO_MATCH")

    @override_settings(DIDIT_MOCK_SUCCESS=False, DIDIT_API_KEY="test-key")
    @patch("users.didit_service.requests.post")
    def test_didit_service_top_up_required_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "detail": "To protect against abuse, database validation is disabled until your organization's first top-up."
        }
        mock_post.return_value = mock_response

        res = DiditVerificationService.verify_nin(
            nin="12345678901",
            first_name="John",
            last_name="Doe",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("top-up", res["message"].lower())


TEST_MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    WHITENOISE_MANIFEST_STRICT=False,
    MIDDLEWARE=TEST_MIDDLEWARE,
)
class NINVerificationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.role_mechanic, _ = Role.objects.get_or_create(
            name=Role.MECHANIC, defaults={"description": "Mechanic"}
        )
        self.role_merchant, _ = Role.objects.get_or_create(
            name=Role.MERCHANT, defaults={"description": "Merchant"}
        )

        self.user = User.objects.create_user(
            email="mechanic@test.com",
            password="SecurePassword123!",
            first_name="Chidi",
            last_name="Okafor",
        )
        self.user.roles.add(self.role_mechanic)
        self.user.active_role = self.role_mechanic
        self.user.save()

        self.mechanic_profile = MechanicProfile.objects.create(
            user=self.user,
            location="Ikeja, Lagos",
            lga="Ikeja",
        )

    def test_unauthenticated_access_blocked(self):
        response = self.client.post(
            "/api/v1/users/nin/verify/",
            {"nin_number": "12345678901"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_nin_rejected(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v1/users/nin/verify/",
            {"nin_number": "invalid-nin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data.get("status"))

    @override_settings(DIDIT_MOCK_SUCCESS=True)
    def test_successful_nin_verification_flow(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/v1/users/nin/verify/",
            {
                "nin_number": "12345678901",
                "first_name": "Chidi",
                "last_name": "Okafor",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("status"))
        self.assertEqual(response.data["data"]["status"], "verified")
        self.assertEqual(response.data["data"]["nin_masked"], "*******8901")

        # Verify audit record was created in database
        verification = NINVerification.objects.filter(user=self.user).first()
        self.assertIsNotNone(verification)
        self.assertEqual(verification.status, NINVerification.STATUS_VERIFIED)
        self.assertEqual(verification.nin_number, "12345678901")

        # Verify profile was updated
        self.mechanic_profile.refresh_from_db()
        self.assertTrue(self.mechanic_profile.nin_is_verified)
        self.assertEqual(self.mechanic_profile.nin_number, "12345678901")
        self.assertIsNotNone(self.mechanic_profile.nin_verified_at)

        # Check User helper property
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_nin_verified)

    @override_settings(DIDIT_MOCK_SUCCESS=True)
    def test_nin_status_endpoint(self):
        self.client.force_authenticate(user=self.user)

        # Verify NIN first
        self.client.post(
            "/api/v1/users/nin/verify/",
            {"nin_number": "12345678901"},
            format="json",
        )

        # Query status
        response = self.client.get("/api/v1/users/nin/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("status"))

        data = response.data["data"]
        self.assertTrue(data["is_nin_verified"])
        self.assertEqual(data["verified_nin"], "*******8901")
        self.assertIn("mechanic", data["profiles"])
        self.assertTrue(data["profiles"]["mechanic"]["nin_is_verified"])
        self.assertEqual(len(data["recent_verifications"]), 1)

    def test_changing_nin_resets_verification_status(self):
        # Set profile as verified
        self.mechanic_profile.nin_number = "11111111111"
        self.mechanic_profile.nin_is_verified = True
        self.mechanic_profile.nin_verified_at = timezone.now()
        self.mechanic_profile.save()

        # Now update via serializer to new NIN
        from users.serializers import MechanicProfileSerializer

        serializer = MechanicProfileSerializer(
            instance=self.mechanic_profile,
            data={"nin_number": "22222222222"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_profile = serializer.save()

        self.assertFalse(updated_profile.nin_is_verified)
        self.assertIsNone(updated_profile.nin_verified_at)
        self.assertEqual(updated_profile.nin_number, "22222222222")
