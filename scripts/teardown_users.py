"""Delete all load-test users (and their dependent data) from the backend DB.

Usage:
    cat scripts/teardown_users.py | docker exec -i easychef-dc01 python manage.py shell

    # Dry-run first to see what would be deleted:
    LOAD_TEST_DRY_RUN=1 docker exec -i easychef-dc01 python manage.py shell \
        < scripts/teardown_users.py
"""

import os

from django.db import transaction

from easychef.users.models import User


EMAIL_PREFIX = "loadtest+"
DRY_RUN = os.environ.get("LOAD_TEST_DRY_RUN", "").lower() in ("1", "true", "yes")


qs = User.objects.filter(email__startswith=EMAIL_PREFIX)
count = qs.count()

if count == 0:
    print("No load-test users found.")
elif DRY_RUN:
    print(f"DRY RUN: would delete {count} load-test users and their related data.")
else:
    with transaction.atomic():
        deleted, _per_model = qs.delete()
    print(f"Deleted {count} load-test users ({deleted} total rows cascaded).")
