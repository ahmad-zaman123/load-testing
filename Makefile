.PHONY: install seed teardown watch-db smoke ramp pantry-read-smoke pantry-read-ramp reads-smoke reads-ramp reads-all-smoke reads-all-ramp reads-sweep journey-cook scenarios-all clean help

# Apps with a read-only scenario, used by reads-sweep.
READ_APPS ?= recipes products ingredients cookbooks pantry meal-planner communications shop users

HOST ?= http://localhost:8000
USERS ?= 5
RUN_TIME ?= 60s
SPAWN_RATE ?= 1
RESULTS_DIR ?= results

help:
	@echo "Setup (source config/<env>.env first, or pass ENV=<name>):"
	@echo "  seed            seed users into the target backend + pull tokens.json"
	@echo "  teardown        delete the load-test users (LOAD_TEST_DRY_RUN=1 previews)"
	@echo "  watch-db        sample DB connection usage during a run (needs DATABASE_URL)"
	@echo ""
	@echo "Targets:"
	@echo "  install         pip install -r requirements.txt"
	@echo "  smoke           quick 5-user / 60s read-only run (Scenario A)"
	@echo "  ramp            full stepped ramp (UnifiedSteppedRamp, ~24 min)"
	@echo "  pantry-read-smoke   quick 5-user / 60s pantry read run (Scenario E)"
	@echo "  pantry-read-ramp    full stepped ramp over pantry read endpoints (Scenario E)"
	@echo "  reads-smoke READS=<app>   quick read smoke for one app (recipes|products|...)"
	@echo "  reads-ramp  READS=<app>   stepped ramp over one app's read endpoints"
	@echo "  reads-all-smoke / reads-all-ramp   all apps' reads loaded together"
	@echo "  reads-sweep         baseline every app's reads back-to-back (READ_APPS)"
	@echo "  sustained       Phase 2 autoscaling test (SustainedLoadShape; default ~38 min)"
	@echo "                  Env: SUSTAIN_USERS, SUSTAIN_MINUTES, RAMPUP_MINUTES, RAMPDOWN_MINUTES"
	@echo "  journey-cook            returning-user cook journey"
	@echo "  journey-onboarding      new-user registration → onboarding → first cook (needs backend OTP hack)"
	@echo "  journey-import          paste recipe URL → poll → see in list (etl-bound)"
	@echo "  journey-pantry-scan     upload pantry images → poll → bulk add"
	@echo "  journey-meal-planner    today → add slot → mark eaten → weekly stats"
	@echo "  journey-shop            search → add to cart → adjust → checkout"
	@echo "  journey-reviewer        cook + review 3-8 recipes in one session"
	@echo "  journeys-all            run every journey back-to-back"
	@echo "  scenarios-all           run A, B, C, D1 back-to-back (capped, ~20 min)"
	@echo ""
	@echo "Env overrides: HOST, USERS, SPAWN_RATE, RUN_TIME, RESULTS_DIR"

install:
	pip install -r requirements.txt

# --- environment setup (config-driven) ---------------------------------------
# `source config/<env>.env` first (so HOST/SSH_HOST/... are exported), then:
#   make seed        seed users into the target backend + pull fixtures/tokens.json
#   make teardown    delete the load-test users (LOAD_TEST_DRY_RUN=1 to preview)
#   make watch-db    sample DB connection usage during a run (needs DATABASE_URL)
# Or skip sourcing and point at a file: make seed ENV=staging

seed:
	@scripts/seed.sh $(if $(ENV),--env config/$(ENV).env,)

teardown:
	@scripts/teardown.sh $(if $(ENV),--env config/$(ENV).env,)

watch-db:
	@scripts/watch_db.sh $(if $(ENV),--env config/$(ENV).env,)

smoke:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=a LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/smoke.html --csv=$(RESULTS_DIR)/smoke

ramp:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=a locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --html=$(RESULTS_DIR)/ramp.html --csv=$(RESULTS_DIR)/ramp

