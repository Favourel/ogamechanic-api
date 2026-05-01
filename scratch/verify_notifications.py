import os
import django
import uuid

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings.dev')
django.setup()

from users.models import User, Notification, Role, Device
from users.services import NotificationService
from mechanics.models import RepairRequest
from unittest.mock import patch, MagicMock

def verify_notifications():
    print("Testing Notification Creation...")
    
    # Get or create a test user
    user, _ = User.objects.get_or_create(email="test_mechanic@example.com", defaults={"first_name": "Test", "last_name": "Mechanic"})
    
    # Ensure user has an active device with an Expo token
    Device.objects.get_or_create(
        user=user, 
        fcm_token="ExponentPushToken[test-token]",
        defaults={"is_active": True}
    )
    
    # Mock a RepairRequest
    repair = MagicMock(spec=RepairRequest)
    repair.id = uuid.uuid4()
    
    # Mock the celery task to avoid actual networking
    with patch('users.services.send_expo_push_notification.delay') as mock_push:
        with patch('users.services.NotificationService.send_realtime_notification') as mock_ws:
            notification = NotificationService.create_notification(
                user=user,
                title="Test Repair Alert",
                message="You have a new repair request.",
                notification_type='info',
                related_object=repair,
                related_object_type='RepairRequest'
            )
            
            print(f"Notification created: ID={notification.id}")
            print(f"Related Object ID: {notification.related_object_id}")
            print(f"Related Object Type: {notification.related_object_type}")
            
            assert notification.related_object_id == repair.id
            assert notification.related_object_type == 'RepairRequest'
            
            mock_ws.assert_called_once()
            print("WebSocket notification triggered.")
            
            mock_push.assert_called_once()
            print("Expo Push notification task triggered.")
            
    print("Verification Successful!")

if __name__ == "__main__":
    verify_notifications()
