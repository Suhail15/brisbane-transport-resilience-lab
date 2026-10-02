from datetime import timedelta

import pytest
from pydantic import ValidationError

from resilience.contracts import (AdditionalDelay, CorridorClosure, CorridorSegment,
                                 SnapshotMetadata, StopUnavailable, TripCancellation,
                                 WalkingLink)
from resilience.engine import apply_scenarios, evaluate_scenarios, route
from tests.engine.fixtures import MIDNIGHT, connection, request, snapshot, walk


def test_receipt_cutoff_is_distinct_from_event_time_and_times_are_aware():
    data = snapshot(stops=("A",))
    source = data.metadata.sources[0]
    late = source.model_copy(update={"received_at": MIDNIGHT + timedelta(seconds=1),
                                     "event_at": MIDNIGHT - timedelta(hours=1)})
    with pytest.raises(ValidationError, match="received after"):
        SnapshotMetadata(**{**data.metadata.model_dump(), "sources": (late,)})
    later_event = source.model_copy(update={"event_at": MIDNIGHT + timedelta(seconds=20)})
    valid = SnapshotMetadata(**{**data.metadata.model_dump(), "sources": (later_event,)})
    assert valid.sources[0].event_at > valid.snapshot_at
    with pytest.raises(ValidationError, match="timezone"):
        SnapshotMetadata(**{**data.metadata.model_dump(), "snapshot_at": MIDNIGHT.replace(tzinfo=None)})
    assert snapshot(stops=("A",), as_of_s=90000).metadata.snapshot_s == 90000


def test_walking_contract_rejects_fabricated_speed_distance_and_snap_tolerance():
    original = walk("A", "B")
    for update in ({"duration_s": 1}, {"length_m": 601, "duration_s": 501},
                   {"from_snap_distance_m": 31}):
        with pytest.raises(ValidationError):
            WalkingLink(**{**original.model_dump(), **update})


def test_full_trip_contiguity_is_a_validation_gate():
    with pytest.raises(ValidationError, match="contiguous"):
        snapshot((connection("gap", "A", "B", 0, 100, 1),))
    with pytest.raises(ValidationError, match="chronological"):
        snapshot((connection("bad", "A", "B", 0, 200, 0),
                  connection("bad", "B", "C", 100, 300, 1)))


def test_stop_unavailable_blocks_events_but_vehicle_can_pass():
    movements = (connection("pass", "A", "B", 100, 200, 0),
                 connection("pass", "B", "C", 205, 300, 1),
                 connection("later", "B", "C", 301, 400))
    data = snapshot(movements)
    scenario = StopUnavailable(scenario_id="closed", start_s=200, end_s=301, stop_ids=("B",))
    result = apply_scenarios(data, (scenario,))
    assert route(result.snapshot, request("A", "C", 100)).arrival_s == 300
    assert not route(result.snapshot, request("A", "B", 100)).reachable
    assert route(result.snapshot, request("B", "C", 200)).arrival_s == 400
    assert data.connections[0].drop_off_allowed  # original is unchanged


def test_trip_cancellation_removes_full_trip_not_just_overlap():
    data = snapshot((connection("all", "A", "B", 100, 200, 0),
                     connection("all", "B", "C", 300, 400, 1),
                     connection("other", "A", "C", 1000, 1100)))
    cancellation = TripCancellation(scenario_id="cancel", start_s=350, end_s=360,
                                    trip_instance_ids=("all", "other"))
    changed = apply_scenarios(data, (cancellation,))
    assert changed.impact.cancelled_trip_instance_ids == ("all",)
    assert tuple(connection.trip_instance_id for connection in changed.snapshot.connections) == ("other",)


def test_corridor_crossing_cancels_full_trip_with_half_open_boundaries():
    data = snapshot((connection("all", "A", "B", 100, 200, 0),
                     connection("all", "B", "C", 300, 400, 1)))
    segment = CorridorSegment(from_stop_id="B", to_stop_id="C")
    closure = CorridorClosure(scenario_id="corridor", start_s=350, end_s=360, segments=(segment,))
    assert not apply_scenarios(data, (closure,)).snapshot.connections
    after_arrival = closure.model_copy(update={"start_s": 400, "end_s": 401})
    before_departure = closure.model_copy(update={"start_s": 200, "end_s": 300})
    assert apply_scenarios(data, (after_arrival,)).snapshot.connections == data.connections
    assert apply_scenarios(data, (before_departure,)).snapshot.connections == data.connections


def test_additional_delays_are_future_only_cumulative_and_order_independent():
    data = snapshot((connection("trip", "A", "B", 100, 200, 0),
                     connection("trip", "B", "C", 300, 400, 1),
                     connection("trip", "C", "D", 500, 600, 2)), as_of_s=250)
    first = AdditionalDelay(scenario_id="one", start_s=0, end_s=1000,
                            trip_instance_ids=("trip",), additional_seconds=60)
    second = AdditionalDelay(scenario_id="two", start_s=280, end_s=350,
                             trip_instance_ids=("trip",), additional_seconds=30)
    changed = apply_scenarios(data, (first, second))
    assert changed == apply_scenarios(data, (second, first))
    assert [(c.departure_s, c.arrival_s) for c in changed.snapshot.connections] == [
        (100, 200), (390, 490), (590, 690)]
    assert [(c.departure_s, c.arrival_s) for c in data.connections] == [
        (100, 200), (300, 400), (500, 600)]


