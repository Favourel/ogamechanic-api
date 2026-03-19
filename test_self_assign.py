import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ogamechanic.settings')
django.setup()

from users.models import User, Role, MechanicProfile
from mechanics.models import RepairRequest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
import traceback

print('Creating basic user with roles...')
r_cust, _ = Role.objects.get_or_create(name='primary_user')
r_mech, _ = Role.objects.get_or_create(name='mechanic')

u, created = User.objects.get_or_create(email='test_mech_cust_auth_new@example.com')
u.roles.add(r_cust, r_mech)

MechanicProfile.objects.get_or_create(user=u, defaults={'is_approved': True})

print('Creating repair request...')
rr = RepairRequest.objects.create(
    customer=u, 
    service_type='repair', 
    problem_description='test problem',
    vehicle_year=2020,
    service_latitude=0.0,
    service_longitude=0.0
)

# test assignment
print('\n--- Testing assign_mechanic ---')
res = rr.assign_mechanic(u)
print(f'assign_mechanic returned: {res} (Expected: False)')

# test clean
print('\n--- Testing clean ---')
try:
    rr.mechanic = u
    rr.clean()
    print('Failed: clean did not raise exception')
except ValidationError as e:
    print(f'Success: clean raised ValidationError - {e}')
except Exception as e:
    print(f'Failed: Expected ValidationError, got {type(e).__name__} - {e}')

# cleanup
print('\n--- Cleaning up ---')
rr.delete()
u.delete()

print('Done.')
