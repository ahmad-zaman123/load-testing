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
	@echo "  journey-cook    returning-user cook journey at $(USERS) users"
	@echo "  scenarios-all   run A, B, C, D1 back-to-back (capped, ~20 min)"
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
