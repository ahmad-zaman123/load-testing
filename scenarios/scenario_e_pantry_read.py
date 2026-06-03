"""Scenario E — Pantry read-only.

Exercises every read (GET) endpoint the pantry app exposes, so a Phase-1
single-droplet baseline can isolate which pantry reads are slow under
concurrency — the same treatment Scenario A gives the recipe catalogue.

Pantry read endpoints (mounted under /pantry/, see easychef.pantry.urls):
    GET /pantry/list/       full active pantry, heavy select_related + prefetch
                            + per-category grouping. Supports ?ordering=
                            product__title | created | expiration (prefix "-"
                            for descending).
    GET /pantry/expiring/   items expiring within 14 days, categorized.
    GET /pantry/history/    PantryItemLog feed (ListAPIView, paginated).
                            Filterable by action, source, product,
                            created_after, created_before.

The scan-status read (GET /pantry/scan/<uuid>/) is intentionally excluded:
it needs a live scan session from a prior write, so it's covered by the
pantry-scan journey instead, not by a standalone read scenario.

Weights mirror real pantry usage: opening the pantry list dominates,
expiring is a periodic check, history is browsed occasionally.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, read_wait


# Mirrors easychef.pantry.filters.PantryItemOrderingFilter.ordering_fields.
LIST_ORDERINGS = (
    None,               # default ordering (product__title)
    "product__title",
    "-product__title",
    "created",
    "-created",
    "expiration",
    "-expiration",
)

# Mirrors easychef.pantry.choices.PantryItemAction / PantryItemSource.
HISTORY_ACTIONS = (None, "ADDED", "CONSUMED", "ADJUSTED", "RESTOCKED", "REMOVED")
HISTORY_SOURCES = (None, "MANUAL", "RECIPE", "SHOP", "SCAN")


@tag("scenario_e", "pantry", "read")
class PantryReadUser(AuthenticatedHttpUser):
    """Read-only pantry user. Token comes from the seeded fixture; each
    seeded account has a stocked pantry (LOAD_TEST_PANTRY_ITEMS), so these
    reads hit real rows and exercise the prefetch / categorization cost.
    """

    wait_time = read_wait()

    # --- weighted tasks ---------------------------------------------------

    @task(10)
    def view_pantry(self):
        ordering = random.choice(LIST_ORDERINGS)
        path = "/pantry/list/"
        if ordering:
            path += f"?ordering={ordering}"
        self.client.get(path, name="GET /pantry/list/")

    @task(4)
    def view_expiring(self):
        self.client.get("/pantry/expiring/", name="GET /pantry/expiring/")

    @task(5)
    def view_history(self):
        params = []
        action = random.choice(HISTORY_ACTIONS)
        if action:
            params.append(f"action={action}")
        source = random.choice(HISTORY_SOURCES)
        if source:
            params.append(f"source={source}")
        path = "/pantry/history/"
        if params:
            path += "?" + "&".join(params)
        self.client.get(path, name="GET /pantry/history/")
