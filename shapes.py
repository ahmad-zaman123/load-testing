"""LoadTestShape implementations.

`UnifiedSteppedRamp` drives Scenarios A, B, C, Combined, and journey runs.
`SpikeShape` is used for Scenario D variants (sudden burst, then hold).
`SustainedLoadShape` is used for Phase 2 autoscaling tests — holds at a
chosen concurrency long enough for the autoscaler to react (cold boot
~3-5 min, scale-up trigger threshold ~5 min sustained), then ramps down.
"""

import os

from locust import LoadTestShape


class UnifiedSteppedRamp(LoadTestShape):
    """Stepped ramp shared across Scenarios A, B, C, and the Combined Run.

    `duration` is cumulative seconds from run start, not the length of a step.
    """

    stages = (
        {"duration": 180, "users": 10, "spawn_rate": 5},
        {"duration": 360, "users": 50, "spawn_rate": 10},
        {"duration": 540, "users": 100, "spawn_rate": 15},
        {"duration": 840, "users": 300, "spawn_rate": 20},
        {"duration": 1140, "users": 500, "spawn_rate": 25},
        {"duration": 1440, "users": 1000, "spawn_rate": 50},
    )

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None


class SpikeShape(LoadTestShape):
    """Sudden burst, then hold — matches Scenario D's D1 sub-test profile.

    Ramps 0 → 1000 VUs in 30s, holds for 60s, then ramps down.
    """

    stages = (
        {"duration": 30, "users": 1000, "spawn_rate": 50},
        {"duration": 90, "users": 1000, "spawn_rate": 50},
        {"duration": 120, "users": 0, "spawn_rate": 50},
    )

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None


class SustainedLoadShape(LoadTestShape):
    """Phase 2 — autoscaling test.

    Holds at a sustained concurrency long enough for DO's autoscaler to
    react (typically ~5 min before trigger fires + 3-5 min cold boot for
    a new droplet to start serving). Then ramps DOWN over several minutes
    so we can observe scale-down behavior — does a droplet termination
    drop in-flight requests? Do running Celery tasks survive?

    Env-configurable:
        SUSTAIN_USERS       target concurrency during the sustain phase (default 250)
        SUSTAIN_MINUTES     how long to hold (default 25 — covers trigger + boot + serve)
        RAMPUP_MINUTES      how long to ramp up to target (default 3)
        RAMPDOWN_MINUTES    how long to ramp down to zero (default 10)
        SPAWN_RATE          users spawned per second during ramps (default 5)

    Total run = RAMPUP + SUSTAIN + RAMPDOWN minutes. Defaults = 38 min.
    """

    def __init__(self):
        super().__init__()
        self.target = int(os.environ.get("SUSTAIN_USERS", "250"))
        self.sustain_secs = int(os.environ.get("SUSTAIN_MINUTES", "25")) * 60
        self.rampup_secs = int(os.environ.get("RAMPUP_MINUTES", "3")) * 60
        self.rampdown_secs = int(os.environ.get("RAMPDOWN_MINUTES", "10")) * 60
        self.spawn_rate = int(os.environ.get("SPAWN_RATE", "5"))

        self._rampup_end = self.rampup_secs
        self._sustain_end = self._rampup_end + self.sustain_secs
        self._rampdown_end = self._sustain_end + self.rampdown_secs

    def tick(self):
        t = self.get_run_time()

        if t < self._rampup_end:
            # Linear ramp 0 → target
            users = int((t / self._rampup_end) * self.target)
            return (max(users, 1), self.spawn_rate)

        if t < self._sustain_end:
            # Hold at target
            return (self.target, self.spawn_rate)

        if t < self._rampdown_end:
            # Linear ramp target → 0
            remaining = self._rampdown_end - t
            users = int((remaining / self.rampdown_secs) * self.target)
            return (max(users, 1), self.spawn_rate)

        return None
