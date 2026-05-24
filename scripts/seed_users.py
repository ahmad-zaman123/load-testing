"""Seed load-test users by talking to the backend's Django ORM directly.

This script lives in the harness repo (not the backend) by design — the
backend should not carry stress-test-specific code unless it must. It runs
*inside* the backend's Django shell so it can use the ORM without going
through HTTP (which would be slow for 500+ users and would require the
backend's registration flow + OTP shortcut).

Usage:

    # On the backend host (staging or local dev):
    cd <easychef-backend>
    make dcshell                                  # bash inside Django container
    python manage.py shell < /path/to/seed_users.py

    # Or via stdin from outside the container:
    cat scripts/seed_users.py | docker exec -i easychef-dc01 python manage.py shell

    # Override defaults via env vars:
    LOAD_TEST_COUNT=500 LOAD_TEST_PANTRY_ITEMS=30 \
        python manage.py shell < scripts/seed_users.py

    # Output path (default: /tmp/load_test_tokens.json inside the container):
    LOAD_TEST_OUTPUT=/code/tokens.json python manage.py shell < scripts/seed_users.py

After running, copy the resulting tokens.json out of the container and into
this repo's `fixtures/`:

    docker cp easychef-dc01:/tmp/load_test_tokens.json fixtures/tokens.json

This script is idempotent — re-running tops up the user pool without
duplicating existing loadtest users.
"""

import json
import os
import random

from datetime import date, timedelta

from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from easychef.pantry.models import PantryItem
from easychef.products.models import Product
from easychef.users.choices import (
    HealthFocusType,
    HeightUnitType,
    MeasurementUnitType,
    UserActivityLevel,
    UserGender,
    UserGoal,
    UserOnboardingStep,
    WeightUnitType,
)
from easychef.users.models import User


COUNT = int(os.environ.get("LOAD_TEST_COUNT", "100"))
PANTRY_ITEMS = int(os.environ.get("LOAD_TEST_PANTRY_ITEMS", "20"))
OUTPUT_PATH = os.environ.get("LOAD_TEST_OUTPUT", "/tmp/load_test_tokens.json")
EMAIL_PREFIX = "loadtest+"
EMAIL_DOMAIN = "example.com"
DEFAULT_PASSWORD = "LoadTest!Pass123"


def ensure_users(count):
    existing = {
        u.email: u for u in User.objects.filter(email__startswith=EMAIL_PREFIX)
    }
    print(f"  Found {len(existing)} existing load-test users.")
    users, created = [], 0
    for idx in range(1, count + 1):
        email = f"{EMAIL_PREFIX}{idx:04d}@{EMAIL_DOMAIN}"
        if email in existing:
            users.append(existing[email])
            continue
        with transaction.atomic():
            u = User(
                email=email,
                first_name=f"Load{idx:04d}",
                last_name="Tester",
                is_active=True,
                is_onboarding_complete=True,
                onboarding_step=UserOnboardingStep.ALLERGIES,
                gender=random.choice([UserGender.MALE, UserGender.FEMALE]),
                date_of_birth=date.today() - timedelta(days=random.randint(7000, 20000)),
                height=random.uniform(150.0, 200.0),
                height_unit=HeightUnitType.CENTIMETERS,
                weight=random.uniform(50.0, 110.0),
                weight_unit=WeightUnitType.KILOGRAMS,
                serving_size=random.choice([1.0, 2.0, 3.0, 4.0]),
                measurement_unit=MeasurementUnitType.METRIC,
                activity_level=random.choice(
                    [UserActivityLevel.LOW, UserActivityLevel.MODERATE, UserActivityLevel.HIGH]
                ),
                weight_goal=random.choice(
                    [UserGoal.WEIGHT_LOSS, UserGoal.WEIGHT_MAINTAIN, UserGoal.WEIGHT_GAIN]
                ),
                health_focus=random.choice([c[0] for c in HealthFocusType.choices]),
                meal_frequency=random.choice([3, 4, 5]),
            )
            u.set_password(DEFAULT_PASSWORD)
            u.save()
        users.append(u)
        created += 1
    print(f"  Created {created} new users.")
    return users


def ensure_pantry(users, per_user):
    product_ids = list(Product.objects.values_list("id", flat=True)[:2000])
    if not product_ids:
        print("  No Products in DB — skipping pantry seeding.")
        return
    print(f"  Ensuring ~{per_user} pantry items per user (pool: {len(product_ids)})...")
    total = 0
    for user in users:
        existing = PantryItem.objects.filter(user=user).count()
        needed = per_user - existing
        if needed <= 0:
            continue
        sample = random.sample(product_ids, min(needed, len(product_ids)))
        items = [
            PantryItem(
                user=user,
                product_id=pid,
                numerical_value=random.randint(1, 5),
                short_unit="g",
                expiration=date.today() + timedelta(days=random.randint(1, 30)),
            )
            for pid in sample
        ]
        PantryItem.objects.bulk_create(items, ignore_conflicts=True)
        total += len(items)
    print(f"  Created {total} pantry items.")


def write_tokens(users, path):
    tokens = []
    for u in users:
        refresh = RefreshToken.for_user(u)
        tokens.append(
            {
                "user_id": str(u.id),
                "email": u.email,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )
    payload = {
        "count": len(tokens),
        "default_password": DEFAULT_PASSWORD,
        "tokens": tokens,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(tokens)} tokens to {path}")


print(f"Ensuring {COUNT} load-test users exist...")
_users = ensure_users(COUNT)
ensure_pantry(_users, PANTRY_ITEMS)
write_tokens(_users, OUTPUT_PATH)
