"""Journey: Returning Meal Planner.

A daily-active user opens the app, checks today's plan, swaps a meal they
don't fancy, marks earlier meals as eaten, and reviews weekly progress.

Exercises the meal-planner's hottest paths — including the lazy
DayAssembler trigger (`GET /meal-planner/today/` first-touch costs 8-14s),
the swap-candidates computation, and the per-mark-eaten async refresh task.

Works with seeded users (already onboarding-complete). No backend changes
needed beyond `LOAD_TEST_MODE=true`.
"""

import random
import time

from locust import SequentialTaskSet, between, tag, task

from common import AuthenticatedHttpUser


@tag("journey", "meal_planner")
class MealPlannerTasks(SequentialTaskSet):
    def on_start(self):
        self.slot_ids = []
        self.recipe_uuids_for_swap = []

    # --- step 1: user opens the app, today's plan loads --------------

    @task
    def open_today(self):
        """First-touch may take 8-14s if the DayAssembler hasn't run yet.
        Repeated calls within the same session should be fast (cached)."""
        with self.client.get(
            "/meal-planner/today/",
            name="01 GET /meal-planner/today/",
            catch_response=True,
        ) as r:
            if r.status_code == 500:
                # Real bug we already documented — seeded users may lack
                # meal-planning targets. Mark and continue rather than abort
                # the whole journey, so we still measure the other steps.
                r.failure("today/ 500 — seed user missing targets (known)")
                self.interrupt()
                return
            if r.status_code != 200:
                return
            try:
                body = r.json()
                self.slot_ids = [s["id"] for s in (body.get("slots") or []) if s.get("id")]
            except (ValueError, KeyError):
                pass

    # --- step 2: prime recipe pool for "swap" / "add" steps ----------

    @task
    def prime_recipe_pool(self):
        with self.client.get(
            "/recipes/list/?page=1",
            name="02 GET /recipes/list/ (prime pool)",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                return
            try:
                results = r.json().get("results") or []
                self.recipe_uuids_for_swap = [x["id"] for x in results if x.get("id")][:10]
            except ValueError:
                pass

    # --- step 3: user adds a slot they want to try today -------------

    @task
    def add_a_slot(self):
        if not self.recipe_uuids_for_swap:
            return
        payload = {
            "recipe_id": random.choice(self.recipe_uuids_for_swap),
            "slot_type": random.choice(("BREAKFAST", "LUNCH", "DINNER", "SNACK")),
        }
        with self.client.post(
            "/meal-planner/today/slots/",
            json=payload,
            name="03 POST /meal-planner/today/slots/ (add)",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201):
                try:
                    slots = r.json().get("slots") or []
                    if slots:
                        latest = max(slots, key=lambda s: s.get("slot_order", 0))
                        if latest.get("id"):
                            self.slot_ids.append(latest["id"])
                except ValueError:
                    pass

    # --- step 4: user explores swap candidates for one slot ----------

    @task
    def view_swap_candidates(self):
        if not self.slot_ids:
            return
        slot = random.choice(self.slot_ids)
        self.client.get(
            f"/meal-planner/today/slots/{slot}/swap-candidates/",
            name="04 GET /meal-planner/today/slots/[id]/swap-candidates/",
        )

    # --- step 5: user marks something as eaten -----------------------

    @task
    def mark_eaten(self):
        if not self.slot_ids:
            return
        slot = random.choice(self.slot_ids)
        # Backend requires servings_multiplier in (0.5, 1.0, 1.5)
        # Dispatches refresh_user_meal_planning_task on Celery default queue
        self.client.post(
            f"/meal-planner/today/slots/{slot}/mark-eaten/",
            json={"servings_multiplier": random.choice(["0.5", "1.0", "1.5"])},
            name="05 POST /meal-planner/today/slots/[id]/mark-eaten/",
        )

    # --- step 6: user checks weekly progress -------------------------

    @task
    def view_weekly_stats(self):
        self.client.get(
            "/meal-planner/weekly-stats/",
            name="06 GET /meal-planner/weekly-stats/",
        )

    @task
    def view_history(self):
        self.client.get(
            "/meal-planner/history/",
            name="07 GET /meal-planner/history/",
        )

    # --- step 7: loop or close app -----------------------------------

    @task
    def loop_or_leave(self):
        # Daily users often revisit the app 2-3x per day — loop 50% of the time
        if random.random() < 0.5:
            time.sleep(random.uniform(3.0, 8.0))
            self.interrupt(reschedule=True)
        else:
            self.interrupt(reschedule=False)


class ReturningMealPlannerUser(AuthenticatedHttpUser):
    wait_time = between(1.5, 5.0)
    tasks = [MealPlannerTasks]
