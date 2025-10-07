import base64
import logging
import re
import secrets
from Crypto.Cipher import AES
# from django.contrib.sites.models import Site
from django.utils import timezone
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils.crypto import get_random_string
from users.models import Notification
# from home.models import SiteSetting 


def log_request(*args):
    for arg in args:
        logging.info(arg)


def encrypt_text(text: str):
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32])
    fernet = Fernet(key)
    secure = fernet.encrypt(f"{text}".encode())
    return secure.decode()


def decrypt_text(text: str):
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32])
    fernet = Fernet(key)
    decrypt = fernet.decrypt(text.encode())
    return decrypt.decode()  


def generate_random_password():
    return get_random_string(length=10)


def generate_random_otp():
    return get_random_string(length=6, allowed_chars="1234567890")


def password_checker(password: str):
    try:
        # Python program to check validation of password
        # Module of regular expression is used with search()

        flag = 0
        while True:
            if len(password) < 8:
                flag = -1
                break
            elif not re.search("[a-z]", password):
                flag = -1
                break
            elif not re.search("[A-Z]", password):
                flag = -1
                break
            elif not re.search("[0-9]", password):
                flag = -1
                break
            elif not re.search("[#!_@$-]", password):
                flag = -1
                break
            elif re.search("\s", password):
                flag = -1
                break
            else:
                flag = 0
                break

        if flag == 0:
            return True, "Valid Password"

        return (
            False,
            "Password must contain uppercase, ''lowercase letters'',"
            " '# ! - _ @ $' special characters "
            "and 8 or more characters",
        )
    except (Exception,) as err:
        return False, f"{err}"


def validate_email(email):
    try:
        regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        if re.fullmatch(regex, email):
            return True
        return False
    except (TypeError, Exception) as err:
        logging.error(f"Email validation error: {err}")
        return False


# def get_site_details():
#     try:
#         site, created = SiteSetting.objects.get_or_create(
#             site=Site.objects.get_current()
#         )
#     except Exception as ex:
#         logging.exception(str(ex))
#         site = SiteSetting.objects.filter(
#             site=Site.objects.get_current()).first()
#     return site
#     # pass


def mask_character(number_to_mask, num_chars_to_mask, mask_char="*"):
    if len(number_to_mask) <= num_chars_to_mask:
        return mask_char * len(number_to_mask)
    else:
        return mask_char * num_chars_to_mask + number_to_mask[
            num_chars_to_mask:]


def create_notification(user, text):
    Notification.objects.create(user=user, message=text)
    return True


def api_response(message, status, data=None, **kwargs):
    if data is None:
        data = {}
    try:
        reference_id = secrets.token_hex(30)
        response = dict(
            requestTime=timezone.now(),
            requestType="outbound",
            referenceId=reference_id,
            status=bool(status),
            message=message,
            data=data,
            **kwargs,
        )

        # if "accessToken" in data and 'refreshToken' in data:
        if "accessToken" in data:
            # Encrypting tokens to be
            response["data"]["accessToken"] = encrypt_text(
                text=data["accessToken"])
            logging.info(msg=response)

            response["data"]["accessToken"] = decrypt_text(
                text=data["accessToken"])

        else:
            logging.info(msg=response)

        return response
    except (Exception,) as err:
        return err


def incoming_request_checks(request, require_data_field: bool = True) -> tuple:
    try:
        x_api_key = request.headers.get("X-Api-Key", None) or request.META.get(
            "HTTP_X_API_KEY", None
        )
        request_type = request.data.get("requestType", None)
        data = request.data.get("data", {})

        if not x_api_key:
            return False, ("Missing or Incorrect "
                           "Request-Header field 'X-Api-Key'")

        if x_api_key != settings.X_API_KEY:
            return False, "Invalid value for Request-Header field 'X-Api-Key'"

        if not request_type:
            return False, "'requestType' field is required"

        if request_type != "inbound":
            return False, "Invalid 'requestType' value"

        # Support multipart/form-data: 'data' may be a JSON string
        if isinstance(data, str):
            try:
                import json
                parsed = json.loads(data or "{}")
                data = parsed
            except Exception:
                # Keep data as-is (likely empty string); we'll try to recover below # noqa
                pass

        # Merge uploaded files into data when present
        try:
            if hasattr(request, "FILES") and request.FILES:
                for key in request.FILES:
                    data[key] = request.FILES.get(key)
        except Exception:
            pass

        # Recover non-file fields submitted as top-level form fields when 'data' JSON isn't parsed # noqa
        try:
            # DRF's request.data is a dict-like (QueryDict) for multipart
            if isinstance(request.data, dict):
                print(request.data)
                top_level_fields = {}
                for k, v in request.data.items():
                    # Exclude control keys and already-handled 'data'
                    if k in ("requestType", "data"):
                        continue
                    # Skip file keys (already merged)
                    if hasattr(request, "FILES") and k in request.FILES:
                        continue
                    top_level_fields[k] = v
                # If client sent fields at top-level, merge them into data
                if top_level_fields:
                    if not isinstance(data, dict):
                        data = {}
                    # Don't overwrite any keys already present from parsed JSON
                    for k, v in top_level_fields.items():
                        if k not in data:
                            data[k] = v
        except Exception:
            pass

        if require_data_field:
            if not data:
                return (
                    False,
                    "'data' field was not passed or is empty. "
                    "It is required to contain all request data",
                )

        # Normalize known list/object fields that sometimes arrive as JSON strings in multipart # noqa
        # Normalize known list/object fields
        try:
            import json as _json
            for key in ['vehicle_make_ids', 'expertise_details']:
                if key in data:
                    if isinstance(data[key], str):
                        if data[key].strip() == "":
                            # empty string → normalize to empty list
                            data[key] = []
                        else:
                            try:
                                data[key] = _json.loads(data[key])
                            except Exception:
                                # fallback: wrap string in list
                                data[key] = [data[key]]
            # Coerce vehicle_make_ids elements to ints when possible
            if isinstance(data.get('vehicle_make_ids'), list):
                coerced = []
                for item in data['vehicle_make_ids']:
                    try:
                        coerced.append(int(item))
                    except Exception:
                        coerced.append(item)
                data['vehicle_make_ids'] = coerced
        except Exception:
            pass

        return True, data
    except (Exception,) as err:
        return False, f"{err}"


