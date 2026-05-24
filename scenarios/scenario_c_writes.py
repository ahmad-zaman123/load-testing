"""Scenario C — Writes + Celery Dispatch.

Tests how writes fan out to Celery. The interesting failure mode here is the
etl queue (concurrency = 2) saturating; the expected outcome is that web
latency stays healthy while the etl backlog grows.

The recipe-from-URL action is the only heavy etl path included. It's gated
behind the `scenario_c_full` tag so the default `scenario_c` run leaves it
out, matching the plan doc's choice to avoid heavy external-API mocking.
"""

import random
import uuid

from locust import between, tag, task

from common import AuthenticatedHttpUser


SAMPLE_URLS = (
    "https://www.allrecipes.com/recipe/213742/cheesy-chicken-broccoli-casserole/",
    "https://www.foodnetwork.com/recipes/food-network-kitchen/spaghetti-carbonara",
    "https://www.bbcgoodfood.com/recipes/simple-chocolate-cake",
)


@tag("scenario_c", "writes")
class CartWriteUser(AuthenticatedHttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self):
        super().on_start()
        self._recipe_uuids = []
        self._product_ids = []
        self._cart_id = None
        self._cart_item_ids = []
        self._fetch_cart_id()
        self._prime_recipe_and_product_pool()

    # --- session setup ----------------------------------------------------

    def _fetch_cart_id(self):
        with self.client.get(
            "/shop/carts/",
            name="GET /shop/carts/ (prime)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                return
            try:
                body = response.json()
            except ValueError:
                return
            carts = body if isinstance(body, list) else body.get("results") or []
            for cart in carts:
                if cart.get("status") in ("ACTIVE", "active", None):
                    self._cart_id = cart.get("id")
                    break
            if self._cart_id is None and carts:
                self._cart_id = carts[0].get("id")

    def _prime_recipe_and_product_pool(self):
        with self.client.get(
            "/recipes/list/?page=1",
            name="GET /recipes/list/ (prime)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    results = response.json().get("results") or []
                    self._recipe_uuids = [r.get("id") for r in results if r.get("id")]
                except ValueError:
                    pass

        with self.client.get(
            "/products/list/?page=1",
            name="GET /products/list/ (prime)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    results = response.json().get("results") or []
                    self._product_ids = [p.get("id") for p in results if p.get("id")]
                except ValueError:
                    pass

    # --- weighted tasks ---------------------------------------------------

    @task(5)
    def add_product_to_cart(self):
        if self._cart_id is None or not self._product_ids:
            return
        with self.client.post(
            f"/shop/cart/{self._cart_id}/product/",
            json={"product": random.choice(self._product_ids), "quantity": 1},
            name="POST /shop/cart/[id]/product/",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                try:
                    item_id = response.json().get("id")
                    if item_id is not None and len(self._cart_item_ids) < 50:
                        self._cart_item_ids.append(item_id)
                except ValueError:
                    pass

    @task(3)
    def update_cart_item(self):
        if not self._cart_item_ids:
            return
        item_id = random.choice(self._cart_item_ids)
        self.client.put(
            f"/shop/cart-items/{item_id}/",
            json={"quantity": random.randint(1, 5)},
            name="PUT /shop/cart-items/[id]/",
        )

    @task(2)
    def sync_cart(self):
        if self._cart_id is None or not self._cart_item_ids:
            return
        # Backend expects a list of {id, quantity} objects (the client's view
        # of which items + quantities should be in the active cart). The sync
        # endpoint deletes any active items NOT in this payload, so cached
        # cart_item_ids may go stale between calls in a flat-weighted scenario.
        payload = [
            {"id": item_id, "quantity": random.randint(1, 3)}
            for item_id in self._cart_item_ids[:10]
        ]
        with self.client.post(
            f"/shop/cart/{self._cart_id}/sync/",
            json=payload,
            name="POST /shop/cart/[id]/sync/",
            catch_response=True,
        ) as r:
            if r.status_code == 400:
                # Stale item id (already deleted by a prior sync) — accept and
                # clear cache so the next add_product re-populates fresh ids.
                r.success()
                self._cart_item_ids = []

    @task(1)
    def add_recipe_to_cart(self):
        if self._cart_id is None or not self._recipe_uuids:
            return
        self.client.post(
            f"/shop/cart/{self._cart_id}/recipe/",
            json={"recipe": random.choice(self._recipe_uuids)},
            name="POST /shop/cart/[id]/recipe/",
        )

    @task(1)
    def start_cook_mode(self):
        if not self._recipe_uuids:
            return
        recipe_uuid = random.choice(self._recipe_uuids)
        self.client.post(
            f"/recipes/{recipe_uuid}/cook-mode/start/",
            json={"products": [], "serving_size": random.choice([1, 2, 4])},
            name="POST /recipes/[uuid]/cook-mode/start/",
        )

    @task(1)
    def update_pantry_after_cook(self):
        if not self._recipe_uuids:
            return
        recipe_uuid = random.choice(self._recipe_uuids)
        self.client.post(
            f"/recipes/{recipe_uuid}/cook-mode/update-pantry/",
            json={"updates": []},
            name="POST /recipes/[uuid]/cook-mode/update-pantry/",
        )

    @task(1)
    def submit_review(self):
        if not self._recipe_uuids:
            return
        recipe_uuid = random.choice(self._recipe_uuids)
        self.client.post(
            f"/recipes/{recipe_uuid}/reviews/",
            json={"stars": random.randint(3, 5), "comment": "Tasty!"},
            name="POST /recipes/[uuid]/reviews/",
        )


@tag("scenario_c_full", "writes", "etl")
class HeavyWriteUser(CartWriteUser):
    """Adds the etl-queue-bound actions (recipe-from-URL, pantry scan)
    excluded from the default Scenario C. Run with `--tags scenario_c_full`
    only when you accept the etl backlog impact.
    """

    @task(2)
    def create_recipe_from_url(self):
        self.client.post(
            "/recipes/create-from-url/",
            json={"url": random.choice(SAMPLE_URLS)},
            name="POST /recipes/create-from-url/",
        )

    @task(5)
    def pantry_scan(self):
        # Posting a tiny placeholder image. Real flow uses image upload —
        # we expect 4xx in unmocked env but the dispatch path is what we
        # want to exercise.
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="image"; filename="x.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
            "\x89PNG\r\n\x1a\n"
            f"\r\n--{boundary}--\r\n"
        ).encode("latin-1")
        self.client.post(
            "/pantry/scan/",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            name="POST /pantry/scan/",
        )
