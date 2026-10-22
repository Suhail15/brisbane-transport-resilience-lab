"""Independently reconcile the frozen morning matrix from immutable full runs.

The integrity helper checks archived bytes and source receipts. All arithmetic,
scenario-event transformations, duty checks and comparisons below use plain JSON;
no routing, recovery, evaluation or metric helper is called.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services"))
from resilience.pipeline.archive import Archive
from resilience.pipeline.integrity import verify_run

DATES = ("2026-10-19", "2026-10-20", "2026-10-21")
SCENARIOS = ("cancellation", "stop_closure", "rail_corridor", "bus_delay")
BUDGETS = (0, 2, 4, 8)
OFFSETS = (0, 900, 1800, 2700, 3600)
DEFAULT_SUMMARY = Path("data/processed/morning-evaluation-v1/summary.json")
DEFAULT_CONFIG = Path("configs/morning-evaluation.v1.json")
ASSUMPTIONS = {
    "max_walk_m": 600, "walking_speed_m_s": 1.2, "max_stop_snap_m": 30,
    "walking_length_basis": "actual_osm_edges", "transfer_slack_s": 300,
    "max_boardings": 4, "max_requests": 500, "primary_request_weight": 1,
    "reachability_horizon_s": 3600, "duration_cap_s": 5400,
    "activation_lead_s": 600, "bus_duty_s": 7200, "terminal_turn_s": 300,
    "bus_hours_per_duty": 2, "max_candidates": 12, "max_buses": 4,
    "trip_updates_cadence_s": 30, "vehicle_positions_cadence_s": 30,
    "alerts_cadence_s": 60,
    "recording_window": "weekdays 06:00-12:00 Australia/Brisbane",
    "fleet_availability": "hypothetical_unverified",
    "passenger_demand": "unknown_equal_request_weights",
}


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


def read_json(path):
    return json.loads(Path(path).read_bytes())


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_combinations():
    """54 prescribed cells, independent of the driver's matrix generator."""
    cells = {}
    for date in DATES:
        for scenario in SCENARIOS:
            for budget in BUDGETS:
                cells[f"{date}.{scenario}.b{budget}.s0"] = (date, scenario, budget, 0)
        for delta in (300, 600):
            cells[f"{date}.stop_closure.b2.s{delta}"] = (date, "stop_closure", 2, delta)
    return cells


def snapshot_second(snapshot):
    local = datetime.fromisoformat(snapshot["metadata"]["snapshot_at"]).astimezone(
        ZoneInfo("Australia/Brisbane"))
    return local.hour * 3600 + local.minute * 60 + local.second


