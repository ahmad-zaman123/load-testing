"""Locust entry point. Pick a scenario or journey via the SCENARIO env var.

Flat scenarios (random weighted tasks):
    SCENARIO=a            read-heavy browsing
    SCENARIO=b            meal planner
    SCENARIO=c            writes (cart, cook mode, reviews) — default skips etl-bound actions
    SCENARIO=c_full       writes + recipe-from-URL + pantry scan (needs LOAD_TEST_MODE on backend)
    SCENARIO=d1           anonymous login flood
    SCENARIO=d2           OTP burst
    SCENARIO=d3           authenticated flood (one token hammers /recipes/list/)
    SCENARIO=combined     A + B + C user classes loaded together

Chain journeys (sequential user flows):
    SCENARIO=journey-cook            returning user: browse → cook → review
    SCENARIO=journey-onboarding      new user: register → OTP → onboarding → first cook
                                     (requires backend OTP shortcut — see docs/backend-contract.md)
    SCENARIO=journey-import          paste URL → wait → see recipe in list (etl-bound)
    SCENARIO=journey-pantry-scan     upload images → poll status → bulk add to pantry
    SCENARIO=journey-meal-planner    open today → add slot → mark eaten → weekly stats
    SCENARIO=journey-shop            search → open recipe → add to cart → adjust → checkout
    SCENARIO=journey-reviewer        power user: cook + review 3-8 recipes in one session

Examples:
    SCENARIO=a locust -f locustfile.py --host=https://staging-api --headless

    # Local smoke (shape disabled, --users takes effect):
    SCENARIO=a LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
        --host=http://localhost:8000 --headless \
        --users 5 --spawn-rate 1 --run-time 30s

    # Scenario D1 with the spike shape:
    SCENARIO=d1 LOAD_TEST_SHAPE=spike locust -f locustfile.py \
        --host=https://staging-api --headless
"""

import os

from common import AuthenticatedHttpUser  # noqa: F401  (token loader fires here)


SCENARIO = os.environ.get("SCENARIO", "a").lower()


# --- flat scenarios ----------------------------------------------------------

if SCENARIO == "a":
    from scenarios.scenario_a_browse import BrowseUser  # noqa: F401
elif SCENARIO == "b":
    from scenarios.scenario_b_meal_planner import TodayPlanUser  # noqa: F401
elif SCENARIO == "c":
    from scenarios.scenario_c_writes import CartWriteUser  # noqa: F401
elif SCENARIO == "c_full":
    from scenarios.scenario_c_writes import HeavyWriteUser  # noqa: F401
elif SCENARIO == "d1":
    from scenarios.scenario_d_auth_spike import AnonLoginFloodUser  # noqa: F401
elif SCENARIO == "d2":
    from scenarios.scenario_d_auth_spike import OTPBurstUser  # noqa: F401
elif SCENARIO == "d3":
    from scenarios.scenario_d_auth_spike import AuthenticatedFloodUser  # noqa: F401
elif SCENARIO == "combined":
    from scenarios.scenario_a_browse import BrowseUser  # noqa: F401
    from scenarios.scenario_b_meal_planner import TodayPlanUser  # noqa: F401
    from scenarios.scenario_c_writes import CartWriteUser  # noqa: F401

# --- chain journeys ----------------------------------------------------------

elif SCENARIO in ("journey-cook", "cook"):
    from journeys.returning_user_cook import ReturningUserCookUser  # noqa: F401
elif SCENARIO in ("journey-onboarding", "onboarding"):
    from journeys.onboarding_to_first_cook import OnboardingToFirstCookUser  # noqa: F401
elif SCENARIO in ("journey-import", "import"):
    from journeys.recipe_import_from_url import RecipeImportUser  # noqa: F401
elif SCENARIO in ("journey-pantry-scan", "pantry-scan"):
    from journeys.pantry_ai_scan import PantryScanUser  # noqa: F401
elif SCENARIO in ("journey-meal-planner", "meal-planner"):
    from journeys.returning_meal_planner import ReturningMealPlannerUser  # noqa: F401
elif SCENARIO in ("journey-shop", "shop"):
    from journeys.shop_and_checkout import ShopAndCheckoutUser  # noqa: F401
elif SCENARIO in ("journey-reviewer", "reviewer"):
    from journeys.reviewer import ReviewerUser  # noqa: F401

else:
    raise SystemExit(
        f"Unknown SCENARIO={SCENARIO!r}. Expected one of: "
        "a, b, c, c_full, d1, d2, d3, combined, "
        "journey-cook, journey-onboarding, journey-import, "
        "journey-pantry-scan, journey-meal-planner, journey-shop, journey-reviewer.",
    )


# Shape selection. Default = unified stepped ramp.
#   LOAD_TEST_SHAPE=spike       → SpikeShape (Scenario D)
#   LOAD_TEST_SHAPE=sustained   → SustainedLoadShape (Phase 2 autoscaling test)
#   LOAD_TEST_NO_SHAPE=1        → no shape; --users/--spawn-rate/--run-time take effect
_shape_choice = os.environ.get("LOAD_TEST_SHAPE", "ramp").lower()
_skip_shape = os.environ.get("LOAD_TEST_NO_SHAPE") in ("1", "true", "yes")

if not _skip_shape:
    if _shape_choice == "spike":
        from shapes import SpikeShape  # noqa: F401
    elif _shape_choice == "sustained":
        from shapes import SustainedLoadShape  # noqa: F401
    else:
        from shapes import UnifiedSteppedRamp  # noqa: F401
