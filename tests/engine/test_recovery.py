from itertools import combinations

import pytest

from resilience.contracts import (CorridorClosure, CorridorSegment, RecoveryCandidate,
                                 StopUnavailable, TripCancellation)
from resilience.engine import RecoveryCancelled, build_recovery_duty, exhaustive_recovery, plan_recovery
from tests.engine.fixtures import paired_pattern, request, snapshot


def candidate(candidate_id, pair_id="p", activation=600):
    return RecoveryCandidate(candidate_id=candidate_id, pair_id=pair_id, activation_s=activation)


def test_duty_is_one_bus_two_hours_with_both_turnarounds_and_complete_cycles():
    pair, sources = paired_pattern("p", "A", "B", 600, 600)
    data = snapshot(sources, pairs=(pair,))
    duty, movements = build_recovery_duty(data, candidate("bus"))
    # 600 out + 300 turn + 600 back + 300 turn = 1800; 7200 / 1800 = 4.
    assert duty.cycle_count == 4
    assert duty.duty_end_s == 7800
    assert [c.departure_s for c in movements] == [600, 1500, 2400, 3300, 4200, 5100, 6000, 6900]
    assert movements[-1].arrival_s == 7500
    assert movements[-1].arrival_s + 300 == duty.duty_end_s
    assert all(c.provenance == "hypothetical_relief" for c in movements)
    assert duty.candidate.bus_hours == 2


def test_partial_round_trip_is_not_generated_but_full_duty_is_costed():
    pair, sources = paired_pattern("p", "A", "B", 1000, 1000)
    duty, movements = build_recovery_duty(snapshot(sources, pairs=(pair,)), candidate("bus"))
    # Complete cycle2600: two cycles5200 fit, three7800 do not.
    assert duty.cycle_count == 2
    assert len(movements) == 4
    assert movements[-1].arrival_s == 5500
    assert duty.duty_end_s == 7800
    assert duty.candidate.bus_hours == 2


def test_activation_lead_and_existing_patterns_are_enforced():
    pair, sources = paired_pattern("p", "A", "B")
    data = snapshot(sources, pairs=(pair,))
    with pytest.raises(ValueError, match="ten minutes"):
        build_recovery_duty(data, candidate("early", activation=599))
    with pytest.raises(ValueError, match="source trip"):
        build_recovery_duty(snapshot(pairs=(pair,)), candidate("invented"))
    huge_pair, huge_sources = paired_pattern("huge", "A", "B", 4000, 4000)
    with pytest.raises(ValueError, match="whole round trip"):
        build_recovery_duty(snapshot(huge_sources, pairs=(huge_pair,)), candidate("too_long", "huge"))


def recovery_fixture():
    p, p_sources = paired_pattern("p", "A", "B", 600, 600)
    q, q_sources = paired_pattern("q", "C", "D", 300, 300)
    data = snapshot(p_sources + q_sources, pairs=(p, q), stops=("E", "F"))
    queries = (request("A", "B", request_id="p-query"), request("C", "D", request_id="q-query"))
    scenario = TripCancellation(scenario_id="cancel", start_s=0, end_s=700,
                                trip_instance_ids=("p:source:out", "q:source:out"))
    additions = (candidate("p-fast", "p"), candidate("p-late", "p", 1200),
                 candidate("q1", "q"), candidate("q2", "q"))
    return data, queries, (scenario,), additions


def independent_small_plan_objective(selected):
    # Manual duty arrival arithmetic for two isolated OD pairs. Unreachable5400;
    # p-fast600+600=1200, p-late1200+600=1800, q600+300=900.
    p = min([1200 if c == "p-fast" else 1800 for c in selected if c.startswith("p-")] or [5400])
    q = 900 if any(c.startswith("q") for c in selected) else 5400
    restored = int(p <= 3600) + int(q <= 3600)
    return -restored, p + q, 2 * len(selected), tuple(sorted(selected))


