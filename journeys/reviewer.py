"""Journey: Power Reviewer.

A power user (food blogger, super-engaged user) who cooks multiple recipes
in one session and leaves a review for each. Reviews trigger nutritional
score recalculation on the default Celery queue, so this journey exercises
the review write path + the dispatch fan-out at higher than normal rates.

Different from `returning_user_cook` in that one session = N cook+review
iterations (instead of N sessions × 1 each). Tests batched-write throughput
on the reviews table.
"""

import random
import time

from locust import SequentialTaskSet, between, tag, task

from common import AuthenticatedHttpUser


REVIEW_PHRASES = (
    "Five stars, perfect for a weeknight.",
    "Will absolutely make again.",
    "Easy to follow, great result.",
    "Family devoured it.",
    "Took me about 30 min start to finish.",
    "Swapped paprika for chili — worked great.",
    "Will halve the salt next time.",
    "Crowd pleaser. Used canned tomatoes — fine.",
)

REVIEWS_PER_SESSION = (3, 8)  # range — how many recipes this user reviews in one session


@tag("journey", "reviewer")
class ReviewerTasks(SequentialTaskSet):
    def on_start(self):
        self.recipe_uuids = []
        self.target_review_count = random.randint(*REVIEWS_PER_SESSION)
        self.reviews_submitted = 0

    # --- step 1: load a pool of recipes to review --------------------

    @task
    def prime_pool(self):
        with self.client.get(
            "/recipes/list/?page=1",
            name="01 GET /recipes/list/ (prime pool)",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                self.interrupt()
                return
            try:
                results = r.json().get("results") or []
                self.recipe_uuids = [x["id"] for x in results if x.get("id")]
            except ValueError:
                self.interrupt()
                return
            if not self.recipe_uuids:
                self.interrupt()

    # --- step 2: cook + review loop ----------------------------------

    @task
    def cook_and_review_one(self):
        """One iteration of: open detail → start cook → finish cook → review.
        Repeats up to self.target_review_count times within the same VU."""
        if not self.recipe_uuids:
            self.interrupt()
            return

        recipe = random.choice(self.recipe_uuids)

        self.client.get(
            f"/recipes/{recipe}/",
            name="02 GET /recipes/[uuid]/",
        )

        self.client.post(
            f"/recipes/{recipe}/cook-mode/start/",
            json={"products": [], "serving_size": random.choice([1, 2, 4])},
            name="03 POST /recipes/[uuid]/cook-mode/start/",
        )

        self.client.post(
            f"/recipes/{recipe}/cook-mode/update-pantry/",
            json={"updates": []},
            name="04 POST /recipes/[uuid]/cook-mode/update-pantry/",
        )

        with self.client.post(
            f"/recipes/{recipe}/reviews/",
            json={
                "stars": random.randint(3, 5),
                "comment": random.choice(REVIEW_PHRASES),
            },
            name="05 POST /recipes/[uuid]/reviews/",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201):
                self.reviews_submitted += 1

        # Loop or exit
        if self.reviews_submitted < self.target_review_count:
            time.sleep(random.uniform(2.0, 5.0))
        else:
            self.interrupt(reschedule=False)


class ReviewerUser(AuthenticatedHttpUser):
    wait_time = between(1.0, 3.0)
    tasks = [ReviewerTasks]
