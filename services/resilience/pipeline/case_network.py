"""Source-fixed bus coverage for the separate station-census study.

Discovery uses only the two development sources and existing directed OSM links.
It reads no disruption/recovery result and never invents stops, trips or walks.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
from io import BytesIO
import json
from math import ceil
from pathlib import Path
from zoneinfo import ZoneInfo
import zipfile

import pandas as pd

from .files import atomic_write

VERSION = "station-access-network-v1"
DEVELOPMENT_DATES = ("2026-10-09", "2026-10-13")
PLATFORMS = ("600052", "600194", "600006", "600188", "600033", "600036", "600018", "600017")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_bytes())


def _table(source, name):
    try:
        return pd.read_csv(source.open(name), dtype=str, keep_default_na=False)
    except KeyError:
        return pd.DataFrame()


def active_services(calendar, exceptions, day):
    stamp, weekday = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    active = set()
    if not calendar.empty:
        active.update(calendar.loc[(calendar.start_date <= stamp) & (calendar.end_date >= stamp) &
                                   (calendar[weekday] == "1"), "service_id"])
    if not exceptions.empty:
        for item in exceptions[exceptions.date == stamp].itertuples():
            if item.exception_type == "1":
                active.add(item.service_id)
            elif item.exception_type == "2":
                active.discard(item.service_id)
    return active


def _walking_neighbors(snapshot):
    neighbors = {platform: set() for platform in PLATFORMS}
    witnesses = []
    for link in snapshot["walking_links"]:
        touched = set(PLATFORMS) & {link["from_stop_id"], link["to_stop_id"]}
        if not touched:
            continue
        if not (0 < link["length_m"] <= 600 and link["duration_s"] == ceil(link["length_m"] / 1.2)
                and len(link["osm_node_ids"]) >= 2 and len(link["geometry"]) >= 2
                and 0 <= link.get("from_snap_distance_m", 0) <= 30 and 0 <= link.get("to_snap_distance_m", 0) <= 30):
            raise ValueError("Development walking witness violates the existing source-path contract")
        for platform in touched:
            neighbors[platform].update({link["from_stop_id"], link["to_stop_id"]} - {platform})
        witnesses.append(link)
    return neighbors, witnesses


def _audit_feed(payload, day, neighbors, base_names):
    """Read the unfiltered feed; route selection never uses recovery outcomes."""
    with zipfile.ZipFile(BytesIO(payload)) as source:
        routes, trips = _table(source, "routes.txt"), _table(source, "trips.txt")
        services = active_services(_table(source, "calendar.txt"), _table(source, "calendar_dates.txt"), day)
        active = trips[trips.service_id.isin(services)].set_index("trip_id")
        buses = routes[routes.route_type == "3"].set_index("route_id")
        active_bus = active[active.route_id.isin(buses.index)]
        bus_trip_ids = set(active_bus.index)
        targets = set().union(*neighbors.values())
        pieces, stop_counts = [], defaultdict(int)
        for chunk in pd.read_csv(source.open("stop_times.txt"), dtype=str, keep_default_na=False,
                                 chunksize=500000, usecols=["trip_id", "stop_id", "departure_time"]):
            for trip_id, count in chunk.groupby("trip_id", sort=False).size().items():
                stop_counts[trip_id] += int(count)
            selected = chunk[chunk.trip_id.isin(bus_trip_ids) & chunk.stop_id.isin(targets)]
            if len(selected):
                pieces.append(selected)
        if not pieces:
            raise ValueError("No source-active bus service touches a development walking catchment")
        touched = pd.concat(pieces, ignore_index=True)
        touched["route_id"] = touched.trip_id.map(active_bus.route_id)
        route_ids = set(touched.route_id)
        names = {str(buses.loc[rid].route_short_name) for rid in route_ids}
        stop_ids = sorted(set(touched.stop_id))
        by_platform = {p: sorted(set(touched.loc[touched.stop_id.isin(stops), "stop_id"]))
                       for p, stops in neighbors.items()}
        by_platform_routes = {p: sorted(set(touched.loc[touched.stop_id.isin(stops), "route_id"]))
                              for p, stops in neighbors.items()}
        route_proof = []
        for rid, group in touched.groupby("route_id", sort=True):
            route_proof.append({"route_id": str(rid), "route_short_name": str(buses.loc[rid].route_short_name),
                "catchment_stop_ids": sorted(set(group.stop_id)), "active_touching_trip_count": int(group.trip_id.nunique()),
                "active_touching_trip_ids_sha256": digest(sorted(set(group.trip_id)))})
        expanded_names = set(base_names) | names
        def resources(selected_names):
            ids = set(routes.loc[routes.route_short_name.isin(selected_names) & routes.route_type.isin(["2", "3"]), "route_id"])
            selected = active[active.route_id.isin(ids)]
            return {"active_trip_count": len(selected),
                    "adjacent_connection_count": sum(max(0, stop_counts[tid] - 1) for tid in selected.index)}
        return {"bus_route_short_names": sorted(names), "bus_route_ids": sorted(route_ids),
                "catchment_bus_stop_ids": stop_ids, "bus_stop_ids_by_platform": by_platform,
                "bus_route_ids_by_platform": by_platform_routes, "route_witnesses": route_proof,
                "base_resources": resources(base_names), "own_date_expanded_resources": resources(expanded_names),
                "all_source_active_bus_trip_count": len(active_bus)}, routes, active, stop_counts


def derive_network(archive, development_snapshots, base_pilot_path=Path("configs/pilot.json")):
    if set(development_snapshots) != set(DEVELOPMENT_DATES):
        raise ValueError("Network discovery requires exactly the two fixed development dates")
    base_pilot_path = Path(base_pilot_path)
    base = load_json(base_pilot_path)
    base_names = set(base["route_short_names"])
    dates, bus_names, bus_stops, resource_sources = [], set(), set(), []
    for day in DEVELOPMENT_DATES:
        path = Path(development_snapshots[day])
        snapshot = load_json(path)
        metadata = snapshot["metadata"]
        cutoff = datetime.fromisoformat(metadata["snapshot_at"])
        if (cutoff.utcoffset() is None or cutoff.astimezone(ZoneInfo("Australia/Brisbane")).isoformat() != day + "T07:30:05+10:00"
                or metadata["service_date"] != day):
            raise ValueError("Development source cutoff differs from the frozen morning")
        neighbors, walking = _walking_neighbors(snapshot)
        gtfs = [s for s in metadata["sources"] if s["source_kind"] == "gtfs"]
        osm = [s for s in metadata["sources"] if s["source_kind"] == "osm"]
        if len(gtfs) != 1 or len(osm) != 1:
            raise ValueError("Exactly one existing GTFS and OSM source is required")
        refs = []
        for source in (gtfs[0], osm[0]):
            receipt = archive.get(source["record_id"])
            if (not receipt or receipt["status"] != "valid" or receipt["sha256"] != source["sha256"]
                    or datetime.fromisoformat(receipt["received_at"]) != datetime.fromisoformat(source["received_at"])
                    or datetime.fromisoformat(receipt["received_at"]) > cutoff):
                raise ValueError("Development source receipt is absent, mismatched or after the cutoff")
            payload = archive.read(receipt)
            if hashlib.sha256(payload).hexdigest() != source["sha256"]:
                raise ValueError("Development source object content differs")
            refs.append({"record_id": receipt["record_id"], "feed": receipt["feed"], "received_at": receipt["received_at"],
                         "sha256": receipt["sha256"], "source_url": receipt["source_url"]})
        payload = archive.read(archive.get(gtfs[0]["record_id"]))
        audit, routes, active, stop_counts = _audit_feed(payload, date.fromisoformat(day), neighbors, base_names)
        bus_names.update(audit["bus_route_short_names"])
        bus_stops.update(audit["catchment_bus_stop_ids"])
        relevant = [link for link in walking if link["from_stop_id"] in set(audit["catchment_bus_stop_ids"]) or link["to_stop_id"] in set(audit["catchment_bus_stop_ids"])]
        dates.append({"date": day, "snapshot_id": metadata["snapshot_id"], "snapshot_sha256": file_hash(path),
                      "snapshot_at": metadata["snapshot_at"], "sources": refs,
                      "walking_link_witnesses": [{"link_id": link["link_id"], "from_stop_id": link["from_stop_id"],
                          "to_stop_id": link["to_stop_id"], "length_m": link["length_m"], "duration_s": link["duration_s"],
                          "source_link_sha256": digest(link)} for link in sorted(relevant, key=lambda x: x["link_id"])], **audit})
        resource_sources.append((routes, active, stop_counts))
    expanded = base_names | bus_names
    for audit, (routes, active, stop_counts) in zip(dates, resource_sources):
        ids = set(routes.loc[routes.route_short_name.isin(expanded) & routes.route_type.isin(["2", "3"]), "route_id"])
        selected = active[active.route_id.isin(ids)]
        audit["frozen_union_resources"] = {"active_trip_count": len(selected),
            "adjacent_connection_count": sum(max(0, stop_counts[tid] - 1) for tid in selected.index)}
    return {"schema_version": 1, "network_version": VERSION, "timezone": "Australia/Brisbane",
        "development_dates": list(DEVELOPMENT_DATES), "decision_local_time": "07:30:05", "primary_platform_ids": list(PLATFORMS),
        "selection_rule": "Union every bus route short name with any source-active trip on either development service day serving a bus stop joined to any fixed platform by an existing directed OSM walking link, in either direction. Union the unchanged base pilot. No time-of-day, frequency, disruption or recovery threshold; preserve full active trips on every later date. Do not recursively discover routes from newly exposed stops.",
        "base_pilot_sha256": file_hash(base_pilot_path), "base_pilot_canonical_sha256": digest(base),
        "base_route_short_names": sorted(base_names), "catchment_bus_stop_ids": sorted(bus_stops),
        "development_bus_route_short_names": sorted(bus_names), "expanded_route_short_names": sorted(expanded),
        "added_route_short_names": sorted(bus_names - base_names), "development_source_audits": dates,
        "classification": "Source-only development route-coverage derivation; schedule service is not observed operation",
        "limitations": ["Existing OSM links have unresolved platform/entrance association and incomplete geographic coverage; no new straight-line connection is inferred.",
                        "These are fixed known walking catchments, not a claim that all possible pedestrian-access alternatives are represented.",
                        "Later normalized stops may expose more real walking links; they do not change the frozen line-selection rule.",
                        "No passenger demand, vehicle capacity or available replacement fleet is established."]}


def write_network_config(archive, development_snapshots, destination=Path("configs/station-access-network.v1.json"),
                         base_pilot_path=Path("configs/pilot.json")):
    config = derive_network(archive, development_snapshots, base_pilot_path)
    atomic_write(Path(destination), encoded(config), immutable=True)
    return {"path": str(destination), "sha256": file_hash(destination),
            "catchment_bus_stop_count": len(config["catchment_bus_stop_ids"]),
            "development_bus_route_count": len(config["development_bus_route_short_names"]),
            "expanded_route_name_count": len(config["expanded_route_short_names"])}


def materialize_pilot(network_config_path, output_path, base_pilot_path=Path("configs/pilot.json")):
    network, base = load_json(network_config_path), load_json(base_pilot_path)
    if network["schema_version"] != 1 or network["network_version"] != VERSION:
        raise ValueError("Unapproved source-network specification")
    if file_hash(base_pilot_path) != network["base_pilot_sha256"] or digest(base) != network["base_pilot_canonical_sha256"]:
        raise ValueError("Base pilot differs from frozen development derivation")
    if (sorted(set(base["route_short_names"]) | set(network["development_bus_route_short_names"])) != network["expanded_route_short_names"]
            or sorted(set(network["catchment_bus_stop_ids"])) != network["catchment_bus_stop_ids"]):
        raise ValueError("Frozen route/stop union is inconsistent")
    pilot = {**base, "version": 2, "network_version": VERSION, "network_config_sha256": file_hash(network_config_path),
        "route_short_names": network["expanded_route_short_names"],
        "bus_seed_stop_ids": sorted(set(base["bus_seed_stop_ids"]) | set(network["catchment_bus_stop_ids"])),
        "selection_rule": network["selection_rule"]}
    atomic_write(Path(output_path), encoded(pilot), immutable=True)
    return {"pilot_path": str(output_path), "pilot_sha256": file_hash(output_path),
            "network_config_sha256": file_hash(network_config_path), "network_version": VERSION}


def snapshot_coverage(archive, snapshot, pilot_path, *, cancelled_trip_ids=()):
    """Compare complete dated GTFS topology independently of filtered caches.

    The caller supplies bare source trip IDs from recorded builder cancellation
    diagnostics. Their freshness/entity interpretation is a separate RT check;
    this proof checks the declared exclusions and every remaining full topology.
    Predicted times/access flags are deliberately not compared to schedule times.
    """
    if hasattr(snapshot, "model_dump"):
        snapshot = snapshot.model_dump(mode="json")
    pilot = load_json(pilot_path)
    metadata = snapshot["metadata"]
    sources = [s for s in metadata["sources"] if s["source_kind"] == "gtfs"]
    if len(sources) != 1:
        raise ValueError("Coverage proof requires one GTFS source")
    source = sources[0]
    receipt = archive.get(source["record_id"])
    if (not receipt or receipt["status"] != "valid" or receipt["sha256"] != source["sha256"]
            or datetime.fromisoformat(receipt["received_at"]) > datetime.fromisoformat(metadata["snapshot_at"])):
        raise ValueError("Coverage source is absent, mismatched or after the cutoff")
    payload = archive.read(receipt)
    if hashlib.sha256(payload).hexdigest() != source["sha256"]:
        raise ValueError("Coverage source object content differs")
    day = date.fromisoformat(metadata["service_date"])
    with zipfile.ZipFile(BytesIO(payload)) as feed:
        routes, trips = _table(feed, "routes.txt"), _table(feed, "trips.txt")
        selected = routes[routes.route_short_name.isin(pilot["route_short_names"]) & routes.route_type.isin(["2", "3"])]
        modes = dict(zip(selected.route_id, selected.route_type.map({"2": "rail", "3": "bus"})))
        services = active_services(_table(feed, "calendar.txt"), _table(feed, "calendar_dates.txt"), day)
        trips = trips[trips.service_id.isin(services) & trips.route_id.isin(selected.route_id)].set_index("trip_id")
        pieces = []
        for chunk in pd.read_csv(feed.open("stop_times.txt"), dtype=str, keep_default_na=False, chunksize=500000,
                                 usecols=["trip_id", "stop_id", "stop_sequence"]):
            keep = chunk[chunk.trip_id.isin(trips.index)]
            if len(keep):
                pieces.append(keep)
        times = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=["trip_id", "stop_id", "stop_sequence"])
    times["stop_sequence"] = times.stop_sequence.astype(int)
    times = times.sort_values(["trip_id", "stop_sequence"])
    exclusions = sorted(set(cancelled_trip_ids))
    if not set(exclusions) <= set(trips.index):
        raise ValueError("Declared cancellation is not a selected source-active trip")
    expected, complete_trips = [], set()
    for trip_id, group in times.groupby("trip_id", sort=True):
        if len(group) < 2:
            continue
        complete_trips.add(trip_id)
        if trip_id in exclusions:
            continue
        stop_ids = list(group.stop_id)
        route_id = str(trips.loc[trip_id].route_id)
        tid = f"{day.isoformat()}:{trip_id}"
        for sequence, (a, b) in enumerate(zip(stop_ids, stop_ids[1:])):
            expected.append({"connection_id": f"{tid}:{sequence}", "trip_instance_id": tid, "route_id": route_id,
                             "mode": modes[route_id], "sequence": sequence, "from_stop_id": a, "to_stop_id": b})
    keys = ("connection_id", "trip_instance_id", "route_id", "mode", "sequence", "from_stop_id", "to_stop_id")
    actual = [{k: c[k] for k in keys} for c in snapshot["connections"]]
    expected.sort(key=lambda c: c["connection_id"])
    actual.sort(key=lambda c: c["connection_id"])
    if encoded(expected) != encoded(actual):
        expected_ids, actual_ids = {c["connection_id"] for c in expected}, {c["connection_id"] for c in actual}
        raise ValueError(f"Normalized full-trip topology differs: {len(expected_ids - actual_ids)} missing, "
                         f"{len(actual_ids - expected_ids)} extra connection IDs; topology/route/sequence must match")
    return {"schema_version": 1, "method": "raw-gtfs-complete-selected-trip-topology-v1",
        "service_date": day.isoformat(), "snapshot_id": metadata["snapshot_id"], "snapshot_canonical_sha256": digest(snapshot),
        "pilot_sha256": file_hash(pilot_path), "gtfs_record_id": source["record_id"], "gtfs_sha256": source["sha256"],
        "source_active_selected_trip_count": len(trips), "source_complete_trip_count": len(complete_trips),
        "declared_cancelled_trip_ids": exclusions, "expected_full_trip_count": len(complete_trips - set(exclusions)),
        "actual_full_trip_count": len({c["trip_instance_id"] for c in actual}),
        "expected_connection_count": len(expected), "actual_connection_count": len(actual),
        "expected_route_count": len({c["route_id"] for c in expected}), "actual_route_count": len({c["route_id"] for c in actual}),
        "expected_topology_sha256": digest(expected), "actual_topology_sha256": digest(actual),
        "passed": True, "limitations": ["Cancellation exclusions are supplied from recorded normalization diagnostics; independent real-time entity validation is separate.",
            "This verifies source membership and complete stop/route/mode topology, not predicted-time accuracy or observed vehicle operation."]}