pantry-read-smoke:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=e LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/pantry_read_smoke.html --csv=$(RESULTS_DIR)/pantry_read_smoke

pantry-read-ramp:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=e locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --html=$(RESULTS_DIR)/pantry_read_ramp.html --csv=$(RESULTS_DIR)/pantry_read_ramp

# Read-only single-app run. Pick the app with READS=<app>, e.g. READS=recipes.
# Smoke = fixed --users/--run-time (no shape); ramp = stepped ramp (cap with MAX_USERS).
reads-smoke:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=reads-$(READS) LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/reads_$(READS)_smoke.html --csv=$(RESULTS_DIR)/reads_$(READS)_smoke

reads-ramp:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=reads-$(READS) locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --html=$(RESULTS_DIR)/reads_$(READS)_ramp.html --csv=$(RESULTS_DIR)/reads_$(READS)_ramp

reads-all-smoke:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=reads-all LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/reads_all_smoke.html --csv=$(RESULTS_DIR)/reads_all_smoke

reads-all-ramp:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=reads-all locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --html=$(RESULTS_DIR)/reads_all_ramp.html --csv=$(RESULTS_DIR)/reads_all_ramp

# Baseline every app's read scenario back-to-back (Phase-1 per-app sweep).
reads-sweep:
	mkdir -p $(RESULTS_DIR)
	@for app in $(READ_APPS); do \
	    echo "=== reads-$$app ($(USERS) users, $(RUN_TIME)) ==="; \
	    SCENARIO=reads-$$app LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	        --host=$(HOST) --headless \
	        --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	        --html=$(RESULTS_DIR)/reads_$$app.html --csv=$(RESULTS_DIR)/reads_$$app \
	        || echo "  (reads-$$app exited non-zero — see report)"; \
	done

sustained:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=$(or $(SCENARIO),a) LOAD_TEST_SHAPE=sustained locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --html=$(RESULTS_DIR)/sustained.html --csv=$(RESULTS_DIR)/sustained

journey-cook:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-cook LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_cook.html --csv=$(RESULTS_DIR)/journey_cook

journey-onboarding:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-onboarding LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_onboarding.html --csv=$(RESULTS_DIR)/journey_onboarding

journey-import:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-import LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_import.html --csv=$(RESULTS_DIR)/journey_import

journey-pantry-scan:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-pantry-scan LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_pantry_scan.html --csv=$(RESULTS_DIR)/journey_pantry_scan

journey-meal-planner:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-meal-planner LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_meal_planner.html --csv=$(RESULTS_DIR)/journey_meal_planner

journey-shop:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-shop LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_shop.html --csv=$(RESULTS_DIR)/journey_shop

journey-reviewer:
	mkdir -p $(RESULTS_DIR)
	SCENARIO=journey-reviewer LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	    --host=$(HOST) --headless \
	    --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	    --html=$(RESULTS_DIR)/journey_reviewer.html --csv=$(RESULTS_DIR)/journey_reviewer

journeys-all:
	$(MAKE) journey-cook
	$(MAKE) journey-import
	$(MAKE) journey-pantry-scan
	$(MAKE) journey-meal-planner
	$(MAKE) journey-shop
	$(MAKE) journey-reviewer

scenarios-all:
	mkdir -p $(RESULTS_DIR)
	@for s in a b c d1; do \
	    echo "=== Running scenario $$s ==="; \
	    SCENARIO=$$s LOAD_TEST_NO_SHAPE=1 locust -f locustfile.py \
	        --host=$(HOST) --headless \
	        --users $(USERS) --spawn-rate $(SPAWN_RATE) --run-time $(RUN_TIME) \
	        --html=$(RESULTS_DIR)/$$s.html --csv=$(RESULTS_DIR)/$$s; \
	done

clean:
	rm -rf $(RESULTS_DIR) __pycache__ */__pycache__ */*/__pycache__
