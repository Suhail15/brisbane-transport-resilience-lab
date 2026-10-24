"""Independent checker fixtures are hand-built; no producer/engine metric calls."""
from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("case_study_verifier", REPO / "scripts/verify_case_study.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
DAY = "2026-10-09"
VERSION = "corridor-impact-staggered-v1"


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def checksum(value):
    return hashlib.sha256(raw(value)).hexdigest()


def write(path, value, *, signed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw(value))
    if signed:
        write(path.with_suffix(".sha256.json"), {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def empty_metrics(count):
    # Every unavailable query has a declared cost of 5,400 seconds, not zero.
    return {"request_count": count, "baseline_within60_count": 0, "disrupted_within60_count": 0,
            "recovered_within60_count": 0, "lost_count": 0, "restored_count": 0, "restored_fraction": None,
            "baseline_total_capped_duration_s": 5400 * count, "disrupted_total_capped_duration_s": 5400 * count,
            "total_capped_duration_s": 5400 * count, "added_capped_duration_s": 0,
            "saved_capped_duration_s": 0, "improved_count": 0, "used_bus_hours": 0,
            "saved_query_minutes_per_bus_hour": None, "decomposition": {
                "nominal_impacted": {"count": 0, "saved_capped_duration_s": 0, "improved_count": 0},
                "not_nominal_impacted": {"count": count, "saved_capped_duration_s": 0, "improved_count": 0},
                "arrival_after_closure": {"count": 0, "saved_capped_duration_s": 0, "improved_count": 0},
                "arrival_by_closure_or_unavailable": {"count": count, "saved_capped_duration_s": 0, "improved_count": 0}}}


def unavailable(req):
    return {"request": req, "reachable": False, "arrival_s": None, "duration_s": None,
            "boardings": 0, "transfers": 0, "legs": [], "quality": {"realtime_status": "missing"}}


def unavailable_row(req):
    return {**req, "baseline_duration_s": None, "disrupted_duration_s": None, "recovered_duration_s": None,
            "baseline_capped_duration_s": 5400, "disrupted_capped_duration_s": 5400, "recovered_capped_duration_s": 5400,
            "baseline_within60": False, "disrupted_within60": False, "recovered_within60": False,
            "nominal_impacted": False, "saved_capped_duration_s": 0, "improved": False,
            "recovered_arrival_after_closure": False}


def input_identity(result):
    return checksum({**{k: result[k] for k in ("manifest_sha256", "selection_sha256", "budget_bus_hours",
                                           "additional_bus_seconds", "derived_snapshot_sha256", "code_sha256")},
                     "scoring_sha256": checksum(result["scoring"])})


@pytest.fixture
def frozen_study(tmp_path):
    repo = tmp_path / "repo"
    data, study = repo / "data", repo / "data/processed/corridor-impact-v1"
    config = json.loads((REPO / "configs/corridor-impact.v1.json").read_bytes())
    control_config = json.loads((REPO / "configs/journey-set.v1.json").read_bytes())
    write(repo / "configs/corridor-impact.v1.json", config)
    write(repo / config["control_journey_set"], control_config)
    code = ["services/resilience/contracts.py", "scripts/run_case_study.py", "services/resilience/engine/__init__.py",
            *["services/resilience/pipeline/" + name for name in
              ("case_study.py", "analysis.py", "sensitivity.py", "files.py", "integrity.py")]]
    for relative in code:
        p = repo / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Synthetic checker fixture; no producer implementation.\n")
    frozen_files = {}
    for index in range(530):
        relative = f"preserved/{index}.txt"
        p = repo / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(index))
        frozen_files[relative] = hashlib.sha256(p.read_bytes()).hexdigest()
    preservation = repo / verifier.DEFAULT_PRESERVATION
    write(preservation, {"scope": "synthetic 530-file fixture", "files": frozen_files})
    protocol = {"config": config, "config_sha256": hashlib.sha256((repo / "configs/corridor-impact.v1.json").read_bytes()).hexdigest(),
                "config_canonical_sha256": checksum(config), "selection_version": VERSION,
                "candidate_selection_version": VERSION, "scoring_version": "whole-source-trips-capped-horizon-v1",
                "code_sha256": verifier.code_hash(repo),
                "control_config_sha256": hashlib.sha256((repo / config["control_journey_set"]).read_bytes()).hexdigest()}
    write(study / "protocol.json", protocol)
    primary = []
    for origin_station in config["primary_station_platforms"]:
        for destination_station in config["primary_station_platforms"]:
            if origin_station["station"] == destination_station["station"]:
                continue
            for origin in origin_station["stop_ids"]:
                for destination in destination_station["stop_ids"]:
                    for offset in (0, 900, 1800, 2700, 3600):
                        primary.append({"request_id": f"{VERSION}:{origin}:{destination}:{offset}", "origin_stop_id": origin,
                                        "destination_stop_id": destination, "departure_s": 27005 + offset, "od_weight": None})
    controls = [{"request_id": f"pilot-od20-v1:{pair['pair_id']}:{offset}", "origin_stop_id": pair["origin_stop_id"],
                 "destination_stop_id": pair["destination_stop_id"], "departure_s": 27005 + offset, "od_weight": None}
                for pair in control_config["pairs"] for offset in (0, 900, 1800, 2700, 3600)]
    cutoff = datetime.fromisoformat(DAY + "T07:30:05+10:00")
    payload = b"Synthetic source identity fixture, not a real GTFS feed"
    source_hash = hashlib.sha256(payload).hexdigest()
    receipt = {"record_id": "synthetic-receipt", "feed": "GTFS", "received_at": (cutoff - timedelta(minutes=1)).astimezone(__import__("datetime").timezone.utc).isoformat(),
               "event_at": None, "sha256": source_hash, "gtfs_sha256": None, "source_url": "https://example.invalid/synthetic",
               "object_path": f"raw/objects/{source_hash}.gz", "status": "valid", "details": "{}"}
    object_path = data / receipt["object_path"]
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(gzip.compress(payload, mtime=0))
    (data / "runtime").mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data / "runtime/archive.sqlite") as db:
        db.execute("CREATE TABLE receipts (record_id TEXT,feed TEXT,received_at TEXT,event_at TEXT,sha256 TEXT,gtfs_sha256 TEXT,source_url TEXT,object_path TEXT,status TEXT,details TEXT)")
        db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(receipt.values()))
    source = {"record_id": receipt["record_id"], "source_kind": "gtfs", "received_at": receipt["received_at"],
              "event_at": None, "sha256": source_hash, "source_ref": receipt["source_url"]}
    stop_names = {"600052": "Fairfield station, platform 1", "600194": "Fairfield station, platform 2",
                  "600006": "South Bank station, platform 1", "600188": "South Bank station, platform 2",
                  "600033": "Roma Street station, platform 3", "600036": "Roma Street station, platform 4",
                  "600018": "Central station, platform 1", "600017": "Central station, platform 2",
                  "600051": "Dutton Park station, platform 1", "600012": "South Brisbane station, platform 1"}
    snapshot = {"metadata": {"snapshot_id": "synthetic-snapshot", "snapshot_at": cutoff.isoformat(), "service_date": DAY,
                              "timezone": "Australia/Brisbane", "sources": [source], "quality": {"realtime_status": "missing"}},
                "stops": [{"stop_id": sid, "name": name, "latitude": -27.5, "longitude": 153.0} for sid, name in stop_names.items()],
                "connections": [{"connection_id": "rail", "trip_instance_id": "train", "route_id": "rail1", "mode": "rail", "sequence": 0,
                                 "from_stop_id": "600052", "to_stop_id": "600018", "departure_s": 27105, "arrival_s": 27505,
                                 "pickup_allowed": True, "drop_off_allowed": True, "provenance": "scheduled"}],
                "walking_links": [], "recovery_pairs": []}
    write(study / "snapshots" / (DAY + ".json"), snapshot)
    scenario = {"scenario_id": VERSION + ":rail-section", "kind": "corridor_closure", "start_s": 27005, "end_s": 34205,
                "segments": [{"from_stop_id": "600052", "to_stop_id": "600018", "bidirectional": False}]}
    manifest = {"date": DAY, "role": "development", "snapshot_id": "synthetic-snapshot", "snapshot_sha256": checksum(snapshot),
                "protocol_sha256": checksum(protocol), "sources": [{**source, "receipt": receipt}], "primary": primary, "controls": controls,
                "scenarios": [scenario], "primary_sha256": checksum(primary), "control_sha256": checksum(controls), "scenario_sha256": checksum([scenario])}
    write(study / "inputs" / (DAY + ".json"), manifest, signed=True)
    selection = {"manifest_sha256": checksum(manifest), "selection_version": VERSION, "candidate_selection_version": VERSION,
                 "candidates": [], "candidate_sha256": checksum([]), "nominal_impacted_request_ids": [], "frequency_ranking": []}
    write(study / "selections" / (DAY + ".json"), selection, signed=True)
    policies = {}
    for name in ("no_action", "simple_frequency", "best_evaluated"):
        policy = {"candidate_ids": [], "duties": [], "full": empty_metrics(240), "impacted": empty_metrics(0),
                  "scoring_objective": {"restored_count": 0, "total_capped_duration_s": 1296000, "bus_hours": 0},
                  "controls": empty_metrics(100), "queries": [unavailable_row(r) for r in primary],
                  "control_queries": [unavailable_row(r) for r in controls]}
        for kind in ("baseline", "disrupted", "recovered"):
            policy[kind + "_routes"] = [unavailable(r) for r in primary]
            policy["control_" + kind + "_routes"] = [unavailable(r) for r in controls]
        policies[name] = policy
    for budget, delta in ((0, 0), (2, 0), (4, 0), (8, 0), (2, 300), (2, 600)):
        transform = {"method": "bus-running-time-proportional-v1", "delta_seconds": delta, "unsupported_trip_ids": []}
        if delta:
            transform.update(nominal_snapshot_id="synthetic-snapshot", classification="hypothetical running-time sensitivity; not observed delay")
        result = {"date": DAY, "budget_bus_hours": budget, "additional_bus_seconds": delta, "manifest_sha256": checksum(manifest),
                  "selection_sha256": checksum(selection), "code_sha256": protocol["code_sha256"], "candidate_selection_version": VERSION,
                  "derived_snapshot_sha256": checksum(snapshot), "transform": transform, "policies": deepcopy(policies),
                  "scoring": {"version": "whole-source-trips-capped-horizon-v1", "cutoff_s": 36005,
                              "full_snapshot_sha256": checksum(snapshot), "scoring_snapshot_sha256": checksum(snapshot),
                              "full_connection_count": 1, "scoring_connection_count": 1, "retained_trip_ids": ["train"],
                              "retained_trip_ids_sha256": checksum(["train"]), "candidate_source_witnesses": [], "scenario_segment_witnesses": []},
                  "simple_policy_rejections": [], "infeasible_candidates": [], "search_evaluated_plan_count": 1,
                  "comparison_evaluated_plan_count": 1,
                  "best_evaluated_scope": "Best lexicographic objective among unchanged bounded search, independently scored simple frequency plan and no action",
                  "optimality_proven": False}
        result["input_sha256"] = input_identity(result)
        write(study / "cells" / f"{DAY}-b{budget}-d{delta}.json", {"result": result, "calculation_elapsed_seconds": 0.1}, signed=True)
    return {"repo": repo, "data": data, "study": study, "manifest": manifest, "snapshot": snapshot}


