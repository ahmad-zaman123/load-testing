# easychef-load-tests

External stress-testing harness for the [easychef-backend](../easychef-backend)
API. Lives in its own repo on purpose: stress tests should run from a
different machine than the system under test, otherwise CPU contention and
loopback networking hide real bottlenecks.

## What's in here

```
.
├── README.md / RUNBOOK.md           docs
├── Makefile                          common one-liners
├── requirements.txt                  just: locust + requests
├── locustfile.py                     SCENARIO=... dispatcher
├── common.py                         token loader + base HttpUser
├── shapes.py                         UnifiedSteppedRamp + SpikeShape
├── scenarios/                        flat random-weighted scenarios
│   ├── scenario_a_browse.py
│   ├── scenario_b_meal_planner.py
│   ├── scenario_c_writes.py
│   └── scenario_d_auth_spike.py
├── journeys/                         sequential user-flow journeys
│   ├── returning_user_cook.py        browse → cook → review (works w/ seeded tokens)
│   ├── onboarding_to_first_cook.py   register → OTP → onboarding → first cook (needs OTP shortcut)
│   ├── recipe_import_from_url.py     paste URL → wait → see in list (etl-bound)
│   ├── pantry_ai_scan.py             upload images → poll → bulk add
│   ├── returning_meal_planner.py     today → add slot → mark eaten → weekly stats
│   ├── shop_and_checkout.py          search → add to cart → adjust → checkout
│   └── reviewer.py                   cook + review 3-8 recipes in one session
├── fixtures/                         tokens.json (generated, gitignored)
│   └── search_terms.txt
├── config/                           env templates per environment
│   ├── staging.env.example
│   └── prod.env.example
└── docs/
    └── backend-contract.md           endpoints, payloads, auth shapes
```

## Setup

```bash
git clone <this repo>
cd easychef-load-tests
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Get a tokens.json fixture

The backend deliberately has no `seed_load_test_users` command — seeding
logic lives here, in `scripts/seed_users.py`, and is exec'd inside the
backend's Django shell to use its ORM directly.

```bash
# 1. SSH to the backend host (staging or local dev)
ssh staging-host

# 2. Pipe the seed script into Django shell inside the Django container
LOAD_TEST_COUNT=500 LOAD_TEST_PANTRY_ITEMS=20 \
    docker exec -i easychef-dc01 python manage.py shell \
    < ../easychef-load-tests/scripts/seed_users.py

# 3. Copy the resulting fixture out of the container into this repo
docker cp easychef-dc01:/tmp/load_test_tokens.json fixtures/tokens.json

# 4. (If running Locust from a different machine — your laptop)
scp staging-host:/tmp/load_test_tokens.json fixtures/tokens.json
```

Cleanup later with:

```bash
docker exec -i easychef-dc01 python manage.py shell \
    < scripts/teardown_users.py
```

Env vars `LOAD_TEST_COUNT`, `LOAD_TEST_PANTRY_ITEMS`, `LOAD_TEST_OUTPUT`
let you tune count, pantry depth, and output path. See `scripts/seed_users.py`
docstring for details.

## Run something

```bash
# Quick local smoke (read-only, 5 users, 60s):
make smoke HOST=http://localhost:8000

# Returning-user cook journey, 50 users, 3 min:
make journey-cook HOST=https://staging-api USERS=50 RUN_TIME=3m

# Full stepped ramp on staging (10 → 1000 over 24 min):
make ramp HOST=https://staging-api

# Pick a specific scenario manually:
SCENARIO=b LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
    --host=https://staging-api --headless \
    --users 20 --spawn-rate 2 --run-time 5m
```

See `RUNBOOK.md` for the full pre-flight checklist and staging campaign.

## Scenarios vs journeys

| Type | Pattern | When to use |
|---|---|---|
| **Scenario** | Each VU fires random weighted tasks for the session | Throughput / endpoint-level numbers |
| **Journey** | Each VU executes a sequential flow (step 1 → step 2 → ...) | End-to-end user experience, realistic chains |

Scenarios are great for "how fast is `/recipes/list/`?". Journeys are great
for "how does the system hold up under realistic 7-step user sessions?".
Both have their place.

## Pre-conditions on the backend

- `LOAD_TEST_MODE=true` must be set on the backend before running write
  scenarios or journeys. It mocks all 12 external clients (LLM, FCM, OAuth,
  scraper, etc.) so the load test doesn't fire real API calls.
- `seed_load_test_users` must have been run there so `tokens.json` has
  valid identities.
- For `journey-onboarding`, the backend additionally needs a deterministic
  OTP shortcut (see `docs/backend-contract.md` § Known friction points).

## License

Internal tooling. Same license as the backend.
