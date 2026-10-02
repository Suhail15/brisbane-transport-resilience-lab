"""Independent time-dependent graph oracle, deliberately not a connection scan.

It enumerates every legal board/alight pair on a full trip, turns those into ride
edges, and performs a heap search. It imports contracts only, never engine code.
"""

from collections import defaultdict
from heapq import heappop, heappush


def earliest_arrival(snapshot, request, maximum_boardings=4):
    trips = defaultdict(list)
    for movement in snapshot.connections:
        trips[movement.trip_instance_id].append(movement)
    rides = defaultdict(list)
    for movements in trips.values():
        ordered = sorted(movements, key=lambda movement: movement.sequence)
        for index, departure in enumerate(ordered):
            if not departure.pickup_allowed:
                continue
            for arrival in ordered[index:]:
                if arrival.drop_off_allowed:
                    rides[departure.from_stop_id].append(
                        (departure.departure_s, arrival.arrival_s, arrival.to_stop_id))
    walks = defaultdict(list)
    for link in snapshot.walking_links:
        walks[link.from_stop_id].append((link.to_stop_id, link.duration_s))
    initial = (request.origin_stop_id, 0, True)
    distances = {initial: request.departure_s}
    queue = [(request.departure_s, 0, request.origin_stop_id, True)]
    answers = []
    while queue:
        arrival, count, stop, may_walk = heappop(queue)
        if distances[(stop, count, may_walk)] != arrival:
            continue
        if stop == request.destination_stop_id:
            answers.append((arrival, count))
        next_states = []
        if may_walk:
            next_states.extend((arrival + duration, count, target, False)
                               for target, duration in walks[stop])
        if count < maximum_boardings:
            readiness = arrival + (300 if count else 0)
            next_states.extend((end, count + 1, target, True)
                               for start, end, target in rides[stop] if start >= readiness)
        for end, used, target, walking_allowed in next_states:
            state = target, used, walking_allowed
            if end < distances.get(state, float("inf")):
                distances[state] = end
                heappush(queue, (end, used, target, walking_allowed))
    return min(answers) if answers else (None, 0)