def review(fixture, **kwargs):
    return verifier.verify_study(fixture["study"], repo=fixture["repo"], data_dir=fixture["data"], dates=[DAY],
                                config_path=fixture["repo"] / "configs/corridor-impact.v1.json", **kwargs)


def mutate_cell(fixture, mutate, budget=2, delta=0):
    path = fixture["study"] / "cells" / f"{DAY}-b{budget}-d{delta}.json"
    doc = json.loads(path.read_bytes())
    mutate(doc["result"])
    write(path, doc, signed=True)


def test_complete_handwritten_null_matrix(frozen_study):
    report = review(frozen_study)
    assert report["passed"], report["errors"]
    assert report["status"] == "complete" and report["verified_cell_count"] == 6
    assert report["preservation"]["file_count"] == 530
    assert all(c["primary"]["request_count"] == 240 and c["controls"]["request_count"] == 100 for c in report["cells"].values())
    assert all(c["primary"]["restored_fraction"] is None and c["primary"]["saved_query_minutes_per_bus_hour"] is None for c in report["cells"].values())


@pytest.mark.parametrize("mutate,expected", [
    (lambda r: r["policies"]["best_evaluated"]["full"].update(saved_capped_duration_s=1), "independent arithmetic"),
    (lambda r: r["policies"]["best_evaluated"]["full"].update(request_count=340), "independent arithmetic"),
    (lambda r: r["policies"]["best_evaluated"]["controls"].update(request_count=240), "independent arithmetic"),
    (lambda r: r["policies"]["best_evaluated"]["impacted"].update(request_count=1), "impacted arithmetic"),
    (lambda r: r["policies"]["best_evaluated"]["full"].update(restored_fraction=0), "independent arithmetic"),
    (lambda r: r["policies"]["best_evaluated"]["full"].update(used_bus_hours=2), "independent arithmetic"),
    (lambda r: r["policies"]["best_evaluated"]["full"].update(improved_count=False), "independent arithmetic"),
    (lambda r: r.update(budget_bus_hours=8), "cell budget_bus_hours"),
    (lambda r: r.update(date="2026-10-22"), "cell date"),
    (lambda r: r.update(additional_bus_seconds=300), "cell additional_bus_seconds"),
    (lambda r: r.update(input_sha256="altered"), "normalized cell input hash"),
    (lambda r: r["scoring"].update(cutoff_s=36004), "scoring retention proof"),
    (lambda r: r["scoring"].update(retained_trip_ids=[]), "scoring retention proof"),
    (lambda r: r["policies"]["best_evaluated"].update(candidate_ids=["fabricated-duty"]), "selection exceeds budget or is infeasible"),
    (lambda r: r["policies"]["best_evaluated"]["recovered_routes"].pop(), "ordered route requests"),
    (lambda r: r["policies"]["best_evaluated"]["queries"][0].update(nominal_impacted=True), "paired query rows"),
])
def test_resigned_result_corruption_still_fails(frozen_study, mutate, expected):
    mutate_cell(frozen_study, mutate)
    report = review(frozen_study)
    assert not report["passed"]
    assert any(expected in error for error in report["errors"]), report["errors"]


