"""Read-only scenario — shop app.

The only standalone shop read is the cart list. The cart-scoped reads
(cart-items, export-pdf, export-text) need a cart id, so they chain off
/shop/carts/. Seeded users start with no carts, so in a pure-read run the
cart list is usually empty and the chained reads rarely fire — that's
expected. (Cart creation lives in the write scenarios / shop journey.)
The PDF/text export reads are excluded: they 400 unless the cart has active
items, i.e. they need a write to be meaningful.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, read_wait


@tag("reads", "shop", "read")
class ShopReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    def on_start(self):
        super().on_start()
        self._cart_ids = []
        self._refresh_carts()

    def _refresh_carts(self):
        with self.client.get("/shop/carts/", name="GET /shop/carts/", catch_response=True) as r:
            if r.status_code != 200:
                return
            try:
                body = r.json()
            except ValueError:
                return
            # /shop/carts/ returns a bare JSON list (no pagination wrapper).
            if isinstance(body, dict):
                results = body.get("results") or body.get("data") or []
            elif isinstance(body, list):
                results = body
            else:
                results = []
            self._cart_ids = [
                item.get("id") for item in results
                if isinstance(item, dict) and item.get("id") is not None
            ]

    @task(10)
    def list_carts(self):
        self._refresh_carts()

    @task(4)
    def cart_items(self):
        if self._cart_ids:
            cid = random.choice(self._cart_ids)
            self.client.get(
                f"/shop/cart/{cid}/cart-items/",
                name="GET /shop/cart/[id]/cart-items/",
            )
