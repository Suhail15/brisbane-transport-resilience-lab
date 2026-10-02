"""Paired-pattern bus duties and bounded search over recomputed journey routes."""

from __future__ import annotations

from itertools import combinations
from math import comb
from typing import Callable, Sequence

from resilience.contracts import (BusPattern, CandidateIssue, Connection, JourneyRequest, PatternPair,
                                 RecoveryCandidate, RecoveryDuty, RecoveryObjective,
                                 RecoveryPlan, RecoveryProgress, RecoveryResult, Scenario,
                                 TimetableSnapshot)
from resilience.engine.evaluation import _evaluate_routes
from resilience.engine.routing import route_many
from resilience.engine.scenarios import apply_scenarios

TURNAROUND_SECONDS = 300
ACTIVATION_LEAD_SECONDS = 600
BUDGETS = (0, 2, 4, 8)
MAX_CANDIDATES = 12


class RecoveryCancelled(Exception):
    """Cancellation acknowledgement; no partial RecoveryResult is returned."""


def _pattern_has_source(snapshot: TimetableSnapshot, pattern: BusPattern) -> bool:
    for trip_id in pattern.source_trip_instance_ids:
        trip = sorted((connection for connection in snapshot.connections
                       if connection.trip_instance_id == trip_id), key=lambda connection: connection.sequence)
        if not trip:
            continue
        stop_ids = (trip[0].from_stop_id,) + tuple(connection.to_stop_id for connection in trip)
        if (all(connection.mode == "bus" and connection.route_id == pattern.route_id for connection in trip)
                and stop_ids == tuple(stop.stop_id for stop in pattern.stops)):
            return True
    return False


def _pair(snapshot: TimetableSnapshot, pair_id: str) -> PatternPair:
    pairs = {pair.pair_id: pair for pair in snapshot.recovery_pairs}
    if pair_id not in pairs:
        raise ValueError("candidate references an unknown paired pattern")
    pair = pairs[pair_id]
    if not all(_pattern_has_source(snapshot, pattern) for pattern in (pair.outbound, pair.inbound)):
        raise ValueError("both bus patterns require a matching full source trip in the snapshot")
    return pair


def build_recovery_duty(snapshot: TimetableSnapshot,
                        candidate: RecoveryCandidate) -> tuple[RecoveryDuty, tuple[Connection, ...]]:
    if candidate.activation_s < snapshot.metadata.snapshot_s + ACTIVATION_LEAD_SECONDS:
        raise ValueError("a bus duty requires at least ten minutes activation lead")
    pair = _pair(snapshot, candidate.pair_id)
    outbound_s = pair.outbound.stops[-1].arrival_offset_s
    inbound_s = pair.inbound.stops[-1].arrival_offset_s
    cycle_s = outbound_s + TURNAROUND_SECONDS + inbound_s + TURNAROUND_SECONDS
    cycles = candidate.duty_duration_s // cycle_s
    if cycles < 1:
        raise ValueError("the two-hour duty cannot complete one whole round trip and both terminal turns")
    connections = []
    trip_ids = []
    for cycle in range(cycles):
        cycle_start = candidate.activation_s + cycle * cycle_s
        for direction, pattern, departure in (
                ("out", pair.outbound, cycle_start),
                ("back", pair.inbound, cycle_start + outbound_s + TURNAROUND_SECONDS)):
            trip_id = f"relief:{candidate.candidate_id}:{cycle}:{direction}"
            trip_ids.append(trip_id)
            for sequence, (previous, current) in enumerate(zip(pattern.stops, pattern.stops[1:])):
                connections.append(Connection(connection_id=f"{trip_id}:{sequence}",
                                              trip_instance_id=trip_id, route_id=pattern.route_id,
                                              mode="bus", sequence=sequence,
                                              from_stop_id=previous.stop_id, to_stop_id=current.stop_id,
                                              departure_s=departure + previous.departure_offset_s,
                                              arrival_s=departure + current.arrival_offset_s,
                                              pickup_allowed=previous.pickup_allowed,
                                              drop_off_allowed=current.drop_off_allowed,
                                              provenance="hypothetical_relief"))
    old_connections = {connection.connection_id for connection in snapshot.connections}
    old_trips = {connection.trip_instance_id for connection in snapshot.connections}
    if old_connections & {connection.connection_id for connection in connections} or old_trips & set(trip_ids):
        raise ValueError("relief identifiers collide with existing services")
    duty = RecoveryDuty(candidate=candidate, cycle_count=cycles,
                        duty_end_s=candidate.activation_s + candidate.duty_duration_s,
                        connection_ids=tuple(connection.connection_id for connection in connections),
                        trip_instance_ids=tuple(trip_ids))
    return duty, tuple(connections)


def _objective_key(objective: RecoveryObjective) -> tuple[int, int, int]:
    return -objective.restored_count, objective.total_capped_duration_s, objective.bus_hours


def _plan_key(plan: RecoveryPlan) -> tuple[int, int, int, tuple[str, ...]]:
    return _objective_key(plan.objective) + (plan.candidate_ids,)