def test_original_byte_corruption_fails(frozen_study):
    (frozen_study["repo"] / "preserved/7.txt").write_text("changed")
    report = review(frozen_study)
    assert not report["passed"] and "original frozen file changed" in report["errors"][0]


def test_snapshot_tampering_fails(frozen_study):
    path = frozen_study["study"] / "snapshots" / (DAY + ".json")
    snapshot = json.loads(path.read_bytes())
    snapshot["connections"][0]["arrival_s"] += 1
    write(path, snapshot)
    report = review(frozen_study)
    assert not report["passed"] and any("snapshot exact-byte hash" in error for error in report["errors"])


def test_primary_denominator_not_silently_dropped(frozen_study):
    path = frozen_study["study"] / "inputs" / (DAY + ".json")
    manifest = json.loads(path.read_bytes())
    manifest["primary"].pop()
    manifest["primary_sha256"] = checksum(manifest["primary"])
    write(path, manifest, signed=True)
    report = review(frozen_study)
    assert not report["passed"] and any("fixed ordered primary" in error for error in report["errors"])


def test_resigned_snapshot_cannot_cancel_source_buses(frozen_study):
    snapshot = deepcopy(frozen_study["snapshot"])
    snapshot["connections"].append({**snapshot["connections"][0], "connection_id": "bus", "trip_instance_id": "bus", "mode": "bus"})
    write(frozen_study["study"] / "snapshots" / (DAY + ".json"), snapshot)
    manifest = deepcopy(frozen_study["manifest"])
    manifest["snapshot_sha256"] = checksum(snapshot)
    write(frozen_study["study"] / "inputs" / (DAY + ".json"), manifest, signed=True)
    report = review(frozen_study)
    assert not report["passed"] and any("rail-only source trips" in error for error in report["errors"])


