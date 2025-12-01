import os
from celery import Celery
# from celery.schedules import crontab
from datetime import timedelta # noqa
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Set the default Django settings module for the 'celery' program.
if os.getenv('env', 'dev') == 'prod':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.prod') # noqa
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.dev')

app = Celery('ogamechanic')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Explicitly set Redis as broker if not set in settings
if not app.conf.get('broker_url'):
    app.conf.broker_url = 'redis://localhost:6379/5'
if not app.conf.get('result_backend'):
    app.conf.result_backend = 'redis://localhost:6379/5'

# Configure Celery to use Redis
app.conf.update(
    broker_url='redis://localhost:6379/5',
    result_backend='redis://localhost:6379/5',
    broker_transport_options={'visibility_timeout': 3600},
    result_expires=3600,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Africa/Lagos',  # Use Lagos timezone
    enable_utc=False,  # Disable UTC to use local timezone
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_prefetch_multiplier=1,  # Disable prefetching
    task_acks_late=True,  # Only acknowledge tasks after they complete
    task_reject_on_worker_lost=True,  # Requeue tasks if worker dies
    task_track_started=True,  # Track started tasks
    task_time_limit=3600,  # 1 hour max runtime per task
    task_soft_time_limit=3300,  # Soft limit 55 minutes
    # Beat scheduler configuration - use database scheduler
    beat_scheduler='django_celery_beat.schedulers:DatabaseScheduler',
)

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(name='cleanup_expired_tokens')
def cleanup_expired_tokens():
    """Clean up expired tokens from the blacklist."""
    from django.utils import timezone
    from rest_framework_simplejwt.token_blacklist.models import (
        OutstandingToken
    )

    OutstandingToken.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()


# Configure Celery Beat schedule
# app.conf.beat_schedule = {
#     'cleanup-expired-tokens': {
#         'task': 'cleanup_expired_tokens',
#         'schedule': crontab(hour=0, minute=0),  # Run daily at midnight
#     },

#     'unlock-expired-accounts': {
#         'task': 'users.tasks.unlock_expired_accounts',
#         'schedule': crontab(minute='*/15'),  # Every 15 minutes
#     },
#     # Add more periodic tasks here

#     'delete-expired-pending-rides': {
#         'task': 'rides.tasks.delete_expired_pending_rides',
#         'schedule': crontab(minute='*/30'),  # Every 30 minutes
#     },

# }


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