def frozen_inputs(root, archive, config_path):
    """Validate the existing freeze; never choose or replace scenario targets."""
    config = read_json(config_path)
    fixed = {
        "version": "morning-evaluation-v1", "timezone": "Australia/Brisbane",
        "evaluation_dates": list(DATES), "decision_local_time": "07:30:05",
        "scenarios": list(SCENARIOS), "budgets_bus_hours": list(BUDGETS),
        "max_swap_evaluations": 128, "sensitivity_scenario": "stop_closure",
        "sensitivity_budget_bus_hours": 2, "sensitivity_seconds": [0, 300, 600],
        "closed_stop_id": "3713", "scenario_duration_seconds": 7200,
        "additional_bus_delay_seconds": 1200, "journey_set_version": "pilot-od20-v1",
    }
    require(all(config.get(k) == v for k, v in fixed.items()), "frozen protocol configuration changed")
    saved = read_json(root / "plan.json")
    plan = read_json(root / "decision-manifest.json")
    require(saved["config"] == config and saved["config_sha256"] == digest(config),
            "saved plan/config identity differs")
    require(saved["plan"] == plan and saved["plan_sha256"] == digest(plan),
            "decision manifest differs from frozen plan")
    require(set(plan["decision_snapshots"]) == set(DATES)
            and len(set(plan["decision_snapshots"].values())) == 3, "fixed decision snapshots differ")
    journey_path = Path(config["journey_set"])
    if not journey_path.is_absolute():
        journey_path = REPO / journey_path
    journey = read_json(journey_path)
    require(journey["version"] == "pilot-od20-v1" and journey["primary_weight"] == 1
            and journey["offset_seconds"] == list(OFFSETS) and journey["request_count"] == 100,
            "journey specification changed")
    pairs = journey["pairs"]
    require(len(pairs) == len({p["pair_id"] for p in pairs}) == 20
            and len({(p["origin_stop_id"], p["destination_stop_id"]) for p in pairs}) == 20,
            "journey set must contain 20 distinct fixed pairs")
    require({p.name for p in (root / "targets").glob("*.json")} == {f"{d}.json" for d in DATES},
            "target file set differs from three fixed final dates")
    manifests, snapshots = {}, {}
    for date in DATES:
        manifest = read_json(root / "targets" / f"{date}.json")
        require(manifest["date"] == date and manifest["version"] == config["version"]
                and manifest["snapshot_id"] == plan["decision_snapshots"][date], "target identity differs")
        require(manifest["status"] == "prepared" and manifest["unsupported_targets"] == [],
                f"{date}: unsupported frozen source target")
        require(manifest["config_sha256"] == digest(config)
                and manifest["plan_sha256"] == digest(plan)
                and manifest["journey_set_sha256"] == digest(journey), "target freeze hash differs")
        path = archive.root / "processed" / "snapshots" / f"{manifest['snapshot_id']}.json"
        require(file_hash(path) == manifest["snapshot_content_sha256"], "target snapshot hash differs")
        snapshot = read_json(path)
        metadata = snapshot["metadata"]
        cutoff = datetime.fromisoformat(metadata["snapshot_at"])
        require(cutoff.utcoffset() is not None, "naive decision cutoff")
        local = cutoff.astimezone(ZoneInfo(config["timezone"]))
        require(local.isoformat() == f"{date}T07:30:05+10:00"
                and metadata["service_date"] == date and metadata["timezone"] == config["timezone"]
                and metadata["snapshot_id"] == manifest["snapshot_id"]
                and cutoff == datetime.fromisoformat(manifest["snapshot_at"]), "decision cutoff/date differs")
        source_ids = sorted(s["record_id"] for s in metadata["sources"])
        require(source_ids == manifest["source_record_ids"] and len(set(source_ids)) == len(source_ids),
                "frozen source identities differ")
        for source in metadata["sources"]:
            receipt = archive.get(source["record_id"])
            require(receipt is not None and receipt["sha256"] == source["sha256"], "missing source identity")
            received = datetime.fromisoformat(source["received_at"])
            require(received == datetime.fromisoformat(receipt["received_at"]) and received <= cutoff,
                    "source received time differs or exceeds decision cutoff")
        requests = [{"request_id": f"{journey['version']}:{p['pair_id']}:{offset}",
                     "origin_stop_id": p["origin_stop_id"], "destination_stop_id": p["destination_stop_id"],
                     "departure_s": 27005 + offset, "od_weight": None}
                    for p in pairs for offset in OFFSETS]
        require(manifest["requests"] == requests and manifest["request_set_sha256"] == digest(requests),
                "fixed ordered 100-request identity differs")
        connections = {c["connection_id"]: c for c in snapshot["connections"]}
        bus, rail = manifest["targets"]["bus"], manifest["targets"]["rail"]
        for target, mode in ((bus, "bus"), (rail, "rail")):
            require(target and connections.get(target["connection_id"]) == target
                    and target["mode"] == mode and target["departure_s"] >= 27005,
                    "frozen target is not an eligible existing source movement")
        require(bus["from_stop_id"] in config["corridor_bus_origin_ids"], "frozen bus target outside rule")
        require(rail["from_stop_id"] in config["rail_origin_ids"]
                or rail["to_stop_id"] in config["rail_destination_ids"], "frozen rail target outside OR rule")
        require(manifest["targets"]["closed_stop_id"] == "3713"
                and any(s["stop_id"] == "3713" for s in snapshot["stops"]), "frozen closed stop absent")
        common = {"start_s": 27005, "end_s": 34205}
        scenarios = {
            "cancellation": dict(common, kind="trip_cancellation", scenario_id=f"morning:{date}:cancel",
                                 trip_instance_ids=[bus["trip_instance_id"]]),
            "stop_closure": dict(common, kind="stop_unavailable", scenario_id=f"morning:{date}:stop", stop_ids=["3713"]),
            "rail_corridor": dict(common, kind="corridor_closure", scenario_id=f"morning:{date}:rail",
                                  segments=[{"from_stop_id": rail["from_stop_id"], "to_stop_id": rail["to_stop_id"], "bidirectional": True}]),
            "bus_delay": dict(common, kind="additional_delay", scenario_id=f"morning:{date}:delay",
                              trip_instance_ids=[bus["trip_instance_id"]], additional_seconds=1200),
        }
        require(manifest["scenarios"] == scenarios, "scenario differs from frozen source target")
        manifests[date], snapshots[date] = manifest, snapshot
    return config, manifests, snapshots


