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
├── config/                           env templates — copy to <name>.env, fill in
│   ├── local.env.example             local docker backend
│   └── staging.env.example           remote backend over SSH
├── scripts/
│   ├── seed.sh / teardown.sh         env-driven seed/teardown (local OR remote SSH)
│   ├── watch_db.sh                   sample DB connections during a run
│   └── seed_users.py / teardown_users.py   run inside the backend's Django shell
└── docs/
    └── backend-contract.md           endpoints, payloads, auth shapes
```

## Quickstart

A fresh clone only needs **one env file** filled in — everything else is
driven from it.

```bash
git clone <this repo> && cd easychef-load-tests
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Create your env file from a template and fill in the blanks.
cp config/local.env.example config/local.env      # or staging.env.example
$EDITOR config/local.env

# 2. Load it (exports HOST, SSH_HOST, container name, seed tuning, ...).
source config/local.env

# 3. Seed users into the target backend + pull fixtures/tokens.json locally.
make seed

# 4. Run.
make reads-all-smoke      # or: make smoke / make reads-all-ramp / ...
```

`make seed` figures out *where* the backend is from your env file:

- **`SSH_HOST` empty** → backend runs in docker on this machine; it uses
  `docker exec` directly.
- **`SSH_HOST` set** → it runs the seed over SSH (`ssh <host> docker exec ...`)
  and `scp`s the resulting `tokens.json` back into `fixtures/`.

Either way it runs `scripts/seed_users.py` **inside the backend's Django
shell** — seeding needs the ORM and model signals, so it goes through Django,
not a direct DB connection. (`DATABASE_URL` in the env file is only for the
optional `make watch-db` monitor, never for seeding.)

Prefer not to `source`? Point any setup target at a file instead:

```bash
make seed ENV=staging                 # = scripts/seed.sh --env config/staging.env
make teardown ENV=staging             # delete the load-test users
LOAD_TEST_DRY_RUN=1 make teardown ENV=staging   # preview first
```

Tune the seed with `LOAD_TEST_COUNT` / `LOAD_TEST_PANTRY_ITEMS` in the env
file. Pantry reads filter to APPROVED products, so `seed_users.py` draws from
the approved pool — set `LOAD_TEST_PANTRY_ITEMS=110` to get ~100+ items
actually visible per user.

## Run something

With `config/<env>.env` sourced, `HOST`/`USERS`/etc come from it, so the
commands shorten to `make <target>`. You can still override any of them on the
CLI (shown explicitly below).

```bash
# Quick local smoke (read-only, 5 users, 60s):
make smoke HOST=http://localhost:8000

# Every app's read endpoints, stepped 10→50 (after `source config/local.env`):
make reads-all-ramp

# One app's reads in isolation:
make reads-ramp READS=recipes

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
- `make seed` must have been run so `fixtures/tokens.json` holds identities
  that exist in the target environment's DB. Stale tokens (e.g. after a DB
  reset) surface as `401 user_not_found` — just re-run `make seed`.
- For `journey-onboarding`, the backend additionally needs a deterministic
  OTP shortcut (see `docs/backend-contract.md` § Known friction points).

## License

Internal tooling. Same license as the backend.