def test_future_source_receipt_rejected_even_when_resigned(frozen_study):
    snapshot, manifest = deepcopy(frozen_study["snapshot"]), deepcopy(frozen_study["manifest"])
    future = "2026-10-08T21:30:06+00:00"
    snapshot["metadata"]["sources"][0]["received_at"] = future
    manifest["sources"][0]["received_at"] = future
    manifest["sources"][0]["receipt"]["received_at"] = future
    with sqlite3.connect(frozen_study["data"] / "runtime/archive.sqlite") as db:
        db.execute("UPDATE receipts SET received_at=?", (future,))
    write(frozen_study["study"] / "snapshots" / (DAY + ".json"), snapshot)
    manifest["snapshot_sha256"] = checksum(snapshot)
    write(frozen_study["study"] / "inputs" / (DAY + ".json"), manifest, signed=True)
    report = review(frozen_study)
    assert not report["passed"] and any("exceeds cutoff" in error for error in report["errors"])


def test_missing_cells_are_explicit(frozen_study):
    (frozen_study["study"] / "cells" / f"{DAY}-b2-d600.json").unlink()
    strict = review(frozen_study)
    assert not strict["passed"] and strict["missing_cells"] == [f"{DAY}-b2-d600"]
    partial = review(frozen_study, allow_partial=True)
    assert partial["passed"] and partial["status"] == "partial" and partial["verified_cell_count"] == 5


