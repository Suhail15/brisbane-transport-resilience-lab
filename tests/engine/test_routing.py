import random

import pytest

from resilience.contracts import QualityMetadata
from resilience.engine import generate_journey_requests, route, route_many
from tests.engine.fixtures import connection, request, snapshot, walk
from tests.engine.oracle import earliest_arrival


def test_first_boarding_has_no_transfer_allowance_and_full_vehicle_continuation():
    # Six movements are one boarding, even with only 5s intermediate dwell.
    movements = [connection("through", f"s{i}", f"s{i + 1}", 100 + i * 105,
                            200 + i * 105, i) for i in range(6)]
    result = route(snapshot(movements), request("s0", "s6", 100))
    assert (result.arrival_s, result.duration_s, result.boardings, result.transfers) == (725, 625, 1, 0)
    assert len(result.legs) == 1
    assert result.legs[0].connection_ids == tuple(f"through:{i}" for i in range(6))


def test_transfer_exact_300_seconds_is_allowed_but_299_is_not():
    first = connection("first", "A", "B", 100, 200)
    exact = connection("exact", "B", "C", 500, 600)
    too_early = connection("early", "B", "C", 499, 599)
    assert route(snapshot((first, exact)), request("A", "C", 100)).arrival_s == 600
    assert not route(snapshot((first, too_early)), request("A", "C", 100)).reachable


def test_transfer_walk_is_added_once_and_egress_is_actual_walk():
    paths = (walk("B", "X", 120), walk("C", "D", 120))
    first = connection("first", "A", "B", 100, 200)
    second = connection("second", "X", "C", 600, 700)
    result = route(snapshot((first, second), paths), request("A", "D", 100))
    assert (result.arrival_s, result.boardings, result.transfers) == (800, 2, 1)
    assert [leg.kind for leg in result.legs] == ["transit", "walk", "transit", "walk"]
    assert result.legs[1].departure_s == 200
    assert result.legs[1].arrival_s == 300
    assert result.legs[1].geometry == paths[0].geometry
    earlier = second.model_copy(update={"departure_s": 599, "arrival_s": 699})
    assert not route(snapshot((first, earlier), paths), request("A", "D", 100)).reachable


def test_no_walking_chain_can_evade_the_600_metre_limit():
    data = snapshot(walks=(walk("A", "B", 360), walk("B", "C", 360)))
    assert not route(data, request("A", "C")).reachable
    direct = snapshot(walks=data.walking_links + (walk("A", "C", 600),))
    assert route(direct, request("A", "C")).duration_s == 500


def test_later_arrival_with_fewer_boardings_survives_pareto_pruning():
    movements = (connection("via1", "A", "X", 0, 100),
                 connection("via2", "X", "B", 400, 500),
                 connection("direct", "A", "B", 0, 600),
                 connection("tail1", "B", "C", 900, 1000),
                 connection("tail2", "C", "D", 1300, 1400),
                 connection("tail3", "D", "E", 1700, 1800))
    result = route(snapshot(movements), request("A", "E"))
    assert (result.arrival_s, result.boardings) == (1800, 4)
    assert result.legs[0].trip_instance_id == "direct"
    assert not route(snapshot(movements), request("A", "E"), max_boardings=3).reachable


def test_equal_arrival_prefers_fewer_changes_and_is_input_order_independent():
    movements = (connection("via1", "A", "X", 0, 100),
                 connection("via2", "X", "B", 400, 500),
                 connection("direct", "A", "B", 20, 500))
    expected = route(snapshot(movements), request("A", "B"))
    assert (expected.arrival_s, expected.boardings) == (500, 1)
    assert route(snapshot(tuple(reversed(movements))), request("A", "B")) == expected