def stressed_snapshot(nominal, delta):
    """Independent integer arithmetic for the documented proportional stress."""
    if not delta:
        return nominal
    trips = defaultdict(list)
    for connection in nominal["connections"]:
        trips[connection["trip_instance_id"]].append(connection)
    changed = []
    unsupported = []
    cutoff = snapshot_second(nominal)
    for trip_id, trip in trips.items():
        trip = sorted(trip, key=lambda c: c["sequence"])
        duration = trip[-1]["arrival_s"] - trip[0]["departure_s"]
        future = [c for c in trip if c["departure_s"] >= cutoff]
        if trip[0]["mode"] != "bus" or duration <= 0 or not future:
            if trip[0]["mode"] == "bus" and duration <= 0:
                unsupported.append(trip_id)
            changed.extend(trip)
            continue
        anchor, first_sequence = future[0]["departure_s"], future[0]["sequence"]
        for connection in trip:
            item = dict(connection)
            if item["sequence"] >= first_sequence:
                for field in ("departure_s", "arrival_s"):
                    offset = item[field] - anchor
                    item[field] = anchor + (offset * (duration + delta) + duration - 1) // duration
            changed.append(item)
    pairs = []
    for pair in nominal["recovery_pairs"]:
        revised = dict(pair)
        for direction in ("outbound", "inbound"):
            pattern = pair[direction]
            duration = pattern["stops"][-1]["arrival_offset_s"]
            require(duration > 0, "unsupported zero-duration relief pattern")
            stops = []
            for stop in pattern["stops"]:
                item = dict(stop)
                for field in ("arrival_offset_s", "departure_offset_s"):
                    item[field] = (item[field] * (duration + delta) + duration - 1) // duration
                stops.append(item)
            revised[direction] = dict(pattern, stops=stops)
        pairs.append(revised)
    return dict(nominal, connections=changed, recovery_pairs=pairs), unsupported


