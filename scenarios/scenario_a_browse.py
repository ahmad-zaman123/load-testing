"""Scenario A — Read-heavy browsing.

Simulates the most common user journey: open the app, browse and search the
recipe catalogue, drill into a recipe's detail page, reviews, and shopping
ingredients. Weights mirror the plan doc.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser


SEARCH_TERMS = (
    "chicken",
    "pasta",
    "salad",
    "rice",
    "beef",
    "vegetarian",
    "soup",
    "breakfast",
    "smoothie",
    "salmon",
    "curry",
    "tofu",
    "quinoa",
    "tomato",
    "egg",
)

CUISINE_FILTERS = (None, None, None, "italian", "indian", "mexican", "asian")


@tag("scenario_a", "browse", "read")
class BrowseUser(AuthenticatedHttpUser):
    """Read-heavy browsing user. Holds a small cache of recipe UUIDs picked
    from the list response so detail/reviews/products tasks have realistic
    targets — same pattern a real user follows after clicking from a list.
    """

    wait_time = between(1.0, 4.0)

    def on_start(self):
        super().on_start()
        self._recipe_uuids = []
        self._load_reference_data()
        self._refresh_recipe_pool()

    # --- session-once reference data --------------------------------------

    def _load_reference_data(self):
        for path in (
            "/recipes/cuisines/",
            "/recipes/dietary-preferences/",
            "/recipes/allergies/",
            "/recipes/meals/",
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

    def _pick_recipe_uuid(self):
        if not self._recipe_uuids:
            self._refresh_recipe_pool()
        if not self._recipe_uuids:
            return None
        return random.choice(self._recipe_uuids)

    # --- weighted tasks ---------------------------------------------------

    @task(10)
    def browse_recipes(self):
        page = random.randint(1, 10)
        cuisine = random.choice(CUISINE_FILTERS)
        params = f"?page={page}"
        if cuisine:
            params += f"&cuisine={cuisine}"
        self.client.get(f"/recipes/list/{params}", name="GET /recipes/list/")

    @task(8)
    def view_recipe_detail(self):
        uuid_value = self._pick_recipe_uuid()
        if not uuid_value:
            return
        self.client.get(
            f"/recipes/{uuid_value}/",
            name="GET /recipes/[uuid]/",
        )

    @task(5)
    def search_recipes(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/recipes/list/?search={term}",
            name="GET /recipes/list/?search=",
        )

    @task(4)
    def read_reviews(self):
        uuid_value = self._pick_recipe_uuid()
        if not uuid_value:
            return
        self.client.get(
            f"/recipes/{uuid_value}/reviews/",
            name="GET /recipes/[uuid]/reviews/",
        )

    @task(3)
    def view_recommended(self):
        self.client.get("/recipes/recommended/", name="GET /recipes/recommended/")

    @task(2)
    def view_trending(self):
        self.client.get("/recipes/trending/", name="GET /recipes/trending/")

    @task(2)
    def view_recipe_products(self):
        uuid_value = self._pick_recipe_uuid()
        if not uuid_value:
            return
        self.client.get(
            f"/recipes/{uuid_value}/products/",
            name="GET /recipes/[uuid]/products/",
        )