class _Search:
    def __init__(self, snapshot: TimetableSnapshot, requests: Sequence[JourneyRequest],
                 scenarios: Sequence[Scenario], candidates: Sequence[RecoveryCandidate], budget: int,
                 on_progress: Callable[[RecoveryProgress], None] | None = None,
                 should_cancel: Callable[[], bool] | None = None):
        if budget not in BUDGETS:
            raise ValueError("bus-hour budget must be 0, 2, 4 or 8")
        if not requests:
            raise ValueError("recovery requires a nonempty fixed request set")
        if len(candidates) > MAX_CANDIDATES:
            raise ValueError("at most twelve recovery candidates are supported")
        if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
            raise ValueError("candidate ids must be unique")
        self.snapshot, self.requests, self.scenarios = snapshot, requests, scenarios
        self.budget, self.max_buses = budget, budget // 2
        self.candidates = {candidate.candidate_id: candidate for candidate in candidates}
        self.on_progress, self.should_cancel = on_progress, should_cancel
        self.stage, self.evaluation_upper_bound = "preparing", None
        self.cache: dict[tuple[str, ...], RecoveryPlan] = {}
        self.duties: dict[str, RecoveryDuty] = {}
        self.notify()
        self.changed = apply_scenarios(snapshot, scenarios)
        self.check_cancel()
        self.baseline = route_many(snapshot, requests)
        self.check_cancel()
        self.disrupted = route_many(self.changed.snapshot, requests)
        self.additions: dict[str, tuple[Connection, ...]] = {}
        self.infeasible: list[str] = []
        self.infeasible_reasons: list[CandidateIssue] = []

        for candidate_id in sorted(self.candidates):
            self.check_cancel()
            try:
                duty, additions = build_recovery_duty(snapshot, self.candidates[candidate_id])
                extended = TimetableSnapshot(metadata=snapshot.metadata, stops=snapshot.stops,
                                             connections=snapshot.connections + additions,
                                             walking_links=snapshot.walking_links,
                                             recovery_pairs=snapshot.recovery_pairs)
                changed = apply_scenarios(extended, scenarios)
                if set(duty.trip_instance_ids) & set(changed.impact.cancelled_trip_instance_ids):
                    raise ValueError("the scenario blocks an added bus trip, so the complete duty is infeasible")
                self.duties[candidate_id], self.additions[candidate_id] = duty, additions
            except ValueError as exc:
                self.infeasible.append(candidate_id)
                self.infeasible_reasons.append(CandidateIssue(candidate_id=candidate_id, reason=str(exc)))
        self.feasible = tuple(sorted(self.duties))
        self.notify()

    def check_cancel(self) -> None:
        if self.should_cancel is not None and self.should_cancel():
            raise RecoveryCancelled("recovery cancelled at a plan evaluation boundary")

    def notify(self) -> None:
        self.check_cancel()
        if self.on_progress is not None:
            self.on_progress(RecoveryProgress(stage=self.stage, evaluated_plan_count=len(self.cache),
                                              considered_candidate_count=len(self.candidates),
                                              feasible_candidate_count=len(self.duties),
                                              evaluation_upper_bound=self.evaluation_upper_bound))
        self.check_cancel()

    def evaluate(self, candidate_ids: Sequence[str]) -> RecoveryPlan:
        self.check_cancel()
        selected = tuple(sorted(candidate_ids))
        if len(set(selected)) != len(selected) or len(selected) > self.max_buses:
            raise ValueError("plan duplicates a bus duty or exceeds the budget")
        if set(selected) - set(self.feasible):
            raise ValueError("plan selects an infeasible candidate")
        if selected in self.cache:
            return self.cache[selected]
        if selected:
            additions = tuple(connection for candidate_id in selected
                              for connection in self.additions[candidate_id])
            extended = TimetableSnapshot(metadata=self.snapshot.metadata, stops=self.snapshot.stops,
                                         connections=self.snapshot.connections + additions,
                                         walking_links=self.snapshot.walking_links,
                                         recovery_pairs=self.snapshot.recovery_pairs)
            final = apply_scenarios(extended, self.scenarios).snapshot
            recovered = route_many(final, self.requests)
        else:
            recovered = self.disrupted
        evaluation = _evaluate_routes(self.baseline, self.disrupted, recovered,
                                      self.changed.snapshot, self.changed.impact)
        self.check_cancel()
        objective = RecoveryObjective(restored_count=evaluation.metrics.restored_count,
                                      total_capped_duration_s=evaluation.metrics.recovered_total_capped_duration_s,
                                      bus_hours=len(selected) * 2)
        plan = RecoveryPlan(candidate_ids=selected,
                            duties=tuple(self.duties[candidate_id] for candidate_id in selected),
                            bus_count=len(selected), bus_hours=len(selected) * 2,
                            objective=objective, evaluation=evaluation)
        self.cache[selected] = plan
        self.notify()
        return plan

    def busiest(self) -> RecoveryPlan | None:
        if self.max_buses == 0 or not self.feasible:
            return None
        original = {connection.connection_id: connection for connection in self.snapshot.connections}
        final = {connection.connection_id: connection for connection in self.changed.snapshot.connections}
        affected = {connection.trip_instance_id for connection_id, connection in original.items()
                    if final.get(connection_id) != connection}
        counts = {}
        for candidate_id in self.feasible:
            pair = _pair(self.snapshot, self.candidates[candidate_id].pair_id)
            source_ids = set(pair.outbound.source_trip_instance_ids + pair.inbound.source_trip_instance_ids)
            counts[candidate_id] = len(source_ids & affected)
        eligible = [candidate_id for candidate_id in self.feasible if counts[candidate_id] > 0]
        if not eligible:
            return None
        busiest_id = min(eligible, key=lambda candidate_id: (-counts[candidate_id],
                                                           self.candidates[candidate_id].pair_id,
                                                           self.candidates[candidate_id].activation_s,
                                                           candidate_id))
        pair_id = self.candidates[busiest_id].pair_id
        matching = sorted((candidate_id for candidate_id in self.feasible
                           if self.candidates[candidate_id].pair_id == pair_id),
                          key=lambda candidate_id: (self.candidates[candidate_id].activation_s, candidate_id))
        return self.evaluate(matching[:self.max_buses])

    def result(self, method: str, optimality_proven: bool) -> RecoveryResult:
        no_action = self.evaluate(())
        busiest = self.busiest()
        best = min(self.cache.values(), key=_plan_key)
        self.stage = "completed"
        self.notify()
        return RecoveryResult(budget_bus_hours=self.budget, plan=best,
                              no_intervention=no_action.objective,
                              busiest_affected_pattern=busiest.objective if busiest else None,
                              evaluated_plan_count=len(self.cache),
                              considered_candidate_ids=tuple(sorted(self.candidates)),
                              infeasible_candidate_ids=tuple(self.infeasible),
                              infeasible_candidates=tuple(self.infeasible_reasons),
                              method=method, optimality_proven=optimality_proven)


