"""Pure scenario transformations: future delay first, then restrictions."""

from __future__ import annotations

from typing import Sequence

from resilience.contracts import (AdditionalDelay, Connection, CorridorClosure,
                                 Scenario, ScenarioApplication, ScenarioImpact,
                                 StopUnavailable, TimetableSnapshot, TripCancellation)


def _overlaps(connection: Connection, start_s: int, end_s: int) -> bool:
    if connection.departure_s == connection.arrival_s:
        return start_s <= connection.departure_s < end_s
    return connection.departure_s < end_s and connection.arrival_s > start_s


def _crosses(connection: Connection, scenario: CorridorClosure) -> bool:
    for segment in scenario.segments:
        if (connection.from_stop_id, connection.to_stop_id) == (segment.from_stop_id, segment.to_stop_id):
            return True
        if segment.bidirectional and (connection.to_stop_id, connection.from_stop_id) == (
                segment.from_stop_id, segment.to_stop_id):
            return True
    return False


def _validate_scenarios(snapshot: TimetableSnapshot, scenarios: Sequence[Scenario]) -> None:
    if len({scenario.scenario_id for scenario in scenarios}) != len(scenarios):
        raise ValueError("scenario ids must be unique")
    trips = {connection.trip_instance_id for connection in snapshot.connections}
    stops = {stop.stop_id for stop in snapshot.stops}
    for scenario in scenarios:
        if isinstance(scenario, (TripCancellation, AdditionalDelay)):
            if set(scenario.trip_instance_ids) - trips:
                raise ValueError("scenario references an unknown trip instance")
        elif isinstance(scenario, StopUnavailable):
            if set(scenario.stop_ids) - stops:
                raise ValueError("scenario references an unknown stop")
        elif isinstance(scenario, CorridorClosure):
            for segment in scenario.segments:
                if segment.from_stop_id not in stops or segment.to_stop_id not in stops:
                    raise ValueError("corridor references an unknown stop")
                if not any(_crosses(connection, CorridorClosure(
                        scenario_id=scenario.scenario_id, start_s=scenario.start_s,
                        end_s=scenario.end_s, segments=(segment,))) for connection in snapshot.connections):
                    raise ValueError("corridor does not identify an existing adjacent movement")


def apply_scenarios(snapshot: TimetableSnapshot, scenarios: Sequence[Scenario]) -> ScenarioApplication:
    _validate_scenarios(snapshot, scenarios)
    delays: dict[str, list[tuple[int, int]]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, AdditionalDelay):
            continue
        start = max(scenario.start_s, snapshot.metadata.snapshot_s)
        for trip_id in set(scenario.trip_instance_ids):
            eligible = [connection.sequence for connection in snapshot.connections
                        if connection.trip_instance_id == trip_id
                        and start <= connection.departure_s < scenario.end_s]
            if eligible:
                delays.setdefault(trip_id, []).append((min(eligible), scenario.additional_seconds))

    effective = []
    for connection in snapshot.connections:
        delta = sum(amount for sequence, amount in delays.get(connection.trip_instance_id, ())
                    if connection.sequence >= sequence)
        effective.append(connection.model_copy(update={
            "departure_s": connection.departure_s + delta,
            "arrival_s": connection.arrival_s + delta,
        }) if delta else connection)

    cancelled: set[str] = set()
    unavailable: set[str] = set()
    for scenario in scenarios:
        if isinstance(scenario, TripCancellation):
            selected = set(scenario.trip_instance_ids)
            cancelled.update(connection.trip_instance_id for connection in effective
                             if connection.trip_instance_id in selected
                             and _overlaps(connection, scenario.start_s, scenario.end_s))
        elif isinstance(scenario, CorridorClosure):
            cancelled.update(connection.trip_instance_id for connection in effective
                             if _crosses(connection, scenario)
                             and _overlaps(connection, scenario.start_s, scenario.end_s))
        elif isinstance(scenario, StopUnavailable):
            unavailable.update(scenario.stop_ids)

    result = []
    for connection in effective:
        if connection.trip_instance_id in cancelled:
            continue
        pickup = connection.pickup_allowed
        drop_off = connection.drop_off_allowed
        for scenario in scenarios:
            if not isinstance(scenario, StopUnavailable):
                continue
            if (connection.from_stop_id in scenario.stop_ids
                    and scenario.start_s <= connection.departure_s < scenario.end_s):
                pickup = False
            if (connection.to_stop_id in scenario.stop_ids
                    and scenario.start_s <= connection.arrival_s < scenario.end_s):
                drop_off = False
        result.append(connection.model_copy(update={"pickup_allowed": pickup,
                                                    "drop_off_allowed": drop_off})
                      if pickup != connection.pickup_allowed or drop_off != connection.drop_off_allowed
                      else connection)
    transformed = TimetableSnapshot(metadata=snapshot.metadata, stops=snapshot.stops,
                                    connections=tuple(result), walking_links=snapshot.walking_links,
                                    recovery_pairs=snapshot.recovery_pairs)
    return ScenarioApplication(snapshot=transformed,
                               impact=ScenarioImpact(cancelled_trip_instance_ids=tuple(sorted(cancelled)),
                                                     delayed_trip_instance_ids=tuple(sorted(delays)),
                                                     unavailable_stop_ids=tuple(sorted(unavailable))))