def test_unregistered_cell_rejected(frozen_study):
    write(frozen_study["study"] / "cells" / f"{DAY}-b6-d0.json", {})
    assert any("unregistered cell" in error for error in review(frozen_study)["errors"])


def test_hand_calculated_lost_restored_delay_and_efficiency():
    # B=1,800/2,400/unavailable; D=4,000/2,500/unavailable;
    # R=3,000/2,000/unavailable. Only query 1 is lost and restored.
    requests = [{"request_id": str(i), "origin_stop_id": "a", "destination_stop_id": "b", "departure_s": 27005, "od_weight": None} for i in range(3)]
    def values(durations):
        return [{"request": req, "reachable": d is not None, "duration_s": d,
                 "arrival_s": 27005 + d if d is not None else None} for req, d in zip(requests, durations)]
    rows = verifier.rows_from_routes(values([1800, 2400, None]), values([4000, 2500, None]), values([3000, 2000, None]), {"0", "1"}, 30000)
    actual = verifier.arithmetic(rows, 2)
    assert actual["request_count"] == 3 and actual["baseline_within60_count"] == 2
    assert actual["disrupted_within60_count"] == 1 and actual["recovered_within60_count"] == 2
    assert actual["lost_count"] == actual["restored_count"] == 1 and actual["restored_fraction"] == 1.0
    assert actual["baseline_total_capped_duration_s"] == 9600
    assert actual["disrupted_total_capped_duration_s"] == 11900 and actual["total_capped_duration_s"] == 10400
    assert actual["added_capped_duration_s"] == 2300 and actual["saved_capped_duration_s"] == 1500
    assert actual["improved_count"] == 2 and actual["saved_query_minutes_per_bus_hour"] == 12.5
    assert actual["decomposition"]["nominal_impacted"]["saved_capped_duration_s"] == 1500
    assert actual["decomposition"]["arrival_after_closure"] == {"count": 1, "saved_capped_duration_s": 1000, "improved_count": 1}


def test_duration_cap_and_signed_negative_values():
    rows = [{"request_id": "q", "baseline_within60": False, "disrupted_within60": False, "recovered_within60": False,
             "baseline_capped_duration_s": 5400, "disrupted_capped_duration_s": 5300, "recovered_capped_duration_s": 5400,
             "nominal_impacted": False, "recovered_arrival_after_closure": True}]
    actual = verifier.arithmetic(rows, 2)
    assert actual["added_capped_duration_s"] == actual["saved_capped_duration_s"] == -100
    assert actual["saved_query_minutes_per_bus_hour"] == -100 / 120
    assert verifier.cost({"duration_s": 9000}) == verifier.cost({"duration_s": None}) == 5400


