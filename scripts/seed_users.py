"""Seed load-test users (and their data) by talking to the backend's Django ORM.

This script lives in the harness repo (not the backend) by design — the
backend should not carry stress-test-specific code unless it must. It runs
*inside* the backend's Django shell so it can use the ORM without going
through HTTP (which would be slow and would require the registration flow).

Usage:

    cat scripts/seed_users.py | docker exec -i easychef-dc01 python manage.py shell

    # Override defaults via env vars (see the knobs block below):
    LOAD_TEST_COUNT=50 LOAD_TEST_PANTRY_ITEMS=100 \
        docker exec -i easychef-dc01 python manage.py shell < scripts/seed_users.py

Then copy the fixture out:

    docker cp easychef-dc01:/tmp/load_test_tokens.json fixtures/tokens.json

(The `make seed` / scripts/seed.sh wrapper does all of this for you.)

What it creates per user (counts are env-tunable):
    - profile complete enough to pass the meal-planner profile gate
    - LOAD_TEST_PANTRY_ITEMS pantry items (from APPROVED products)
    - LOAD_TEST_MY_RECIPES own recipes        (GET /recipes/me/)
    - LOAD_TEST_COOKBOOKS own cookbooks, each holding
      LOAD_TEST_COOKBOOK_RECIPES recipes      (GET /cookbooks/, /cookbooks/<id>/)
    - LOAD_TEST_RECOMMENDED recommended recipes (GET /recipes/recommended/)
    - one ACTIVE cart with LOAD_TEST_CART_ITEMS items (GET /shop/...)
    - LOAD_TEST_NOTIFICATIONS notifications   (GET /communications/notifications/)
    - LOAD_TEST_MY_PRODUCTS user-created products (GET /products/me/)
Plus, globally (not per user):
    - LOAD_TEST_COMMUNITY_COOKBOOKS PUBLIC cookbooks (GET /cookbooks/community-cookbooks/)

Idempotent: re-running tops up each section to its target without duplicating.
All inserts use bulk_create / direct field assignment, which skip model
signals — so no embeddings, FCM pushes, or Celery tasks fire while seeding.
"""

import json
import os
import random

from datetime import date, timedelta
from uuid import uuid4

from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from easychef.cookbooks.choices import CookbookStatus
from easychef.cookbooks.models import Cookbook, CookbookRecipe
from easychef.communications.choices import NotificationType
from easychef.communications.models import Notification
from easychef.pantry.models import PantryItem
from easychef.products.choices import ProductSource, ProductStatus
from easychef.products.models import Product
from easychef.recipes.choices import RecipeProcessingStatus, RecipeSource, RecipeStatus
from easychef.recipes.models import Recipe
from easychef.shop.choices import CartItemStatus, CartStatus
from easychef.shop.models import Cart, CartItem
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


# --- knobs -------------------------------------------------------------------
COUNT = int(os.environ.get("LOAD_TEST_COUNT", "50"))
PANTRY_ITEMS = int(os.environ.get("LOAD_TEST_PANTRY_ITEMS", "100"))
MY_RECIPES = int(os.environ.get("LOAD_TEST_MY_RECIPES", "50"))
COOKBOOKS = int(os.environ.get("LOAD_TEST_COOKBOOKS", "50"))
COOKBOOK_RECIPES = int(os.environ.get("LOAD_TEST_COOKBOOK_RECIPES", "100"))
COMMUNITY_COOKBOOKS = int(os.environ.get("LOAD_TEST_COMMUNITY_COOKBOOKS", "100"))
RECOMMENDED = int(os.environ.get("LOAD_TEST_RECOMMENDED", "100"))
CART_ITEMS = int(os.environ.get("LOAD_TEST_CART_ITEMS", "100"))
NOTIFICATIONS = int(os.environ.get("LOAD_TEST_NOTIFICATIONS", "100"))
MY_PRODUCTS = int(os.environ.get("LOAD_TEST_MY_PRODUCTS", "50"))

OUTPUT_PATH = os.environ.get("LOAD_TEST_OUTPUT", "/tmp/load_test_tokens.json")
EMAIL_PREFIX = "loadtest+"
EMAIL_DOMAIN = "example.com"
DEFAULT_PASSWORD = "LoadTest!Pass123"
BATCH = 1000