def scenario_connections(connections, scenarios, cutoff):
    """Reconstruct effective source events without importing engine transforms."""
    starts = defaultdict(list)
    for scenario in scenarios:
        if scenario["kind"] == "additional_delay":
            for trip_id in set(scenario["trip_instance_ids"]):
                sequences = [c["sequence"] for c in connections if c["trip_instance_id"] == trip_id
                             and max(cutoff, scenario["start_s"]) <= c["departure_s"] < scenario["end_s"]]
                if sequences:
                    starts[trip_id].append((min(sequences), scenario["additional_seconds"]))
    effective = []
    for connection in connections:
        amount = sum(delta for seq, delta in starts[connection["trip_instance_id"]] if connection["sequence"] >= seq)
        effective.append(dict(connection, departure_s=connection["departure_s"] + amount,
                              arrival_s=connection["arrival_s"] + amount) if amount else connection)
    cancelled, unavailable = set(), set()
    for scenario in scenarios:
        kind = scenario["kind"]
        if kind == "stop_unavailable":
            unavailable.update(scenario["stop_ids"])
            continue
        if kind not in ("trip_cancellation", "corridor_closure"):
            continue
        for c in effective:
            if c["arrival_s"] == c["departure_s"]:
                overlaps = scenario["start_s"] <= c["departure_s"] < scenario["end_s"]
            else:
                overlaps = c["departure_s"] < scenario["end_s"] and c["arrival_s"] > scenario["start_s"]
            if kind == "trip_cancellation":
                targeted = c["trip_instance_id"] in scenario["trip_instance_ids"]
            else:
                targeted = any((c["from_stop_id"], c["to_stop_id"]) == (s["from_stop_id"], s["to_stop_id"])
                               or s["bidirectional"] and (c["to_stop_id"], c["from_stop_id"]) == (s["from_stop_id"], s["to_stop_id"])
                               for s in scenario["segments"])
            if overlaps and targeted:
                cancelled.add(c["trip_instance_id"])
    result = {}
    for c in effective:
        if c["trip_instance_id"] in cancelled:
            continue
        item = dict(c)
        for s in scenarios:
            if s["kind"] == "stop_unavailable":
                if c["from_stop_id"] in s["stop_ids"] and s["start_s"] <= c["departure_s"] < s["end_s"]:
                    item["pickup_allowed"] = False
                if c["to_stop_id"] in s["stop_ids"] and s["start_s"] <= c["arrival_s"] < s["end_s"]:
                    item["drop_off_allowed"] = False
        require(c["connection_id"] not in result, "duplicate source connection id")
        result[c["connection_id"]] = item
    impact = {"cancelled_trip_instance_ids": sorted(cancelled),
              "delayed_trip_instance_ids": sorted(k for k, values in starts.items() if values),
              "unavailable_stop_ids": sorted(unavailable)}
    return result, impact


def checked_routes(routes, requests, label):
    require(len(routes) == len(requests) and [r["request"] for r in routes] == requests,
            f"{label}: ordered request arrays differ")
    require(len({r["request_id"] for r in requests}) == len(requests), "duplicate request ids")
    for r in routes:
        request_id = r["request"]["request_id"]
        require(type(r["reachable"]) is bool, f"{label}/{request_id}: invalid reachable flag")
        if r["reachable"]:
            require(type(r["duration_s"]) is int and type(r["arrival_s"]) is int
                    and r["duration_s"] >= 0 and r["duration_s"] == r["arrival_s"] - r["request"]["departure_s"],
                    f"{label}/{request_id}: duration/arrival arithmetic differs")
        else:
            require(r["duration_s"] is None and r["arrival_s"] is None and r["legs"] == []
                    and r["boardings"] == r["transfers"] == 0,
                    f"{label}/{request_id}: malformed unreachable journey")


