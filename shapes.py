"""LoadTestShape implementations.

`UnifiedSteppedRamp` drives Scenarios A, B, C, Combined, and journey runs.
`SpikeShape` is used for Scenario D variants (sudden burst, then hold).
"""

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
