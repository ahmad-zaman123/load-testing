"""Scenario D — Auth / Spike.

Three independent sub-tests, picked via tag:

  --tags d1   Anonymous login flood   (POST /users/auth/)
  --tags d2   OTP burst                (resend-otp + verify-otp)
  --tags d3   Authenticated flood      (one token hammers /recipes/list/)

D uses a spike pattern, not the stepped ramp. Use `--users` and
`--spawn-rate` directly (set `LOAD_TEST_NO_SHAPE=1` so the unified shape
doesn't apply) or load `SpikeShape` from shapes.
"""

import os
import random

from locust import HttpUser, between, constant, tag, task

from common import pick_random_token


SHARED_PASSWORD = "LoadTest!Pass123"


@tag("scenario_d", "d1", "auth")
class AnonLoginFloodUser(HttpUser):
    """D1 — Hammers the unified auth endpoint with valid credentials.

    Each VU picks a random seeded loadtest user and POSTs to /users/auth/.
    """

    wait_time = constant(0)

    @task
    def login(self):
        token = pick_random_token()
        self.client.post(
            "/users/auth/",
            json={"email": token["email"], "password": SHARED_PASSWORD},
            name="POST /users/auth/",
        )


@tag("scenario_d", "d2", "auth")
class OTPBurstUser(HttpUser):
    """D2 — Anonymous OTP resend + verify burst.

    These endpoints carry AnonRateThrottle (1000/hour). Expectation: 429s
    fire after the budget is hit. We do not actually verify successful OTPs
    — we just want to load the throttle and the OTP-issue path.
    """

    wait_time = constant(0)

    @task(2)
    def resend_otp(self):
        token = pick_random_token()
        self.client.post(
            "/users/auth/resend-otp/",
            json={"email": token["email"], "purpose": "REGISTRATION"},
            name="POST /users/auth/resend-otp/",
        )

    @task(1)
    def verify_otp(self):
        token = pick_random_token()
        self.client.post(
            "/users/auth/verify-otp/",
            json={
                "email": token["email"],
                "otp": str(random.randint(1000, 9999)),
                "purpose": "REGISTRATION",
            },
            name="POST /users/auth/verify-otp/",
        )


@tag("scenario_d", "d3", "auth")
class AuthenticatedFloodUser(HttpUser):
    """D3 — Single seeded token hammers /recipes/list/.

    Demonstrates the throttle gap: authenticated endpoints have no rate
    limit, so one token can saturate the API. Expectation: high RPS, no
    429s. The finding is the absence of a limit, not a performance number.

    NOTE: Set --users to a single value (e.g. 1) and use --rps via
    `wait_time = constant(0)` — Locust spawns N greenlets all using the
    same identity.
    """

    wait_time = constant(0)

    def on_start(self):
        token = pick_random_token()
        self.client.cookies.set("my-app-auth", token["access"])
        self.client.headers.update({"Authorization": f"Bearer {token['access']}"})

    @task
    def hammer_list(self):
        self.client.get("/recipes/list/?page=1", name="GET /recipes/list/")


# Optional sustained-burst user for combined D-style runs that aren't picked
# via a single sub-tag. Uses moderate wait_time so it isn't max-RPS.
@tag("scenario_d_mild")
class MildAuthSpikeUser(HttpUser):
    wait_time = between(0.05, 0.5)

    @task
    def login(self):
        token = pick_random_token()
        self.client.post(
            "/users/auth/",
            json={"email": token["email"], "password": SHARED_PASSWORD},
            name="POST /users/auth/ (mild)",
        )


# Sanity check — exporting a helper so locustfile.py can warn if the user
# forgot to set LOAD_TEST_NO_SHAPE.
def warn_if_shape_active():
    if not os.environ.get("LOAD_TEST_NO_SHAPE"):
        print(
            "[scenario_d] Warning: UnifiedSteppedRamp may still be active. "
            "Set LOAD_TEST_NO_SHAPE=1 so --users/--spawn-rate take effect.",
        )
