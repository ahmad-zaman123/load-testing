"""Journey: Recipe Import from URL.

A returning user pastes a recipe URL into the app and waits for the imported
recipe to appear in their list. This exercises the etl-bound code path
(scraper + LLM) and is one of the most expensive flows in the system.

The backend dispatches the import to the `etl` Celery queue (concurrency=2)
and returns quickly. The harness polls the user's recipe list afterward to
simulate "user waits and refreshes to see their import".

Requires `LOAD_TEST_MODE=true` on the backend — otherwise the ScraperAPI
and LLM clients fire for real. **Do not run without mocks.**
"""

import random
import time

from locust import SequentialTaskSet, between, tag, task

from common import AuthenticatedHttpUser


SAMPLE_URLS = (
    "https://www.allrecipes.com/recipe/213742/cheesy-chicken-broccoli-casserole/",
    "https://www.foodnetwork.com/recipes/food-network-kitchen/spaghetti-carbonara",
    "https://www.bbcgoodfood.com/recipes/simple-chocolate-cake",
    "https://www.seriouseats.com/perfect-pan-seared-steak-recipe",
    "https://cooking.nytimes.com/recipes/1019737-skillet-chicken-with-mushrooms",
)


@tag("journey", "import")
class RecipeImportTasks(SequentialTaskSet):
    def on_start(self):
        self.import_dispatched = False

    # --- step 1: user opens the app, checks their existing recipes -----

    @task
    def view_my_recipes_before(self):
        with self.client.get(
            "/recipes/me/",
            name="01 GET /recipes/me/ (before import)",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"my-recipes returned {r.status_code}")

    # --- step 2: user pastes a URL and triggers the import -------------

    @task
    def submit_url_for_import(self):
        url = random.choice(SAMPLE_URLS)
        with self.client.post(
            "/recipes/create-from-url/",
            json={"url": url},
            name="02 POST /recipes/create-from-url/",
            catch_response=True,
        ) as r:
            # Endpoint should return 200/202 (dispatched) quickly. The actual
            # scrape+LLM happens on the etl queue.
            if r.status_code in (200, 201, 202):
                self.import_dispatched = True
            else:
                r.failure(f"create-from-url returned {r.status_code}")

    # --- step 3: user "waits" then refreshes their recipes -------------

    @task
    def wait_for_processing(self):
        # Simulate the user looking away for a bit. The etl pipeline takes
        # 30s+ even with mocks; we wait ~5s here to keep the journey short
        # but realistic for the polling pattern.
        time.sleep(random.uniform(3.0, 6.0))

    @task
    def view_my_recipes_after(self):
        # User refreshes hoping to see the new recipe
        self.client.get(
            "/recipes/me/",
            name="03 GET /recipes/me/ (after import dispatch)",
        )

    # --- step 4: user might trigger another import or leave ------------

    @task
    def loop_or_leave(self):
        # 30% import another, 70% leave. Multiple imports per session is the
        # real "etl queue saturation" stress case.
        if random.random() < 0.3:
            time.sleep(random.uniform(2.0, 6.0))
            self.interrupt(reschedule=True)
        else:
            self.interrupt(reschedule=False)


class RecipeImportUser(AuthenticatedHttpUser):
    wait_time = between(2.0, 6.0)
    tasks = [RecipeImportTasks]
