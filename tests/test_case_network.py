"""Synthetic source fixtures for the optional study network; no live fetches."""
from copy import deepcopy
import csv
from datetime import datetime, timedelta
from io import BytesIO, StringIO
import json
from pathlib import Path
import zipfile

import pytest

from resilience.pipeline.archive import Archive
from resilience.pipeline.case_network import (PLATFORMS, derive_network, encoded, materialize_pilot,
                                               snapshot_coverage, write_network_config)
from resilience.pipeline.schedule import Schedule
from resilience.pipeline.snapshots import build_snapshot


def table(headers, rows):
    target = StringIO()
    writer = csv.writer(target, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return target.getvalue()


def feed():
    source = BytesIO()
    stops = ["a", "b", "c", "bus-access", "z", "d", "f", "remote", *PLATFORMS]
    tables = {
        "stops.txt": table(["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station", "location_type"],
                           [[sid, sid, "0", "0", "", "0"] for sid in stops]),
        "routes.txt": table(["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
                            [[rid, "synthetic", short, "Synthetic fixture", "3"] for rid, short in
                             (("A-v1", "A"), ("M2-v1", "M2"), ("61-v1", "61"), ("BAD-v1", "BAD"), ("REMOTE-v1", "REMOTE"))]),
        "trips.txt": table(["route_id", "service_id", "trip_id", "direction_id"], [
            ["A-v1", "regular", "a-out", "0"], ["A-v1", "regular", "a-back", "1"],
            ["M2-v1", "regular", "m-out", "0"], ["M2-v1", "regular", "m-back", "1"],
            ["61-v1", "added", "61-out", "0"], ["61-v1", "added", "61-back", "1"],
            ["BAD-v1", "inactive", "bad", "0"], ["REMOTE-v1", "regular", "remote", "0"]]),
        "calendar.txt": table(["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
                              [["regular", *["1"] * 7, "20260101", "20261231"],
                               ["added", *["0"] * 7, "20260101", "20261231"],
                               ["inactive", *["0"] * 7, "20260101", "20261231"]]),
        "calendar_dates.txt": table(["service_id", "date", "exception_type"], [["added", "20261009", "1"]]),
    }
    times = []
    for tid, stop_ids in (("a-out", ["a", "b", "c"]), ("a-back", ["c", "b", "a"]),
                          ("m-out", ["bus-access", "z", "d"]), ("m-back", ["d", "z", "bus-access"]),
                          ("61-out", ["bus-access", "f"]), ("61-back", ["f", "bus-access"]),
                          ("bad", ["bus-access", "f"]), ("remote", ["remote", "f"])):
        for index, stop_id in enumerate(stop_ids):
            clock = f"08:{index * 10:02d}:00"
            times.append([tid, clock, clock, stop_id, index + 1, "0", "0"])
    tables["stop_times.txt"] = table(["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence", "pickup_type", "drop_off_type"], times)
    with zipfile.ZipFile(source, "w") as target:
        for name, value in tables.items():
            target.writestr(name, value)
    return source.getvalue()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


@pytest.fixture
def source_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    archive = Archive(tmp_path / "data")
    at = datetime.fromisoformat("2026-10-09T07:30:05+10:00")
    receipt = archive.append("GTFS", feed(), at - timedelta(minutes=1), "https://example.invalid/synthetic-gtfs")
    pilot = {"version": 1, "route_short_names": ["A"], "bus_seed_stop_ids": ["a"], "platform_seed_stop_ids": [],
             "parents": [], "selection_rule": "Synthetic base fixture", "max_walk_m": 600,
             "walking_speed_m_s": 1.2, "transfer_slack_s": 300, "max_transfers": 3}
    write(tmp_path / "configs/pilot.json", pilot)
    return archive, receipt, at, pilot


def test_custom_pilot_caches_cannot_reuse_default_filtered_rows(source_archive, tmp_path):
    archive, receipt, _, pilot = source_archive
    baseline = Schedule(archive, receipt)
    custom_path = tmp_path / "network/pilot.json"
    write(custom_path, {**pilot, "route_short_names": ["A", "M2"]})
    expanded = Schedule(archive, receipt, lock_path=custom_path)
    assert baseline.cache == archive.root / "processed" / receipt["sha256"]
    assert expanded.cache != baseline.cache
    assert set(baseline.stop_times.trip_id) == {"a-out", "a-back"}
    assert set(expanded.stop_times.trip_id) == {"a-out", "a-back", "m-out", "m-back"}
    assert list(expanded.stop_times[expanded.stop_times.trip_id == "m-out"].stop_id) == ["bus-access", "z", "d"]
    other_path = tmp_path / "network/other.json"
    write(other_path, {**pilot, "route_short_names": ["M2"]})
    other = Schedule(archive, receipt, lock_path=other_path)
    assert other.cache != expanded.cache and set(other.stop_times.trip_id) == {"m-out", "m-back"}
    assert Schedule(archive, receipt).cache == baseline.cache


def test_actual_custom_pilot_bytes_change_snapshot_method_identity(source_archive, tmp_path):
    archive, _, at, pilot = source_archive
    first_path, second_path = tmp_path / "first.json", tmp_path / "second.json"
    write(first_path, {**pilot, "route_short_names": ["A", "M2"], "note": "first exact source contract"})
    write(second_path, {**pilot, "route_short_names": ["A", "M2"], "note": "second exact source contract"})
    baseline = build_snapshot(archive, at, store=False, include_realtime=False)
    first = build_snapshot(archive, at, store=False, include_realtime=False, pilot_path=first_path)
    second = build_snapshot(archive, at, store=False, include_realtime=False, pilot_path=second_path)
    assert len(baseline.connections) == 4 and len(first.connections) == len(second.connections) == 8
    assert first.connections == second.connections
    assert first.metadata.snapshot_id != second.metadata.snapshot_id != baseline.metadata.snapshot_id
    assert build_snapshot(archive, at, store=False, include_realtime=False).metadata.snapshot_id == baseline.metadata.snapshot_id


def development_snapshots(source_archive, tmp_path, *, reverse_link=False):
    archive, receipt, at, _ = source_archive
    osm = archive.append("OSM", b'<osm version="0.6"><node id="1" lat="0" lon="0"/><node id="2" lat="0" lon="0.001"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way></osm>',
                         at - timedelta(minutes=2), "https://example.invalid/synthetic-osm")
    paths = {}
    for day in ("2026-10-09", "2026-10-13"):
        sources = [{"record_id": r["record_id"], "source_kind": kind, "received_at": r["received_at"],
                    "sha256": r["sha256"], "source_ref": r["source_url"]} for r, kind in ((receipt, "gtfs"), (osm, "osm"))]
        a, b = ("bus-access", PLATFORMS[0]) if reverse_link else (PLATFORMS[0], "bus-access")
        link = {"link_id": "synthetic-source-walk", "from_stop_id": a, "to_stop_id": b, "length_m": 120.0,
                "duration_s": 100, "osm_node_ids": [1, 2], "geometry": [[0, 0], [0.001, 0]],
                "from_snap_distance_m": 0, "to_snap_distance_m": 0}
        snapshot = {"metadata": {"snapshot_id": "development-" + day, "service_date": day,
                                "snapshot_at": day + "T07:30:05+10:00", "sources": sources},
                    "walking_links": [link], "stops": [], "connections": []}
        paths[day] = tmp_path / "development" / (day + ".json")
        write(paths[day], snapshot)
    return paths


@pytest.mark.parametrize("reverse_link", [False, True])
def test_discovery_uses_calendar_active_routes_and_existing_directed_links(source_archive, tmp_path, reverse_link):
    archive, _, _, _ = source_archive
    paths = development_snapshots(source_archive, tmp_path, reverse_link=reverse_link)
    derived = derive_network(archive, paths)
    assert derived["catchment_bus_stop_ids"] == ["bus-access"]
    assert derived["development_bus_route_short_names"] == ["61", "M2"]
    assert derived["expanded_route_short_names"] == ["61", "A", "M2"]
    assert "BAD" not in derived["expanded_route_short_names"] and "REMOTE" not in derived["expanded_route_short_names"]
    first, second = derived["development_source_audits"]
    assert first["bus_route_short_names"] == ["61", "M2"] and second["bus_route_short_names"] == ["M2"]
    assert first["walking_link_witnesses"][0]["link_id"] == "synthetic-source-walk"
    assert len(first["sources"]) == 2 and first["route_witnesses"][0]["active_touching_trip_count"] == 2


def test_frozen_config_and_pilot_are_immutable_and_bind_base_bytes(source_archive, tmp_path):
    archive, _, _, _ = source_archive
    paths = development_snapshots(source_archive, tmp_path)
    config_path = tmp_path / "frozen-network.json"
    report = write_network_config(archive, paths, config_path)
    assert report["catchment_bus_stop_count"] == 1 and report["development_bus_route_count"] == 2
    output = tmp_path / "prepared/network/pilot.json"
    pilot = materialize_pilot(config_path, output)
    assert json.loads(output.read_bytes())["route_short_names"] == ["61", "A", "M2"]
    assert json.loads(output.read_bytes())["bus_seed_stop_ids"] == ["a", "bus-access"]
    assert materialize_pilot(config_path, output) == pilot
    base_path = tmp_path / "configs/pilot.json"
    base = json.loads(base_path.read_bytes())
    base["selection_rule"] = "changed after network derivation"
    write(base_path, base)
    with pytest.raises(ValueError, match="Base pilot differs"):
        materialize_pilot(config_path, tmp_path / "changed.json")


def test_coverage_proof_reconciles_full_trips_and_rejects_clipping(source_archive):
    archive, _, at, _ = source_archive
    data = build_snapshot(archive, at, store=False, include_realtime=False)
    coverage = snapshot_coverage(archive, data, Path("configs/pilot.json"))
    assert coverage["passed"] and coverage["actual_full_trip_count"] == coverage["expected_full_trip_count"] == 2
    assert coverage["actual_connection_count"] == coverage["expected_connection_count"] == 4
    assert coverage["actual_topology_sha256"] == coverage["expected_topology_sha256"]
    clipped = data.model_copy(update={"connections": data.connections[:-1]})
    with pytest.raises(ValueError, match="full-trip topology differs"):
        snapshot_coverage(archive, clipped, Path("configs/pilot.json"))


def test_coverage_allows_only_declared_source_cancellations(source_archive):
    archive, _, at, _ = source_archive
    data = build_snapshot(archive, at, store=False, include_realtime=False)
    remaining = data.model_copy(update={"connections": tuple(c for c in data.connections if not c.trip_instance_id.endswith(":a-out"))})
    result = snapshot_coverage(archive, remaining, Path("configs/pilot.json"), cancelled_trip_ids=["a-out"])
    assert result["actual_full_trip_count"] == 1 and result["declared_cancelled_trip_ids"] == ["a-out"]
    with pytest.raises(ValueError, match="not a selected source-active trip"):
        snapshot_coverage(archive, remaining, Path("configs/pilot.json"), cancelled_trip_ids=["fabricated"])


def test_future_and_missing_walking_sources_fail_discovery(source_archive, tmp_path):
    archive, _, _, _ = source_archive
    paths = development_snapshots(source_archive, tmp_path)
    first = json.loads(paths["2026-10-09"].read_bytes())
    first["metadata"]["snapshot_at"] = "2026-10-09T07:30:06+10:00"
    write(paths["2026-10-09"], first)
    with pytest.raises(ValueError, match="cutoff differs"):
        derive_network(archive, paths)
    first["metadata"]["snapshot_at"] = "2026-10-09T07:30:05+10:00"
    first["metadata"]["sources"] = [s for s in first["metadata"]["sources"] if s["source_kind"] != "osm"]
    write(paths["2026-10-09"], first)
    with pytest.raises(ValueError, match="GTFS and OSM source"):
        derive_network(archive, paths)