@pytest.mark.parametrize("budget", [0, 2, 4, 8])
def test_greedy_swap_and_exhaustive_match_independently_calculated_small_optimum(budget):
    data, queries, scenarios, additions = recovery_fixture()
    bounded = plan_recovery(data, queries, scenarios, additions, budget)
    exact = exhaustive_recovery(data, queries, scenarios, additions, budget)
    ids = tuple(c.candidate_id for c in additions)
    all_feasible = [subset for count in range(min(budget // 2, len(ids)) + 1) for subset in combinations(ids, count)]
    independently_best = min(all_feasible, key=independent_small_plan_objective)
    assert bounded.plan.candidate_ids == exact.plan.candidate_ids == tuple(sorted(independently_best))
    expected = independent_small_plan_objective(independently_best)
    assert (bounded.plan.objective.restored_count, bounded.plan.objective.total_capped_duration_s,
            bounded.plan.objective.bus_hours) == (-expected[0], expected[1], expected[2])
    assert bounded.optimality_proven is False
    assert exact.optimality_proven is True
    assert bounded.plan.bus_count <= 4 and bounded.plan.bus_hours <= budget
    assert bounded.plan.objective.restored_count >= bounded.no_intervention.restored_count
    if bounded.busiest_affected_pattern:
        actual = (-bounded.plan.objective.restored_count, bounded.plan.objective.total_capped_duration_s,
                  bounded.plan.bus_hours)
        simple = (-bounded.busiest_affected_pattern.restored_count,
                  bounded.busiest_affected_pattern.total_capped_duration_s,
                  bounded.busiest_affected_pattern.bus_hours)
        assert actual <= simple


def test_no_intervention_wins_when_additions_have_no_request_benefit():
    data, _, scenarios, additions = recovery_fixture()
    result = plan_recovery(data, (request("E", "F"),), scenarios, additions, 8)
    assert result.plan.candidate_ids == ()
    assert result.plan.objective.total_capped_duration_s == 5400
    assert result.plan.bus_hours == 0


def test_corridor_blocks_whole_added_duty_but_unavailable_stop_can_be_passed():
    pair, sources = paired_pattern("p", "A", "B")
    data = snapshot(sources, pairs=(pair,))
    closure = CorridorClosure(scenario_id="block", start_s=601, end_s=700,
                              segments=(CorridorSegment(from_stop_id="A", to_stop_id="B"),))
    result = plan_recovery(data, (request("A", "B"),), (closure,), (candidate("bus"),), 2)
    assert result.infeasible_candidate_ids == ("bus",)
    assert result.plan.candidate_ids == ()
    closed_stop = StopUnavailable(scenario_id="stop", start_s=0, end_s=10000, stop_ids=("B",))
    passed = plan_recovery(data, (request("A", "B"),), (closed_stop,), (candidate("bus"),), 2)
    assert passed.infeasible_candidate_ids == ()
    assert passed.plan.candidate_ids == ()  # feasible bus, but it cannot restore this OD


def test_search_limits_invalid_budgets_duplicate_candidates_and_swap_bound():
    data, queries, scenarios, additions = recovery_fixture()
    with pytest.raises(ValueError, match="budget"):
        plan_recovery(data, queries, scenarios, additions, 6)
    with pytest.raises(ValueError, match="twelve"):
        plan_recovery(data, queries, scenarios, tuple(candidate(str(i)) for i in range(13)), 2)
    with pytest.raises(ValueError, match="unique"):
        plan_recovery(data, queries, scenarios, additions + (additions[0],), 2)
    with pytest.raises(ValueError, match="swap"):
        plan_recovery(data, queries, scenarios, additions, 2, max_swap_evaluations=4097)


def test_progress_is_metadata_only_and_monotonic_until_atomic_result():
    data, queries, scenarios, additions = recovery_fixture()
    progress = []
    result = plan_recovery(data, queries, scenarios, additions, 4, on_progress=progress.append)
    assert progress[0].stage == "preparing"
    assert progress[-1].stage == "completed"
    counts = [event.evaluated_plan_count for event in progress]
    assert counts == sorted(counts)
    assert counts[-1] == result.evaluated_plan_count
    assert all(not hasattr(event, "plan") and not hasattr(event, "result") for event in progress)
    assert result.evaluated_plan_count <= progress[-1].evaluation_upper_bound


def test_cancel_boundary_raises_and_never_returns_or_publishes_partial_result():
    data, queries, scenarios, additions = recovery_fixture()
    events = []
    def cancelled():
        return bool(events and events[-1].evaluated_plan_count >= 2)
    with pytest.raises(RecoveryCancelled, match="boundary"):
        plan_recovery(data, queries, scenarios, additions, 4,
                      on_progress=events.append, should_cancel=cancelled)
    assert events[-1].evaluated_plan_count == 2
    assert all(event.stage != "completed" for event in events)
    with pytest.raises(RecoveryCancelled):
        plan_recovery(data, queries, scenarios, additions, 4, should_cancel=lambda: True)

