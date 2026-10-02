"""Equal-request metrics, explicit unreachable costs, and planned transfer misses."""

from __future__ import annotations

from typing import Sequence

from resilience.contracts import (EvaluationMetrics, JourneyRequest, MissedConnection,
                                 RouteResult, Scenario, ScenarioEvaluation,
                                 ScenarioImpact, TimetableSnapshot, TransitLeg,
                                 WalkingLeg)
from resilience.engine.routing import TRANSFER_SECONDS, route_many
from resilience.engine.scenarios import apply_scenarios

REACHABILITY_SECONDS = 3600
DURATION_CAP_SECONDS = 5400


def _within_horizon(result: RouteResult) -> bool:
    return result.reachable and result.duration_s is not None and result.duration_s <= REACHABILITY_SECONDS


def _capped_duration(result: RouteResult) -> int:
    return min(result.duration_s, DURATION_CAP_SECONDS) if result.duration_s is not None else DURATION_CAP_SECONDS


def _missed_connections(baseline: Sequence[RouteResult],
                        disrupted_snapshot: TimetableSnapshot) -> tuple[MissedConnection, ...]:
    connections = {connection.connection_id: connection for connection in disrupted_snapshot.connections}
    misses = []
    for journey in baseline:
        previous: TransitLeg | None = None
        walking_s = 0
        for leg in journey.legs:
            if isinstance(leg, WalkingLeg):
                if previous is not None:
                    walking_s += leg.arrival_s - leg.departure_s
                continue
            if previous is not None:
                # Missing services / unavailable events are not timing failures.
                still_exists = all(connection_id in connections
                                   for connection_id in previous.connection_ids + leg.connection_ids)
                if still_exists:
                    alight = connections[previous.connection_ids[-1]]
                    board = connections[leg.connection_ids[0]]
                    earliest = alight.arrival_s + walking_s + TRANSFER_SECONDS
                    if alight.drop_off_allowed and board.pickup_allowed and earliest > board.departure_s:
                        misses.append(MissedConnection(request_id=journey.request.request_id,
                                                       from_trip_instance_id=previous.trip_instance_id,
                                                       to_trip_instance_id=leg.trip_instance_id,
                                                       alight_stop_id=previous.to_stop_id,
                                                       board_stop_id=leg.from_stop_id,
                                                       earliest_boarding_s=earliest,
                                                       departure_s=board.departure_s))
            previous = leg
            walking_s = 0
    return tuple(misses)


def _evaluate_routes(baseline: tuple[RouteResult, ...], disrupted: tuple[RouteResult, ...],
                     recovered: tuple[RouteResult, ...], disrupted_snapshot: TimetableSnapshot,
                     impact: ScenarioImpact) -> ScenarioEvaluation:
    ids = tuple(result.request.request_id for result in baseline)
    if (tuple(result.request.request_id for result in disrupted) != ids
            or tuple(result.request.request_id for result in recovered) != ids):
        raise ValueError("compared routes must use the identical ordered request set")
    baseline_ids = {result.request.request_id for result in baseline if _within_horizon(result)}
    disrupted_ids = {result.request.request_id for result in disrupted if _within_horizon(result)}
    recovered_ids = {result.request.request_id for result in recovered if _within_horizon(result)}
    lost = baseline_ids - disrupted_ids
    restored = lost & recovered_ids
    misses = _missed_connections(baseline, disrupted_snapshot)
    metrics = EvaluationMetrics(
        request_count=len(baseline), baseline_reachable_count=len(baseline_ids),
        disrupted_reachable_count=len(disrupted_ids), recovered_reachable_count=len(recovered_ids),
        lost_count=len(lost), restored_count=len(restored),
        restored_fraction=len(restored) / len(lost) if lost else None,
        baseline_total_capped_duration_s=sum(_capped_duration(result) for result in baseline),
        disrupted_total_capped_duration_s=sum(_capped_duration(result) for result in disrupted),
        recovered_total_capped_duration_s=sum(_capped_duration(result) for result in recovered),
        requests_with_missed_connections=len({miss.request_id for miss in misses}),
        missed_connection_count=len(misses),
    )
    return ScenarioEvaluation(baseline=baseline, disrupted=disrupted, recovered=recovered,
                              metrics=metrics, missed_connections=misses, impact=impact)


def evaluate_scenarios(snapshot: TimetableSnapshot, requests: Sequence[JourneyRequest],
                       scenarios: Sequence[Scenario],
                       *, recovered_snapshot: TimetableSnapshot | None = None) -> ScenarioEvaluation:
    if not requests:
        raise ValueError("an evaluation requires at least one journey request")
    changed = apply_scenarios(snapshot, scenarios)
    baseline = route_many(snapshot, requests)
    disrupted = route_many(changed.snapshot, requests)
    if recovered_snapshot is None:
        recovered = disrupted
    else:
        if recovered_snapshot.metadata != snapshot.metadata:
            raise ValueError("recovery must retain the original snapshot provenance and quality")
        recovered = route_many(recovered_snapshot, requests)
    return _evaluate_routes(baseline, disrupted, recovered, changed.snapshot, changed.impact)

