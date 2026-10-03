"""Stable pure-engine exports. No I/O occurs during import or analysis."""

ENGINE_VERSION = "csa-resilience-1.1.0"
JOURNEY_SET_VERSION = "equal-weight-fixed-requests-v1"
OBJECTIVE_VERSION = "restored-60m-duration-cap-90m-bus-hours-v1"

from resilience.engine.evaluation import evaluate_scenarios
from resilience.engine.candidates import generate_recovery_candidates
from resilience.engine.recovery import (RecoveryCancelled, build_recovery_duty, exhaustive_recovery,
                                       plan_recovery)
from resilience.engine.routing import generate_journey_requests, route, route_many
from resilience.engine.scenarios import apply_scenarios

__all__ = ["route", "route_many", "generate_journey_requests", "apply_scenarios",
           "evaluate_scenarios", "generate_recovery_candidates", "build_recovery_duty",
           "plan_recovery", "exhaustive_recovery", "RecoveryCancelled", "ENGINE_VERSION",
           "JOURNEY_SET_VERSION", "OBJECTIVE_VERSION"]
