"""Read-only scenario — products app.

Covers every product GET endpoint (mobile API). Detail and swappable-list
reads chain off a product-uuid pool refreshed from /products/list/.
"""

import os
import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, load_search_terms, read_wait


SEARCH_TERMS = tuple(load_search_terms())
LOOKUP_TITLES = ("milk", "eggs", "chicken breast", "olive oil", "tomato", "rice")

# /products/ingredient-lookup/ is the one read endpoint that can fire an
# EXTERNAL call: on a cache miss it computes an OpenAI text embedding
# (find_ingredient_by_product_title -> openai_embeddings.get_embeddings).
# It's cached 24h per title, but to keep read runs safe WITHOUT enabling the
# backend's LOAD_TEST_MODE (which mocks the LLM clients), it's opt-in. Set
# LOAD_TEST_INCLUDE_EXTERNAL_READS=1 to include it (do this only when
# LOAD_TEST_MODE is on, or you accept the ~6 real embedding calls).
INCLUDE_EXTERNAL_READS = os.environ.get(
    "LOAD_TEST_INCLUDE_EXTERNAL_READS", ""
).lower() in ("1", "true", "yes")


@tag("reads", "products", "read")
class ProductsReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    def on_start(self):
        super().on_start()
        self._product_uuids = []
        self._refresh_product_pool()

    def _refresh_product_pool(self):
        with self.client.get(
            "/products/list/",
            name="GET /products/list/",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"list returned {response.status_code}")
                return
            try:
                body = response.json()
            except ValueError:
                response.failure("list response was not JSON")
                return
            results = body.get("results") or body.get("data") or []
            uuids = [item.get("id") for item in results if item.get("id")]
            if uuids:
                self._product_uuids = uuids

    def _pick(self):
        if not self._product_uuids:
            self._refresh_product_pool()
        return random.choice(self._product_uuids) if self._product_uuids else None

    # --- list reads -------------------------------------------------------

    @task(10)
    def list_products(self):
        term = random.choice((None, None) + SEARCH_TERMS)
        path = "/products/list/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /products/list/")

    @task(3)
    def shop_list(self):
        self.client.get("/products/shop-list/", name="GET /products/shop-list/")

    @task(2)
    def chatgpt_list(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(f"/products/chatgpt/?search={term}", name="GET /products/chatgpt/")

    @task(1)
    def my_products(self):
        self.client.get("/products/me/", name="GET /products/me/")

    @task(2)
    def ingredient_lookup(self):
        # Opt-in only — fires an OpenAI embedding on cache miss. See module note.
        if not INCLUDE_EXTERNAL_READS:
            return
        title = random.choice(LOOKUP_TITLES)
        self.client.get(
            f"/products/ingredient-lookup/?product_title={title}",
            name="GET /products/ingredient-lookup/",
        )

    # --- detail reads (chained) -------------------------------------------

    @task(6)
    def product_detail(self):
        pid = self._pick()
        if pid:
            self.client.get(f"/products/{pid}/", name="GET /products/[uuid]/")

    @task(3)
    def swappable_list(self):
        pid = self._pick()
        if pid:
            self.client.get(
                f"/products/{pid}/swappable-list/",
                name="GET /products/[uuid]/swappable-list/",
            )