def test_immutable_predecessors_survive_a_better_later_stop_label():
    # The through vehicle's immutable path must not point to a replacement A->B
    # label created after it boards, nor form a cycle at B.
    movements = (connection("through", "A", "B", 0, 700, 0),
                 connection("through", "B", "C", 710, 800, 1),
                 connection("better", "A", "B", 100, 500))
    result = route(snapshot(movements), request("A", "C"))
    assert result.arrival_s == 800
    assert result.boardings == 1
    assert result.legs[0].connection_ids == ("through:0", "through:1")


def test_walked_and_transit_arrival_states_remain_separate():
    # Earlier arrival at B by walking cannot walk again; later arrival by bus can.
    data = snapshot((connection("bus", "A", "B", 0, 200),),
                    (walk("A", "B", 120), walk("B", "C", 120)))
    result = route(data, request("A", "C"))
    assert (result.arrival_s, result.boardings) == (300, 1)


def test_pickup_dropoff_flags_do_not_block_same_vehicle_continuation():
    movements = (connection("pass", "A", "B", 100, 200, 0, drop_off_allowed=False),
                 connection("pass", "B", "C", 205, 300, 1, pickup_allowed=False))
    data = snapshot(movements)
    assert route(data, request("A", "C", 100)).arrival_s == 300
    assert not route(data, request("A", "B", 100)).reachable
    assert not route(data, request("B", "C", 100)).reachable


def test_service_day_times_above_24_hours_and_quality_are_preserved():
    quality = QualityMetadata(realtime_status="stale", warnings=("fixture stale feed",))
    data = snapshot((connection("late", "A", "B", 90000, 90600),), as_of_s=89000, quality=quality)
    result = route(data, request("A", "B", 89900))
    assert result.duration_s == 700
    assert result.quality == quality
    with pytest.raises(ValueError, match="precedes"):
        route(data, request("A", "B", 88000))


def test_request_factory_is_fixed_equal_weight_and_capped():
    all_requests = generate_journey_requests(["B", "A"], ["C"], 100)
    assert len(all_requests) == 10
    assert {r.departure_s for r in all_requests} == {100, 1000, 1900, 2800, 3700}
    assert all(r.od_weight is None for r in all_requests)
    many = generate_journey_requests([f"o{i}" for i in range(20)], [f"d{i}" for i in range(20)], 0)
    assert len(many) == 500
    assert many == generate_journey_requests(list(reversed([f"o{i}" for i in range(20)])),
                                            list(reversed([f"d{i}" for i in range(20)])), 0)
    with pytest.raises(ValueError, match="500"):
        route_many(snapshot(stops=("A", "B")), [request("A", "B", request_id=str(i)) for i in range(501)])


def test_csa_matches_independent_ride_edge_heap_oracle_on_seeded_networks():
    rng = random.Random(8713)
    stops = tuple("ABCDEF")
    for network in range(24):
        movements = []
        for trip_index in range(9):
            chosen = rng.sample(stops, rng.randint(2, 5))
            departure = rng.randint(0, 1000)
            mode = rng.choice(("bus", "rail"))
            for index, (origin, destination) in enumerate(zip(chosen, chosen[1:])):
                arrival = departure + rng.randint(0, 400)
                movements.append(connection(f"n{network}t{trip_index}", origin, destination,
                                            departure, arrival, index, mode=mode,
                                            pickup_allowed=rng.random() > 0.15,
                                            drop_off_allowed=rng.random() > 0.15))
                departure = arrival + rng.randint(0, 100)
        paths = [walk(origin, destination, rng.randint(1, 600))
                 for origin in stops for destination in stops if origin != destination and rng.random() < 0.15]
        data = snapshot(movements, paths, stops=stops)
        rng.shuffle(movements)
        for query_index in range(12):
            origin, destination = rng.sample(stops, 2)
            query = request(origin, destination, rng.randint(0, 600), str(query_index))
            expected_arrival, expected_boardings = earliest_arrival(data, query)
            actual = route(data, query)
            assert (actual.arrival_s, actual.boardings) == (expected_arrival, expected_boardings)

