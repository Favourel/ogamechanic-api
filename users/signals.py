# import secrets
# from datetime import timedelta
# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.utils import timezone
# from .models import User, UserEmailVerification
# from .tasks import send_verification_email_task
# import logging
# import traceback

# logger = logging.getLogger(__name__)


# @receiver(post_save, sender=User)
# def create_email_verification(sender, instance, created, **kwargs):
#     if created and not instance.is_verified:
#         try:
#             token = secrets.token_urlsafe(32)
#             expires_at = timezone.now() + timedelta(hours=1)
#             UserEmailVerification.objects.create(
#                 user=instance,
#                 token=token,
#                 expires_at=expires_at
#             )
#             try:
#                 send_verification_email_task.delay(instance.email, token)
#             except Exception as e:
#                 # Log or handle email sending failure
#                 logger.error(f"Failed to send verification email: {e}\n\n {traceback.format_exc()}") # noqa
#                 pass
#         except Exception as e:
#             # Log or handle creation failure
#             logger.error(f"Failed to create email verification: {e}\n\n {traceback.format_exc()}") # noqa
#             pass
