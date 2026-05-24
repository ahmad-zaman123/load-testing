"""Journey: Onboarding → First Cook.

Each virtual user represents a brand-new user who registers, verifies email
via OTP, completes the onboarding wizard, browses the catalogue, picks a
recipe, and cooks it. This is the highest-fidelity "first user experience"
load test we have.

**REQUIRES BACKEND SUPPORT** for the OTP step. See docs/backend-contract.md
§ "Known friction points" for details. Without it, the verify-otp step 4xxs
and the journey aborts — which still gives you `register` + `resend-otp`
throughput numbers but not the rest.

The backend shortcut (recommended): when `LOAD_TEST_MODE=true` on the
backend, `/users/auth/verify-otp/` accepts a fixed value (default `0000`)
for any `loadtest+*@example.com` email. Until that lands, run
`journey-cook` instead.
"""

import random
import time
import uuid

from locust import SequentialTaskSet, between, tag, task

from common import JWT_COOKIE_NAME, AuthenticatedHttpUser


# When the backend's LOAD_TEST_MODE shortcut is in place, this OTP is
# accepted for any loadtest+*@example.com email. Override with env var if
# the backend uses a different value.
import os  # noqa: E402

LOAD_TEST_OTP = os.environ.get("LOAD_TEST_OTP", "0000")
DEFAULT_PASSWORD = "LoadTest!Pass123"


def _new_email():
    return f"loadtest+journey-{uuid.uuid4().hex[:10]}@example.com"


