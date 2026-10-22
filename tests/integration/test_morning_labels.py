from datetime import datetime
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from resilience.pipeline.bundle import capture_label
from resilience.pipeline.snapshots import capture_quality_warning, is_weekday_morning_capture


MORNING_WARNING = "Recorded morning inputs; complete-window receipt coverage is audited separately"
OUTSIDE_WARNING = "Recorded inputs outside the weekday morning evaluation window"


def _install_public_export_stubs(monkeypatch, tmp_path, captured_at_by_id):
    from resilience.pipeline import bundle, evidence, integrity

    snapshots_by_id = {}
    index = []
    for snapshot_id, captured_at in captured_at_by_id.items():
        source = SimpleNamespace(
            source_kind="gtfs",
            record_id=f"gtfs-{snapshot_id}",
            sha256=(snapshot_id[0].lower() * 64),
        )
        metadata = SimpleNamespace(
            sources=(source,),
            snapshot_at=datetime.fromisoformat(captured_at),
            model_dump=lambda mode=None, sid=snapshot_id, digest=source.sha256: {
                "snapshot_id": sid,
                "sources": [{"record_id": f"gtfs-{sid}", "sha256": digest}],
            },
        )
        snapshots_by_id[snapshot_id] = SimpleNamespace(metadata=metadata)
        index.append({
            "snapshot_id": snapshot_id,
            "snapshot_at": captured_at,
            "service_date": captured_at[:10],
            "quality": {},
            "url": f"snapshots/{snapshot_id}.json",
        })

    monkeypatch.setattr(bundle, "release_gate", lambda _archive: {"gates": {}, "blocking": [], "passed": True})
    monkeypatch.setattr(bundle, "snapshot_index", lambda _archive: index)
    monkeypatch.setattr(bundle, "load_snapshot", lambda _archive, snapshot_id: snapshots_by_id[snapshot_id])
    monkeypatch.setattr(bundle, "display_frame", lambda _archive, snapshot_id: {"snapshot_id": snapshot_id})
    monkeypatch.setattr(bundle, "choices", lambda _archive, snapshot_id: {"snapshot_id": snapshot_id})
    monkeypatch.setattr(evidence, "release_evidence", lambda: {"public_bundle_service_dates": ["2026-10-21"]})
    monkeypatch.setattr(integrity, "recorded_runs", lambda _archive: {})
    monkeypatch.setattr(
        bundle,
        "network",
        lambda _archive, snapshot_id: {"type": "FeatureCollection", "features": [], "chosen_snapshot_id": snapshot_id},
    )
    archive = SimpleNamespace(root=Path(tmp_path), records=lambda as_of: [])
    return bundle, archive


@pytest.mark.parametrize(
    ("captured_at", "expected"),
    [
        ("2026-10-21T06:00:00+10:00", MORNING_WARNING),
        ("2026-10-21T11:59:59+10:00", MORNING_WARNING),
        ("2026-10-21T12:00:00+10:00", OUTSIDE_WARNING),
        ("2026-10-21T05:59:59+10:00", OUTSIDE_WARNING),
        ("2026-10-24T08:00:00+10:00", OUTSIDE_WARNING),
        ("2026-10-20T20:00:00+00:00", MORNING_WARNING),
    ],
)
def test_snapshot_quality_label_uses_brisbane_weekday_morning_window(captured_at, expected):
    instant = datetime.fromisoformat(captured_at)

    assert capture_quality_warning(instant) == expected
    assert is_weekday_morning_capture(instant) is (expected == MORNING_WARNING)


def test_bundle_capture_label_requires_every_selected_frame_to_be_a_weekday_morning():
    morning_frames = [
        {"snapshot_at": "2026-10-21T06:00:00+10:00"},
        {"snapshot_at": "2026-10-22T11:59:59+10:00"},
    ]
    mixed_frames = morning_frames + [{"snapshot_at": "2026-10-24T08:00:00+10:00"}]

    assert capture_label(morning_frames) == "Recorded morning inputs; private preview"
    assert capture_label(mixed_frames) == "Recorded source inputs; private preview"
    assert capture_label([]) == "Recorded source inputs; private preview"
    assert capture_label([], public=True) == "Three real recorded mornings"


