from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
import logging
from django.utils import timezone

User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, email, reset_token):
    """
    Send password reset email asynchronously.
    Retries up to 3 times on failure, logs errors, and uses 
    robust email sending.
    """
    import logging

    logger = logging.getLogger(__name__)
    subject = 'Password Reset Request'

    frontend_url = getattr(settings, 'FRONTEND_URL', None)
    if not frontend_url:
        logger.error("FRONTEND_URL is not set in settings.")
        return

    reset_url = f"{frontend_url}/reset-password?token={reset_token}"

    try:
        html_message = render_to_string(
            'emails/password_reset.html',
            {
                'reset_url': reset_url,
                'expiry_hours': getattr(settings, 'PASSWORD_RESET_TIMEOUT', 3600) // 3600,  # noqa
                'now': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        )
        plain_message = strip_tags(html_message)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            to=[email],
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Password reset email sent to {email}")
    except Exception as exc:
        logger.error(
            f"Failed to send password reset email to {email}: {exc}", 
            exc_info=True)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical(
                f"Max retries exceeded for sending password reset email to {email}")  # noqa


@shared_task
def unlock_expired_accounts():
    """Unlock accounts where lockout period has expired."""
    from django.utils import timezone
    
    try:
        unlocked_count = User.objects.filter(
            locked_until__lt=timezone.now(),
            locked_until__isnull=False
        ).update(
            locked_until=None,
            failed_login_attempts=0
        )
        
        if unlocked_count > 0:
            print(f"Unlocked {unlocked_count} expired accounts")
        
        return f"Unlocked {unlocked_count} accounts"
    except Exception as e:
        print(f"Error unlocking accounts: {e}")
        return f"Error: {str(e)}"


# @shared_task
# def send_verification_email_task(email, token):
#     logger = logging.getLogger(__name__)
#     subject = 'Verify your email address'
#     base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
#     verification_link = f"{base_url}/verify-email/?token={token}"
#     try:
#         logger.info(f"Preparing verification email for {email}")
#         html_content = render_to_string(
#             'emails/verification_email.html',
#             {
#                 'verification_link': verification_link,
#                 'now': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
#             }
#         )
#         text_content = (
#             f"Please verify your email by clicking the following link: "
#             f"{verification_link}"
#         )
#         msg = EmailMultiAlternatives(
#             subject,
#             text_content,
#             settings.DEFAULT_FROM_EMAIL,
#             [email],
#         )
#         msg.attach_alternative(html_content, "text/html")
#         msg.send()
#         print(f"Verification email sent to {email}")
#     except Exception as e:
#         print(f"Failed to send verification email to {email}: {e}", exc_info=True) # noqa
#         raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_step_by_step_verification_email(self, email, verification_code):
    """
    Send 6-digit verification code for step-by-step registration.
    Production-ready: robust error handling, logging, and configuration.
    """
    logger = logging.getLogger(__name__)
    subject = 'Complete Your Registration - OGAMECHANIC'

    try:
        logger.info(
            f"Preparing to send step-by-step verification code to {email}")

        # Use configured expiry or default to 1 hour
        expiry_hours = getattr(settings, "VERIFICATION_CODE_EXPIRY_HOURS", 1)

        # Create verification code context
        context = {
            'verification_code': verification_code,
            'email': email,
            'now': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            'expiry_hours': expiry_hours,
            'registration_type': 'step_by_step'
        }

        # Render email template
        try:
            html_content = render_to_string(
                'emails/step_by_step_verification.html',
                context
            )
        except Exception as template_exc:
            logger.error(
                f"Failed to render verification email template: {template_exc}", # noqa
                exc_info=True)
            html_content = None  # Fallback to plain text only

        # Plain text fallback
        text_content = (
            f"Welcome to OGAMECHANIC!\n\n"
            f"Your verification code is: {verification_code}\n\n"
            f"Enter this code in the registration form to continue.\n"
            f"This code will expire in {expiry_hours} hour(s).\n\n"
            f"If you didn't request this code, please ignore this email.\n\n"
            f"Best regards,\nOGAMECHANIC Team"
        )

        # Validate email settings
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
        if not from_email:
            logger.error("DEFAULT_FROM_EMAIL is not set in Django settings.")
            raise ValueError("DEFAULT_FROM_EMAIL is not configured.")

        # Send email
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[email],
        )
        if html_content:
            msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info(
            f"Step-by-step verification email sent successfully to {email}")
        return f"Verification email sent to {email}: {verification_code}"

    except Exception as e:
        logger.error(
            f"Failed to send step-by-step verification email to {email}: {e}",
            exc_info=True
        )
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.critical(
                f"Max retries exceeded for sending verification email to {email}") # noqa
        return f"Error sending verification email to {email}: {str(e)}"