def test_restrictions_use_delayed_effective_times():
    data = snapshot((connection("trip", "A", "B", 100, 200),))
    delay = AdditionalDelay(scenario_id="delay", start_s=0, end_s=150,
                            trip_instance_ids=("trip",), additional_seconds=100)
    closed = StopUnavailable(scenario_id="closed", start_s=300, end_s=301, stop_ids=("B",))
    changed = apply_scenarios(data, (closed, delay))
    assert changed.snapshot.connections[0].arrival_s == 300
    assert not changed.snapshot.connections[0].drop_off_allowed
    closure = CorridorClosure(scenario_id="corridor", start_s=250, end_s=251,
                              segments=(CorridorSegment(from_stop_id="A", to_stop_id="B"),))
    assert not apply_scenarios(data, (closure, delay)).snapshot.connections


def test_unknown_scenario_references_fail_explicitly():
    data = snapshot((connection("trip", "A", "B", 100, 200),), stops=("C",))
    with pytest.raises(ValueError, match="unknown trip"):
        apply_scenarios(data, (TripCancellation(scenario_id="x", start_s=0, end_s=1000,
                                               trip_instance_ids=("absent",)),))
    with pytest.raises(ValueError, match="adjacent"):
        apply_scenarios(data, (CorridorClosure(scenario_id="x", start_s=0, end_s=1000,
                                              segments=(CorridorSegment(from_stop_id="A", to_stop_id="C"),)),))


def test_metrics_use_all_requests_and_do_not_drop_unreachable_durations_or_use_weights():
    data = snapshot((connection("lost", "A", "B", 0, 300),
                     connection("late", "A", "C", 0, 4000)), stops=("D",))
    queries = (request("A", "B", request_id="q1", od_weight=100),
               request("A", "C", request_id="q2", od_weight=1),
               request("A", "D", request_id="q3"))
    scenario = TripCancellation(scenario_id="cancel", start_s=0, end_s=500,
                                trip_instance_ids=("lost",))
    disrupted = apply_scenarios(data, (scenario,)).snapshot
    relief = connection("test-relief", "A", "B", 600, 900, provenance="hypothetical_relief")
    recovered = snapshot(disrupted.connections + (relief,), stops=("D",))
    evaluation = evaluate_scenarios(data, queries, (scenario,), recovered_snapshot=recovered)
    metrics = evaluation.metrics
    assert (metrics.request_count, metrics.baseline_reachable_count, metrics.disrupted_reachable_count,
            metrics.recovered_reachable_count, metrics.lost_count, metrics.restored_count) == (3, 1, 0, 1, 1, 1)
    assert metrics.restored_fraction == 1
    # Independently: 300+4000+5400; 5400+4000+5400; 900+4000+5400.
    assert (metrics.baseline_total_capped_duration_s, metrics.disrupted_total_capped_duration_s,
            metrics.recovered_total_capped_duration_s) == (9700, 14800, 10300)
    assert evaluation.baseline[1].duration_s == 4000
    assert evaluation.baseline[2].duration_s is None


def test_zero_lost_denominator_is_null_and_long_reachable_duration_is_capped():
    data = snapshot((connection("long", "A", "B", 0, 8000),))
    evaluation = evaluate_scenarios(data, (request("A", "B"),), ())
    assert evaluation.metrics.restored_fraction is None
    assert evaluation.metrics.baseline_total_capped_duration_s == 5400
    assert evaluation.baseline[0].duration_s == 8000


def test_missed_connection_is_timing_failure_with_one_walk_and_one_allowance():
    data = snapshot((connection("first", "A", "B", 100, 200),
                     connection("next", "X", "C", 600, 700),
                     connection("alternative", "X", "C", 1000, 1100)), (walk("B", "X"),))
    delay = AdditionalDelay(scenario_id="delay", start_s=100, end_s=101,
                            trip_instance_ids=("first",), additional_seconds=1)
    evaluation = evaluate_scenarios(data, (request("A", "C", 100),), (delay,))
    assert (evaluation.metrics.requests_with_missed_connections, evaluation.metrics.missed_connection_count) == (1, 1)
    assert (evaluation.missed_connections[0].earliest_boarding_s,
            evaluation.missed_connections[0].departure_s) == (601, 600)
    assert evaluation.disrupted[0].arrival_s == 1100
    cancellation = TripCancellation(scenario_id="cancel", start_s=0, end_s=900,
                                    trip_instance_ids=("next",))
    assert evaluate_scenarios(data, (request("A", "C", 100),), (cancellation,)).metrics.missed_connection_count == 0
    closed = StopUnavailable(scenario_id="closed", start_s=600, end_s=601, stop_ids=("X",))
    assert evaluate_scenarios(data, (request("A", "C", 100),), (closed,)).metrics.missed_connection_count == 0

