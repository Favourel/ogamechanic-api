
from users.models import Notification, Role
from django.db import models
mechanic_role = Role.objects.get(name='mechanic')
# Search for anything with 'repair' in title or message
count = Notification.objects.filter(role__isnull=True).filter(
    models.Q(title__icontains='repair') | models.Q(message__icontains='repair')
).update(role=mechanic_role, notification_type='repair_status')
print(f"Updated {count} notifications to mechanic role.")