def _approved_product_ids(limit):
    return list(
        Product.objects.filter(status=ProductStatus.APPROVED).values_list("id", flat=True)[:limit]
    )


def _public_recipe_ids(limit):
    return list(
        Recipe.objects.filter(
            status=RecipeStatus.PUBLIC,
            processing_status=RecipeProcessingStatus.APPROVED,
        ).values_list("id", flat=True)[:limit]
    )


def ensure_users(count):
    existing = {u.email: u for u in User.objects.filter(email__startswith=EMAIL_PREFIX)}
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
    # Pantry reads filter to APPROVED products, so seed from the approved pool.
    product_ids = _approved_product_ids(max(2000, per_user * 10))
    if not product_ids:
        print("  No APPROVED Products — skipping pantry.")
        return
    print(f"  Pantry: ~{per_user}/user (pool {len(product_ids)})...")
    total = 0
    for user in users:
        need = per_user - PantryItem.objects.filter(user=user).count()
        if need <= 0:
            continue
        sample = random.sample(product_ids, min(need, len(product_ids)))
        PantryItem.objects.bulk_create(
            [
                PantryItem(
                    user=user,
                    product_id=pid,
                    numerical_value=random.randint(1, 5),
                    short_unit="g",
                    expiration=date.today() + timedelta(days=random.randint(1, 30)),
                )
                for pid in sample
            ],
            ignore_conflicts=True,
        )
        total += len(sample)
    print(f"  Pantry: created {total} items.")


def ensure_my_recipes(users, per_user):
    print(f"  My recipes: ~{per_user}/user...")
    total = 0
    for uidx, user in enumerate(users, 1):
        have = Recipe.objects.filter(user=user, title__startswith="LT Recipe").count()
        need = per_user - have
        if need <= 0:
            continue
        # slug is unique and auto-set only in Model.save(); bulk_create skips
        # save(), so we set a unique slug ourselves.
        Recipe.objects.bulk_create(
            [
                Recipe(
                    title=f"LT Recipe {uidx:04d}-{i:03d}",
                    slug=f"lt-recipe-{uidx:04d}-{i:03d}-{uuid4().hex[:8]}",
                    user=user,
                    source=RecipeSource.USER_CREATED,
                    status=RecipeStatus.PRIVATE,
                )
                for i in range(have, per_user)
            ],
            ignore_conflicts=True,
        )
        total += need
    print(f"  My recipes: created {total}.")


def _link_recipes(cookbook, recipe_ids):
    CookbookRecipe.objects.bulk_create(
        [CookbookRecipe(cookbook=cookbook, recipe_id=rid) for rid in recipe_ids],
        ignore_conflicts=True,
        batch_size=BATCH,
    )


def ensure_own_cookbooks(users, per_user, recipes_per, pool):
    if not pool:
        print("  No public recipes — skipping cookbooks.")
        return
    print(f"  Own cookbooks: ~{per_user}/user x {recipes_per} recipes...")
    made = 0
    for user in users:
        have = Cookbook.objects.filter(user=user, name__startswith="LT Cookbook").count()
        for i in range(have, per_user):
            cb = Cookbook.objects.create(
                user=user,
                name=f"LT Cookbook {i:03d}",
                status=CookbookStatus.PRIVATE,
            )
            _link_recipes(cb, random.sample(pool, min(recipes_per, len(pool))))
            made += 1
    print(f"  Own cookbooks: created {made}.")


def ensure_community_cookbooks(users, total, recipes_per, pool):
    if not pool or not users:
        print("  No public recipes/users — skipping community cookbooks.")
        return
    have = Cookbook.objects.filter(
        status=CookbookStatus.PUBLIC, name__startswith="LT Community"
    ).count()
    print(f"  Community cookbooks: {total} target ({have} exist) x {recipes_per} recipes...")
    made = 0
    for i in range(have, total):
        owner = users[i % len(users)]  # round-robin owner; community list is global
        cb = Cookbook.objects.create(
            user=owner,
            name=f"LT Community {i:04d}",
            status=CookbookStatus.PUBLIC,
        )
        # Must hold >=1 PUBLIC+APPROVED recipe to appear in the community list.
        _link_recipes(cb, random.sample(pool, min(recipes_per, len(pool))))
        made += 1
    print(f"  Community cookbooks: created {made}.")


