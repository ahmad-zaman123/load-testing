"""Category scenarios — endpoints grouped by measured load class.

Unlike the per-app read scenarios, these group endpoints by the latency/cost
class established in the incremental load-test report (P95 @ 100 users):

    light    P95 < 1000ms,  ~90-110 req/s   cheap reads
    medium   P95 1000-2500ms, ~45-80 req/s  mid-tier reads
    heavy    P95 > 2500ms,  <= ~21 req/s     expensive list/aggregation reads

Purpose: run one class at a time (isolated) and then `cat-all` (blended) while
sampling server CPU/memory (scripts/watch_stats.sh), to attribute resource cost
to a category and detect contention when the categories run together.

Each class hits ONLY its bucket's endpoints with no reference-data or uuid-pool
warmup in on_start, so the resource measurement is not contaminated by calls
from other buckets. The `name=` labels match the per-app read scenarios so the
stats line up with the existing report.

The 3 endpoints that fail under load in the report (users, users-document,
users-me) are deliberately excluded — 100% failures exercise atypical paths and
skew a category comparison.
"""

import random

from locust import tag, task

from common import AuthenticatedHttpUser, load_search_terms, read_wait


SEARCH_TERMS = tuple(load_search_terms())
CATEGORY_TERMS = ("meat", "dairy", "produce", "grain", "spice", "seafood")
RECENTLY_EATEN_LIMITS = (10, 20, 50)


# --- light -------------------------------------------------------------------


@tag("reads", "category", "light")
class LightReadUser(AuthenticatedHttpUser):
    """P95 < 1000ms bucket — 11 cheap reads."""

    wait_time = read_wait()

    @task
    def recipes_meals(self):
        self.client.get("/recipes/meals/", name="GET /recipes/meals/")

    @task
    def shop_carts(self):
        self.client.get("/shop/carts/", name="GET /shop/carts/")

    @task
    def meal_planner_recently_eaten(self):
        limit = random.choice(RECENTLY_EATEN_LIMITS)
        self.client.get(
            f"/meal-planner/recently-eaten/?limit={limit}",
            name="GET /meal-planner/recently-eaten/",
        )

    @task
    def recipes_dietary_preferences(self):
        self.client.get("/recipes/dietary-preferences/", name="GET /recipes/dietary-preferences/")

    @task
    def communications_notification_preferences(self):
        self.client.get(
            "/communications/notification-preferences/",
            name="GET /communications/notification-preferences/",
        )

    @task
    def meal_planner_meal_frequency(self):
        self.client.get("/meal-planner/meal-frequency/", name="GET /meal-planner/meal-frequency/")

    @task
    def recipes_allergies(self):
        self.client.get("/recipes/allergies/", name="GET /recipes/allergies/")

    @task
    def recipes_preparation_type(self):
        self.client.get("/recipes/preparation-type/", name="GET /recipes/preparation-type/")

    @task
    def communications_notifications(self):
        self.client.get(
            "/communications/notifications/",
            name="GET /communications/notifications/",
        )

    @task
    def recipes_cuisines(self):
        self.client.get("/recipes/cuisines/", name="GET /recipes/cuisines/")

    @task
    def pantry_history(self):
        self.client.get("/pantry/history/", name="GET /pantry/history/")


# --- medium ------------------------------------------------------------------


@tag("reads", "category", "medium")
class MediumReadUser(AuthenticatedHttpUser):
    """P95 1000-2500ms bucket — 16 mid-tier reads."""

    wait_time = read_wait()

    def _get_profile_gated(self, path, name):
        # today/weekly-stats return 400 + missing_fields on an incomplete
        # nutrition profile, 404 when there is nothing to assemble yet. Both
        # are documented contract responses, not load failures.
        with self.client.get(path, name=name, catch_response=True) as r:
            if r.status_code in (400, 404):
                r.success()

    @task
    def products_me(self):
        self.client.get("/products/me/", name="GET /products/me/")

    @task
    def products_shop_list(self):
        self.client.get("/products/shop-list/", name="GET /products/shop-list/")

    @task
    def recipes_recommended(self):
        self.client.get("/recipes/recommended/", name="GET /recipes/recommended/")

    @task
    def meal_planner_weekly_stats(self):
        self._get_profile_gated("/meal-planner/weekly-stats/", "GET /meal-planner/weekly-stats/")

    @task
    def categories_search(self):
        term = random.choice((None,) + CATEGORY_TERMS)
        path = "/categories/search/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /categories/search/")

    @task
    def meal_planner_plans(self):
        self.client.get("/meal-planner/plans/", name="GET /meal-planner/plans/")

    @task
    def meal_planner_recipes(self):
        term = random.choice((None,) + SEARCH_TERMS)
        path = "/meal-planner/recipes/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /meal-planner/recipes/")

    @task
    def ingredients_list(self):
        term = random.choice((None,) + SEARCH_TERMS)
        path = "/ingredients/list/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /ingredients/list/")

    @task
    def ingredients_search(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(f"/ingredients/search/?search={term}", name="GET /ingredients/search/")

    @task
    def products_list(self):
        self.client.get("/products/list/", name="GET /products/list/")

    @task
    def recipes_shop_list(self):
        self.client.get("/recipes/shop-list/", name="GET /recipes/shop-list/")

    @task
    def ingredients_search_recipe_creation(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/ingredients/search/recipe-creation/?search={term}",
            name="GET /ingredients/search/recipe-creation/",
        )

    @task
    def meal_planner_today(self):
        # A read that lazily triggers the DayAssemblerEngine (8-14s) on first
        # touch if the day is not assembled — kept at single weight, not hammered.
        self._get_profile_gated("/meal-planner/today/", "GET /meal-planner/today/")

    @task
    def users_quick_actions_list(self):
        self.client.get("/users/quick-actions/list/", name="GET /users/quick-actions/list/")

    @task
    def recipes_trending(self):
        self.client.get("/recipes/trending/", name="GET /recipes/trending/")

    @task
    def recipes_me(self):
        self.client.get("/recipes/me/", name="GET /recipes/me/")


# --- heavy -------------------------------------------------------------------


@tag("reads", "category", "heavy")
class HeavyReadUser(AuthenticatedHttpUser):
    """P95 > 2500ms bucket — 6 expensive list/aggregation reads."""

    wait_time = read_wait()

    @task
    def pantry_ingredients(self):
        ordering = random.choice((None, "name", "-name"))
        path = "/pantry/ingredients/"
        if ordering:
            path += f"?ordering={ordering}"
        self.client.get(path, name="GET /pantry/ingredients/")

    @task
    def cookbooks_community_cookbooks(self):
        self.client.get(
            "/cookbooks/community-cookbooks/",
            name="GET /cookbooks/community-cookbooks/",
        )

    @task
    def cookbooks(self):
        self.client.get("/cookbooks/", name="GET /cookbooks/")

    @task
    def recipes_list(self):
        page = random.randint(1, 10)
        term = random.choice((None,) + SEARCH_TERMS)
        path = f"/recipes/list/?page={page}"
        if term:
            path += f"&search={term}"
        self.client.get(path, name="GET /recipes/list/")

    @task
    def pantry_list(self):
        self.client.get("/pantry/list/", name="GET /pantry/list/")

    @task
    def pantry_expiring(self):
        self.client.get("/pantry/expiring/", name="GET /pantry/expiring/")
