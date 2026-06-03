"""Read-only scenario — recipes app.

Comprehensive coverage of every recipe GET endpoint (mobile API), including
the ones Scenario A doesn't touch: preparation-type, shop-list, me,
cook-mode, cook-mode/instructions, recommended-products. Detail-style reads
chain off a recipe-uuid pool refreshed from /recipes/list/, the same way a
real user clicks through from a list.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, load_search_terms, read_wait


SEARCH_TERMS = tuple(load_search_terms())
CUISINE_FILTERS = (None, None, None, "italian", "indian", "mexican", "asian")


@tag("reads", "recipes", "read")
class RecipesReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    def on_start(self):
        super().on_start()
        self._recipe_uuids = []
        self._load_reference_data()
        self._refresh_recipe_pool()

    # --- session-once reference data (cached 1h backend-side) -------------

    def _load_reference_data(self):
        for path in (
            "/recipes/cuisines/",
            "/recipes/dietary-preferences/",
            "/recipes/allergies/",
            "/recipes/meals/",
            "/recipes/preparation-type/",
        ):
            self.client.get(path, name=f"REF {path}")

    # --- helpers ----------------------------------------------------------

    def _refresh_recipe_pool(self):
        with self.client.get(
            "/recipes/list/?page=1",
            name="GET /recipes/list/",
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
                self._recipe_uuids = uuids

    def _pick(self):
        if not self._recipe_uuids:
            self._refresh_recipe_pool()
        return random.choice(self._recipe_uuids) if self._recipe_uuids else None

    # --- list / discovery reads -------------------------------------------

    @task(10)
    def browse_recipes(self):
        page = random.randint(1, 10)
        cuisine = random.choice(CUISINE_FILTERS)
        params = f"?page={page}"
        if cuisine:
            params += f"&cuisine={cuisine}"
        self.client.get(f"/recipes/list/{params}", name="GET /recipes/list/")

    @task(5)
    def search_recipes(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(f"/recipes/list/?search={term}", name="GET /recipes/list/?search=")

    @task(2)
    def shop_list(self):
        self.client.get("/recipes/shop-list/", name="GET /recipes/shop-list/")

    @task(3)
    def recommended(self):
        self.client.get("/recipes/recommended/", name="GET /recipes/recommended/")

    @task(2)
    def trending(self):
        self.client.get("/recipes/trending/", name="GET /recipes/trending/")

    @task(1)
    def my_recipes(self):
        self.client.get("/recipes/me/", name="GET /recipes/me/")

    # --- detail reads (chained off the uuid pool) -------------------------

    @task(8)
    def recipe_detail(self):
        rid = self._pick()
        if rid:
            self.client.get(f"/recipes/{rid}/", name="GET /recipes/[uuid]/")

    @task(4)
    def recipe_reviews(self):
        rid = self._pick()
        if rid:
            self.client.get(f"/recipes/{rid}/reviews/", name="GET /recipes/[uuid]/reviews/")

    @task(2)
    def recipe_products(self):
        rid = self._pick()
        if rid:
            self.client.get(f"/recipes/{rid}/products/", name="GET /recipes/[uuid]/products/")

    @task(3)
    def cook_mode(self):
        rid = self._pick()
        if rid:
            self.client.get(f"/recipes/{rid}/cook-mode/", name="GET /recipes/[uuid]/cook-mode/")

    @task(2)
    def cook_mode_instructions(self):
        rid = self._pick()
        if rid:
            serving = random.randint(1, 6)
            self.client.get(
                f"/recipes/{rid}/cook-mode/instructions/?serving_size={serving}",
                name="GET /recipes/[uuid]/cook-mode/instructions/",
            )

    @task(2)
    def recommended_products(self):
        rid = self._pick()
        if rid:
            self.client.get(
                f"/recipes/{rid}/recommended-products/",
                name="GET /recipes/[uuid]/recommended-products/",
            )
