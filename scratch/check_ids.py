
from users.models import Notification
ids = [158, 156, 152, 151, 150, 149, 148, 147, 74, 73, 41, 32, 30, 27]
for n in Notification.objects.filter(id__in=ids):
    print(f"ID: {n.id}, Title: {n.title}, Role: {n.role}")
