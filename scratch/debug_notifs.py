
from users.models import Notification
print(f"Total role-less notifications: {Notification.objects.filter(role__isnull=True).count()}")
for n in Notification.objects.filter(role__isnull=True)[:10]:
    print(f"ID: {n.id}, Title: {n.title}")
