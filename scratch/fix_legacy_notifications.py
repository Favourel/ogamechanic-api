
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings')
django.setup()

from users.models import Notification, Role

def fix_legacy_notifications():
    print("Starting notification cleanup...")
    
    # Get roles
    mechanic_role = Role.objects.filter(name=Role.MECHANIC).first()
    driver_role = Role.objects.filter(name=Role.DRIVER).first()
    primary_user_role = Role.objects.filter(name=Role.PRIMARY_USER).first()
    
    if not all([mechanic_role, driver_role, primary_user_role]):
        print("Error: Required roles not found in database.")
        return

    # 1. Fix Repair Requests (Mechanic)
    repairs = Notification.objects.filter(
        role__isnull=True,
        title__icontains="Repair Request"
    ).update(role=mechanic_role, notification_type='repair_status')
    print(f"Updated {repairs} legacy Repair Request notifications to MECHANIC role.")

    # 2. Fix Ride Requests (Driver)
    rides = Notification.objects.filter(
        role__isnull=True,
        title__icontains="Ride Request"
    ).update(role=driver_role, notification_type='ride_status')
    print(f"Updated {rides} legacy Ride Request notifications to DRIVER role.")

    # 3. Fix Account/Profile notifications (Primary User)
    account = Notification.objects.filter(
        role__isnull=True,
        title__icontains="Account"
    ).update(role=primary_user_role)
    print(f"Updated {account} legacy Account notifications to PRIMARY_USER role.")

    # 4. Fix specific titles seen in user logs
    # E.g. "Support: Hi" should probably stay role-agnostic or go to primary_user
    # For now, let's keep support chats role-agnostic so they show up everywhere,
    # OR tag them as primary_user if that's where the user expects them.
    
    print("Cleanup complete.")

if __name__ == "__main__":
    fix_legacy_notifications()
