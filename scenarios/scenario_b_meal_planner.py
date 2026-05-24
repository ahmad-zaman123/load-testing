"""Scenario B — Meal Planner (CPU-bound).

GET /meal-planner/today/ lazily triggers DayAssemblerEngine (8–14s per
first-touch user). This scenario is unique in that the expected ceiling is
much lower than the others — past ~100 users the test mostly characterises
how the system collapses rather than how much more it can handle.

Weights mirror the plan doc. Slot IDs returned by `add slot` are stashed so
mark-eaten/skip have valid targets later in the session.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser


@tag("scenario_b", "meal_planner")
class TodayPlanUser(AuthenticatedHttpUser):
    wait_time = between(2.0, 6.0)

    def on_start(self):
        super().on_start()
        self._recipe_uuids = []
        self._slot_ids = []
        self._prime_recipe_pool()

    def _prime_recipe_pool(self):
        with self.client.get(
            "/recipes/list/?page=1",
            name="GET /recipes/list/ (prime)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                return
            try:
                results = response.json().get("results") or []
            except ValueError:
                return
            self._recipe_uuids = [item.get("id") for item in results if item.get("id")]

    def _pick_slot_id(self):
        if not self._slot_ids:
            return None
        return random.choice(self._slot_ids)

    @task(3)
    def open_today(self):
        self.client.get(
            "/meal-planner/today/",
            name="GET /meal-planner/today/",
        )

    @task(3)
    def add_slot(self):
        if not self._recipe_uuids:
            return
        payload = {
            "recipe_id": random.choice(self._recipe_uuids),
            "slot_type": random.choice(("BREAKFAST", "LUNCH", "DINNER", "SNACK")),
        }
        with self.client.post(
            "/meal-planner/today/slots/",
            json=payload,
            name="POST /meal-planner/today/slots/",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                try:
                    body = response.json()
                    # Response is the full today payload; pull the most recent slot id
                    slots = body.get("slots") or []
                    if slots:
                        latest = max(slots, key=lambda s: s.get("slot_order", 0))
                        if latest.get("id") is not None:
                            self._slot_ids.append(latest["id"])
                except ValueError:
                    pass

    @task(3)
    def mark_eaten(self):
        slot_id = self._pick_slot_id()
        if slot_id is None:
            return
        self.client.post(
            f"/meal-planner/today/slots/{slot_id}/mark-eaten/",
            name="POST /meal-planner/today/slots/[id]/mark-eaten/",
        )

    @task(2)
    def view_weekly_stats(self):
        self.client.get(
            "/meal-planner/weekly-stats/",
            name="GET /meal-planner/weekly-stats/",
        )

    @task(2)
    def swap_candidates(self):
        slot_id = self._pick_slot_id()
        if slot_id is None:
            return
        self.client.get(
            f"/meal-planner/today/slots/{slot_id}/swap-candidates/",
            name="GET /meal-planner/today/slots/[id]/swap-candidates/",
        )

    @task(1)
    def view_history(self):
        self.client.get(
            "/meal-planner/history/",
            name="GET /meal-planner/history/",
        )

    @task(1)
    def skip_slot(self):
        slot_id = self._pick_slot_id()
        if slot_id is None:
            return
        self.client.post(
            f"/meal-planner/today/slots/{slot_id}/skip/",
            name="POST /meal-planner/today/slots/[id]/skip/",
        )