def recompute_metrics(evaluation, requests, disrupted_connections):
    """All primary counts and capped totals, including unavailable requests."""
    routes = [evaluation[name] for name in ("baseline", "disrupted", "recovered")]
    for name, values in zip(("baseline", "disrupted", "recovered"), routes):
        checked_routes(values, requests, name)
    within = [{r["request"]["request_id"] for r in values if r["reachable"] and r["duration_s"] <= 3600}
              for values in routes]
    totals = [sum(min(r["duration_s"], 5400) if r["reachable"] else 5400 for r in values) for values in routes]
    lost, misses = within[0] - within[1], []
    for route in routes[0]:
        previous, walk = None, 0
        for leg in route["legs"]:
            if leg["kind"] == "walk":
                if previous is not None:
                    walk += leg["arrival_s"] - leg["departure_s"]
                continue
            if previous is not None:
                retained = all(cid in disrupted_connections for cid in previous["connection_ids"] + leg["connection_ids"])
                if retained:
                    alight = disrupted_connections[previous["connection_ids"][-1]]
                    board = disrupted_connections[leg["connection_ids"][0]]
                    earliest = alight["arrival_s"] + walk + 300
                    if alight["drop_off_allowed"] and board["pickup_allowed"] and earliest > board["departure_s"]:
                        misses.append({"request_id": route["request"]["request_id"],
                                       "from_trip_instance_id": previous["trip_instance_id"],
                                       "to_trip_instance_id": leg["trip_instance_id"],
                                       "alight_stop_id": previous["to_stop_id"], "board_stop_id": leg["from_stop_id"],
                                       "earliest_boarding_s": earliest, "departure_s": board["departure_s"]})
            previous, walk = leg, 0
    restored = len(lost & within[2])
    return {"request_count": len(requests), "reachability_horizon_s": 3600, "duration_cap_s": 5400,
            "baseline_reachable_count": len(within[0]), "disrupted_reachable_count": len(within[1]),
            "recovered_reachable_count": len(within[2]), "lost_count": len(lost), "restored_count": restored,
            "restored_fraction": restored / len(lost) if lost else None,
            "baseline_total_capped_duration_s": totals[0], "disrupted_total_capped_duration_s": totals[1],
            "recovered_total_capped_duration_s": totals[2], "requests_with_missed_connections": len({m["request_id"] for m in misses}),
            "missed_connection_count": len(misses)}, misses


def independent_duty(candidate, snapshot):
    require(candidate["bus_hours"] == 2 and candidate["duty_duration_s"] == 7200
            and candidate["activation_s"] >= snapshot_second(snapshot) + 600,
            "candidate duty cost/duration/activation differs")
    pairs = {p["pair_id"]: p for p in snapshot["recovery_pairs"]}
    require(candidate["pair_id"] in pairs, "candidate lacks an existing paired pattern")
    pair = pairs[candidate["pair_id"]]
    trips = defaultdict(list)
    for c in snapshot["connections"]:
        trips[c["trip_instance_id"]].append(c)
    for pattern in (pair["outbound"], pair["inbound"]):
        source_matches = False
        for trip_id in pattern["source_trip_instance_ids"]:
            trip = sorted(trips[trip_id], key=lambda c: c["sequence"])
            if trip and all(c["mode"] == "bus" and c["route_id"] == pattern["route_id"] for c in trip):
                source_matches |= [trip[0]["from_stop_id"], *[c["to_stop_id"] for c in trip]] == [s["stop_id"] for s in pattern["stops"]]
        require(source_matches, "relief pattern lacks full bus source-trip topology")
    out, back = pair["outbound"]["stops"], pair["inbound"]["stops"]
    require(out[-1]["stop_id"] == back[0]["stop_id"] and back[-1]["stop_id"] == out[0]["stop_id"],
            "relief pattern terminals do not meet")
    cycle_seconds = out[-1]["arrival_offset_s"] + back[-1]["arrival_offset_s"] + 600
    cycles = 7200 // cycle_seconds
    require(cycles > 0, "duty cannot complete a round trip and both turns")
    additions, trip_ids = [], []
    for cycle in range(cycles):
        start = candidate["activation_s"] + cycle * cycle_seconds
        for direction, pattern, departure in (("out", pair["outbound"], start),
                                              ("back", pair["inbound"], start + out[-1]["arrival_offset_s"] + 300)):
            trip_id = f"relief:{candidate['candidate_id']}:{cycle}:{direction}"
            trip_ids.append(trip_id)
            for sequence, (previous, following) in enumerate(zip(pattern["stops"], pattern["stops"][1:])):
                additions.append({"connection_id": f"{trip_id}:{sequence}", "trip_instance_id": trip_id,
                                  "route_id": pattern["route_id"], "mode": "bus", "sequence": sequence,
                                  "from_stop_id": previous["stop_id"], "to_stop_id": following["stop_id"],
                                  "departure_s": departure + previous["departure_offset_s"],
                                  "arrival_s": departure + following["arrival_offset_s"],
                                  "pickup_allowed": previous["pickup_allowed"], "drop_off_allowed": following["drop_off_allowed"],
                                  "provenance": "hypothetical_relief"})
    return {"candidate": candidate, "cycle_count": cycles, "duty_end_s": candidate["activation_s"] + 7200,
            "connection_ids": [c["connection_id"] for c in additions], "trip_instance_ids": trip_ids}, additions