def test_complete_cycle_requires_both_terminal_turns():
    def pattern(origin, destination):
        return {"route_id": "bus", "stops": [{"stop_id": origin, "arrival_offset_s": 0, "departure_offset_s": 0,
                "pickup_allowed": True, "drop_off_allowed": True}, {"stop_id": destination, "arrival_offset_s": 900,
                "departure_offset_s": 900, "pickup_allowed": True, "drop_off_allowed": True}]}
    snapshot = {"recovery_pairs": [{"pair_id": "pair", "outbound": pattern("a", "b"), "inbound": pattern("b", "a")}]}
    candidate = {"candidate_id": "c", "pair_id": "pair", "activation_s": 27605, "duty_duration_s": 7200, "bus_hours": 2}
    duty, additions = verifier.duty(candidate, snapshot)
    assert duty["cycle_count"] == 3 and duty["duty_end_s"] == 34805 and len(additions) == 6
    assert additions[0]["departure_s"] == 27605 and additions[0]["arrival_s"] == 28505
    assert additions[1]["departure_s"] == 28805 and additions[1]["arrival_s"] == 29705
    assert additions[-1]["arrival_s"] + 300 == duty["duty_end_s"]
    with pytest.raises(verifier.VerificationError, match="cost/duration"):
        verifier.duty({**candidate, "bus_hours": 1}, snapshot)
    snapshot["recovery_pairs"][0]["outbound"]["stops"][-1].update(arrival_offset_s=3600, departure_offset_s=3600)
    snapshot["recovery_pairs"][0]["inbound"]["stops"][-1].update(arrival_offset_s=3600, departure_offset_s=3600)
    with pytest.raises(verifier.VerificationError, match="complete round trip"):
        verifier.duty(candidate, snapshot)


def test_whole_trip_scoring_matches_all_small_fixture_subsets_and_ties():
    """Actual unchanged engine; no producer pruning or summary helper is used."""
    from itertools import combinations
    from resilience.contracts import CorridorClosure, CorridorSegment, RecoveryCandidate, TimetableSnapshot
    from resilience.engine import exhaustive_recovery, plan_recovery
    from resilience.engine.recovery import _Search, _plan_key
    from tests.engine.fixtures import connection, paired_pattern, request, snapshot, walk

    pair, sources = paired_pattern("p", "A", "B", 600, 600)
    # Candidate source witnesses are deliberately beyond the 6,300s global cap.
    sources = (sources[0].model_copy(update={"departure_s": 10000, "arrival_s": 10600}),
               sources[1].model_copy(update={"departure_s": 12000, "arrival_s": 12600}))
    connections = (*sources,
        connection("rail-first", "RA", "RB", 100, 500, mode="rail"),
        connection("rail-second", "RA", "RB", 1000, 1400, mode="rail"),
        connection("sixty", "C", "D", 900, 4500),
        connection("at-cap", "X", "Y", 6300, 6300),
        connection("over-cap", "Z", "W", 6301, 6302),
        connection("unrelated-late", "L", "M", 20000, 20500),
        connection("late-rail-witness", "RZ", "RW", 20000, 20100, mode="rail"),
        connection("whole", "P", "Q", 5000, 5100),
        connection("whole", "Q", "R", 7000, 7100, sequence=1))
    full = snapshot(connections, walks=(walk("RA", "A"), walk("B", "RB")), pairs=(pair,), stops=("U", "V"))
    queries = (request("RA", "RB", 0, request_id="first"), request("RA", "RB", 900, request_id="later"),
               request("C", "D", 900, request_id="exact60"), request("X", "Y", 900, request_id="exact90"),
               request("Z", "W", 900, request_id="over90"), request("U", "V", 900, request_id="unavailable"))
    scenario = CorridorClosure(scenario_id="rail", start_s=0, end_s=7200, segments=(
        CorridorSegment(from_stop_id="RA", to_stop_id="RB", bidirectional=False),
        CorridorSegment(from_stop_id="RZ", to_stop_id="RW", bidirectional=False)))
    candidates = tuple(RecoveryCandidate(candidate_id=cid, pair_id="p", activation_s=activation)
                       for cid, activation in (("a", 600), ("b", 600), ("c", 1500), ("d", 2400)))
    scoring, proof = verifier.scoring_snapshot(full.model_dump(mode="json"), [r.model_dump(mode="json") for r in queries],
        [c.model_dump(mode="json") for c in candidates], scenario.model_dump(mode="json"))
    scored = TimetableSnapshot.model_validate(scoring)
    assert proof["cutoff_s"] == 6300
    assert "over-cap" not in proof["retained_trip_ids"] and "unrelated-late" not in proof["retained_trip_ids"]
    assert "whole" in proof["retained_trip_ids"] and any(c["trip_instance_id"] == "whole" and c["departure_s"] == 7000 for c in scoring["connections"])
    assert len(proof["candidate_source_witnesses"]) == 2
    assert proof["scenario_segment_witnesses"] == [{"from_stop_id": "RZ", "to_stop_id": "RW", "bidirectional": False,
                                                     "trip_instance_id": "late-rail-witness"}]
    full_search, scored_search = _Search(full, queries, (scenario,), candidates, 8), _Search(scored, queries, (scenario,), candidates, 8)
    checked = 0
    for count in range(5):
        for ids in combinations(("a", "b", "c", "d"), count):
            full_plan, scored_plan = full_search.evaluate(ids), scored_search.evaluate(ids)
            assert _plan_key(full_plan) == _plan_key(scored_plan)
            assert full_plan.objective == scored_plan.objective and full_plan.duties == scored_plan.duties
            checked += 1
    assert checked == 16
    # Beyond-cap raw routes differ; only original full routes are publishable.
    full_over = next(r for r in full_search.evaluate(()).evaluation.recovered if r.request.request_id == "over90")
    scored_over = next(r for r in scored_search.evaluate(()).evaluation.recovered if r.request.request_id == "over90")
    assert full_over.duration_s == 5402 and scored_over.duration_s is None
    for budget, expected in ((0, ()), (2, ("a",)), (4, ("a", "c")), (8, ("a", "c"))):
        original = exhaustive_recovery(full, queries, (scenario,), candidates, budget)
        pruned = exhaustive_recovery(scored, queries, (scenario,), candidates, budget)
        bounded = plan_recovery(scored, queries, (scenario,), candidates, budget)
        assert original.plan.candidate_ids == pruned.plan.candidate_ids == bounded.plan.candidate_ids == expected
        assert original.plan.objective == pruned.plan.objective == bounded.plan.objective


