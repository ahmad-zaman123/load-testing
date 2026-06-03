"""Read-only scenario — users app.

Reads a logged-in user hits: own profile (/users/me/), quick actions,
onboarding previews, legal documents, and a chef profile. Most operate on
request.user (no id needed); chef-profile takes a user uuid — we use the
session's own user_id (every seeded token carries one).

Onboarding previews gate on a complete profile (400 / 404 when incomplete);
those are treated as valid documented responses, not load failures.
"""

import random

from locust import between, tag, task

from common import AuthenticatedHttpUser, read_wait


PREVIEW_TYPES = ("bmi", "daily_intake", "meal_split", "summary")
DOC_TYPES = ("privacy_policy", "terms_of_use", "return_policy")


@tag("reads", "users", "read")
class UsersReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    @task(10)
    def me(self):
        self.client.get("/users/me/", name="GET /users/me/")

    @task(5)
    def quick_actions(self):
        self.client.get("/users/quick-actions/list/", name="GET /users/quick-actions/list/")

    @task(4)
    def onboarding_preview(self):
        preview = random.choice(PREVIEW_TYPES)
        with self.client.get(
            f"/users/onboarding/{preview}/",
            name="GET /users/onboarding/[type]/",
            catch_response=True,
        ) as r:
            if r.status_code in (400, 404):
                # Documented: incomplete/!done profile → 400/404.
                r.success()

    @task(3)
    def document(self):
        doc = random.choice(DOC_TYPES)
        with self.client.get(
            f"/users/document-retrieve/?type={doc}",
            name="GET /users/document-retrieve/",
            catch_response=True,
        ) as r:
            if r.status_code in (400, 404):
                # Documented: unknown type → 400, unseeded document → 404.
                # Not every env has all legal docs loaded.
                r.success()

    @task(4)
    def chef_profile(self):
        self.client.get(
            f"/users/{self.user_id}/chef-profile/",
            name="GET /users/[uuid]/chef-profile/",
        )
