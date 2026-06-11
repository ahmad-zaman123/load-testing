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
- [ ] You have a Python venv with `pip install -r requirements.txt`,
      OR Docker for running the official locust image (`locustio/locust`).
- [ ] `fixtures/tokens.json` exists. Generate via:
      ```bash
      docker exec -i easychef-dc01 python manage.py shell \
          < scripts/seed_users.py
      docker cp easychef-dc01:/tmp/load_test_tokens.json fixtures/tokens.json
      ```

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

# 3. Seed users via the harness script (run on staging VM)
LOAD_TEST_COUNT=500 LOAD_TEST_PANTRY_ITEMS=20 \
    docker exec -i easychef-dc01 python manage.py shell \
    < /path/to/easychef-load-tests/scripts/seed_users.py
```

If you don't see `applied 12/12 external-client mocks` → **stop and debug**.
Real external API calls would fire otherwise.

### 2.3 Pull the fixture to your laptop

```bash
# First copy out of the container to the staging host
ssh staging-host "docker cp easychef-dc01:/tmp/load_test_tokens.json /tmp/"

# Then to your laptop
scp staging-host:/tmp/load_test_tokens.json fixtures/tokens.json
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

# Run the harness teardown script via shell_plus
docker exec -i easychef-dc01 python manage.py shell \
    < /path/to/easychef-load-tests/scripts/teardown_users.py

# Drop LOAD_TEST_MODE
# (remove the LOAD_TEST_MODE=true line from .env.do.stage)
make down && make up.d
```

Then announce in `#engineering` that staging is back to normal.

---

## Part 3 — Category load-class profiling (CPU/memory)

**Goal**: measure how much CPU and memory each *load class* of endpoints
costs the backend, and detect contention when classes run together. Use this
after the per-endpoint report has bucketed endpoints into light / medium /
heavy (P95 @ 100 users):

| Class | P95 @ 100u | Endpoints | Scenario |
|-------|-----------|-----------|----------|
| light | < 1000ms | 11 cheap reads | `cat-light` |
| medium | 1000–2500ms | 16 mid-tier reads | `cat-medium` |
| heavy | > 2500ms | 6 list/aggregation reads | `cat-heavy` |

Bucket membership is defined in `scenarios/scenario_categories.py`. The 3
endpoints that fail under load (`users`, `users-document`, `users-me`) are
excluded — 100% failures skew the comparison.

### 3.1 Pre-flight

- [ ] Backend prepped + users seeded — same as **2.2** and **2.3** (mocks
      applied, `fixtures/tokens.staging.json` current). Re-seed if stale.
- [ ] `source config/staging.env` in **both** terminals below.
- [ ] Run Locust from a machine that is **not** the droplet — otherwise the
      load generator's CPU contaminates the measurement.

### 3.2 Start the resource sampler (terminal 1)

Leave this running for the whole campaign. It SSHes to the droplet and samples
every running container's CPU/memory via `docker stats`, appending one CSV row
per container per tick.

```bash
STATS_OUT=results/stats.csv WATCH_INTERVAL=5 make watch-stats ENV=staging
```

CSV columns: `time,container,cpu_perc,mem_usage,mem_perc,net_io,block_io`
(`cpu_perc` / `mem_perc` have `%` stripped for plotting).

### 3.3 Isolated runs — one class at a time (terminal 2)

`cat-sweep` runs light, then medium, then heavy back-to-back at a fixed load.
`LOAD_TEST_WAIT=0` removes think-time so `USERS` == in-flight concurrency,
making the three classes directly comparable under equal pressure.

```bash
LOAD_TEST_WAIT=0 USERS=50 RUN_TIME=3m make cat-sweep ENV=staging
```

Each class writes its own `results/cat_<class>.csv` + `.html`. Note the
wall-clock start/stop of each so you can slice `stats.csv` by window.

To hold a single concurrency level across a longer ramp instead:

```bash
LOAD_TEST_WAIT=0 RAMP_STEPS=50 RAMP_STEP_SECS=180 make cat-ramp CAT=heavy ENV=staging
```

### 3.4 Blended run — all classes together

```bash
LOAD_TEST_WAIT=0 USERS=50 RUN_TIME=3m make cat-smoke CAT=all ENV=staging
```

Locust spreads the 50 VUs across all three classes at once.

### 3.5 Interpret

- Slice `results/stats.csv` by the time window of each run and by container.
- **Key comparison**: blended (3.4) CPU/mem vs the **sum** of the three
  isolated runs (3.3). If blended exceeds the sum, that's contention
  (worker / DB-connection-pool starvation) — the likely cause of the
  `meal_planner_history` and `users_*` collapses in the report.
- **Django vs Postgres**: compare the `easychef-dc01` (uvicorn) container
  against the postgres container. A heavy class that lights up Postgres CPU
  is query-bound; one that lights up uvicorn CPU is serialization-bound.

### 3.6 Teardown

Same as **2.8** when the campaign is done.

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
- **CPU / memory** — `make watch-stats ENV=staging` samples every container's
  CPU/mem on the droplet via `docker stats`, into a CSV. See **Part 3** for
  the category-profiling workflow that uses it.

---

## Abort criteria

Hit Ctrl-C immediately if:

- Real users get 5xx on staging (uncontained blast radius)
- DB connections exceed 80% of PgBouncer pool size
- Flower shows queues over 10k tasks growing
- Anything looks like data corruption