def get_incoming_request_checks(request) -> tuple:
    try:
        x_api_key = request.headers.get("X-Api-Key", None) or request.META.get(
            "HTTP_X_API_KEY", None
        )

        if not x_api_key:
            return False, "Missing or Incorrect Request-Header field 'X-Api-Key'" # noqa

        if x_api_key != settings.X_API_KEY:
            return False, "Invalid value for Request-Header field 'X-Api-Key'"

        return True, ""
    except (Exception,) as err:
        return False, f"{err}"


def format_phone_number(phone_number):
    # Remove any non-digit characters
    phone_number = "".join(filter(str.isdigit, phone_number))

    # Ensure it starts with '0' (Nigerian format) before reformatting
    if phone_number.startswith("0") and len(phone_number) == 11:
        # Replace leading '0' with '234'
        return f"234{phone_number[1:]}"
    elif phone_number.startswith("234") and len(phone_number) == 13:
        # Already formatted correctly
        return phone_number
    else:
        # Invalid number
        raise ValueError("Invalid phone number format")


def decrypt_pin(content):
    encryption_key = settings.DECRYPTION_KEY
    key = bytes.fromhex(encryption_key)
    data = bytes.fromhex(content)
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted_data = cipher.decrypt(data)
    data = bytes(decrypted_data.decode("utf-8"), "utf-8")
    return data.rstrip(b"\x00").decode("utf-8")


def transaction_pin_correct(user, trans_pin):
    decrypted_pin = decrypt_pin(trans_pin)
    correct_pin = decrypt_text(user.userprofile.transactionPin)
    if str(decrypted_pin) != str(correct_pin):
        return False
    return True



def resize_and_save_image(input_image, width, height):
    """
    Resizes an image to the given width and height, applies sharpening, and saves it to the database.

    Parameters:
    input_image (InMemoryUploadedFile): Image file uploaded by the user.
    width (int): Desired width for the image.
    height (int): Desired height for the image.

    Returns:
    ContentFile: Resized image ready to be saved to the database.
    """

    try:
        from PIL import Image, ImageFilter, UnidentifiedImageError
        from pillow_heif import register_heif_opener
        from django.core.files.base import ContentFile
        from io import BytesIO
        import imageio, os
        import ghostscript

        # Register HEIF/AVIF opener
        register_heif_opener()

        # Determine the file extension
        ext = os.path.splitext(input_image.name)[-1].lower()

        # Open the image
        if ext == ".eps":
            # EPS-specific handling using Ghostscript
            try:
                img = Image.open(input_image)
                img.load(scale=2)  # Load at 2x resolution for better quality
                img = img.convert("RGB")  # Convert EPS to RGB mode
            except Exception as e:
                log_request(f"Error processing EPS file: {e}")
                return None
        else:
            try:
                # Open non-EPS formats
                img = Image.open(input_image)
                img = img.convert("RGB")  # Ensure compatibility
            except UnidentifiedImageError:
                # Fallback for unsupported formats
                img = imageio.imread(input_image)
                img = Image.fromarray(img)  # Convert to Pillow Image object

        original_width, original_height = img.size

        log_request(
            f"Processing image: {input_image.name}, size: {original_width}x{original_height}"
        )

        # Resize if needed
        if original_width > width or original_height > height:
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            # img.thumbnail((width, height), Image.LANCZOS)

            log_request(f"Resized size: {img.size}")
            # print(f"Resized size: {img.size}")

            # Apply sharpening
            img = img.filter(ImageFilter.SHARPEN)

        # Save the resized image to a buffer as JPEG
        buffer = BytesIO()
        img.save(buffer, format="JPEG", optimize=True, quality=85)
        buffer.seek(0)

        return ContentFile(buffer.read(), name=f"{input_image.name.split('.')[0]}.jpg")

    except Exception as e:
        log_request(f"Error resizing image: {e}")
        return None