@tag("journey", "onboarding")
class OnboardingToFirstCookTasks(SequentialTaskSet):
    """Full chain: register → OTP → onboarding → browse → cook → review."""

    def on_start(self):
        self.email = _new_email()
        self.password = DEFAULT_PASSWORD
        self.access_token = None
        self.recipe_uuid = None

    # --- step 1: register ------------------------------------------------

    @task
    def register(self):
        with self.client.post(
            "/users/auth/registration/",
            json={
                "email": self.email,
                "password1": self.password,
                "password2": self.password,
            },
            name="01 POST /users/auth/registration/",
            catch_response=True,
        ) as r:
            # dj_rest_auth registration returns 201 with a key, 400 if email
            # exists. We always retry with a fresh email if it collides.
            if r.status_code == 400 and "email" in (r.text or "").lower():
                self.email = _new_email()
                r.success()

    # --- step 2: verify OTP ----------------------------------------------

    @task
    def verify_otp(self):
        """Verifies the OTP. REQUIRES backend support — see module docstring.

        Without the LOAD_TEST_MODE shortcut, this step 4xxs and the journey
        bails out at this point. Treat the journey's downstream metrics as
        invalid until the backend supports a deterministic OTP for load
        testing.
        """
        with self.client.post(
            "/users/auth/verify-otp/",
            json={
                "email": self.email,
                "otp": LOAD_TEST_OTP,
                "purpose": "REGISTRATION",
            },
            name="02 POST /users/auth/verify-otp/",
            catch_response=True,
        ) as r:
            if r.status_code not in (200, 201):
                r.failure(
                    "OTP verification failed — backend likely missing the "
                    "LOAD_TEST_MODE OTP shortcut. See docs/backend-contract.md.",
                )
                self.interrupt()
                return
            try:
                body = r.json()
            except ValueError:
                r.failure("verify-otp returned non-JSON")
                self.interrupt()
                return
            # Token shape depends on dj_rest_auth config; try common keys
            access = (
                body.get("access")
                or body.get("access_token")
                or (body.get("tokens") or {}).get("access")
            )
            if not access:
                r.failure(f"verify-otp returned no access token: keys={list(body)}")
                self.interrupt()
                return
            self.access_token = access
            self.client.cookies.set(JWT_COOKIE_NAME, access)
            self.client.headers.update({"Authorization": f"Bearer {access}"})

    # --- step 3: complete onboarding wizard ------------------------------

    @task
    def onboarding_personal_info(self):
        self.client.post(
            "/users/onboarding/",
            json={
                "step": "PERSONAL_INFO",
                "first_name": "Load",
                "last_name": "Tester",
                "gender": random.choice(["MALE", "FEMALE"]),
                "date_of_birth": "1990-01-01",
            },
            name="03 POST /users/onboarding/ (personal info)",
        )

    @task
    def onboarding_physical_info(self):
        self.client.post(
            "/users/onboarding/",
            json={
                "step": "PHYSICAL_INFO",
                "height": 175.0,
                "height_unit": "cm",
                "weight": 75.0,
                "weight_unit": "kg",
            },
            name="04 POST /users/onboarding/ (physical info)",
        )

    @task
    def onboarding_activity_and_goal(self):
        self.client.post(
            "/users/onboarding/",
            json={
                "step": "ACTIVITY_LEVEL",
                "activity_level": random.choice(["LOW", "MODERATE", "HIGH"]),
            },
            name="05 POST /users/onboarding/ (activity)",
        )
        self.client.post(
            "/users/onboarding/",
            json={
                "step": "WEIGHT_GOAL",
                "weight_goal": random.choice(
                    ["WEIGHT_LOSS", "WEIGHT_MAINTAIN", "WEIGHT_GAIN"],
                ),
            },
            name="06 POST /users/onboarding/ (goal)",
        )

    @task
    def onboarding_health_meal_diet(self):
        self.client.post(
            "/users/onboarding/",
            json={
                "step": "HEALTH_FOCUS",
                "health_focus": random.choice(["HEART", "GENERAL", "PERFORMANCE"]),
            },
            name="07 POST /users/onboarding/ (health)",
        )
        self.client.post(
            "/users/onboarding/",
            json={"step": "MEAL_FREQUENCY", "meal_frequency": 3},
            name="08 POST /users/onboarding/ (meal frequency)",
        )

    # --- step 4: first browse + first cook -------------------------------

    @task
    def first_browse(self):
        with self.client.get(
            "/recipes/list/?page=1",
            name="09 GET /recipes/list/ (first browse)",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"first browse returned {r.status_code}")
                self.interrupt()
                return
            try:
                results = r.json().get("results") or []
            except ValueError:
                r.failure("first browse not JSON")
                self.interrupt()
                return
            if not results:
                r.failure("first browse empty")
                self.interrupt()
                return
            self.recipe_uuid = random.choice(results).get("id")

    @task
    def open_first_recipe(self):
        if not self.recipe_uuid:
            self.interrupt()
            return
        self.client.get(
            f"/recipes/{self.recipe_uuid}/",
            name="10 GET /recipes/[uuid]/ (first detail)",
        )

    @task
    def start_first_cook(self):
        self.client.post(
            f"/recipes/{self.recipe_uuid}/cook-mode/start/",
            json={"products": [], "serving_size": 2},
            name="11 POST /recipes/[uuid]/cook-mode/start/",
        )

    @task
    def finish_first_cook(self):
        self.client.post(
            f"/recipes/{self.recipe_uuid}/cook-mode/update-pantry/",
            json={"updates": []},
            name="12 POST /recipes/[uuid]/cook-mode/update-pantry/",
        )

    @task
    def review_first_cook(self):
        self.client.post(
            f"/recipes/{self.recipe_uuid}/reviews/",
            json={"stars": 5, "comment": "First cook — loved it!"},
            name="13 POST /recipes/[uuid]/reviews/",
        )

    # --- step 5: end of journey ------------------------------------------

    @task
    def end(self):
        # Each VU runs the journey exactly once, then a new VU starts a
        # fresh journey with a brand-new user. That keeps the seed pool
        # representative of "first user experience" throughput.
        time.sleep(random.uniform(0.5, 2.0))
        self.interrupt(reschedule=False)


class OnboardingToFirstCookUser(AuthenticatedHttpUser):
    """One VU = one brand-new user living through the onboarding-to-cook flow.

    Note: this user class does NOT call super().on_start() because the
    journey starts unauthenticated and earns its token during the OTP step.
    """

    abstract = False
    wait_time = between(1.0, 4.0)
    tasks = [OnboardingToFirstCookTasks]

    def on_start(self):
        # Skip the parent class's token-from-fixture install — journey
        # users start anonymous and authenticate during the flow.
        pass