def test_source_closure_cancels_whole_trip_and_half_open_window():
    c = lambda cid, trip, a, b, d, r: {"connection_id": cid, "trip_instance_id": trip,
                                      "from_stop_id": a, "to_stop_id": b, "departure_s": d, "arrival_s": r}
    connections = [c("outside", "affected", "x", "a", 10, 20), c("crossing", "affected", "a", "b", 100, 120),
                   c("at-end", "retained", "a", "b", 200, 200), c("before-start", "retained2", "a", "b", 90, 100)]
    scenario = {"start_s": 100, "end_s": 200, "segments": [{"from_stop_id": "a", "to_stop_id": "b", "bidirectional": False}]}
    retained, cancelled = verifier.restricted(connections, scenario)
    assert cancelled == {"affected"} and [c["connection_id"] for c in retained] == ["at-end", "before-start"]


def test_json_duplicate_keys_and_nonfinite_are_rejected(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"lost":1,"lost":2}')
    with pytest.raises(verifier.VerificationError, match="duplicate JSON"):
        verifier.read_json(path)
    path.write_text('{"diagnostic":NaN}')
    with pytest.raises(verifier.VerificationError, match="nonfinite"):
        verifier.read_json(path)


def test_v2_network_artifact_binding_is_independently_reconstructed(frozen_study):
    repo, study = frozen_study["repo"], frozen_study["study"]
    for relative in ("configs/pilot.json", "configs/station-access-network.v1.json"):
        (repo / relative).write_bytes((REPO / relative).read_bytes())
    spec = json.loads((repo / "configs/station-access-network.v1.json").read_bytes())
    base = json.loads((repo / "configs/pilot.json").read_bytes())
    config_hash = hashlib.sha256((repo / "configs/station-access-network.v1.json").read_bytes()).hexdigest()
    pilot = {**base, "version": 2, "network_version": spec["network_version"], "network_config_sha256": config_hash,
             "route_short_names": spec["expanded_route_short_names"],
             "bus_seed_stop_ids": sorted(set(base["bus_seed_stop_ids"]) | set(spec["catchment_bus_stop_ids"])),
             "selection_rule": spec["selection_rule"]}
    write(study / "network/pilot.json", pilot)
    (study / "network/source-audit.json").write_bytes((repo / "configs/station-access-network.v1.json").read_bytes())
    network = {"network_version": spec["network_version"], "pilot_path": "network/pilot.json", "pilot_sha256": checksum(pilot),
               "network_config_path": "configs/station-access-network.v1.json", "network_config_sha256": config_hash,
               "source_audit_path": "network/source-audit.json", "source_audit_sha256": config_hash,
               "base_pilot_sha256": hashlib.sha256((repo / "configs/pilot.json").read_bytes()).hexdigest()}
    protocol = {"config": {"network_config": "configs/station-access-network.v1.json"}, "network": network}
    verifier.check_network_binding(study, protocol, repo)
    invalid_path = deepcopy(protocol)
    invalid_path["network"]["pilot_path"] = "/Users/someone/private/pilot.json"
    with pytest.raises(verifier.VerificationError, match="portable pilot"):
        verifier.check_network_binding(study, invalid_path, repo)
    # Even a re-signed pilot cannot silently omit a frozen source route.
    pilot["route_short_names"].remove("M2")
    write(study / "network/pilot.json", pilot)
    protocol["network"]["pilot_sha256"] = checksum(pilot)
    with pytest.raises(verifier.VerificationError, match="expanded pilot reconstruction"):
        verifier.check_network_binding(study, protocol, repo)