def plan_recovery(snapshot: TimetableSnapshot, requests: Sequence[JourneyRequest],
                  scenarios: Sequence[Scenario], candidates: Sequence[RecoveryCandidate],
                  budget_bus_hours: int, *, max_swap_evaluations: int = 128,
                  on_progress: Callable[[RecoveryProgress], None] | None = None,
                  should_cancel: Callable[[], bool] | None = None) -> RecoveryResult:
    if not 0 <= max_swap_evaluations <= 4096:
        raise ValueError("swap evaluation bound must lie between zero and 4096")
    search = _Search(snapshot, requests, scenarios, candidates, budget_bus_hours,
                     on_progress, should_cancel)
    search.evaluation_upper_bound = (2 + sum(max(0, len(search.feasible) - index)
                                             for index in range(search.max_buses))
                                      + max_swap_evaluations)
    search.stage = "greedy"
    search.evaluate(())
    search.busiest()
    greedy: tuple[str, ...] = ()
    for _ in range(min(search.max_buses, len(search.feasible))):
        trials = [search.evaluate(greedy + (candidate_id,)) for candidate_id in search.feasible
                  if candidate_id not in greedy]
        greedy = min(trials, key=_plan_key).candidate_ids

    # Start swaps from every greedy prefix and the simple policy, retaining no
    # action independently. One- and two-duty replacements can expose complementarity.
    seeds = sorted(search.cache, key=lambda ids: _plan_key(search.cache[ids]))
    search.stage = "swaps"
    search.notify()
    pending: set[tuple[str, ...]] = set()
    for seed in seeds:
        for remove_count in range(min(2, len(seed)) + 1):
            for removed in combinations(seed, remove_count):
                retained = set(seed) - set(removed)
                available = tuple(candidate_id for candidate_id in search.feasible if candidate_id not in retained)
                for add_count in range(min(2, search.max_buses - len(retained)) + 1):
                    for added in combinations(available, add_count):
                        selected = tuple(sorted(retained | set(added)))
                        if selected not in search.cache:
                            pending.add(selected)
    for selected in sorted(pending, key=lambda ids: (len(ids), ids))[:max_swap_evaluations]:
        search.evaluate(selected)
    return search.result("greedy_bounded_swap", False)


def exhaustive_recovery(snapshot: TimetableSnapshot, requests: Sequence[JourneyRequest],
                        scenarios: Sequence[Scenario], candidates: Sequence[RecoveryCandidate],
                        budget_bus_hours: int, *,
                        on_progress: Callable[[RecoveryProgress], None] | None = None,
                        should_cancel: Callable[[], bool] | None = None) -> RecoveryResult:
    if len(candidates) > 8:
        raise ValueError("exhaustive reference is limited to eight candidate duties")
    search = _Search(snapshot, requests, scenarios, candidates, budget_bus_hours,
                     on_progress, should_cancel)
    search.stage = "exhaustive"
    search.evaluation_upper_bound = sum(comb(len(search.feasible), count)
                                        for count in range(min(search.max_buses, len(search.feasible)) + 1))
    for count in range(min(search.max_buses, len(search.feasible)) + 1):
        for selected in combinations(search.feasible, count):
            search.evaluate(selected)
    return search.result("exhaustive", True)
