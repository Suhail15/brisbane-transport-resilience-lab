"""Auditable connection scan with immutable paths and bounded boardings."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from hashlib import sha256
from typing import Sequence

from resilience.contracts import (Connection, JourneyRequest, RouteResult,
                                 TimetableSnapshot, TransitLeg, WalkingLeg,
                                 WalkingLink)

TRANSFER_SECONDS = 300
MAX_REQUESTS = 500


@dataclass(frozen=True)
class _Ride:
    connection: Connection


@dataclass(frozen=True)
class _Walk:
    link: WalkingLink
    departure_s: int


_Step = _Ride | _Walk


@dataclass(frozen=True)
class _Label:
    arrival_s: int
    boardings: int
    path: tuple[_Step, ...]

    @property
    def ready_s(self) -> int:
        return self.arrival_s + (TRANSFER_SECONDS if self.boardings else 0)


@dataclass(frozen=True)
class _Prepared:
    snapshot: TimetableSnapshot
    stops: frozenset[str]
    connections: tuple[Connection, ...]
    departures: tuple[int, ...]
    walks: dict[str, tuple[WalkingLink, ...]]


def _prepare(snapshot: TimetableSnapshot) -> _Prepared:
    connections = tuple(sorted(snapshot.connections,
                               key=lambda c: (c.departure_s, c.trip_instance_id,
                                              c.sequence, c.connection_id)))
    walks: dict[str, list[WalkingLink]] = {}
    for link in snapshot.walking_links:
        walks.setdefault(link.from_stop_id, []).append(link)
    return _Prepared(snapshot, frozenset(stop.stop_id for stop in snapshot.stops),
                     connections, tuple(c.departure_s for c in connections),
                     {stop: tuple(sorted(links, key=lambda w: w.link_id))
                      for stop, links in walks.items()})


def _path_key(path: tuple[_Step, ...]) -> tuple[str, ...]:
    return tuple("ride:" + step.connection.connection_id if isinstance(step, _Ride)
                 else "walk:" + step.link.link_id for step in path)


def _label_key(label: _Label) -> tuple[int, int, tuple[str, ...]]:
    return label.arrival_s, label.boardings, _path_key(label.path)


def _legs(path: tuple[_Step, ...]) -> tuple[TransitLeg | WalkingLeg, ...]:
    result: list[TransitLeg | WalkingLeg] = []
    for step in path:
        if isinstance(step, _Walk):
            link = step.link
            result.append(WalkingLeg(from_stop_id=link.from_stop_id,
                                     to_stop_id=link.to_stop_id,
                                     departure_s=step.departure_s,
                                     arrival_s=step.departure_s + link.duration_s,
                                     link_id=link.link_id, length_m=link.length_m,
                                     osm_node_ids=link.osm_node_ids,
                                     geometry=link.geometry))
            continue
        connection = step.connection
        if (result and isinstance(result[-1], TransitLeg)
                and result[-1].trip_instance_id == connection.trip_instance_id
                and result[-1].to_stop_id == connection.from_stop_id):
            previous = result[-1]
            result[-1] = previous.model_copy(update={
                "to_stop_id": connection.to_stop_id,
                "arrival_s": connection.arrival_s,
                "connection_ids": previous.connection_ids + (connection.connection_id,),
            })
        else:
            result.append(TransitLeg(mode=connection.mode,
                                     trip_instance_id=connection.trip_instance_id,
                                     route_id=connection.route_id,
                                     from_stop_id=connection.from_stop_id,
                                     to_stop_id=connection.to_stop_id,
                                     departure_s=connection.departure_s,
                                     arrival_s=connection.arrival_s,
                                     connection_ids=(connection.connection_id,),
                                     provenance=connection.provenance))
    return tuple(result)


def _route(prepared: _Prepared, request: JourneyRequest, max_boardings: int) -> RouteResult:
    if not 0 <= max_boardings <= 4:
        raise ValueError("max_boardings must be between zero and four")
    if request.origin_stop_id not in prepared.stops or request.destination_stop_id not in prepared.stops:
        raise ValueError("journey references an unknown stop")
    if request.departure_s < prepared.snapshot.metadata.snapshot_s:
        raise ValueError("journey departure precedes the snapshot")

    # An off-vehicle label has a separate state for walking eligibility. A label
    # reached by walking cannot concatenate another footpath; a later transit
    # arrival at the same stop must therefore remain available independently.
    labels: dict[tuple[str, int, bool], _Label] = {}
    onboard: dict[tuple[str, int], tuple[int, _Label]] = {}
    best: _Label | None = None

    def add_label(stop_id: str, label: _Label, walk_eligible: bool) -> None:
        nonlocal best
        key = stop_id, label.boardings, walk_eligible
        previous = labels.get(key)
        if previous is not None and _label_key(previous) <= _label_key(label):
            return
        labels[key] = label
        if stop_id == request.destination_stop_id:
            if best is None or _label_key(label) < _label_key(best):
                best = label
        if walk_eligible:
            for link in prepared.walks.get(stop_id, ()):
                walked = _Label(label.arrival_s + link.duration_s, label.boardings,
                                label.path + (_Walk(link, label.arrival_s),))
                add_label(link.to_stop_id, walked, False)

    add_label(request.origin_stop_id, _Label(request.departure_s, 0, ()), True)
    start = bisect_left(prepared.departures, request.departure_s)
    for connection in prepared.connections[start:]:
        if best is not None and connection.departure_s > best.arrival_s:
            break
        for boardings in range(1, max_boardings + 1):
            state = onboard.get((connection.trip_instance_id, boardings))
            continued: _Label | None = None
            if state is not None and state[0] == connection.sequence - 1:
                continued = state[1]
            boarded: _Label | None = None
            if connection.pickup_allowed:
                choices = [labels[(connection.from_stop_id, boardings - 1, eligible)]
                           for eligible in (False, True)
                           if (connection.from_stop_id, boardings - 1, eligible) in labels]
                choices = [label for label in choices if label.ready_s <= connection.departure_s]
                if choices:
                    chosen = min(choices, key=_label_key)
                    boarded = _Label(chosen.arrival_s, boardings, chosen.path)
            candidates = [candidate for candidate in (continued, boarded) if candidate is not None]
            if not candidates:
                continue
            predecessor = min(candidates, key=lambda label: _path_key(label.path))
            reached = _Label(connection.arrival_s, boardings,
                             predecessor.path + (_Ride(connection),))
            onboard[(connection.trip_instance_id, boardings)] = connection.sequence, reached
            if connection.drop_off_allowed:
                add_label(connection.to_stop_id, reached, True)

    quality = prepared.snapshot.metadata.quality
    if best is None:
        return RouteResult(request=request, reachable=False, quality=quality)
    return RouteResult(request=request, reachable=True, arrival_s=best.arrival_s,
                       duration_s=best.arrival_s - request.departure_s,
                       boardings=best.boardings, transfers=max(0, best.boardings - 1),
                       legs=_legs(best.path), quality=quality)


def route(snapshot: TimetableSnapshot, request: JourneyRequest,
          *, max_boardings: int = 4) -> RouteResult:
    return _route(_prepare(snapshot), request, max_boardings)


def route_many(snapshot: TimetableSnapshot,
               requests: Sequence[JourneyRequest]) -> tuple[RouteResult, ...]:
    if len(requests) > MAX_REQUESTS:
        raise ValueError("a fixed evaluation supports at most 500 requests")
    if len({request.request_id for request in requests}) != len(requests):
        raise ValueError("journey request ids must be unique")
    prepared = _prepare(snapshot)
    return tuple(_route(prepared, request, 4) for request in requests)


def generate_journey_requests(origin_stop_ids: Sequence[str], destination_stop_ids: Sequence[str],
                              start_s: int, *, limit: int = 500) -> tuple[JourneyRequest, ...]:
    if start_s < 0 or not 1 <= limit <= MAX_REQUESTS:
        raise ValueError("invalid request start or limit")
    requests = []
    for origin in sorted(set(origin_stop_ids)):
        for destination in sorted(set(destination_stop_ids)):
            if origin == destination:
                continue
            for step in range(5):
                departure = start_s + step * 900
                digest = sha256(f"{origin}\0{destination}\0{departure}".encode()).hexdigest()
                requests.append((digest, JourneyRequest(request_id="od:" + digest[:20],
                                                       origin_stop_id=origin,
                                                       destination_stop_id=destination,
                                                       departure_s=departure)))
    # Stable hash sampling avoids always truncating the last geographic OD block.
    selected = sorted(requests, key=lambda item: item[0])[:limit]
    return tuple(sorted((request for _, request in selected),
                        key=lambda r: (r.departure_s, r.origin_stop_id, r.destination_stop_id)))