def raw_coverage_fixture():
    from tests.test_case_network import feed
    payload = feed()
    receipt = {"record_id": "synthetic-source", "sha256": hashlib.sha256(payload).hexdigest(),
               "received_at": "2026-10-08T21:29:05+00:00"}
    connections = []
    for tid, stops in (("a-out", ["a", "b", "c"]), ("a-back", ["c", "b", "a"])):
        for sequence, (a, b) in enumerate(zip(stops, stops[1:])):
            connections.append({"connection_id": f"{DAY}:{tid}:{sequence}", "trip_instance_id": f"{DAY}:{tid}",
                                "route_id": "A-v1", "mode": "bus", "sequence": sequence, "from_stop_id": a, "to_stop_id": b})
    snapshot = {"metadata": {"snapshot_id": "synthetic-v2", "service_date": DAY, "snapshot_at": DAY + "T07:30:05+10:00"},
                "connections": connections}
    return snapshot, {"route_short_names": ["A"]}, {"GTFS": (payload, receipt)}


def test_independent_raw_csv_coverage_rejects_dropped_trip_suffix():
    snapshot, pilot, sources = raw_coverage_fixture()
    proof = verifier.independent_source_coverage(snapshot, pilot, sources)
    assert proof["passed"] and proof["expected_full_trip_count"] == proof["actual_full_trip_count"] == 2
    assert proof["expected_connection_count"] == proof["actual_connection_count"] == 4
    snapshot["connections"].pop()
    with pytest.raises(verifier.VerificationError, match="raw-GTFS complete-trip topology"):
        verifier.independent_source_coverage(snapshot, pilot, sources)


def test_independent_source_cancellation_uses_fresh_recorded_entities():
    from google.transit import gtfs_realtime_pb2
    snapshot, pilot, sources = raw_coverage_fixture()
    cutoff = int(datetime.fromisoformat(DAY + "T07:30:05+10:00").timestamp())
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.timestamp = cutoff
    entity = message.entity.add()
    entity.id = "synthetic-cancellation"
    entity.trip_update.trip.trip_id = "a-out"
    entity.trip_update.trip.schedule_relationship = 3
    entity.trip_update.timestamp = cutoff
    sources["TripUpdates"] = (message.SerializeToString(), {"received_at": "2026-10-08T21:30:04+00:00"})
    snapshot["connections"] = [c for c in snapshot["connections"] if not c["trip_instance_id"].endswith(":a-out")]
    proof = verifier.independent_source_coverage(snapshot, pilot, sources)
    assert proof["declared_cancelled_trip_ids"] == ["a-out"] and proof["actual_connection_count"] == 2
    entity.trip_update.timestamp = cutoff - 121
    sources["TripUpdates"] = (message.SerializeToString(), sources["TripUpdates"][1])
    with pytest.raises(verifier.VerificationError, match="raw-GTFS complete-trip topology"):
        verifier.independent_source_coverage(snapshot, pilot, sources)
