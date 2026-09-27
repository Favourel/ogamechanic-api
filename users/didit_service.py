import logging
import re
from typing import Any, Dict, Optional, Tuple, Union
from datetime import date, datetime
from django.conf import settings
import requests

logger = logging.getLogger(__name__)


def clean_nin(nin: str) -> str:
    """
    Remove spaces, hyphens, and non-numeric characters from NIN string.
    """
    if not nin:
        return ""
    return re.sub(r"\D", "", str(nin).strip())


def validate_nin_format(nin: str) -> Tuple[bool, str]:
    """
    Validate that NIN is non-empty and consists of exactly 11 numeric digits.

    Returns:
        (is_valid: bool, result_or_error_message: str)
    """
    if not nin:
        return False, "NIN number is required."

    cleaned = clean_nin(nin)
    if not re.match(r"^\d{11}$", cleaned):
        return False, "NIN must be exactly 11 numeric digits."

    return True, cleaned


class DiditVerificationService:
    """
    Service to interact with the Didit Identity Verification API
    specifically for Nigeria National Identity Number (NIMC) lookup.
    """

    @classmethod
    def get_api_key(cls) -> str:
        return getattr(settings, "DIDIT_API_KEY", "") or ""

    @classmethod
    def get_api_url(cls) -> str:
        url = getattr(settings, "DIDIT_API_URL", "https://verification.didit.me") or "https://verification.didit.me"
        return url.rstrip("/")

    @classmethod
    def verify_nin(
        cls,
        nin: str,
        first_name: str,
        last_name: str,
        date_of_birth: Optional[Union[date, datetime, str]] = None,
        vendor_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify a Nigerian National Identification Number (NIN) against NIMC via Didit.

        Args:
            nin: 11-digit NIN string
            first_name: First name of the individual
            last_name: Last name of the individual
            date_of_birth: Optional date of birth (date, datetime, or 'YYYY-MM-DD' string)
            vendor_data: Optional stable user reference (e.g. user UUID)

        Returns:
            Dict containing:
                - success (bool): True if verification matched, False otherwise
                - status (str): MATCH, PARTIAL_MATCH, NO_MATCH, ERROR, etc.
                - request_id (str, optional): Unique request ID from Didit
                - data (dict): Raw response payload
                - message (str): Human-readable outcome or error message
                - source_data (dict, optional): Extracted data from official records if returned
        """
        is_valid_format, clean_result = validate_nin_format(nin)
        if not is_valid_format:
            return {
                "success": False,
                "status": "INVALID_FORMAT",
                "message": clean_result,
                "data": {},
            }

        cleaned_nin = clean_result

        first_name_clean = (first_name or "").strip()
        last_name_clean = (last_name or "").strip()

        if not first_name_clean or not last_name_clean:
            return {
                "success": False,
                "status": "MISSING_NAMES",
                "message": "Both first name and last name are required for NIN verification.",
                "data": {},
            }

        # Check for mock / test mode setting
        mock_success = getattr(settings, "DIDIT_MOCK_SUCCESS", False)
        if mock_success:
            logger.warning(
                "DIDIT_MOCK_SUCCESS is enabled. Returning mock successful NIN verification for %s.",
                cleaned_nin[-4:],
            )
            return {
                "success": True,
                "status": "MATCH",
                "request_id": f"mock-req-{cleaned_nin}",
                "data": {
                    "mock": True,
                    "status": "Approved",
                    "database_validation": {
                        "status": "Approved",
                        "validations": [
                            {
                                "service_id": "nga_national_id",
                                "service_name": "Nigeria National ID (NIMC)",
                                "outcome_code": "MATCH",
                                "source_data": {
                                    "first_name": first_name_clean,
                                    "last_name": last_name_clean,
                                    "national_id": cleaned_nin,
                                },
                            }
                        ],
                    },
                },
                "source_data": {
                    "first_name": first_name_clean,
                    "last_name": last_name_clean,
                    "national_id": cleaned_nin,
                },
                "message": "NIN verified successfully (mock mode enabled).",
            }

        api_key = cls.get_api_key()
        if not api_key:
            logger.error("DIDIT_API_KEY is not configured in settings.")
            return {
                "success": False,
                "status": "CONFIGURATION_ERROR",
                "message": "Didit API key is not configured.",
                "data": {},
            }

        api_url = cls.get_api_url()
        endpoint = f"{api_url}/v3/database-validation/"

        payload: Dict[str, Any] = {
            "issuing_state": "NGA",
            "services": "nga_national_id",
            "validation_type": "nga_national_id",
            "type": "nga_national_id",
            "first_name": first_name_clean,
            "last_name": last_name_clean,
            "national_id": cleaned_nin,
            "personal_number": cleaned_nin,
        }

        if date_of_birth:
            if hasattr(date_of_birth, "strftime"):
                payload["date_of_birth"] = date_of_birth.strftime("%Y-%m-%d")
            else:
                payload["date_of_birth"] = str(date_of_birth).strip()

        if vendor_data:
            payload["vendor_data"] = str(vendor_data)

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            logger.info(
                "Initiating Didit NIN verification for user vendor_data=%s, NIN ending with %s",
                vendor_data,
                cleaned_nin[-4:],
            )
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=30,
            )

            try:
                response_json = response.json()
            except ValueError:
                response_json = {"raw_response": response.text}

            request_id = response_json.get("request_id")

            if response.status_code == 200:
                return cls._parse_success_response(response_json, request_id)

            # Handle 4xx / 5xx error responses from Didit
            return cls._parse_error_response(response.status_code, response_json, request_id)

        except requests.exceptions.Timeout:
            logger.error("Didit NIN verification timed out for endpoint %s", endpoint)
            return {
                "success": False,
                "status": "TIMEOUT",
                "message": "NIN verification service timed out. Please try again shortly.",
                "data": {},
            }
        except requests.exceptions.RequestException as e:
            logger.exception("Didit NIN verification connection error: %s", str(e))
            return {
                "success": False,
                "status": "CONNECTION_ERROR",
                "message": f"Unable to reach NIN verification service: {str(e)}",
                "data": {},
            }

    @classmethod
    def _parse_success_response(
        cls, response_json: Dict[str, Any], request_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Parse successful (HTTP 200) Didit response.
        """
        db_val = response_json.get("database_validation") or {}
        validations = db_val.get("validations") or []
        db_status = (db_val.get("status") or "").upper()
        top_status = (response_json.get("status") or "").upper()

        outcome_codes = []
        source_data = {}
        for item in validations:
            if isinstance(item, dict):
                code = item.get("outcome_code")
                if code:
                    outcome_codes.append(str(code).upper())
                if item.get("source_data"):
                    source_data = item.get("source_data")

        # Check for Match
        is_match = False
        match_status = "MATCH"

        if "MATCH" in outcome_codes:
            is_match = True
            match_status = "MATCH"
        elif "PARTIAL_MATCH" in outcome_codes:
            is_match = True
            match_status = "PARTIAL_MATCH"
        elif db_status in ("MATCH", "APPROVED", "COMPLETED"):
            is_match = True
            match_status = db_status
        elif top_status in ("MATCH", "APPROVED", "COMPLETED"):
            is_match = True
            match_status = top_status

        if is_match:
            logger.info("Didit NIN verification succeeded with status %s", match_status)
            return {
                "success": True,
                "status": match_status,
                "request_id": request_id,
                "data": response_json,
                "source_data": source_data,
                "message": "NIN verified successfully.",
            }

        # Check for explicit failure
        is_no_match = "NO_MATCH" in outcome_codes or db_status in ("NO_MATCH", "DECLINED", "FAILED")
        if is_no_match:
            logger.warning("Didit NIN verification reported NO_MATCH.")
            return {
                "success": False,
                "status": "NO_MATCH",
                "request_id": request_id,
                "data": response_json,
                "source_data": source_data,
                "message": "NIN verification failed: The provided details do not match official NIMC records.",
            }

        # In review or other status
        return {
            "success": False,
            "status": db_status or top_status or "PENDING",
            "request_id": request_id,
            "data": response_json,
            "source_data": source_data,
            "message": f"NIN verification returned status: {db_status or top_status}",
        }

    @classmethod
    def _parse_error_response(
        cls, status_code: int, response_json: Dict[str, Any], request_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Parse non-200 responses from Didit.
        """
        detail = (
            response_json.get("detail")
            or response_json.get("message")
            or response_json.get("error")
            or "Unknown error"
        )

        logger.error(
            "Didit API returned error %s: %s (request_id=%s)",
            status_code,
            detail,
            request_id,
        )

        user_friendly_message = str(detail)
        if "first top-up" in user_friendly_message.lower():
            user_friendly_message = (
                "Didit database validation is currently disabled pending organization balance top-up. "
                "Please top up credits on your Didit Business Console, or enable DIDIT_MOCK_SUCCESS in development."
            )
        elif status_code == 401:
            user_friendly_message = "Didit authentication failed. Please check your API key."
        elif status_code == 404:
            user_friendly_message = "NIN verification endpoint not found. Please check API URL."
        elif status_code >= 500:
            user_friendly_message = "Didit verification server encountered an internal error. Please try again later."

        return {
            "success": False,
            "status": "ERROR",
            "error_code": status_code,
            "request_id": request_id,
            "data": response_json,
            "message": user_friendly_message,
        }
