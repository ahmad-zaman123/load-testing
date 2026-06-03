"""Read-only scenario — meal planner app.

Covers the meal-planner GET endpoints. Two caveats baked into the weights:

  * GET /meal-planner/today/ lazily triggers the DayAssemblerEngine (8-14s)
    on first touch if the day isn't assembled — it's a read that can do heavy
    work, so it's kept at a modest weight and not hammered.
  * /today/, /weekly-stats/ gate on a complete nutrition profile and return
    400 + missing_fields if incomplete; we treat that 400 as a valid response
    (it's the documented contract, not a load failure).

The PDF export reads are included at low weight (they generate a document,
so they're heavier than a JSON read). The swap-candidates read is excluded:
it needs a DaySlot id created by a write.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, load_search_terms, read_wait


SEARCH_TERMS = tuple(load_search_terms())


@tag("reads", "meal-planner", "read")
class MealPlannerReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    def _get_profile_gated(self, path, name):
        with self.client.get(path, name=name, catch_response=True) as r:
            if r.status_code in (400, 404):
                # Documented: incomplete profile → 400 + missing_fields;
                # nothing to export yet (no history/stats) → 404.
                r.success()

    @task(5)
    def today(self):
        self._get_profile_gated("/meal-planner/today/", "GET /meal-planner/today/")

    @task(4)
    def weekly_stats(self):
        self._get_profile_gated("/meal-planner/weekly-stats/", "GET /meal-planner/weekly-stats/")

    @task(3)
    def meal_frequency(self):
        self.client.get("/meal-planner/meal-frequency/", name="GET /meal-planner/meal-frequency/")

    @task(5)
    def eligible_recipes(self):
        term = random.choice((None,) + SEARCH_TERMS)
        path = "/meal-planner/recipes/"
        if term:
            path += f"?search={term}"
        self.client.get(path, name="GET /meal-planner/recipes/")

    @task(4)
    def history(self):
        self.client.get("/meal-planner/history/", name="GET /meal-planner/history/")

    @task(3)
    def plans(self):
        self.client.get("/meal-planner/plans/", name="GET /meal-planner/plans/")

    @task(3)
    def recently_eaten(self):
        limit = random.choice((10, 20, 50))
        self.client.get(
            f"/meal-planner/recently-eaten/?limit={limit}",
            name="GET /meal-planner/recently-eaten/",
        )

    @task(1)
    def weekly_stats_pdf(self):
        self._get_profile_gated(
            "/meal-planner/weekly-stats/pdf/", "GET /meal-planner/weekly-stats/pdf/"
        )

    @task(1)
    def history_pdf(self):
        self._get_profile_gated("/meal-planner/history/pdf/", "GET /meal-planner/history/pdf/")
