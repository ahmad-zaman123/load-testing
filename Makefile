.PHONY: install smoke ramp journey-cook scenarios-all clean help

HOST ?= http://localhost:8000
USERS ?= 5
RUN_TIME ?= 60s
SPAWN_RATE ?= 1
RESULTS_DIR ?= results

help:
	@echo "Targets:"
	@echo "  install         pip install -r requirements.txt"
	@echo "  smoke           quick 5-user / 60s read-only run (Scenario A)"
	@echo "  ramp            full stepped ramp (UnifiedSteppedRamp, ~24 min)"
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