def objective_key(objective, candidate_ids=()):
    return (-objective["restored_count"], objective["total_capped_duration_s"], objective["bus_hours"], tuple(candidate_ids))


def verify_plan(result, inp, snapshot, metrics, evaluation):
    plan, budget = result["plan"], inp["budget_bus_hours"]
    candidates = {c["candidate_id"]: c for c in inp["candidates"]}
    require(len(candidates) == len(inp["candidates"]) <= 12, "candidate count/uniqueness differs")
    require(result["considered_candidate_ids"] == sorted(candidates), "considered candidate identities differ")
    require(result["budget_bus_hours"] == budget and result["method"] == "greedy_bounded_swap"
            and result["optimality_proven"] is False and result["hypothetical"] is True,
            "result method/budget/hypothetical status differs")
    ids = plan["candidate_ids"]
    require(ids == sorted(set(ids)) and set(ids) <= set(candidates), "selected candidate identities differ")
    require(plan["bus_count"] == len(ids) <= min(4, budget // 2)
            and plan["bus_hours"] == 2 * len(ids) <= budget and len(plan["duties"]) == len(ids),
            "selected resource count/cost exceeds frozen budget")
    infeasible = result["infeasible_candidate_ids"]
    require(infeasible == sorted(set(infeasible)) and set(infeasible) <= set(candidates)
            and not set(ids) & set(infeasible), "infeasible candidate accounting differs")
    require([issue["candidate_id"] for issue in result["infeasible_candidates"]] == infeasible
            and all(issue["reason"] for issue in result["infeasible_candidates"]), "missing infeasibility reasons")
    for candidate in inp["candidates"]:
        require(candidate["bus_hours"] == 2 and candidate["duty_duration_s"] == 7200
                and candidate["activation_s"] >= snapshot_second(snapshot) + 600, "candidate resource assumption differs")
    for candidate_id, recorded in zip(ids, plan["duties"]):
        expected, additions = independent_duty(candidates[candidate_id], snapshot)
        require(recorded == expected, "selected duty cycles/end/identifiers differ")
        _, impact = scenario_connections(additions, inp["scenarios"], snapshot_second(snapshot))
        require(not set(expected["trip_instance_ids"]) & set(impact["cancelled_trip_instance_ids"]),
                "scenario blocks a selected duty trip")
    expected_objective = {"restored_count": metrics["restored_count"],
                          "total_capped_duration_s": metrics["recovered_total_capped_duration_s"],
                          "bus_hours": 2 * len(ids)}
    require(plan["objective"] == expected_objective, "selected objective differs from independent metrics/resources")
    no_action = {"restored_count": 0, "total_capped_duration_s": metrics["disrupted_total_capped_duration_s"], "bus_hours": 0}
    require(result["no_intervention"] == no_action, "no-intervention objective differs from disrupted routes")
    require(objective_key(expected_objective, ids) <= objective_key(no_action), "selected plan is worse than no intervention")
    if not ids:
        require(evaluation["recovered"] == evaluation["disrupted"], "empty plan changes disrupted route outcomes")
    simple = result["busiest_affected_pattern"]
    if simple is not None:
        require(simple["bus_hours"] in (2, 4, 6, 8) and simple["bus_hours"] <= budget,
                "simple comparison exceeds budget")
        require(objective_key(expected_objective)[:3] <= objective_key(simple)[:3], "selected objective worse than simple comparison")


def review_run(archive, root, key, row, cell, manifest, nominal, cross):
    date, scenario, budget, delta = cell
    run, inp = verify_run(archive, row["run_id"])
    require(read_json(root / "results" / f"{key}.json") == run, "local final differs from immutable archive result")
    require(run["status"] == "completed" and run.get("error") is None, "run is not successfully completed")
    require(inp["snapshot_id"] == manifest["snapshot_id"] and run["snapshot_id"] == manifest["snapshot_id"]
            and inp["snapshot_at"] == manifest["snapshot_at"]
            and inp["snapshot_content_sha256"] == manifest["snapshot_content_sha256"]
            and inp["source_record_ids"] == manifest["source_record_ids"], "run differs from frozen source snapshot")
    require(inp["requests"] == manifest["requests"] and inp["scenarios"] == [manifest["scenarios"][scenario]],
            "run differs from frozen ordered requests/scenario")
    require(inp["budget_bus_hours"] == budget and inp["max_swap_evaluations"] == 128
            and inp["journey_set_version"] == "pilot-od20-v1"
            and inp["search_method"] == "greedy_bounded_swap"
            and inp["objective_version"] == "restored-60m-duration-cap-90m-bus-hours-v1", "run search/objective setting differs")
    require(inp["assumptions"] == dict(ASSUMPTIONS, bus_running_time_sensitivity_seconds=delta),
            "frozen analysis assumptions differ")
    if delta:
        derived = inp["derived_input"]
        require(derived and derived["method"] == "bus-running-time-proportional-v1"
                and derived["delta_seconds"] == delta and derived["nominal_snapshot_id"] == manifest["snapshot_id"],
                "sensitivity nominal provenance differs")
        path = (archive.root / "processed" / derived["path"]).resolve()
        require(path.is_relative_to((archive.root / "processed" / "derived-inputs").resolve()), "unsafe derived input path")
        snapshot = read_json(path)
        independently_stressed, unsupported = stressed_snapshot(nominal, delta)
        require(snapshot == independently_stressed and derived["unsupported_trip_ids"] == unsupported,
                "derived sensitivity differs from proportional source transformation")
    else:
        require(inp["derived_input"] is None, "nominal run unexpectedly uses derived input")
        snapshot = nominal
    connections, impact = scenario_connections(snapshot["connections"], inp["scenarios"], snapshot_second(snapshot))
    result = run["result"]
    evaluation = result["plan"]["evaluation"]
    require(evaluation["impact"] == impact, "scenario impact differs from independent source events")
    metrics, misses = recompute_metrics(evaluation, inp["requests"], connections)
    require(evaluation["metrics"] == metrics, "reported metrics differ from independent route arithmetic")
    require(evaluation["missed_connections"] == misses, "missed-connection details differ from effective source events")
    verify_plan(result, inp, snapshot, metrics, evaluation)
    expected_row = {"run_id": run["run_id"], "input_sha256": run["metadata"]["input_sha256"],
                    "status": "completed", "date": date, "scenario": scenario, "budget_bus_hours": budget,
                    "sensitivity_seconds": delta, "request_count": 100, "error": None,
                    "metrics": metrics, "objective": result["plan"]["objective"],
                    "considered_candidate_ids": result["considered_candidate_ids"]}
    require(row == expected_row, "summary row differs from independently checked full result")
    identities = {
        ("requests", date): digest(inp["requests"]),
        ("scenarios", date, scenario): digest(inp["scenarios"]),
        ("nominal_candidates_including_stress", date, scenario): digest(inp["candidates"]),
        ("baseline", date, delta): digest(evaluation["baseline"]),
        ("disrupted", date, scenario, delta): digest(evaluation["disrupted"]),
    }
    for group, identity in identities.items():
        require(cross.setdefault(group, identity) == identity, f"shared {group[0]} differs across compared budgets/scenarios/stress")
    return {"run_id": run["run_id"], "input_sha256": row["input_sha256"], "passed": True,
            "metrics": metrics, "objective": result["plan"]["objective"], "bus_count": result["plan"]["bus_count"],
            "candidate_count": len(inp["candidates"]), "missed_connections_independently_recomputed": True,
            "immutable_result_sha256": file_hash(archive.root / "processed" / "run-results" / f"{run['run_id']}.json")}


def verify_summary(summary_path=DEFAULT_SUMMARY, *, archive=None, config_path=DEFAULT_CONFIG, allow_partial=False):
    summary_path = Path(summary_path)
    root = summary_path.parent
    report = {"version": "morning-independent-verification-v1", "checked_at": datetime.now(timezone.utc).isoformat(),
              "summary_path": str(summary_path), "verifier_sha256": file_hash(__file__), "passed": False,
              "status": "failed", "expected_combinations": 54, "verified_combinations": 0,
              "runs": {}, "errors": [], "missing_combinations": [], "limitations": [
                  "Scenario outputs count configured equal-weight requests, not passengers or measured service outcomes.",
                  "Checks reconcile immutable source/input/result bytes and route arithmetic; no routing optimality or exhaustive recovery claim.",
                  "Simple-policy duration has no separate route arrays in the run schema; its reported objective is checked as a comparison only.",
                  "OTP, performance, collection completeness, public permissions and offline recovery reproduction are separate reviews.",
              ]}
    cells = expected_combinations()
    try:
        archive = archive or Archive(Path("data"))
        config, manifests, snapshots = frozen_inputs(root, archive, config_path)
        summary = read_json(summary_path) if summary_path.exists() else {}
        require(isinstance(summary, dict), "summary must be a keyed object")
        report["summary_sha256"] = file_hash(summary_path) if summary_path.exists() else None
        report["config_sha256"] = digest(config)
        report["target_sha256"] = {d: file_hash(root / "targets" / f"{d}.json") for d in DATES}
        report["missing_combinations"] = sorted(set(cells) - set(summary))
        require(not set(summary) - set(cells), "summary contains unapproved combinations")
        files = {p.stem for p in (root / "results").glob("*.json")}
        require(not files - set(cells), "results directory contains unapproved combinations")
        unindexed = sorted(files - set(summary))
        report["unindexed_result_files"] = unindexed
        if unindexed and not allow_partial:
            report["errors"].append("result files absent from summary: " + ", ".join(unindexed))
        ids = [row["run_id"] for row in summary.values()]
        require(len(ids) == len(set(ids)), "one run id is reused for different matrix combinations")
        cross = {}
        for key in sorted(summary):
            try:
                cell = cells[key]
                report["runs"][key] = review_run(archive, root, key, summary[key], cell, manifests[cell[0]], snapshots[cell[0]], cross)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                report["errors"].append(f"{key}: {exc}")
                report["runs"][key] = {"passed": False, "error": str(exc)}
        report["verified_combinations"] = sum(r["passed"] for r in report["runs"].values())
        complete = not report["missing_combinations"] and not unindexed and len(summary) == 54
        report["passed"] = complete and not report["errors"] and report["verified_combinations"] == 54
        report["status"] = "passed" if report["passed"] else ("failed" if report["errors"] else "partial")
        report["partial_review_accepted"] = allow_partial and report["status"] == "partial"
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report["errors"].append(str(exc))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, required=True, help="write the independent JSON report here")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--allow-partial", action="store_true", help="accept a clean partial review; passed remains false until 54/54")
    args = parser.parse_args(argv)
    report = verify_summary(args.summary, archive=Archive(args.data_dir), config_path=args.config, allow_partial=args.allow_partial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_bytes(encoded(report))
    temporary.replace(args.output)
    print(json.dumps({"status": report["status"], "passed": report["passed"],
                      "verified_combinations": report["verified_combinations"], "expected_combinations": 54,
                      "missing_combinations": len(report["missing_combinations"]), "errors": report["errors"],
                      "output": str(args.output)}))
    return 0 if report["passed"] or report.get("partial_review_accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
