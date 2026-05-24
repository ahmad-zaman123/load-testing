# Load Test Runbook

How to run a stress-test campaign against the easychef-backend. Do **Part 1
(local dry run)** before Part 2 (staging) — catches harness issues without
burning staging credibility.

---

## Part 1 — Local dry run

**Goal**: confirm the harness works end-to-end against a local backend
without touching staging.

### 1.1 Pre-flight

- [ ] The backend (`easychef-backend`) is running locally (`make up.d` in
      that repo) with `LOAD_TEST_MODE=true` in its `.env`.
- [ ] You have a Python venv with `pip install -r requirements.txt`.
- [ ] `tokens.json` exists in `fixtures/` — either copy from the backend's
      `easychef/load_testing/locust/fixtures/tokens.json` after running
      its seed command, or run the seed on local backend and `cp` from
      the container volume.

### 1.2 Smoke

```bash
make smoke HOST=http://localhost:8000 USERS=5 RUN_TIME=60s
```

Look for: 0 failures, reasonable latencies (note local-laptop caveats).

### 1.3 Try the cook journey

```bash
make journey-cook HOST=http://localhost:8000 USERS=3 RUN_TIME=2m
```

Each VU runs the full 7-step cook flow once. Watch the per-step latencies
in the HTML report.

### 1.4 Cleanup

```bash
make clean   # drops results/ + __pycache__
```

---

## Part 2 — Staging campaign

### 2.1 Team coordination

Post in `#engineering`:

> Heads-up: running stress tests on staging from `<time>` to `<time>` today.
> External APIs will be mocked (no real LLM/push/scraper calls). If you're
> using staging for QA, please pause until done. — `<name>`

### 2.2 Backend prep (on staging VM)

```bash
ssh staging-host

# 1. Enable LOAD_TEST_MODE
echo 'LOAD_TEST_MODE=true' >> .env.do.stage
make down && make up.d
sleep 10

# 2. Verify mocks applied
docker logs $(docker ps --filter name=django --format '{{.Names}}' | head -1) 2>&1 \
  | grep "applied 12/12 external-client mocks"

# 3. Seed users
make dcshell
python manage.py seed_load_test_users --count 500
exit
exit
```

If you don't see `applied 12/12 external-client mocks` → **stop and debug**.
Real external API calls would fire otherwise.

### 2.3 Pull the fixture to your laptop

```bash
scp staging-host:~/easychef-backend/easychef/load_testing/locust/fixtures/tokens.json \
    fixtures/tokens.json
```

### 2.4 First staging smoke

```bash
make smoke HOST=https://staging-api USERS=5 RUN_TIME=60s
```

Check: 0 failures, p95 < your rough expectation. If anything goes red,
abort.

### 2.5 Capped staging run

```bash
make journey-cook HOST=https://staging-api USERS=50 RUN_TIME=3m
```

Open `results/journey_cook.html` after to inspect per-step latencies and
distribution.

### 2.6 Full stepped ramp

```bash
make ramp HOST=https://staging-api
```

Runs the unified ramp (10 → 50 → 100 → 300 → 500 → 1000) over ~24 min.
This is the "real campaign" run.

### 2.7 Per-scenario sweep

```bash
make scenarios-all HOST=https://staging-api USERS=100 RUN_TIME=5m
```

Runs Scenarios A, B, C, D1 back-to-back at 100 users each.

### 2.8 Teardown

```bash
ssh staging-host
make dcshell
python manage.py teardown_load_test_users
exit

# Drop LOAD_TEST_MODE
# (remove the LOAD_TEST_MODE=true line from .env.do.stage)
make down && make up.d
```

Then announce in `#engineering` that staging is back to normal.

---

## Watching during a run

- **Locust live UI** (`http://localhost:8089` when not `--headless`) —
  RPS, p95, error rate per step
- **Backend Flower** — `https://staging-flower.internal:5555` for Celery
  queue depth (default vs etl)
- **DB** — `SELECT count(*) FROM pg_stat_activity WHERE state='active';`
  every 30s during the run. Staging uses DigitalOcean PgBouncer, so the
  Django-side connection count = PgBouncer client count, not Postgres
  backend count.

---

## Abort criteria

Hit Ctrl-C immediately if:

- Real users get 5xx on staging (uncontained blast radius)
- DB connections exceed 80% of PgBouncer pool size
- Flower shows queues over 10k tasks growing
- Anything looks like data corruption
