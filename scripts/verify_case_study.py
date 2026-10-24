"""Independently reconcile saved corridor-study inputs, paths, duties and arithmetic.

Uses plain JSON and integer arithmetic. Does not import the study producer, metric
helpers, routing or optimization code, and never executes a policy calculation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import gzip
import hashlib
from io import BytesIO, TextIOWrapper
import json
from pathlib import Path
import sqlite3
import sys
import zipfile
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
VERSION = "corridor-impact-staggered-v1"
SCORING_VERSION = "whole-source-trips-capped-horizon-v1"
PLATFORMS = [
    {"station": "Fairfield", "stop_ids": ["600052", "600194"]},
    {"station": "South Bank", "stop_ids": ["600006", "600188"]},
    {"station": "Roma Street", "stop_ids": ["600033", "600036"]},
    {"station": "Central", "stop_ids": ["600018", "600017"]},
]
ROLES = {"development": ["2026-10-09", "2026-10-13"],
         "replication": ["2026-10-19", "2026-10-20", "2026-10-21"],
         "confirmation": ["2026-10-22"]}
OFFSETS, PHASES = (0, 900, 1800, 2700, 3600), (600, 1500, 2400, 3300)
MATRIX = ((0, 0), (2, 0), (4, 0), (8, 0), (2, 300), (2, 600))
POLICIES = ("no_action", "simple_frequency", "best_evaluated")
DEFAULT_PRESERVATION = "data/runtime/impact-study-2026-10-23/original-file-hashes.json"


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    def reject_constant(value):
        raise VerificationError(f"nonfinite JSON number: {value}")
    return json.loads(Path(path).read_bytes(), object_pairs_hook=_unique_object,
                      parse_constant=reject_constant)


def same(actual, expected, label):
    # JSON equality alone accepts True == 1 and 1.0 == 1. Types matter for counts.
    require(encoded(actual) == encoded(expected), f"{label} differs")


def checked_json(path):
    path = Path(path)
    doc = read_json(path)
    same(read_json(path.with_suffix(".sha256.json")), {"sha256": file_hash(path)},
         f"{path.name} sidecar hash")
    require(file_hash(path) == digest(doc), f"{path.name} is not canonical frozen JSON")
    return doc


def safe_path(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "unsafe manifest path")
    path = (Path(root) / relative).resolve()
    require(path.is_relative_to(Path(root).resolve()), "manifest path escapes root")
    return path


def preserve_originals(manifest_path, repo, expected_sha256=None):
    if expected_sha256:
        require(file_hash(manifest_path) == expected_sha256, "reviewed preservation manifest hash differs")
    baseline = read_json(manifest_path)
    files = baseline["files"]
    require(isinstance(files, dict) and len(files) == 530, "original preservation denominator must be 530 files")
    for relative, expected in files.items():
        require(file_hash(safe_path(repo, relative)) == expected,
                f"original frozen file changed: {relative}")
    return {"file_count": len(files), "manifest_sha256": file_hash(manifest_path), "passed": True}


def code_hash(repo, network=False):
    repo = Path(repo)
    paths = [repo / "services/resilience/contracts.py", repo / "scripts/run_case_study.py",
             *sorted((repo / "services/resilience/engine").glob("*.py")),
             *[repo / "services/resilience/pipeline" / name for name in
               ("case_study.py", "analysis.py", "sensitivity.py", "files.py", "integrity.py")]]
    if network:
        paths += [repo / "services/resilience/pipeline" / name for name in
                  ("case_network.py", "snapshots.py", "schedule.py", "walking.py", "archive.py")]
        paths += [repo / "configs/station-access-network.v1.json", repo / "configs/pilot.json"]
    require(len(paths) >= 7, "study code files missing")
    return hashlib.sha256(b"".join(p.relative_to(repo).as_posix().encode() + b"\0" +
                                  p.read_bytes() + b"\0" for p in paths)).hexdigest()


def check_protocol(study, config_path, repo, expected_sha256=None):
    protocol = read_json(Path(study) / "protocol.json")
    if expected_sha256:
        require(file_hash(Path(study) / "protocol.json") == expected_sha256,
                "reviewed protocol hash differs")
    config = read_json(config_path)
    require(config["study_id"] in ("corridor-impact-v1", "corridor-impact-v2"), "unregistered study ID")
    fixed = {"schema_version": 1,
             "timezone": "Australia/Brisbane", "decision_local_time": "07:30:05",
             "primary_station_platforms": PLATFORMS, "offset_seconds": list(OFFSETS),
             "primary_request_count": 240, "control_request_count": 100,
             "section_station_names": ["Fairfield", "Dutton Park", "South Bank", "South Brisbane", "Roma Street", "Central"],
             "closure_duration_seconds": 7200, "candidate_pair_limit": 3,
             "activation_offsets_seconds": list(PHASES), "budgets_bus_hours": [0, 2, 4, 8],
             "sensitivity_budget_bus_hours": 2, "sensitivity_seconds": [0, 300, 600],
             "max_swap_evaluations": 128, "reachability_seconds": 3600,
             "duration_cap_seconds": 5400, "walking_speed_mps": 1.2,
             "maximum_walking_link_metres": 600, "transfer_slack_seconds": 300,
             "maximum_transfers": 3}
    for key, value in {**fixed, **{role + "_dates": days for role, days in ROLES.items()}}.items():
        same(config[key], value, f"registered config/{key}")
    same(protocol["config"], config, "frozen configuration")
    same(protocol["config_sha256"], file_hash(config_path), "config exact-byte hash")
    same(protocol["config_canonical_sha256"], digest(config), "config canonical hash")
    same(protocol["selection_version"], VERSION, "selection version")
    same(protocol["candidate_selection_version"], VERSION, "candidate selection version")
    same(protocol["scoring_version"], SCORING_VERSION, "separate scoring optimization version")
    same(protocol["code_sha256"], code_hash(repo, config["study_id"] == "corridor-impact-v2"), "study code hash")
    if config["study_id"] == "corridor-impact-v2":
        check_network_binding(study, protocol, repo)
    controls_path = safe_path(repo, config["control_journey_set"])
    same(protocol["control_config_sha256"], file_hash(controls_path), "original control config hash")
    controls = read_json(controls_path)
    require(controls["version"] == "pilot-od20-v1" and len(controls["pairs"]) == 20
            and controls["request_count"] == 100 and controls["primary_weight"] == 1,
            "original control configuration denominator/weights differ")
    same(controls["offset_seconds"], list(OFFSETS), "control offsets")
    return protocol, controls


def check_network_binding(study, protocol, repo):
    network = protocol["network"]
    same(protocol["config"]["network_config"], "configs/station-access-network.v1.json", "registered network specification path")
    same(network["pilot_path"], "network/pilot.json", "portable pilot artifact path")
    same(network["source_audit_path"], "network/source-audit.json", "portable source audit path")
    spec_path = safe_path(repo, protocol["config"]["network_config"])
    spec = read_json(spec_path)
    base_path = safe_path(repo, "configs/pilot.json")
    base = read_json(base_path)
    same(spec["schema_version"], 1, "network schema")
    same(spec["network_version"], "station-access-network-v1", "frozen network version")
    same(spec["development_dates"], ROLES["development"], "source discovery development dates")
    same(spec["primary_platform_ids"], [sid for station in PLATFORMS for sid in station["stop_ids"]], "source discovery platform identities")
    same(spec["base_pilot_sha256"], file_hash(base_path), "source discovery base bytes")
    same(spec["base_pilot_canonical_sha256"], digest(base), "source discovery base content")
    require(len(spec["catchment_bus_stop_ids"]) == 29 and len(spec["development_bus_route_short_names"]) == 103
            and len(spec["added_route_short_names"]) == 84 and len(spec["expanded_route_short_names"]) == 156,
            "frozen network stop/route resource bounds differ")
    same(spec["base_route_short_names"], sorted(set(base["route_short_names"])), "original route names")
    same(spec["expanded_route_short_names"], sorted(set(base["route_short_names"]) | set(spec["development_bus_route_short_names"])), "frozen source route union")
    same(spec["added_route_short_names"], sorted(set(spec["development_bus_route_short_names"]) - set(base["route_short_names"])), "frozen route additions")
    same(spec["catchment_bus_stop_ids"], sorted(set(spec["catchment_bus_stop_ids"])), "frozen walking catchment stop identities")
    same(network, {"network_version": spec["network_version"], "pilot_path": "network/pilot.json",
        "pilot_sha256": file_hash(safe_path(study, "network/pilot.json")),
        "network_config_path": protocol["config"]["network_config"], "network_config_sha256": file_hash(spec_path),
        "source_audit_path": "network/source-audit.json", "source_audit_sha256": file_hash(spec_path),
        "base_pilot_sha256": file_hash(base_path)}, "complete network provenance binding")
    require((safe_path(study, network["source_audit_path"])).read_bytes() == spec_path.read_bytes(), "copied network source audit bytes differ")
    pilot = {**base, "version": 2, "network_version": spec["network_version"], "network_config_sha256": file_hash(spec_path),
        "route_short_names": spec["expanded_route_short_names"],
        "bus_seed_stop_ids": sorted(set(base["bus_seed_stop_ids"]) | set(spec["catchment_bus_stop_ids"])),
        "selection_rule": spec["selection_rule"]}
    same(read_json(safe_path(study, network["pilot_path"])), pilot, "independent expanded pilot reconstruction")


def second(snapshot):
    stamp = datetime.fromisoformat(snapshot["metadata"]["snapshot_at"])
    require(stamp.utcoffset() is not None, "snapshot cutoff must be timezone-aware")
    local = stamp.astimezone(ZoneInfo("Australia/Brisbane"))
    return local.hour * 3600 + local.minute * 60 + local.second


def expected_requests(snapshot, controls):
    start = second(snapshot)
    primary = [{"request_id": f"{VERSION}:{origin}:{destination}:{offset}",
                "origin_stop_id": origin, "destination_stop_id": destination,
                "departure_s": start + offset, "od_weight": None}
               for a in PLATFORMS for b in PLATFORMS if a["station"] != b["station"]
               for origin in a["stop_ids"] for destination in b["stop_ids"] for offset in OFFSETS]
    original = [{"request_id": f"{controls['version']}:{pair['pair_id']}:{offset}",
                 "origin_stop_id": pair["origin_stop_id"], "destination_stop_id": pair["destination_stop_id"],
                 "departure_s": start + offset, "od_weight": None}
                for pair in controls["pairs"] for offset in OFFSETS]
    require(len(primary) == len({r["request_id"] for r in primary}) == 240
            and len(original) == len({r["request_id"] for r in original}) == 100,
            "query census does not retain separate 240/100 identities")
    return primary, original


def trip_groups(snapshot):
    trips = defaultdict(list)
    for connection in snapshot["connections"]:
        trips[connection["trip_instance_id"]].append(connection)
    return {tid: sorted(values, key=lambda c: c["sequence"]) for tid, values in trips.items()}


def closure(snapshot, config):
    names = {s["stop_id"]: s["name"].split(" station, platform ")[0]
             for s in snapshot["stops"] if " station, platform " in s["name"]}
    required = set(config["section_station_names"])
    require(required <= set(names.values()), "required source section station absent")
    edges = sorted({(c["from_stop_id"], c["to_stop_id"]) for c in snapshot["connections"]
                    if c["mode"] == "rail" and names.get(c["from_stop_id"]) in required
                    and names.get(c["to_stop_id"]) in required
                    and names[c["from_stop_id"]] != names[c["to_stop_id"]]})
    require(edges, "source rail section is empty")
    return {"kind": "corridor_closure", "scenario_id": VERSION + ":rail-section",
            "start_s": second(snapshot), "end_s": second(snapshot) + 7200,
            "segments": [{"from_stop_id": a, "to_stop_id": b, "bidirectional": False} for a, b in edges]}


def restricted(connections, scenario):
    edges = {(s["from_stop_id"], s["to_stop_id"]) for s in scenario["segments"]}
    edges |= {(b, a) for a, b in list(edges) if any(s["from_stop_id"] == a and
              s["to_stop_id"] == b and s["bidirectional"] for s in scenario["segments"])}
    cancelled = set()
    for c in connections:
        overlaps = (scenario["start_s"] <= c["departure_s"] < scenario["end_s"]
                    if c["arrival_s"] == c["departure_s"] else
                    c["departure_s"] < scenario["end_s"] and c["arrival_s"] > scenario["start_s"])
        if overlaps and (c["from_stop_id"], c["to_stop_id"]) in edges:
            cancelled.add(c["trip_instance_id"])
    return [c for c in connections if c["trip_instance_id"] not in cancelled], cancelled


def check_sources(manifest, snapshot, data_dir):
    cutoff = datetime.fromisoformat(snapshot["metadata"]["snapshot_at"])
    sources = manifest["sources"]
    require(len({s["record_id"] for s in sources}) == len(sources), "duplicate source references")
    same([{k: v for k, v in s.items() if k != "receipt"} for s in sources],
         snapshot["metadata"]["sources"], "snapshot source references")
    raw_sources = {}
    with sqlite3.connect(f"file:{(Path(data_dir) / 'runtime/archive.sqlite').resolve()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for source in sources:
            row = db.execute("SELECT * FROM receipts WHERE record_id=?", (source["record_id"],)).fetchone()
            require(row is not None, "source receipt not found in archive")
            receipt = dict(row)
            same(source["receipt"], receipt, "source receipt identity")
            require(receipt["status"] == "valid" and source["sha256"] == receipt["sha256"]
                    and datetime.fromisoformat(source["received_at"]) == datetime.fromisoformat(receipt["received_at"])
                    and datetime.fromisoformat(receipt["received_at"]) <= cutoff,
                    "source hash/time/status differs or exceeds cutoff")
            same(source["source_ref"], receipt["source_url"], "source URL")
            latest = db.execute("SELECT record_id FROM receipts WHERE feed=? AND status='valid' AND received_at<=? "
                                "ORDER BY received_at DESC LIMIT 1", (receipt["feed"], cutoff.isoformat())).fetchone()
            # RT joins are also bounded by their GTFS digest; do not impose an unjoined latest row.
            if receipt["feed"] in ("GTFS", "OSM"):
                require(latest and latest["record_id"] == receipt["record_id"], "source was not latest eligible static receipt")
            payload = gzip.decompress(safe_path(data_dir, f"raw/objects/{receipt['sha256']}.gz").read_bytes())
            require(hashlib.sha256(payload).hexdigest() == receipt["sha256"], "archived source object hash differs")
            raw_sources[receipt["feed"]] = (payload, receipt)
    require(any(s["source_kind"] == "gtfs" for s in sources), "GTFS source reference absent")
    return raw_sources


def independent_source_coverage(snapshot, pilot, raw_sources):
    """Raw CSV/protobuf reconciliation; imports no producer/adapter helper."""
    payload, receipt = raw_sources["GTFS"]
    day = snapshot["metadata"]["service_date"]
    stamp = day.replace("-", "")
    weekday = datetime.fromisoformat(day).strftime("%A").lower()
    with zipfile.ZipFile(BytesIO(payload)) as feed:
        def records(name):
            if name not in feed.namelist():
                return iter(())
            return csv.DictReader(TextIOWrapper(feed.open(name), encoding="utf-8-sig", newline=""))
        services = {r["service_id"] for r in records("calendar.txt")
                    if r["start_date"] <= stamp <= r["end_date"] and r[weekday] == "1"}
        for r in records("calendar_dates.txt"):
            if r["date"] == stamp:
                if r["exception_type"] == "1":
                    services.add(r["service_id"])
                elif r["exception_type"] == "2":
                    services.discard(r["service_id"])
        modes = {r["route_id"]: {"2": "rail", "3": "bus"}[r["route_type"]] for r in records("routes.txt")
                 if r["route_type"] in ("2", "3") and r["route_short_name"] in pilot["route_short_names"]}
        trips = {r["trip_id"]: r for r in records("trips.txt") if r["service_id"] in services and r["route_id"] in modes}
        stop_times = defaultdict(list)
        for r in records("stop_times.txt"):
            if r["trip_id"] in trips:
                stop_times[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"]))
    cutoff = datetime.fromisoformat(snapshot["metadata"]["snapshot_at"])
    cancelled = set()
    if "TripUpdates" in raw_sources and (cutoff - datetime.fromisoformat(receipt["received_at"])).total_seconds() < 86400:
        from google.transit import gtfs_realtime_pb2
        raw, tu_receipt = raw_sources["TripUpdates"]
        message = gtfs_realtime_pb2.FeedMessage.FromString(raw)
        require(message.IsInitialized(), "invalid archived TripUpdates source")
        latest = {}
        for entity in message.entity:
            if not entity.HasField("trip_update"):
                continue
            update = entity.trip_update
            tid = update.trip.trip_id
            if tid not in trips or update.trip.start_date and update.trip.start_date != stamp or update.trip.route_id and update.trip.route_id != trips[tid]["route_id"]:
                continue
            age = (cutoff - datetime.fromtimestamp(update.timestamp, timezone.utc)).total_seconds() if update.timestamp else None
            if age is None or not 0 <= age <= 120 or (cutoff - datetime.fromisoformat(tu_receipt["received_at"])).total_seconds() > 120:
                continue
            seqs, stops = dict(stop_times[tid]), {sid for _, sid in stop_times[tid]}
            valid = all((not u.HasField("stop_sequence") or u.stop_sequence in seqs) and
                        (not u.stop_id or u.stop_id in stops) and
                        (not u.HasField("stop_sequence") or not u.stop_id or seqs.get(u.stop_sequence) == u.stop_id)
                        for u in update.stop_time_update)
            if valid and update.trip.schedule_relationship in (0, 3) and (tid not in latest or latest[tid].timestamp < update.timestamp):
                latest[tid] = update
        cancelled = {tid for tid, update in latest.items() if update.trip.schedule_relationship == 3}
    expected, complete = [], set()
    for tid, times in sorted(stop_times.items()):
        times.sort()
        if len(times) < 2:
            continue
        complete.add(tid)
        if tid in cancelled:
            continue
        trip_id, route = f"{day}:{tid}", trips[tid]["route_id"]
        for sequence, ((_, a), (_, b)) in enumerate(zip(times, times[1:])):
            expected.append({"connection_id": f"{trip_id}:{sequence}", "trip_instance_id": trip_id,
                "route_id": route, "mode": modes[route], "sequence": sequence, "from_stop_id": a, "to_stop_id": b})
    keys = ("connection_id", "trip_instance_id", "route_id", "mode", "sequence", "from_stop_id", "to_stop_id")
    actual = [{key: c[key] for key in keys} for c in snapshot["connections"]]
    expected.sort(key=lambda c: c["connection_id"])
    actual.sort(key=lambda c: c["connection_id"])
    same(actual, expected, "independent raw-GTFS complete-trip topology")
    return {"schema_version": 1, "method": "raw-gtfs-complete-selected-trip-topology-v1", "service_date": day,
        "snapshot_id": snapshot["metadata"]["snapshot_id"], "snapshot_canonical_sha256": digest(snapshot),
        "gtfs_record_id": receipt["record_id"], "gtfs_sha256": receipt["sha256"],
        "source_active_selected_trip_count": len(trips), "source_complete_trip_count": len(complete),
        "declared_cancelled_trip_ids": sorted(cancelled), "expected_full_trip_count": len(complete - cancelled),
        "actual_full_trip_count": len({c["trip_instance_id"] for c in actual}),
        "expected_connection_count": len(expected), "actual_connection_count": len(actual),
        "expected_route_count": len({c["route_id"] for c in expected}), "actual_route_count": len({c["route_id"] for c in actual}),
        "expected_topology_sha256": digest(expected), "actual_topology_sha256": digest(actual), "passed": True}


def check_input(study, day, protocol, controls, data_dir):
    manifest = checked_json(Path(study) / "inputs" / f"{day}.json")
    path = Path(study) / "snapshots" / f"{day}.json"
    snapshot = read_json(path)
    same(manifest["snapshot_sha256"], file_hash(path), "snapshot exact-byte hash")
    same(manifest["protocol_sha256"], digest(protocol), "input protocol hash")
    role = next(role for role, days in ROLES.items() if day in days)
    require(manifest["date"] == day and manifest["role"] == role, "date role differs")
    metadata = snapshot["metadata"]
    cutoff = datetime.fromisoformat(metadata["snapshot_at"])
    require(cutoff.utcoffset() is not None and cutoff.astimezone(ZoneInfo("Australia/Brisbane")).isoformat() == day + "T07:30:05+10:00"
            and metadata["service_date"] == day and metadata["timezone"] == "Australia/Brisbane"
            and manifest["snapshot_id"] == metadata["snapshot_id"], "snapshot date/cutoff/identity differs")
    primary, original = expected_requests(snapshot, controls)
    for key, expected, hash_key in (("primary", primary, "primary_sha256"), ("controls", original, "control_sha256")):
        same(manifest[key], expected, f"fixed ordered {key} requests")
        same(manifest[hash_key], digest(expected), f"{key} request hash")
    scenarios = [closure(snapshot, protocol["config"])]
    same(manifest["scenarios"], scenarios, "source-defined rail scenario")
    same(manifest["scenario_sha256"], digest(scenarios), "scenario hash")
    retained, cancelled = restricted(snapshot["connections"], scenarios[0])
    modes = {c["trip_instance_id"]: c["mode"] for c in snapshot["connections"]}
    require(cancelled and all(modes[tid] == "rail" for tid in cancelled), "closure must cancel nonempty rail-only source trips")
    require(len({c["connection_id"] for c in snapshot["connections"]}) == len(snapshot["connections"]), "duplicate snapshot connection IDs")
    raw_sources = check_sources(manifest, snapshot, data_dir)
    if protocol["config"]["study_id"] == "corridor-impact-v2":
        same(manifest["network"], protocol["network"], "input network binding")
        same(manifest["source_coverage_sha256"], digest(manifest["source_coverage"]), "source coverage proof hash")
        pilot = read_json(safe_path(study, protocol["network"]["pilot_path"]))
        expected = independent_source_coverage(snapshot, pilot, raw_sources)
        expected["pilot_sha256"] = protocol["network"]["pilot_sha256"]
        actual = manifest["source_coverage"]
        same({k: actual[k] for k in expected}, expected, "independent source coverage evidence")
        require(isinstance(actual["limitations"], list) and actual["limitations"], "source coverage scope missing")
    return manifest, snapshot, len(cancelled)


def stressed(snapshot, delta):
    if not delta:
        return snapshot, {"method": "bus-running-time-proportional-v1", "delta_seconds": 0, "unsupported_trip_ids": []}
    revised, connections, unsupported = deepcopy(snapshot), [], []
    for tid, trip in trip_groups(snapshot).items():
        duration = trip[-1]["arrival_s"] - trip[0]["departure_s"]
        future = next((c for c in trip if c["departure_s"] >= second(snapshot)), None)
        if trip[0]["mode"] == "bus" and duration <= 0:
            unsupported.append(tid)
        for c in trip:
            item = dict(c)
            if trip[0]["mode"] == "bus" and duration > 0 and future and c["sequence"] >= future["sequence"]:
                for field in ("departure_s", "arrival_s"):
                    offset = c[field] - future["departure_s"]
                    item[field] = future["departure_s"] + (offset * (duration + delta) + duration - 1) // duration
            connections.append(item)
    revised["connections"] = connections
    for pair in revised["recovery_pairs"]:
        for direction in ("outbound", "inbound"):
            pattern = pair[direction]
            duration = pattern["stops"][-1]["arrival_offset_s"]
            require(duration > 0, "nonpositive relief pattern running time")
            for stop in pattern["stops"]:
                for field in ("arrival_offset_s", "departure_offset_s"):
                    stop[field] = (stop[field] * (duration + delta) + duration - 1) // duration
    return revised, {"method": "bus-running-time-proportional-v1", "delta_seconds": delta,
                     "nominal_snapshot_id": snapshot["metadata"]["snapshot_id"],
                     "unsupported_trip_ids": unsupported,
                     "classification": "hypothetical running-time sensitivity; not observed delay"}


def source_matches(pattern, trips):
    return [tid for tid in pattern["source_trip_instance_ids"] if tid in trips and
            all(c["mode"] == "bus" and c["route_id"] == pattern["route_id"] for c in trips[tid]) and
            [trips[tid][0]["from_stop_id"], *[c["to_stop_id"] for c in trips[tid]]] == [s["stop_id"] for s in pattern["stops"]]]


def scoring_snapshot(snapshot, requests, candidates, scenario):
    """Independent retention proof; every possible <=90-minute path is retained.

    The base is whole source trips with ANY departure at/before the global cap.
    Full source-pattern and scenario witnesses preserve unchanged engine validation.
    Published paths are checked against the original full effective snapshot.
    """
    cutoff = max(r["departure_s"] for r in requests) + 5400
    trips = trip_groups(snapshot)
    retained = {tid for tid, trip in trips.items() if any(c["departure_s"] <= cutoff for c in trip)}
    pairs = {p["pair_id"]: p for p in snapshot["recovery_pairs"]}
    candidate_witnesses, scenario_witnesses = [], []
    for pair_id in sorted({c["pair_id"] for c in candidates}):
        require(pair_id in pairs, "scoring candidate source pair absent")
        for direction in ("outbound", "inbound"):
            pattern = pairs[pair_id][direction]
            matches = sorted(source_matches(pattern, trips))
            require(matches, "scoring source pattern witness absent")
            tid = matches[0]
            retained.add(tid)
            candidate_witnesses.append({"pair_id": pair_id, "pattern_id": pattern["pattern_id"], "trip_instance_id": tid})

    def matches_segment(connection, segment):
        a, b = connection["from_stop_id"], connection["to_stop_id"]
        return ((a, b) == (segment["from_stop_id"], segment["to_stop_id"]) or
                segment["bidirectional"] and (b, a) == (segment["from_stop_id"], segment["to_stop_id"]))

    for segment in scenario["segments"]:
        matches = sorted((c["trip_instance_id"], c["connection_id"]) for c in snapshot["connections"] if matches_segment(c, segment))
        require(matches, "scoring source segment witness absent")
        if not any(tid in retained for tid, _ in matches):
            tid = matches[0][0]
            retained.add(tid)
            scenario_witnesses.append({**segment, "trip_instance_id": tid})
    revised = dict(snapshot, connections=[c for c in snapshot["connections"] if c["trip_instance_id"] in retained])
    ids = sorted(retained)
    proof = {"version": SCORING_VERSION, "cutoff_s": cutoff, "full_snapshot_sha256": digest(snapshot),
             "scoring_snapshot_sha256": digest(revised), "full_connection_count": len(snapshot["connections"]),
             "scoring_connection_count": len(revised["connections"]), "retained_trip_ids": ids,
             "retained_trip_ids_sha256": digest(ids), "candidate_source_witnesses": candidate_witnesses,
             "scenario_segment_witnesses": scenario_witnesses}
    # A separate direct check protects the reason this pruning is analytically valid.
    kept = {c["connection_id"] for c in revised["connections"]}
    require(all(c["connection_id"] in kept for c in snapshot["connections"] if c["departure_s"] <= cutoff),
            "scoring pruning omitted a movement before the duration cap")
    return revised, proof


def check_selection(study, day, manifest, nominal):
    selection = checked_json(Path(study) / "selections" / f"{day}.json")
    same(selection["manifest_sha256"], digest(manifest), "selection input hash")
    same(selection["selection_version"], VERSION, "selection policy version")
    same(selection["candidate_selection_version"], VERSION, "explicit candidate selection version")
    candidates = selection["candidates"]
    same(selection["candidate_sha256"], digest(candidates), "candidate set hash")
    require(len({c["candidate_id"] for c in candidates}) == len(candidates) <= 12, "candidate limit/identity differs")
    pairs = {p["pair_id"]: p for p in nominal["recovery_pairs"]}
    pair_ids = list(dict.fromkeys(c["pair_id"] for c in candidates))
    require(len(pair_ids) <= 3, "more than three base source pairs")
    expected = [{"candidate_id": f"candidate:{pair_id}:phase:{offset}", "pair_id": pair_id,
                 "activation_s": second(nominal) + offset, "duty_duration_s": 7200, "bus_hours": 2}
                for pair_id in pair_ids for offset in PHASES]
    same(candidates, expected, "four fixed candidate phases/full costs")
    trips = trip_groups(nominal)
    frequency = []
    for pair_id in pair_ids:
        require(pair_id in pairs, "candidate pair absent from source")
        pair = pairs[pair_id]
        supported = set()
        for direction in ("outbound", "inbound"):
            matches = source_matches(pair[direction], trips)
            require(matches, "paired pattern lacks a full matching source bus trip")
            supported.update(tid for tid in matches if second(nominal) <= trips[tid][0]["departure_s"] < second(nominal) + 7200)
        frequency.append({"pair_id": pair_id, "source_trip_count": len(supported), "source_trip_ids": sorted(supported)})
    same(selection["frequency_ranking"], sorted(frequency, key=lambda x: (-x["source_trip_count"], x["pair_id"])),
         "independent nominal source-frequency ranking")
    cohort = selection["nominal_impacted_request_ids"]
    require(cohort == sorted(set(cohort)) and set(cohort) <= {r["request_id"] for r in manifest["primary"]}, "nominal cohort identities differ")
    return selection


def duty(candidate, snapshot):
    require(candidate["bus_hours"] == 2 and candidate["duty_duration_s"] == 7200,
            "candidate cost/duration differs")
    pair = next((p for p in snapshot["recovery_pairs"] if p["pair_id"] == candidate["pair_id"]), None)
    require(pair is not None, "duty pair absent")
    out, back = pair["outbound"], pair["inbound"]
    require(out["stops"][-1]["stop_id"] == back["stops"][0]["stop_id"] and
            back["stops"][-1]["stop_id"] == out["stops"][0]["stop_id"], "duty terminals do not meet")
    duration = out["stops"][-1]["arrival_offset_s"] + back["stops"][-1]["arrival_offset_s"] + 600
    require(duration > 600, "nonpositive source running time")
    cycles = 7200 // duration
    require(cycles > 0, "no complete round trip and terminal turns fit")
    additions, trip_ids = [], []
    for cycle in range(cycles):
        start = candidate["activation_s"] + cycle * duration
        for direction, pattern, departure in (("out", out, start), ("back", back, start + out["stops"][-1]["arrival_offset_s"] + 300)):
            trip_id = f"relief:{candidate['candidate_id']}:{cycle}:{direction}"
            trip_ids.append(trip_id)
            for sequence, (a, b) in enumerate(zip(pattern["stops"], pattern["stops"][1:])):
                additions.append({"connection_id": f"{trip_id}:{sequence}", "trip_instance_id": trip_id,
                    "route_id": pattern["route_id"], "mode": "bus", "sequence": sequence,
                    "from_stop_id": a["stop_id"], "to_stop_id": b["stop_id"],
                    "departure_s": departure + a["departure_offset_s"], "arrival_s": departure + b["arrival_offset_s"],
                    "pickup_allowed": a["pickup_allowed"], "drop_off_allowed": b["drop_off_allowed"], "provenance": "hypothetical_relief"})
    return {"candidate": candidate, "cycle_count": cycles, "duty_end_s": candidate["activation_s"] + 7200,
            "connection_ids": [c["connection_id"] for c in additions], "trip_instance_ids": trip_ids}, additions


def checked_routes(values, requests, snapshot, connections, label):
    same([r["request"] for r in values], requests, label + " ordered route requests")
    by_id = {c["connection_id"]: c for c in connections}
    walks = {w["link_id"]: w for w in snapshot["walking_links"]}
    stops = {s["stop_id"] for s in snapshot["stops"]}
    for route, request in zip(values, requests):
        require(type(route["reachable"]) is bool, label + " invalid reachable flag")
        require(type(route["boardings"]) is int and type(route["transfers"]) is int,
                label + " boarding/transfer counts must be integers")
        if not route["reachable"]:
            require(route["duration_s"] is None and route["arrival_s"] is None and route["legs"] == []
                    and route["boardings"] == route["transfers"] == 0, label + " malformed unavailable route")
            continue
        require(request["origin_stop_id"] in stops and request["destination_stop_id"] in stops,
                label + " available route uses absent source stop")
        require(type(route["duration_s"]) is int and type(route["arrival_s"]) is int and route["duration_s"] >= 0
                and route["arrival_s"] == request["departure_s"] + route["duration_s"], label + " duration/arrival arithmetic differs")
        stop, clock, boardings, last_walk = request["origin_stop_id"], request["departure_s"], 0, False
        for leg in route["legs"]:
            require(leg["from_stop_id"] == stop, label + " disconnected itinerary")
            if leg["kind"] == "walk":
                require(not last_walk and leg["link_id"] in walks, label + " missing/chained walking link")
                link = walks[leg["link_id"]]
                expected = {k: link[k] for k in ("from_stop_id", "to_stop_id", "link_id", "length_m", "osm_node_ids", "geometry")}
                expected.update(kind="walk", departure_s=clock, arrival_s=clock + link["duration_s"])
                same(leg, expected, label + " actual walking leg")
                require(0 < link["length_m"] <= 600 and link["duration_s"] == __import__("math").ceil(link["length_m"] / 1.2),
                        label + " walking budget/speed differs")
                last_walk = True
            else:
                require(leg["kind"] == "transit" and leg["connection_ids"], label + " invalid transit leg")
                require(all(cid in by_id for cid in leg["connection_ids"]), label + " unavailable/cancelled movement in path")
                chain = [by_id[cid] for cid in leg["connection_ids"]]
                first, last = chain[0], chain[-1]
                require(first["pickup_allowed"] and last["drop_off_allowed"], label + " disallowed boarding/alighting")
                require(first["departure_s"] >= clock + (300 if boardings else 0), label + " transfer/wait allowance violated")
                require(all(c["trip_instance_id"] == first["trip_instance_id"] and c["route_id"] == first["route_id"] and c["mode"] == first["mode"] for c in chain), label + " mixed transit trip")
                require(all(b["sequence"] == a["sequence"] + 1 and a["to_stop_id"] == b["from_stop_id"] and a["arrival_s"] <= b["departure_s"] for a, b in zip(chain, chain[1:])), label + " noncontiguous trip leg")
                expected = {"kind": "transit", "mode": first["mode"], "trip_instance_id": first["trip_instance_id"],
                    "route_id": first["route_id"], "from_stop_id": first["from_stop_id"], "to_stop_id": last["to_stop_id"],
                    "departure_s": first["departure_s"], "arrival_s": last["arrival_s"],
                    "connection_ids": leg["connection_ids"], "provenance": first["provenance"]}
                same(leg, expected, label + " source transit leg")
                boardings, last_walk = boardings + 1, False
            stop, clock = leg["to_stop_id"], leg["arrival_s"]
        require(stop == request["destination_stop_id"] and clock == route["arrival_s"]
                and route["boardings"] == boardings <= 4 and route["transfers"] == max(0, boardings - 1),
                label + " final stop/time/boardings differ")


def cost(route):
    return 5400 if route["duration_s"] is None else min(route["duration_s"], 5400)


def rows_from_routes(baseline, disrupted, recovered, cohort, end):
    result = []
    for b, d, r in zip(baseline, disrupted, recovered):
        row = dict(b["request"])
        for name, route in (("baseline", b), ("disrupted", d), ("recovered", r)):
            row[name + "_duration_s"] = route["duration_s"]
            row[name + "_capped_duration_s"] = cost(route)
            row[name + "_within60"] = route["duration_s"] is not None and route["duration_s"] <= 3600
        row.update(nominal_impacted=row["request_id"] in cohort,
                   saved_capped_duration_s=cost(d) - cost(r), improved=cost(r) < cost(d),
                   recovered_arrival_after_closure=r["arrival_s"] is not None and r["arrival_s"] > end)
        result.append(row)
    return result


def arithmetic(rows, used):
    """Independent arithmetic: direct sums over separately checked route pairs."""
    within = {name: {r["request_id"] for r in rows if r[name + "_within60"]} for name in ("baseline", "disrupted", "recovered")}
    lost = within["baseline"] - within["disrupted"]
    restored = lost & within["recovered"]
    totals = {name: sum(r[name + "_capped_duration_s"] for r in rows) for name in within}
    saved = totals["disrupted"] - totals["recovered"]
    masks = {"nominal_impacted": lambda r: r["nominal_impacted"], "not_nominal_impacted": lambda r: not r["nominal_impacted"],
             "arrival_after_closure": lambda r: r["recovered_arrival_after_closure"],
             "arrival_by_closure_or_unavailable": lambda r: not r["recovered_arrival_after_closure"]}
    decomposition = {}
    for name, include in masks.items():
        selected = [r for r in rows if include(r)]
        decomposition[name] = {"count": len(selected), "saved_capped_duration_s": sum(r["disrupted_capped_duration_s"] - r["recovered_capped_duration_s"] for r in selected),
                               "improved_count": sum(r["recovered_capped_duration_s"] < r["disrupted_capped_duration_s"] for r in selected)}
    return {"request_count": len(rows), **{name + "_within60_count": len(ids) for name, ids in within.items()},
            "lost_count": len(lost), "restored_count": len(restored), "restored_fraction": len(restored) / len(lost) if lost else None,
            "baseline_total_capped_duration_s": totals["baseline"], "disrupted_total_capped_duration_s": totals["disrupted"],
            "total_capped_duration_s": totals["recovered"], "added_capped_duration_s": totals["disrupted"] - totals["baseline"],
            "saved_capped_duration_s": saved, "improved_count": sum(r["recovered_capped_duration_s"] < r["disrupted_capped_duration_s"] for r in rows),
            "used_bus_hours": used, "saved_query_minutes_per_bus_hour": saved / 60 / used if used else None,
            "decomposition": decomposition}


def objective(policy):
    metrics = policy["full"]
    return (-metrics["restored_count"], metrics["total_capped_duration_s"], metrics["used_bus_hours"], tuple(sorted(policy["candidate_ids"])))


def check_cell(study, day, budget, delta, protocol, manifest, nominal, selection, shared):
    path = Path(study) / "cells" / f"{day}-b{budget}-d{delta}.json"
    doc = checked_json(path)
    result = doc["result"]
    require(type(doc["calculation_elapsed_seconds"]) in (int, float) and doc["calculation_elapsed_seconds"] >= 0,
            "invalid calculation elapsed time")
    for key, expected in {"date": day, "budget_bus_hours": budget, "additional_bus_seconds": delta,
                          "manifest_sha256": digest(manifest), "selection_sha256": digest(selection),
                          "code_sha256": protocol["code_sha256"], "candidate_selection_version": VERSION,
                          "optimality_proven": False}.items():
        same(result[key], expected, "cell " + key)
    if protocol["config"]["study_id"] == "corridor-impact-v2":
        same(result["network_config_sha256"], protocol["network"]["network_config_sha256"], "cell network specification hash")
        same(result["source_coverage_sha256"], manifest["source_coverage_sha256"], "cell source coverage hash")
    snapshot, transform = stressed(nominal, delta)
    same(result["derived_snapshot_sha256"], digest(snapshot), "independent stressed snapshot hash")
    same(result["transform"], transform, "independent stress transform")
    scoring, scoring_proof = scoring_snapshot(snapshot, manifest["primary"], selection["candidates"], manifest["scenarios"][0])
    same(result["scoring"], scoring_proof, "independent whole-trip scoring retention proof")
    same(result["input_sha256"], digest({"manifest_sha256": digest(manifest), "selection_sha256": digest(selection),
        "budget_bus_hours": budget, "additional_bus_seconds": delta, "derived_snapshot_sha256": digest(snapshot),
        "scoring_sha256": digest(scoring_proof), "code_sha256": protocol["code_sha256"]}), "complete normalized cell input hash")
    scenarios = manifest["scenarios"]
    disrupted, cancelled = restricted(snapshot["connections"], scenarios[0])
    candidates = {c["candidate_id"]: c for c in selection["candidates"]}
    feasible, rejected = {}, {}
    for cid, candidate in candidates.items():
        try:
            value, additions = duty(candidate, snapshot)
            _, blocked = restricted(additions, scenarios[0])
            require(not blocked, "scenario blocks added complete duty")
            feasible[cid] = (value, additions)
        except VerificationError as exc:
            rejected[cid] = str(exc)
    issues = result["infeasible_candidates"]
    require(len({x["candidate_id"] for x in issues}) == len(issues) and
            {x["candidate_id"] for x in issues} == set(rejected) and all(isinstance(x["reason"], str) and x["reason"] for x in issues),
            "infeasible candidate identities/reasons differ")
    simple, rejection_pairs = [], []
    for rank in selection["frequency_ranking"]:
        available = sorted((c for c in candidates.values() if c["pair_id"] == rank["pair_id"] and c["candidate_id"] in feasible),
                           key=lambda c: (c["activation_s"], c["candidate_id"]))
        if available:
            simple = [c["candidate_id"] for c in available[:budget // 2]]
            break
        rejection_pairs.append(rank["pair_id"])
    simple_rejections = result["simple_policy_rejections"]
    same([r["pair_id"] for r in simple_rejections], rejection_pairs, "simple policy rejected pair order")
    for issue in simple_rejections:
        require(issue["reason"] and {x["candidate_id"] for x in issue["candidate_issues"]} ==
                {cid for cid in rejected if candidates[cid]["pair_id"] == issue["pair_id"]}, "simple policy missing candidate rejection evidence")
    same(sorted(result["policies"]), sorted(POLICIES), "compared policy set")
    require(type(result["search_evaluated_plan_count"]) is int and 0 < result["search_evaluated_plan_count"] <= 2 + sum(max(0, len(feasible) - i) for i in range(budget // 2)) + 128,
            "bounded evaluation count differs")
    require(type(result["comparison_evaluated_plan_count"]) is int and 0 < result["comparison_evaluated_plan_count"] <= 3,
            "comparison evaluation count differs")
    same(result["best_evaluated_scope"], "Best lexicographic objective among unchanged bounded search, independently scored simple frequency plan and no action",
         "best evaluated comparison scope")
    for name, policy in result["policies"].items():
        ids = policy["candidate_ids"]
        require(len(ids) == len(set(ids)) <= budget // 2 and set(ids) <= set(feasible), "policy selection exceeds budget or is infeasible")
        if name == "no_action":
            same(ids, [], "no-action candidate IDs")
        if name == "simple_frequency":
            same(ids, simple, "predeclared source-frequency policy IDs")
        if name == "best_evaluated":
            same(ids, sorted(ids), "best evaluated deterministic candidate order")
        same(policy["duties"], [feasible[cid][0] for cid in ids], name + " complete duty cycles/turns/identities")
        additions = [c for cid in ids for c in feasible[cid][1]]
        require(not {c["connection_id"] for c in additions} & {c["connection_id"] for c in snapshot["connections"]}, "added connections collide with source IDs")
        recovered, _ = restricted(snapshot["connections"] + additions, scenarios[0])
        route_sets = {"baseline": snapshot["connections"], "disrupted": disrupted, "recovered": recovered}
        for prefix, requests in (("", manifest["primary"]), ("control_", manifest["controls"])):
            for kind, connections in route_sets.items():
                route_key = prefix + kind + "_routes"
                checked_routes(policy[route_key], requests, snapshot, connections, name + "/" + route_key)
                if kind != "recovered":
                    shared_key = (day, delta, route_key)
                    identity = digest(policy[route_key])
                    require(shared.setdefault(shared_key, identity) == identity, "paired baseline/disrupted routes differ across policies/budgets")
            if not ids:
                same(policy[prefix + "recovered_routes"], policy[prefix + "disrupted_routes"], "empty policy changes disrupted routes")
            cohort = set(selection["nominal_impacted_request_ids"]) if not prefix else set()
            rows = rows_from_routes(policy[prefix + "baseline_routes"], policy[prefix + "disrupted_routes"], policy[prefix + "recovered_routes"], cohort, scenarios[0]["end_s"])
            same(policy["control_queries" if prefix else "queries"], rows, name + " paired query rows")
            same(policy["controls" if prefix else "full"], arithmetic(rows, 2 * len(ids)), name + " full/control independent arithmetic")
            if not prefix:
                same(policy["impacted"], arithmetic([r for r in rows if r["nominal_impacted"]], 2 * len(ids)), name + " independent impacted arithmetic")
                if delta == 0:
                    actual_cohort = sorted(b["request"]["request_id"] for b, d in zip(policy["baseline_routes"], policy["disrupted_routes"])
                                           if b["reachable"] and cost(d) > cost(b))
                    same(selection["nominal_impacted_request_ids"], actual_cohort, "baseline-defined nominal impacted cohort")
        stops = {s["stop_id"] for s in snapshot["stops"]}
        if any(r["origin_stop_id"] in stops and r["destination_stop_id"] in stops for r in manifest["primary"]):
            same(policy["scoring_objective"], {"restored_count": policy["full"]["restored_count"],
                "total_capped_duration_s": policy["full"]["total_capped_duration_s"], "bus_hours": 2 * len(ids)},
                name + " scored objective differs from independently checked full routes")
    best = result["policies"]["best_evaluated"]
    require(objective(best) <= objective(result["policies"]["no_action"]) and objective(best) <= objective(result["policies"]["simple_frequency"]),
            "best evaluated policy is worse than a saved comparison")
    return {"sha256": file_hash(path), "passed": True, "primary": best["full"], "impacted": best["impacted"],
            "controls": best["controls"], "selected_candidate_ids": best["candidate_ids"], "infeasible_candidate_count": len(rejected),
            "baseline_unavailable_count": sum(r["duration_s"] is None for r in best["baseline_routes"]),
            "source_cancelled_rail_trip_count": len(cancelled)}


def verify_study(study_dir, *, data_dir=None, config_path=None, repo=REPO, dates=None, allow_partial=False,
                 preservation_path=None, expected_protocol_sha256=None, expected_preservation_sha256=None):
    study, repo = Path(study_dir), Path(repo)
    data_dir = Path(data_dir) if data_dir is not None else repo / "data"
    config_path = Path(config_path) if config_path is not None else repo / "configs/corridor-impact.v2.json"
    preservation_path = Path(preservation_path) if preservation_path is not None else repo / DEFAULT_PRESERVATION
    report = {"version": "corridor-independent-verification-v1", "checked_at": datetime.now(timezone.utc).isoformat(),
              "verifier_sha256": file_hash(__file__), "passed": False, "status": "failed", "cells": {}, "errors": [],
              "missing_cells": [], "limitations": [
                  "Independently reconciles saved paths, arithmetic, resource assumptions and archived source identities; does not prove earliest arrivals or global plan optimality.",
                  "Snapshot reconstruction, collection completeness, OTP comparison and exact policy reproduction are separate checks.",
                  "Source bus timings, initial bus positions, availability/capacity, pedestrian access and operational feasibility are not calibrated.",
                  "Equal-weight planned queries are not passenger demand, observed impacts or financial savings.",
                  "Date classification and the untouched status of confirmation outcomes require coordinator evidence beyond saved numerical artifacts."]}
    try:
        report["preservation"] = preserve_originals(preservation_path, repo, expected_preservation_sha256)
        protocol, controls = check_protocol(study, config_path, repo, expected_protocol_sha256)
        report["protocol_sha256"] = file_hash(study / "protocol.json")
        registered = [day for days in ROLES.values() for day in days]
        selected = list(dates) if dates is not None else registered
        require(selected and len(set(selected)) == len(selected) and set(selected) <= set(registered), "date filter outside registered protocol")
        report["dates"] = selected
        report["expected_cell_count"] = len(selected) * len(MATRIX)
        expected_names = {f"{day}-b{b}-d{d}.json" for day in registered for b, d in MATRIX}
        actual_names = {p.name for p in (study / "cells").glob("*.json") if not p.name.endswith(".sha256.json")}
        require(actual_names <= expected_names, "unregistered cell file present")
        shared = {}
        for day in selected:
            try:
                manifest, nominal, cancelled_count = check_input(study, day, protocol, controls, data_dir)
                selection = check_selection(study, day, manifest, nominal)
            except (KeyError, OSError, TypeError, ValueError) as exc:
                report["errors"].append(f"{day} input: {exc}")
                continue
            nominal_seen = False
            for budget, delta in MATRIX:
                key = f"{day}-b{budget}-d{delta}"
                if not (study / "cells" / (key + ".json")).exists():
                    report["missing_cells"].append(key)
                    continue
                try:
                    report["cells"][key] = check_cell(study, day, budget, delta, protocol, manifest, nominal, selection, shared)
                    nominal_seen |= delta == 0
                except (KeyError, OSError, TypeError, ValueError) as exc:
                    report["errors"].append(f"{key}: {exc}")
            require(nominal_seen or not any(k.startswith(day) for k in report["cells"]), "stress cells have no independently checked nominal cohort")
        if not allow_partial and report["missing_cells"]:
            report["errors"].append("registered matrix is incomplete")
        report["verified_cell_count"] = len(report["cells"])
        report["passed"] = not report["errors"] and bool(report["cells"])
        report["status"] = ("partial" if report["missing_cells"] else "complete") if report["passed"] else "failed"
    except (KeyError, OSError, TypeError, ValueError) as exc:
        report["errors"].append(str(exc))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=REPO / "data/processed/corridor-impact-v2")
    parser.add_argument("--data-dir", type=Path, default=REPO / "data")
    parser.add_argument("--config", type=Path, default=REPO / "configs/corridor-impact.v2.json")
    parser.add_argument("--preservation-manifest", type=Path, default=REPO / DEFAULT_PRESERVATION)
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument("--expected-preservation-sha256")
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = verify_study(args.study_dir, data_dir=args.data_dir, config_path=args.config, dates=args.dates,
                          allow_partial=args.allow_partial, preservation_path=args.preservation_manifest,
                          expected_protocol_sha256=args.expected_protocol_sha256,
                          expected_preservation_sha256=args.expected_preservation_sha256)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded(report))
    print(json.dumps({k: v for k, v in report.items() if k not in ("cells", "limitations")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
