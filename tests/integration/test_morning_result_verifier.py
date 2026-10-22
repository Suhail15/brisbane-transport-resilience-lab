"""Independent verifier tests use hand-built outputs, never engine evaluations."""
from copy import deepcopy
from datetime import datetime, timedelta
import importlib.util
import json
from pathlib import Path

import pytest

from resilience.contracts import JourneyRequest, TimetableSnapshot
from resilience.pipeline.analysis import canonical, persist_input, prepare_input
from resilience.pipeline.archive import Archive

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_morning_results.py"
spec = importlib.util.spec_from_file_location("morning_result_verifier", SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def connection(cid, trip, origin, destination, departure, arrival, *, mode="bus", route="bus1"):
    return {"connection_id": cid, "trip_instance_id": trip, "route_id": route, "mode": mode,
            "sequence": 0, "from_stop_id": origin, "to_stop_id": destination,
            "departure_s": departure, "arrival_s": arrival, "pickup_allowed": True,
            "drop_off_allowed": True, "provenance": "scheduled"}


def pattern(pid, trip, origin, destination):
    return {"pattern_id": pid, "route_id": "bus1", "direction_id": pid,
            "source_trip_instance_ids": [trip], "stops": [
                {"stop_id": origin, "arrival_offset_s": 0, "departure_offset_s": 0,
                 "pickup_allowed": True, "drop_off_allowed": True},
                {"stop_id": destination, "arrival_offset_s": 900, "departure_offset_s": 900,
                 "pickup_allowed": True, "drop_off_allowed": True}]}


def request(rid, departure=27005):
    return {"request_id": rid, "origin_stop_id": "a", "destination_stop_id": "d",
            "departure_s": departure, "od_weight": None}


def route(req, duration, legs=None):
    transit = sum(leg["kind"] == "transit" for leg in (legs or []))
    return {"request": req, "reachable": duration is not None,
            "arrival_s": req["departure_s"] + duration if duration is not None else None,
            "duration_s": duration, "boardings": transit, "transfers": max(0, transit - 1),
            "legs": legs or [], "quality": {}}


def all_unreachable_metrics():
    # These values are hand specified, independent of the verifier and engine.
    return {"request_count": 100, "reachability_horizon_s": 3600, "duration_cap_s": 5400,
            "baseline_reachable_count": 0, "disrupted_reachable_count": 0, "recovered_reachable_count": 0,
            "lost_count": 0, "restored_count": 0, "restored_fraction": None,
            "baseline_total_capped_duration_s": 540000, "disrupted_total_capped_duration_s": 540000,
            "recovered_total_capped_duration_s": 540000, "requests_with_missed_connections": 0,
            "missed_connection_count": 0}


@pytest.fixture
def frozen_archive(tmp_path):
    archive = Archive(tmp_path / "data")
    root = archive.root / "processed" / "morning-evaluation-v1"
    config = json.loads((SCRIPT.parents[1] / "configs/morning-evaluation.v1.json").read_bytes())
    journey = {"version": "pilot-od20-v1", "primary_weight": 1, "offset_seconds": [0, 900, 1800, 2700, 3600],
               "request_count": 100, "pairs": [{"pair_id": f"od{i:02d}", "origin_stop_id": f"a{i}",
                                               "destination_stop_id": f"b{i}"} for i in range(1, 21)]}
    journey_path = tmp_path / "journeys.json"
    write(journey_path, journey)
    config["journey_set"] = str(journey_path)
    config_path = tmp_path / "morning-config.json"
    write(config_path, config)
    plan = {"version": config["version"], "decision_snapshots": {date: f"snapshot{date[-2:]}" for date in verifier.DATES}}
    write(root / "decision-manifest.json", plan)
    write(root / "plan.json", {"plan": plan, "config": config, "plan_sha256": verifier.digest(plan),
                               "config_sha256": verifier.digest(config)})
    snapshots, manifests = {}, {}
    for date in verifier.DATES:
        cutoff = datetime.fromisoformat(f"{date}T07:30:05+10:00")
        receipt = archive.append("GTFS", b"synthetic test schedule", cutoff - timedelta(minutes=1),
                                 "https://example.invalid/synthetic")
        bus = connection("bus", "bus-trip", "3713", "18", 27100, 28000)
        rail = connection("rail", "rail-trip", "600188", "600016", 27100, 28000, mode="rail", route="rail1")
        back = connection("back", "back-trip", "18", "3713", 28500, 29400)
        data = {"metadata": {"snapshot_id": plan["decision_snapshots"][date], "snapshot_at": cutoff.isoformat(),
                             "service_date": date, "timezone": "Australia/Brisbane", "quality": {},
                             "sources": [{"record_id": receipt["record_id"], "source_kind": "gtfs",
                                          "received_at": receipt["received_at"], "sha256": receipt["sha256"],
                                          "source_ref": receipt["source_url"]}]},
                "stops": [{"stop_id": sid, "name": sid, "latitude": -27.5, "longitude": 153.0}
                          for sid in ("3713", "18", "600188", "600016")],
                "connections": [bus, rail, back], "walking_links": [],
                "recovery_pairs": [{"pair_id": "pair1", "outbound": pattern("out", "bus-trip", "3713", "18"),
                                    "inbound": pattern("back", "back-trip", "18", "3713")}]}
        snap = TimetableSnapshot.model_validate(data)
        snapshots[date] = snap.model_dump(mode="json")
        path = archive.root / "processed" / "snapshots" / f"{snap.metadata.snapshot_id}.json"
        write(path, snap)
        requests = [{"request_id": f"pilot-od20-v1:{p['pair_id']}:{off}", "origin_stop_id": p["origin_stop_id"],
                     "destination_stop_id": p["destination_stop_id"], "departure_s": 27005 + off, "od_weight": None}
                    for p in journey["pairs"] for off in verifier.OFFSETS]
        common = {"start_s": 27005, "end_s": 34205}
        scenarios = {
            "cancellation": dict(common, kind="trip_cancellation", scenario_id=f"morning:{date}:cancel", trip_instance_ids=["bus-trip"]),
            "stop_closure": dict(common, kind="stop_unavailable", scenario_id=f"morning:{date}:stop", stop_ids=["3713"]),
            "rail_corridor": dict(common, kind="corridor_closure", scenario_id=f"morning:{date}:rail",
                                  segments=[{"from_stop_id": "600188", "to_stop_id": "600016", "bidirectional": True}]),
            "bus_delay": dict(common, kind="additional_delay", scenario_id=f"morning:{date}:delay", trip_instance_ids=["bus-trip"], additional_seconds=1200),
        }
        manifest = {"date": date, "version": config["version"], "snapshot_id": snap.metadata.snapshot_id,
                    "snapshot_at": cutoff.isoformat(), "snapshot_content_sha256": verifier.file_hash(path),
                    "config_sha256": verifier.digest(config), "plan_sha256": verifier.digest(plan),
                    "journey_set_sha256": verifier.digest(journey), "request_set_sha256": verifier.digest(requests),
                    "source_record_ids": [receipt["record_id"]], "requests": requests, "scenarios": scenarios,
                    "targets": {"bus": bus, "rail": rail, "closed_stop_id": "3713"}, "unsupported_targets": [], "status": "prepared"}
        write(root / "targets" / f"{date}.json", manifest)
        manifests[date] = manifest
    summary = {}
    for number, (key, (date, scenario, budget, delta)) in enumerate(verifier.expected_combinations().items()):
        manifest = manifests[date]
        nominal = TimetableSnapshot.model_validate(snapshots[date])
        derived = None
        if delta:
            # Fixture events are tiny, so specify the approved transform explicitly.
            stress = deepcopy(snapshots[date])
            for c in stress["connections"]:
                if c["mode"] == "bus":
                    c["arrival_s"] += delta
            for pair in stress["recovery_pairs"]:
                for direction in ("outbound", "inbound"):
                    pair[direction]["stops"][-1]["arrival_offset_s"] += delta
                    pair[direction]["stops"][-1]["departure_offset_s"] += delta
            derived_hash = verifier.digest(stress)
            derived = {"method": "bus-running-time-proportional-v1", "delta_seconds": delta,
                       "nominal_snapshot_id": nominal.metadata.snapshot_id, "unsupported_trip_ids": [],
                       "snapshot_content_sha256": derived_hash, "path": f"derived-inputs/{derived_hash}.json"}
            write(archive.root / "processed" / derived["path"], stress)
        req = tuple(JourneyRequest.model_validate(r) for r in manifest["requests"])
        inp, meta = prepare_input(archive, nominal, req, (), (), budget, journey_set_version="pilot-od20-v1", delta=delta, derived=derived)
        inp["scenarios"] = [manifest["scenarios"][scenario]]
        meta = meta.model_copy(update={"input_sha256": verifier.digest(inp), "scenario_set_sha256": verifier.digest(inp["scenarios"])})
        run_id = f"run{number:02d}"
        persist_input(archive, run_id, inp, meta)
        objective = {"restored_count": 0, "total_capped_duration_s": 540000, "bus_hours": 0}
        routes = [route(r, None) for r in manifest["requests"]]
        impact = {"cancelled_trip_instance_ids": ["bus-trip"] if scenario == "cancellation" else ["rail-trip"] if scenario == "rail_corridor" else [],
                  "delayed_trip_instance_ids": ["bus-trip"] if scenario == "bus_delay" else [],
                  "unavailable_stop_ids": ["3713"] if scenario == "stop_closure" else []}
        result = {"budget_bus_hours": budget, "method": "greedy_bounded_swap", "optimality_proven": False,
                  "hypothetical": True, "considered_candidate_ids": [], "infeasible_candidate_ids": [],
                  "infeasible_candidates": [], "busiest_affected_pattern": None, "no_intervention": objective,
                  "plan": {"candidate_ids": [], "duties": [], "bus_count": 0, "bus_hours": 0, "objective": objective,
                           "evaluation": {"baseline": routes, "disrupted": routes, "recovered": routes,
                                          "metrics": all_unreachable_metrics(), "missed_connections": [], "impact": impact}}}
        run = {"run_id": run_id, "snapshot_id": manifest["snapshot_id"], "status": "completed", "error": None,
               "input": inp, "metadata": meta.model_dump(mode="json"), "result": result}
        for folder in ("run-results", "experiments"):
            write(archive.root / "processed" / folder / f"{run_id}.json", run)
        write(root / "results" / f"{key}.json", run)
        summary[key] = {"run_id": run_id, "input_sha256": meta.input_sha256, "status": "completed", "date": date,
                        "scenario": scenario, "budget_bus_hours": budget, "sensitivity_seconds": delta, "request_count": 100,
                        "error": None, "metrics": all_unreachable_metrics(), "objective": objective, "considered_candidate_ids": []}
    write(root / "summary.json", summary)
    return archive, root, config_path


def review(fixture, **kwargs):
    archive, root, config_path = fixture
    return verifier.verify_summary(root / "summary.json", archive=archive, config_path=config_path, **kwargs)


def alter_run(fixture, key, mutate, *, rewrite_input=False):
    archive, root, _ = fixture
    summary = verifier.read_json(root / "summary.json")
    row = summary[key]
    run = verifier.read_json(root / "results" / f"{key}.json")
    mutate(run)
    if rewrite_input:
        meta = run["metadata"]
        meta["input_sha256"] = verifier.digest(run["input"])
        for array, field in (("requests", "request_set_sha256"), ("scenarios", "scenario_set_sha256"), ("candidates", "candidate_set_sha256")):
            meta[field] = verifier.digest(run["input"][array])
        write(archive.root / "processed/run-inputs" / f"{run['run_id']}.input.json", run["input"])
        write(archive.root / "processed/run-inputs" / f"{run['run_id']}.metadata.json", meta)
        row["input_sha256"] = meta["input_sha256"]
    row["metrics"] = run["result"]["plan"]["evaluation"]["metrics"]
    row["objective"] = run["result"]["plan"]["objective"]
    row["considered_candidate_ids"] = run["result"]["considered_candidate_ids"]
    for path in (root / "results" / f"{key}.json", archive.root / "processed/run-results" / f"{run['run_id']}.json",
                 archive.root / "processed/experiments" / f"{run['run_id']}.json"):
        write(path, run)
    write(root / "summary.json", summary)


def test_full_matrix_is_verified_and_empty_benefits_remain_null(frozen_archive):
    report = review(frozen_archive)
    assert report["passed"] is True and report["status"] == "passed"
    assert report["verified_combinations"] == 54 and not report["errors"]
    assert all(r["metrics"]["restored_fraction"] is None for r in report["runs"].values())
    assert len(verifier.expected_combinations()) == 54


def test_partial_never_claims_final_pass(frozen_archive):
    _, root, _ = frozen_archive
    summary = verifier.read_json(root / "summary.json")
    missing = next(iter(summary))
    del summary[missing]
    write(root / "summary.json", summary)
    (root / "results" / f"{missing}.json").unlink()
    report = review(frozen_archive, allow_partial=True)
    assert report["status"] == "partial" and report["passed"] is False
    assert report["partial_review_accepted"] is True and report["verified_combinations"] == 53
    assert report["missing_combinations"] == [missing]
    assert not review(frozen_archive).get("partial_review_accepted")


@pytest.mark.parametrize("field", ["baseline_reachable_count", "lost_count", "restored_count",
                                  "recovered_total_capped_duration_s", "missed_connection_count"])
def test_coherent_summary_and_archive_metric_corruption_is_recomputed(frozen_archive, field):
    key = "2026-10-19.cancellation.b0.s0"
    def change(run):
        run["result"]["plan"]["evaluation"]["metrics"][field] += 1
    alter_run(frozen_archive, key, change)
    assert any("reported metrics differ" in error for error in review(frozen_archive)["errors"])


@pytest.mark.parametrize("field", ["objective", "no_intervention", "busiest_affected_pattern"])
def test_invalid_comparison_objective_is_rejected(frozen_archive, field):
    def change(run):
        target = run["result"]["plan"] if field == "objective" else run["result"]
        target[field] = {"restored_count": 1, "total_capped_duration_s": 540000, "bus_hours": 0 if field != "busiest_affected_pattern" else 2}
    alter_run(frozen_archive, "2026-10-19.cancellation.b2.s0", change)
    assert review(frozen_archive)["status"] == "failed"


def test_fixed_request_reordering_rejected_even_with_consistent_hashes(frozen_archive):
    def change(run):
        run["input"]["requests"] = list(reversed(run["input"]["requests"]))
    alter_run(frozen_archive, "2026-10-19.cancellation.b2.s0", change, rewrite_input=True)
    assert any("frozen ordered requests" in error for error in review(frozen_archive)["errors"])


def test_candidate_drift_across_budgets_rejected_with_consistent_hashes(frozen_archive):
    def change(run):
        run["input"]["candidates"] = [{"candidate_id": "new", "pair_id": "pair1", "activation_s": 27605,
                                        "duty_duration_s": 7200, "bus_hours": 2}]
        run["result"]["considered_candidate_ids"] = ["new"]
    alter_run(frozen_archive, "2026-10-19.cancellation.b2.s0", change, rewrite_input=True)
    assert any("nominal_candidates_including_stress" in error for error in review(frozen_archive)["errors"])


def test_stress_candidate_drift_rejected_with_consistent_hashes(frozen_archive):
    def change(run):
        run["input"]["candidates"] = [{"candidate_id": "new", "pair_id": "pair1", "activation_s": 27605,
                                        "duty_duration_s": 7200, "bus_hours": 2}]
        run["result"]["considered_candidate_ids"] = ["new"]
    alter_run(frozen_archive, "2026-10-19.stop_closure.b2.s300", change, rewrite_input=True)
    assert any("nominal_candidates_including_stress" in error for error in review(frozen_archive)["errors"])


def test_equal_metrics_do_not_hide_changed_disrupted_route_arrays(frozen_archive):
    def change(run):
        for name in ("disrupted", "recovered"):
            run["result"]["plan"]["evaluation"][name][0]["quality"] = {"warnings": ["changed"]}
    alter_run(frozen_archive, "2026-10-19.cancellation.b2.s0", change)
    assert any("shared disrupted differs" in error for error in review(frozen_archive)["errors"])


def test_summary_local_final_and_archive_must_agree(frozen_archive):
    _, root, _ = frozen_archive
    path = root / "results/2026-10-19.cancellation.b2.s0.json"
    run = verifier.read_json(path)
    run["result"]["plan"]["bus_hours"] = 2
    write(path, run)
    assert any("local final differs" in error for error in review(frozen_archive)["errors"])


def test_future_receipt_is_rejected_without_modifying_sources(frozen_archive):
    archive, root, _ = frozen_archive
    manifest = verifier.read_json(root / "targets/2026-10-19.json")
    with archive.connect() as db:
        db.execute("UPDATE receipts SET received_at=? WHERE record_id=?",
                   ("2026-10-19T00:00:00+00:00", manifest["source_record_ids"][0]))
    assert any("received time differs or exceeds" in error for error in review(frozen_archive)["errors"])


def test_unapproved_date_and_duplicate_run_id_are_rejected(frozen_archive):
    _, root, _ = frozen_archive
    summary = verifier.read_json(root / "summary.json")
    keys = list(summary)
    summary[keys[1]]["run_id"] = summary[keys[0]]["run_id"]
    write(root / "summary.json", summary)
    assert any("run id is reused" in error for error in review(frozen_archive)["errors"])
    summary["2026-10-22.cancellation.b0.s0"] = summary[keys[0]]
    write(root / "summary.json", summary)
    assert any("unapproved combinations" in error for error in review(frozen_archive)["errors"])


def test_metrics_boundaries_unreachable_cap_and_restoration_are_hand_calculated():
    requests = [request(str(i)) for i in range(5)]
    baseline = [route(r, d) for r, d in zip(requests, [3600, 3601, 6000, None, 3000])]
    disrupted = [route(r, d) for r, d in zip(requests, [None, 3600, 5500, None, 3601])]
    recovered = [route(r, d) for r, d in zip(requests, [3600, 3700, 6000, None, 3600])]
    metrics, misses = verifier.recompute_metrics({"baseline": baseline, "disrupted": disrupted, "recovered": recovered}, requests, {})
    assert metrics == {"request_count": 5, "reachability_horizon_s": 3600, "duration_cap_s": 5400,
                       "baseline_reachable_count": 2, "disrupted_reachable_count": 1, "recovered_reachable_count": 2,
                       "lost_count": 2, "restored_count": 2, "restored_fraction": 1.0,
                       "baseline_total_capped_duration_s": 21001, "disrupted_total_capped_duration_s": 23401,
                       "recovered_total_capped_duration_s": 21700, "requests_with_missed_connections": 0,
                       "missed_connection_count": 0}
    assert misses == []
    baseline[0]["duration_s"] -= 1
    with pytest.raises(verifier.VerificationError, match="duration/arrival"):
        verifier.recompute_metrics({"baseline": baseline, "disrupted": disrupted, "recovered": recovered}, requests, {})


def test_missed_connection_uses_actual_walk_and_excludes_unavailable_service():
    req = request("miss", departure=0)
    previous = {"kind": "transit", "trip_instance_id": "one", "connection_ids": ["one"], "to_stop_id": "x"}
    following = {"kind": "transit", "trip_instance_id": "two", "connection_ids": ["two"], "from_stop_id": "y"}
    legs = [previous, {"kind": "walk", "departure_s": 100, "arrival_s": 140}, following]
    journey = route(req, 900, legs)
    ev = {"baseline": [journey], "disrupted": [journey], "recovered": [journey]}
    connections = {"one": {"arrival_s": 400, "drop_off_allowed": True},
                   "two": {"departure_s": 739, "pickup_allowed": True}}
    metrics, misses = verifier.recompute_metrics(ev, [req], connections)
    assert metrics["missed_connection_count"] == metrics["requests_with_missed_connections"] == 1
    assert misses[0]["earliest_boarding_s"] == 740
    connections["two"]["departure_s"] = 740
    assert verifier.recompute_metrics(ev, [req], connections)[0]["missed_connection_count"] == 0
    connections["two"]["departure_s"] = 739
    connections["two"]["pickup_allowed"] = False
    assert verifier.recompute_metrics(ev, [req], connections)[0]["missed_connection_count"] == 0
    del connections["two"]
    assert verifier.recompute_metrics(ev, [req], connections)[0]["missed_connection_count"] == 0


def test_independent_duty_counts_complete_cycles_and_rejects_resource_changes(frozen_archive):
    archive, root, _ = frozen_archive
    manifest = verifier.read_json(root / "targets/2026-10-19.json")
    snapshot = verifier.read_json(archive.root / "processed/snapshots" / f"{manifest['snapshot_id']}.json")
    candidate = {"candidate_id": "test", "pair_id": "pair1", "activation_s": 27605, "duty_duration_s": 7200, "bus_hours": 2}
    duty, additions = verifier.independent_duty(candidate, snapshot)
    assert duty["cycle_count"] == 3  # 900 + 300 + 900 + 300 = 2400 seconds.
    assert duty["duty_end_s"] == 34805 and len(duty["trip_instance_ids"]) == len(additions) == 6
    assert additions[-1]["arrival_s"] == 34505  # Final 300-second turn completes at duty end.
    for field, value in (("activation_s", 27604), ("bus_hours", 1), ("duty_duration_s", 7199)):
        with pytest.raises(verifier.VerificationError, match="cost/duration/activation"):
            verifier.independent_duty(dict(candidate, **{field: value}), snapshot)


def test_selected_bus_count_budget_and_duty_corruption_are_rejected(frozen_archive):
    archive, root, _ = frozen_archive
    manifest = verifier.read_json(root / "targets/2026-10-19.json")
    snapshot = verifier.read_json(archive.root / "processed/snapshots" / f"{manifest['snapshot_id']}.json")
    candidate = {"candidate_id": "test", "pair_id": "pair1", "activation_s": 27605, "duty_duration_s": 7200, "bus_hours": 2}
    duty, _ = verifier.independent_duty(candidate, snapshot)
    ev = {"baseline": [], "disrupted": [], "recovered": []}
    metrics = {"restored_count": 1, "recovered_total_capped_duration_s": 100, "disrupted_total_capped_duration_s": 200}
    result = {"budget_bus_hours": 2, "method": "greedy_bounded_swap", "optimality_proven": False, "hypothetical": True,
              "considered_candidate_ids": ["test"], "infeasible_candidate_ids": [], "infeasible_candidates": [],
              "no_intervention": {"restored_count": 0, "total_capped_duration_s": 200, "bus_hours": 0},
              "busiest_affected_pattern": None, "plan": {"candidate_ids": ["test"], "bus_count": 1, "bus_hours": 2,
                  "duties": [duty], "objective": {"restored_count": 1, "total_capped_duration_s": 100, "bus_hours": 2}}}
    inp = {"budget_bus_hours": 2, "candidates": [candidate], "scenarios": [manifest["scenarios"]["stop_closure"]]}
    verifier.verify_plan(result, inp, snapshot, metrics, ev)
    result["plan"]["duties"][0]["cycle_count"] -= 1
    with pytest.raises(verifier.VerificationError, match="duty cycles/end"):
        verifier.verify_plan(result, inp, snapshot, metrics, ev)
    result["plan"]["duties"][0]["cycle_count"] += 1
    inp["budget_bus_hours"] = result["budget_bus_hours"] = 0
    with pytest.raises(verifier.VerificationError, match="resource count/cost"):
        verifier.verify_plan(result, inp, snapshot, metrics, ev)


def test_cli_partial_exit_is_honest_and_strict_missing_matrix_fails(frozen_archive, tmp_path):
    archive, root, config = frozen_archive
    write(root / "summary.json", {})
    for path in (root / "results").glob("*.json"):
        path.unlink()
    output = tmp_path / "report.json"
    args = ["--summary", str(root / "summary.json"), "--output", str(output), "--data-dir", str(archive.root), "--config", str(config)]
    assert verifier.main(args + ["--allow-partial"]) == 0
    assert verifier.read_json(output)["passed"] is False
    assert verifier.main(args) == 1
