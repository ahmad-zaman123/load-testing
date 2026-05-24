"""Journey: Shop and Checkout.

User searches for a recipe, decides to cook it tonight, adds the recipe's
ingredients to their cart, adjusts a couple of quantities, and proceeds to
the Walmart checkout link.

Exercises the cart write path heavily — especially the recipe-add fan-out
that inserts N cart items in one call, and the cart sync that dispatches
the refresh task.

Works with seeded users + `LOAD_TEST_MODE=true`.
"""

import random
import time

from locust import SequentialTaskSet, between, tag, task

from common import AuthenticatedHttpUser


SEARCH_TERMS = (
    "chicken",
    "pasta",
    "salad",
    "soup",
    "stir fry",
    "tacos",
    "curry",
)


@tag("journey", "shop")
class ShopAndCheckoutTasks(SequentialTaskSet):
    def on_start(self):
        self.cart_id = None
        self.recipe_uuid = None
        self.product_ids = []
        self.cart_item_ids = []

    # --- step 1: user opens shop, app pulls their active cart -------

    @task
    def fetch_cart(self):
        with self.client.get(
            "/shop/carts/",
            name="01 GET /shop/carts/",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"carts list returned {r.status_code}")
                self.interrupt()
                return
            try:
                body = r.json()
            except ValueError:
                r.failure("carts not JSON")
                self.interrupt()
                return
            carts = body if isinstance(body, list) else body.get("results") or []
            if carts:
                self.cart_id = carts[0].get("id")
            if not self.cart_id:
                r.failure("no cart id found")
                self.interrupt()

    # --- step 2: user searches for a recipe to cook tonight ---------

    @task
    def search_for_recipe(self):
        term = random.choice(SEARCH_TERMS)
        with self.client.get(
            f"/recipes/list/?search={term}",
            name="02 GET /recipes/list/?search=",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                return
            try:
                results = r.json().get("results") or []
            except ValueError:
                return
            if results:
                self.recipe_uuid = random.choice(results).get("id")

    # --- step 3: user opens the recipe and checks ingredients -------

    @task
    def open_detail(self):
        if not self.recipe_uuid:
            self.interrupt()
            return
        self.client.get(
            f"/recipes/{self.recipe_uuid}/",
            name="03 GET /recipes/[uuid]/",
        )

    @task
    def view_products_needed(self):
        if not self.recipe_uuid:
            return
        with self.client.get(
            f"/recipes/{self.recipe_uuid}/products/",
            name="04 GET /recipes/[uuid]/products/",
            catch_response=True,
        ) as r:
            if r.status_code == 400:
                # Known case: recipe missing approved product for some ingredient
                r.success()
                return
            if r.status_code != 200:
                return
            try:
                products = r.json() if isinstance(r.json(), list) else r.json().get("results") or []
                self.product_ids = [p.get("id") for p in products if p.get("id")][:10]
            except ValueError:
                pass

    # --- step 4: user adds the whole recipe to their cart -----------

    @task
    def add_recipe_to_cart(self):
        if self.cart_id is None or not self.recipe_uuid:
            return
        self.client.post(
            f"/shop/cart/{self.cart_id}/recipe/",
            json={"recipe": self.recipe_uuid},
            name="05 POST /shop/cart/[id]/recipe/",
        )

    # --- step 5: user adds a couple of standalone items -------------

    @task
    def add_individual_products(self):
        if self.cart_id is None:
            return
        # Need product IDs — pull from products endpoint if we got them
        if not self.product_ids:
            # Fall back to a generic prime
            with self.client.get(
                "/products/list/?page=1",
                name="05a GET /products/list/ (prime)",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    try:
                        body = r.json()
                        self.product_ids = [
                            p.get("id")
                            for p in (body.get("results") or [])
                            if p.get("id")
                        ][:10]
                    except ValueError:
                        pass

        for _ in range(random.randint(1, 3)):
            if not self.product_ids:
                break
            with self.client.post(
                f"/shop/cart/{self.cart_id}/product/",
                json={"product": random.choice(self.product_ids), "quantity": 1},
                name="06 POST /shop/cart/[id]/product/",
                catch_response=True,
            ) as r:
                if r.status_code in (200, 201):
                    try:
                        item_id = r.json().get("id")
                        if item_id is not None:
                            self.cart_item_ids.append(item_id)
                    except ValueError:
                        pass

    # --- step 6: user tweaks quantities ----------------------------

    @task
    def adjust_quantities(self):
        if not self.cart_item_ids:
            return
        item = random.choice(self.cart_item_ids)
        self.client.put(
            f"/shop/cart-items/{item}/",
            json={"quantity": random.randint(1, 4)},
            name="07 PUT /shop/cart-items/[id]/",
        )

    # --- step 7: user reviews their cart contents ------------------

    @task
    def view_cart(self):
        if self.cart_id is None:
            return
        self.client.get(
            f"/shop/cart/{self.cart_id}/cart-items/",
            name="08 GET /shop/cart/[id]/cart-items/",
        )

    # --- step 8: user syncs cart then heads to checkout ------------

    @task
    def sync_cart(self):
        if self.cart_id is None:
            return
        self.client.post(
            f"/shop/cart/{self.cart_id}/sync/",
            name="09 POST /shop/cart/[id]/sync/",
        )

    @task
    def go_to_walmart_checkout(self):
        if self.cart_id is None:
            return
        # This endpoint builds the Walmart-affiliate URL; doesn't actually
        # post to Walmart. Mocked or not, it's a read-only computation.
        self.client.post(
            "/shop/cart/walmart-checkout/",
            json={"cart_id": self.cart_id},
            name="10 POST /shop/cart/walmart-checkout/",
        )

    @task
    def end(self):
        time.sleep(random.uniform(0.5, 2.0))
        self.interrupt(reschedule=False)


class ShopAndCheckoutUser(AuthenticatedHttpUser):
    wait_time = between(1.5, 5.0)
    tasks = [ShopAndCheckoutTasks]
