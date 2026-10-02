"""Small synthetic unit fixtures; never substitutes for real morning evidence."""

from datetime import date, datetime, timedelta, timezone
from math import ceil

from resilience.contracts import (BusPattern, Connection, JourneyRequest, PatternPair,
                                 PatternStop, QualityMetadata, SnapshotMetadata,
                                 SourceRecord, Stop, TimetableSnapshot, WalkingLink)

DAY = date(2026, 10, 2)
MIDNIGHT = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def snapshot(connections=(), walks=(), pairs=(), stops=None, as_of_s=0, quality=None):
    names = set(stops or ())
    for connection in connections:
        names.update((connection.from_stop_id, connection.to_stop_id))
    for walk in walks:
        names.update((walk.from_stop_id, walk.to_stop_id))
    for pair in pairs:
        names.update(stop.stop_id for pattern in (pair.outbound, pair.inbound) for stop in pattern.stops)
    received = MIDNIGHT - timedelta(hours=1)
    metadata = SnapshotMetadata(snapshot_id="synthetic-test-only", service_date=DAY,
                                snapshot_at=MIDNIGHT + timedelta(seconds=as_of_s),
                                sources=(SourceRecord(record_id="fixture", source_kind="gtfs",
                                                      received_at=received, sha256="0" * 64,
                                                      source_ref="synthetic unit fixture"),),
                                quality=quality or QualityMetadata())
    return TimetableSnapshot(metadata=metadata,
                             stops=tuple(Stop(stop_id=name, latitude=-27.5, longitude=153.0)
                                         for name in sorted(names)),
                             connections=tuple(connections), walking_links=tuple(walks),
                             recovery_pairs=tuple(pairs))


def connection(trip, origin, destination, departure, arrival, sequence=0, **kwargs):
    return Connection(connection_id=f"{trip}:{sequence}", trip_instance_id=trip,
                      route_id=kwargs.pop("route_id", trip), mode=kwargs.pop("mode", "bus"),
                      sequence=sequence, from_stop_id=origin, to_stop_id=destination,
                      departure_s=departure, arrival_s=arrival, **kwargs)


def request(origin, destination, departure=0, request_id="q", **kwargs):
    return JourneyRequest(request_id=request_id, origin_stop_id=origin,
                          destination_stop_id=destination, departure_s=departure, **kwargs)


def walk(origin, destination, length=120, link_id=None):
    return WalkingLink(link_id=link_id or f"walk:{origin}:{destination}",
                       from_stop_id=origin, to_stop_id=destination,
                       length_m=length, duration_s=ceil(length / 1.2),
                       osm_node_ids=(1, 2), geometry=((153.0, -27.5), (153.001, -27.5)))


def paired_pattern(pair_id, origin, destination, outward_s=600, inward_s=600):
    out_trip, back_trip = pair_id + ":source:out", pair_id + ":source:back"
    route_id = pair_id + ":route"
    outbound = BusPattern(pattern_id=pair_id + ":out", route_id=route_id, direction_id="0",
                          source_trip_instance_ids=(out_trip,),
                          stops=(PatternStop(stop_id=origin, arrival_offset_s=0, departure_offset_s=0),
                                 PatternStop(stop_id=destination, arrival_offset_s=outward_s,
                                             departure_offset_s=outward_s)))
    inbound = BusPattern(pattern_id=pair_id + ":back", route_id=route_id, direction_id="1",
                         source_trip_instance_ids=(back_trip,),
                         stops=(PatternStop(stop_id=destination, arrival_offset_s=0, departure_offset_s=0),
                                PatternStop(stop_id=origin, arrival_offset_s=inward_s,
                                            departure_offset_s=inward_s)))
    pair = PatternPair(pair_id=pair_id, outbound=outbound, inbound=inbound)
    sources = (connection(out_trip, origin, destination, 0, outward_s, route_id=route_id),
               connection(back_trip, destination, origin, 2000, 2000 + inward_s, route_id=route_id))
    return pair, sources

