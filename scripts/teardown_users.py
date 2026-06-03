"""Delete all load-test users (and their seeded data) from the backend DB.

Usage:
    cat scripts/teardown_users.py | docker exec -i easychef-dc01 python manage.py shell

    # Dry-run first to see what would be deleted:
    LOAD_TEST_DRY_RUN=1 docker exec -i easychef-dc01 python manage.py shell \
        < scripts/teardown_users.py

(The `make teardown` / scripts/teardown.sh wrapper runs this for you.)

All seeded rows hang off a load-test user via on_delete=CASCADE, so deleting
the users alone is *correct*. But the rich seed adds ~250k CookbookRecipe
rows plus tens of thousands of cart items / notifications / recipes, and a
single User.delete() would cascade-collect all of that in one transaction
(slow + memory-heavy). So we delete the heavy child tables in dependency
order first, then the users (whose cascade mops up the small leftovers:
quick actions, the default Favorites cookbook, notification prefs, etc.).

Scoping is by load-test user id, so global recipes/products and other users'
data are never touched — deleting a CookbookRecipe/CartItem join row removes
the link, not the referenced global Recipe/Product.
"""

import os

from django.db import transaction

from easychef.cookbooks.models import Cookbook, CookbookRecipe
from easychef.communications.models import Notification
from easychef.pantry.models import PantryItem
from easychef.products.models import Product
from easychef.recipes.models import Recipe
from easychef.shop.models import Cart, CartItem
from easychef.users.models import User


EMAIL_PREFIX = "loadtest+"
DRY_RUN = os.environ.get("LOAD_TEST_DRY_RUN", "").lower() in ("1", "true", "yes")

user_ids = list(
    User.objects.filter(email__startswith=EMAIL_PREFIX).values_list("id", flat=True)
)

# Child tables to clear (in dependency order) before deleting the users.
# Each entry: (label, queryset). Join tables first so their parents collect cheaply.
steps = [
    ("cookbook_recipes", CookbookRecipe.objects.filter(cookbook__user_id__in=user_ids)),
    ("cart_items", CartItem.objects.filter(cart__user_id__in=user_ids)),
    ("cookbooks", Cookbook.objects.filter(user_id__in=user_ids)),
    ("carts", Cart.objects.filter(user_id__in=user_ids)),
    ("recipes (my)", Recipe.objects.filter(user_id__in=user_ids)),
    ("products (my)", Product.objects.filter(user_id__in=user_ids)),
    ("notifications", Notification.objects.filter(user_id__in=user_ids)),
    ("pantry_items", PantryItem.objects.filter(user_id__in=user_ids)),
]

if not user_ids:
    print("No load-test users found.")
elif DRY_RUN:
    print(f"DRY RUN: would delete {len(user_ids)} load-test users plus:")
    for label, qs in steps:
        print(f"  - {qs.count():>8} {label}")
    print("  (+ cascaded leftovers: quick actions, default cookbook, notification prefs, ...)")
else:
    total = 0
    with transaction.atomic():
        for label, qs in steps:
            deleted, _ = qs.delete()
            print(f"  deleted {deleted:>8} rows  ({label})")
            total += deleted
        users_deleted, _ = User.objects.filter(id__in=user_ids).delete()
        print(f"  deleted {users_deleted:>8} rows  (users + cascaded leftovers)")
        total += users_deleted
    print(f"Done. Removed {len(user_ids)} load-test users; {total} rows total.")