def ensure_recommended(users, n, pool):
    if not pool:
        print("  No public recipes — skipping recommended.")
        return
    print(f"  Recommended: {n}/user...")
    updated = []
    for user in users:
        if len(user.recommended_recipes or []) >= n:
            continue
        user.recommended_recipes = random.sample(pool, min(n, len(pool)))
        updated.append(user)
    if updated:
        User.objects.bulk_update(updated, ["recommended_recipes"], batch_size=BATCH)
    print(f"  Recommended: set for {len(updated)} users.")


def ensure_carts(users, n_items):
    product_ids = _approved_product_ids(max(2000, n_items * 10))
    if not product_ids:
        print("  No APPROVED Products — skipping carts.")
        return
    print(f"  Carts: 1 ACTIVE cart + {n_items} items/user...")
    total = 0
    for user in users:
        cart, _ = Cart.objects.get_or_create(
            user=user, status=CartStatus.ACTIVE, defaults={"name": "Load Test Cart"}
        )
        need = n_items - CartItem.objects.filter(cart=cart).count()
        if need <= 0:
            continue
        # unique_together (cart, product) -> distinct products only.
        sample = random.sample(product_ids, min(need, len(product_ids)))
        CartItem.objects.bulk_create(
            [
                CartItem(
                    cart=cart,
                    product_id=pid,
                    quantity=random.randint(1, 5),
                    status=CartItemStatus.ACTIVE,
                )
                for pid in sample
            ],
            ignore_conflicts=True,
        )
        total += len(sample)
    print(f"  Carts: created {total} items.")


def ensure_notifications(users, n):
    print(f"  Notifications: {n}/user...")
    total = 0
    types = [c[0] for c in NotificationType.choices]
    for user in users:
        have = Notification.objects.filter(user=user, title__startswith="LT Notification").count()
        if have >= n:
            continue
        Notification.objects.bulk_create(
            [
                Notification(
                    user=user,
                    title=f"LT Notification {i:03d}",
                    body=f"Load-test notification #{i} for {user.email}.",
                    type=random.choice(types),
                    is_read=random.choice([True, False]),
                )
                for i in range(have, n)
            ],
            batch_size=BATCH,
        )
        total += n - have
    print(f"  Notifications: created {total}.")


def ensure_my_products(users, n):
    print(f"  My products: {n}/user...")
    total = 0
    for uidx, user in enumerate(users, 1):
        have = Product.objects.filter(
            user=user, source=ProductSource.USER_CREATED, status=ProductStatus.NEW
        ).count()
        if have >= n:
            continue
        Product.objects.bulk_create(
            [
                Product(
                    title=f"LT Product {uidx:04d}-{i:03d}",
                    user=user,
                    source=ProductSource.USER_CREATED,
                    status=ProductStatus.NEW,
                    short_unit="g",
                    numerical_value=random.randint(1, 500),
                )
                for i in range(have, n)
            ],
            batch_size=BATCH,
        )
        total += n - have
    print(f"  My products: created {total}.")


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
    with open(path, "w") as f:
        json.dump(
            {"count": len(tokens), "default_password": DEFAULT_PASSWORD, "tokens": tokens},
            f,
            indent=2,
        )
    print(f"Wrote {len(tokens)} tokens to {path}")


print(f"Ensuring {COUNT} load-test users exist...")
_users = ensure_users(COUNT)

# Shared content pools (global, fetched once).
_recipe_pool = _public_recipe_ids(max(COOKBOOK_RECIPES, RECOMMENDED, 200) * 5)
print(f"  Public+approved recipe pool: {len(_recipe_pool)}")

ensure_pantry(_users, PANTRY_ITEMS)
ensure_my_recipes(_users, MY_RECIPES)
ensure_own_cookbooks(_users, COOKBOOKS, COOKBOOK_RECIPES, _recipe_pool)
ensure_community_cookbooks(_users, COMMUNITY_COOKBOOKS, COOKBOOK_RECIPES, _recipe_pool)
ensure_recommended(_users, RECOMMENDED, _recipe_pool)
ensure_carts(_users, CART_ITEMS)
ensure_notifications(_users, NOTIFICATIONS)
ensure_my_products(_users, MY_PRODUCTS)
write_tokens(_users, OUTPUT_PATH)
print("Done.")
