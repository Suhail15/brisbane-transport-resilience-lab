"""Deterministic source-pattern candidates relevant to disrupted journey corridors.

This is a bounded candidate-selection heuristic, not a passenger demand model or
an optimality claim. The recovery optimizer independently evaluates its output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from resilience.contracts import (JourneyRequest, PatternPair, RecoveryCandidate,
                                 Scenario, TimetableSnapshot, TransitLeg)
from resilience.engine.routing import route_many
from resilience.engine.scenarios import apply_scenarios


@dataclass(frozen=True)
class _RelevantPair:
    pair: PatternPair
    requests: frozenset[str]
    lost_requests: frozenset[str]
    anchor_count: int
    departure_distance: int
    cycle_s: int
    routes: frozenset[str]


def _topology(pair: PatternPair) -> tuple:
    # Timing variants and route-id versions with the same physical stop/access
    # sequences should not consume the twelve-candidate bound repeatedly.
    directions = [tuple((stop.stop_id, stop.pickup_allowed, stop.drop_off_allowed)
                        for stop in pattern.stops) for pattern in (pair.outbound, pair.inbound)]
    return tuple(sorted(directions))


def generate_recovery_candidates(snapshot: TimetableSnapshot, requests: Sequence[JourneyRequest],
                                  scenarios: Sequence[Scenario], *, limit: int = 12
                                  ) -> tuple[RecoveryCandidate, ...]:
    if not 1 <= limit <= 12:
        raise ValueError("candidate limit must be between one and twelve")
    if not requests:
        raise ValueError("candidate selection requires a nonempty fixed request set")
    changed = apply_scenarios(snapshot, scenarios)
    baseline = route_many(snapshot, requests)
    disrupted = route_many(changed.snapshot, requests)
    original = {connection.connection_id: connection for connection in snapshot.connections}
    final = {connection.connection_id: connection for connection in changed.snapshot.connections}
    adjacency: dict[str, set[str]] = {}
    for link in snapshot.walking_links:
        # This expansion establishes corridor relevance only. Routing still uses
        # directed links, real duration and at most one complete walking link.
        adjacency.setdefault(link.from_stop_id, set()).add(link.to_stop_id)
        adjacency.setdefault(link.to_stop_id, set()).add(link.from_stop_id)
    corridors = []
    for before, after in zip(baseline, disrupted):
        if before.duration_s is None:
            continue
        if after.duration_s is not None and after.duration_s <= before.duration_s:
            continue
        affected_anchors = set()
        for leg in before.legs:
            if isinstance(leg, TransitLeg):
                for connection_id in leg.connection_ids:
                    connection = original[connection_id]
                    if final.get(connection_id) != connection:
                        affected_anchors.update((connection.from_stop_id, connection.to_stop_id))
        if len(affected_anchors) < 2:
            affected_anchors.update((before.request.origin_stop_id, before.request.destination_stop_id))
        groups = tuple(frozenset({stop_id} | adjacency.get(stop_id, set()))
                       for stop_id in sorted(affected_anchors))
        lost = before.duration_s <= 3600 and (after.duration_s is None or after.duration_s > 3600)
        corridors.append((before.request.request_id, groups, lost))
    if not corridors:
        return ()

    trip_movements: dict[str, list] = {}
    for movement in snapshot.connections:
        trip_movements.setdefault(movement.trip_instance_id, []).append(movement)
    for movements in trip_movements.values():
        movements.sort(key=lambda movement: movement.sequence)
    activation = snapshot.metadata.snapshot_s + 600
    variants: dict[tuple, _RelevantPair] = {}
    for pair in snapshot.recovery_pairs:
        cycle_s = pair.outbound.stops[-1].arrival_offset_s + pair.inbound.stops[-1].arrival_offset_s + 600
        if cycle_s > 7200:
            continue
        departure_distances = []
        supported = True
        for pattern in (pair.outbound, pair.inbound):
            matches = []
            for trip_id in pattern.source_trip_instance_ids:
                movements = trip_movements.get(trip_id)
                if not movements:
                    continue
                stops = (movements[0].from_stop_id,) + tuple(movement.to_stop_id for movement in movements)
                if (stops == tuple(stop.stop_id for stop in pattern.stops)
                        and all(m.mode == "bus" and m.route_id == pattern.route_id for m in movements)):
                    matches.append(abs(movements[0].departure_s - activation))
            if not matches:
                supported = False
                break
            departure_distances.extend(matches)
        if not supported:
            continue
        usable_stops = {stop.stop_id for pattern in (pair.outbound, pair.inbound) for stop in pattern.stops
                        if stop.pickup_allowed or stop.drop_off_allowed}
        relevant, lost, anchors = set(), set(), 0
        for request_id, groups, is_lost in corridors:
            touched = sum(bool(group & usable_stops) for group in groups)
            if touched >= 2:
                relevant.add(request_id)
                anchors += touched
                if is_lost:
                    lost.add(request_id)
        if not relevant:
            continue
        info = _RelevantPair(pair=pair, requests=frozenset(relevant), lost_requests=frozenset(lost),
                             anchor_count=anchors, departure_distance=min(departure_distances),
                             cycle_s=cycle_s, routes=frozenset((pair.outbound.route_id, pair.inbound.route_id)))
        topology = _topology(pair)
        prior = variants.get(topology)
        variant_key = lambda value: (value.departure_distance, value.cycle_s, value.pair.pair_id)
        if prior is None or variant_key(info) < variant_key(prior):
            variants[topology] = info

    selected = []
    covered_requests, covered_lost, selected_routes = set(), set(), set()
    remaining = list(variants.values())
    while remaining and len(selected) < limit:
        best = min(remaining, key=lambda info: (
            -len(info.lost_requests - covered_lost),
            -len(info.requests - covered_requests),
            len(info.routes & selected_routes),
            -len(info.lost_requests), -len(info.requests), -info.anchor_count,
            info.departure_distance, info.cycle_s, info.pair.pair_id,
        ))
        remaining.remove(best)
        selected.append(RecoveryCandidate(candidate_id="candidate:" + best.pair.pair_id,
                                           pair_id=best.pair.pair_id, activation_s=activation))
        covered_requests.update(best.requests)
        covered_lost.update(best.lost_requests)
        selected_routes.update(best.routes)
    return tuple(selected)

