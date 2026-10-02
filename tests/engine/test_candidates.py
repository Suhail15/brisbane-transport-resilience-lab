from resilience.contracts import TripCancellation
from resilience.engine import generate_recovery_candidates
from tests.engine.fixtures import connection, paired_pattern, request, snapshot, walk


def test_candidate_selection_ignores_unrelated_high_frequency_pairs():
    relevant, p_sources = paired_pattern("relevant", "A", "B")
    unrelated, q_sources = paired_pattern("unrelated", "C", "D")
    more = tuple(connection(f"unrelated:{i}", "C", "D", i * 100, i * 100 + 300,
                            route_id=unrelated.outbound.route_id) for i in range(20))
    unrelated = unrelated.model_copy(update={"outbound": unrelated.outbound.model_copy(update={
        "source_trip_instance_ids": unrelated.outbound.source_trip_instance_ids + tuple(c.trip_instance_id for c in more)})})
    data = snapshot(p_sources + q_sources + more, pairs=(unrelated, relevant))
    cancellation = TripCancellation(scenario_id="cancel", start_s=0, end_s=1000,
                                    trip_instance_ids=("relevant:source:out",))
    candidates = generate_recovery_candidates(data, (request("A", "B"),), (cancellation,))
    assert [c.pair_id for c in candidates] == ["relevant"]
    assert candidates[0].activation_s == 600


def test_topology_variants_choose_source_timing_nearest_activation_and_are_deduplicated():
    early, early_sources = paired_pattern("early", "A", "B")
    nearby, near_sources = paired_pattern("near", "A", "B")
    near_sources = (near_sources[0].model_copy(update={"departure_s": 500, "arrival_s": 1100}), near_sources[1])
    data = snapshot(early_sources + near_sources, pairs=(early, nearby))
    cancellation = TripCancellation(scenario_id="cancel", start_s=0, end_s=2000,
                                    trip_instance_ids=("early:source:out", "near:source:out"))
    candidates = generate_recovery_candidates(data, (request("A", "B"),), (cancellation,))
    assert [c.pair_id for c in candidates] == ["near"]


def test_relevance_expands_only_actual_single_walk_paths_not_geographic_guess_or_chain():
    pair, sources = paired_pattern("bus", "B", "C")
    rail = connection("rail", "A", "D", 0, 1000, mode="rail")
    cancellation = TripCancellation(scenario_id="cancel", start_s=0, end_s=1100,
                                    trip_instance_ids=("rail",))
    actual = snapshot(sources + (rail,), (walk("A", "B"), walk("C", "D")), pairs=(pair,))
    assert len(generate_recovery_candidates(actual, (request("A", "D"),), (cancellation,))) == 1
    chained = snapshot(sources + (rail,), (walk("A", "X"), walk("X", "B"), walk("C", "D")), pairs=(pair,))
    assert generate_recovery_candidates(chained, (request("A", "D"),), (cancellation,)) == ()


def test_unchanged_journeys_do_not_generate_speculative_recovery_candidates():
    pair, sources = paired_pattern("p", "A", "B")
    data = snapshot(sources, pairs=(pair,))
    assert generate_recovery_candidates(data, (request("A", "B"),), ()) == ()

