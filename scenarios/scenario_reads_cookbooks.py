"""Read-only scenario — cookbooks app.

Covers the user's own cookbook list/detail and the community cookbook
list/detail. Detail reads chain off the corresponding list. Seeded users
own no cookbooks (their /cookbooks/ list is empty but still exercises the
query); community cookbooks are global, so the community detail read hits
the heavy prefetch path.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, read_wait


CB_ORDERINGS = (None, "name", "-name", "created", "-created", "modified", "-modified")


@tag("reads", "cookbooks", "read")
class CookbooksReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    def on_start(self):
        super().on_start()
        self._own_ids = []
        self._community_ids = []
        self._refresh_own()
        self._refresh_community()

    def _ids_from(self, response):
        try:
            body = response.json()
        except ValueError:
            return []
        if isinstance(body, dict):
            results = body.get("results") or body.get("data") or []
        elif isinstance(body, list):
            results = body
        else:
            results = []
        return [item.get("id") for item in results if isinstance(item, dict) and item.get("id")]

    def _refresh_own(self):
        with self.client.get("/cookbooks/", name="GET /cookbooks/", catch_response=True) as r:
            if r.status_code == 200:
                self._own_ids = self._ids_from(r)

    def _refresh_community(self):
        with self.client.get(
            "/cookbooks/community-cookbooks/",
            name="GET /cookbooks/community-cookbooks/",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                self._community_ids = self._ids_from(r)

    # --- list reads -------------------------------------------------------

    @task(6)
    def own_list(self):
        ordering = random.choice(CB_ORDERINGS)
        path = "/cookbooks/"
        if ordering:
            path += f"?ordering={ordering}"
        with self.client.get(path, name="GET /cookbooks/", catch_response=True) as r:
            if r.status_code == 200:
                ids = self._ids_from(r)
                if ids:
                    self._own_ids = ids

    @task(8)
    def community_list(self):
        with self.client.get(
            "/cookbooks/community-cookbooks/",
            name="GET /cookbooks/community-cookbooks/",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                ids = self._ids_from(r)
                if ids:
                    self._community_ids = ids

    # --- detail reads (chained) -------------------------------------------

    @task(3)
    def own_detail(self):
        if self._own_ids:
            cid = random.choice(self._own_ids)
            self.client.get(f"/cookbooks/{cid}/", name="GET /cookbooks/[id]/")

    @task(5)
    def community_detail(self):
        if self._community_ids:
            cid = random.choice(self._community_ids)
            self.client.get(
                f"/cookbooks/community-cookbooks/{cid}/",
                name="GET /cookbooks/community-cookbooks/[id]/",
            )
