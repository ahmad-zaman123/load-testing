"""Shared utilities for the Locust load-testing harness.

This module is independent of the backend codebase — it consumes a JSON
token fixture produced by the backend's `seed_load_test_users` command
(see ../easychef-backend) and nothing else.
"""

import json
import os
import random

from pathlib import Path
from typing import Dict, List

from locust import HttpUser, events


TOKEN_FIXTURE_ENV = "LOAD_TEST_TOKEN_FIXTURE"
DEFAULT_FIXTURE_PATH = "fixtures/tokens.json"

JWT_COOKIE_NAME = "my-app-auth"


_token_pool: List[Dict[str, str]] = []


def _resolve_fixture_path() -> Path:
    candidate = os.environ.get(TOKEN_FIXTURE_ENV, DEFAULT_FIXTURE_PATH)
    path = Path(candidate)
    if path.is_absolute():
        return path
    return Path.cwd() / path


@events.init.add_listener
def _load_token_pool(environment, **_kwargs):
    """Read the token fixture exactly once when Locust boots."""
    global _token_pool

    fixture_path = _resolve_fixture_path()
    if not fixture_path.exists():
        raise FileNotFoundError(
            f"Token fixture not found at {fixture_path}. "
            "Generate it on the backend with `python manage.py seed_load_test_users`, "
            "scp the resulting file into ./fixtures/, "
            f"or set {TOKEN_FIXTURE_ENV} to point at an existing fixture.",
        )

    with fixture_path.open() as handle:
        payload = json.load(handle)

    _token_pool = payload.get("tokens", [])

    if not _token_pool:
        raise RuntimeError(f"Token fixture at {fixture_path} is empty.")

    print(f"[load-test] Loaded {len(_token_pool)} tokens from {fixture_path}.")


def pick_random_token() -> Dict[str, str]:
    if not _token_pool:
        raise RuntimeError(
            "Token pool is empty. Did the @events.init listener run?",
        )
    return random.choice(_token_pool)


def token_pool_size() -> int:
    return len(_token_pool)


class AuthenticatedHttpUser(HttpUser):
    """Base class for scenarios that need an authenticated session.

    Picks a random token from the seeded fixture on `on_start` and installs it
    as both a JWT cookie (matching the project's JWTCookieAuthentication) and
    an Authorization header (defensive — works regardless of auth backend).
    """

    abstract = True

    def on_start(self):
        token = pick_random_token()
        self.client.cookies.set(JWT_COOKIE_NAME, token["access"])
        self.client.headers.update(
            {"Authorization": f"Bearer {token['access']}"},
        )
        self.user_email = token["email"]
        self.user_id = token["user_id"]
