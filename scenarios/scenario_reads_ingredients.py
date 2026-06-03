"""Read-only scenario — ingredients app.

The ingredients app is mounted at the ROOT prefix, so its read endpoints
live at /ingredients/..., /categories/..., and /pantry/ingredients/.
All are search/list reads; the pantry-ingredient *detail* endpoint is
skipped because its list response is category-grouped (no flat id to chain).
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, load_search_terms, read_wait


SEARCH_TERMS = tuple(load_search_terms())
CATEGORY_TERMS = ("meat", "dairy", "produce", "grain", "spice", "seafood")


@tag("reads", "ingredients", "read")
class IngredientsReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    @task(8)
    def ingredient_search(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/ingredients/search/?search={term}",
            name="GET /ingredients/search/",
        )

    @task(4)
    def ingredient_search_recipe_creation(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/ingredients/search/recipe-creation/?search={term}",
            name="GET /ingredients/search/recipe-creation/",
        )

    @task(4)
    def pantry_ingredient_filter_list(self):
        term = random.choice((None,) + SEARCH_TERMS)
        path = "/ingredients/list/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /ingredients/list/")

    @task(5)
    def category_search(self):
        term = random.choice((None,) + CATEGORY_TERMS)
        path = "/categories/search/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /categories/search/")

    @task(6)
    def pantry_ingredients_grouped(self):
        ordering = random.choice((None, "name", "-name"))
        path = "/pantry/ingredients/"
        if ordering:
            path += f"?ordering={ordering}"
        self.client.get(path, name="GET /pantry/ingredients/")