@pytest.mark.parametrize("compact", [True, False])
def test_export_caches_network_once_per_gtfs_digest_and_keeps_each_selected_version(tmp_path, monkeypatch, compact):
    from resilience.pipeline import bundle, integrity

    digests = {"morning-a": "a" * 64, "morning-b": "a" * 64, "morning-c": "b" * 64}
    frame_times = {
        "morning-a": "2026-10-21T06:00:00+10:00",
        "morning-b": "2026-10-21T06:15:00+10:00",
        "morning-c": "2026-10-22T06:00:00+10:00",
    }

    class Metadata:
        def __init__(self, snapshot_id):
            self.sources = (SimpleNamespace(source_kind="gtfs", sha256=digests[snapshot_id]),)

        def model_dump(self, mode=None):
            return {"snapshot_id": self.snapshot_id, "sources": [{"sha256": digests[self.snapshot_id]}]}

    snapshots_by_id = {}
    index = []
    for snapshot_id, captured_at in frame_times.items():
        metadata = Metadata(snapshot_id)
        metadata.snapshot_id = snapshot_id
        snapshots_by_id[snapshot_id] = SimpleNamespace(metadata=metadata)
        index.append({
            "snapshot_id": snapshot_id,
            "snapshot_at": captured_at,
            "service_date": captured_at[:10],
            "quality": {},
            "url": f"snapshots/{snapshot_id}.json",
        })

    monkeypatch.setattr(bundle, "release_gate", lambda _archive: {"gates": {}, "blocking": [], "passed": False})
    monkeypatch.setattr(bundle, "snapshot_index", lambda _archive: index)
    monkeypatch.setattr(bundle, "load_snapshot", lambda _archive, snapshot_id: snapshots_by_id[snapshot_id])
    monkeypatch.setattr(bundle, "display_frame", lambda _archive, snapshot_id: {"snapshot_id": snapshot_id})
    monkeypatch.setattr(bundle, "choices", lambda _archive, snapshot_id: {"snapshot_id": snapshot_id})
    monkeypatch.setattr(integrity, "recorded_runs", lambda _archive: {})
    generated_for = []

    def fake_network(_archive, snapshot_id):
        generated_for.append(snapshot_id)
        return {
            "type": "FeatureCollection",
            "features": [],
            "source": {"gtfs_sha256": digests[snapshot_id], "chosen_snapshot_id": snapshot_id},
        }

    monkeypatch.setattr(bundle, "network", fake_network)
    archive = SimpleNamespace(root=Path(tmp_path), latest=lambda feed, as_of: {"sha256": digests["morning-c"]})
    source_snapshots = archive.root / "processed" / "snapshots"
    source_snapshots.mkdir(parents=True)
    for snapshot_id in snapshots_by_id:
        (source_snapshots / f"{snapshot_id}.json").write_text("{}")
    output = tmp_path / "private-bundle"

    bundle.export_bundle(archive, output, compact=compact)

    catalog = json.loads((output / "catalog.json").read_text())
    exported = catalog["snapshots"]
    assert generated_for == ["morning-a", "morning-c"]
    assert exported[0]["network_url"] == exported[1]["network_url"]
    assert exported[0]["network_url"] != exported[2]["network_url"]
    def read_network(relative_path):
        payload = (output / relative_path).read_bytes()
        return json.loads(gzip.decompress(payload) if relative_path.endswith(".gz") else payload)

    first_payload = read_network(exported[0]["network_url"])
    second_version_payload = read_network(exported[2]["network_url"])
    assert first_payload["source"]["chosen_snapshot_id"] == "morning-a"
    assert second_version_payload["source"]["chosen_snapshot_id"] == "morning-c"
    assert catalog["source_summary"]["capture_label"] == "Recorded morning inputs; private preview"
    if not compact:
        assert json.loads((output / "network.geojson").read_text())["source"]["chosen_snapshot_id"] == "morning-c"


def test_public_export_filters_to_requested_ids_before_eligibility(tmp_path, monkeypatch):
    bundle, archive = _install_public_export_stubs(
        monkeypatch,
        tmp_path,
        {
            "morning-a": "2026-10-21T06:00:00+10:00",
            "morning-b": "2026-10-21T06:15:00+10:00",
        },
    )
    output = tmp_path / "selected-public"

    bundle.export_bundle(archive, output, public=True, snapshot_ids=["morning-a"])

    catalog = json.loads((output / "catalog.json").read_text())
    assert [item["snapshot_id"] for item in catalog["snapshots"]] == ["morning-a"]
    assert catalog["source_summary"]["capture_label"] == "Three real recorded mornings"


def test_public_export_rejects_requested_id_that_fails_morning_eligibility(tmp_path, monkeypatch):
    bundle, archive = _install_public_export_stubs(
        monkeypatch,
        tmp_path,
        {
            "morning-a": "2026-10-21T06:00:00+10:00",
            "noon": "2026-10-21T12:00:00+10:00",
        },
    )

    with pytest.raises(ValueError, match="failed public morning eligibility: noon"):
        bundle.export_bundle(archive, tmp_path / "rejected-public", public=True, snapshot_ids=["morning-a", "noon"])


@pytest.mark.parametrize(
    ("snapshot_ids", "message"),
    [(["morning-a", "morning-a"], "Duplicate requested snapshot id"), (["unknown"], "Unknown snapshot id")],
)
def test_export_rejects_duplicate_and_unknown_snapshot_ids(tmp_path, monkeypatch, snapshot_ids, message):
    bundle, archive = _install_public_export_stubs(
        monkeypatch,
        tmp_path,
        {"morning-a": "2026-10-21T06:00:00+10:00"},
    )

    with pytest.raises(ValueError, match=message):
        bundle.export_bundle(archive, tmp_path / "invalid-selection", snapshot_ids=snapshot_ids)
