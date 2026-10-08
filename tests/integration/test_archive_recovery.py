import gzip
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from google.transit import gtfs_realtime_pb2

from resilience.pipeline import archive as archive_module
from resilience.pipeline.archive import Archive, FEEDS, GTFS_URL
from resilience.pipeline.recorder_runtime import recorder_lock


BRISBANE = ZoneInfo("Australia/Brisbane")


def received_at():
    return datetime.combine(date(2026, 10, 12), time(6), BRISBANE)


def full_feed(entity_id="recovery-fixture"):
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    message.header.timestamp = int(datetime(2026, 10, 12, 5, 59, tzinfo=BRISBANE).timestamp())
    message.entity.add(id=entity_id)
    return message.SerializeToString()


def row_count(archive, table, record_id):
    with archive.connect() as db:
        return db.execute(f"SELECT COUNT(*) FROM {table} WHERE record_id=?", (record_id,)).fetchone()[0]


def test_pending_capture_before_journal_recovers_once_without_network_or_receipt_rewrite(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    original_commit = archive._commit_capture

    def fail_before_journal(receipt):
        raise sqlite3.OperationalError("simulated interruption before journal commit")

    monkeypatch.setattr(archive, "_commit_capture", fail_before_journal)
    with pytest.raises(sqlite3.OperationalError, match="before journal"):
        archive.append("TripUpdates", full_feed(), received_at(), FEEDS["TripUpdates"])
    monkeypatch.setattr(archive, "_commit_capture", original_commit)

    pending_files = list((archive.root / "runtime" / "pending-captures").glob("*.json"))
    assert len(pending_files) == 1
    record_id = pending_files[0].stem
    assert archive.get(record_id) is None
    with pytest.raises(RuntimeError, match="recorder lock"):
        archive.recover_pending()

    # Recovery only validates local pending bytes; no HTTP client or source call
    # exists on the recovery path.
    with recorder_lock(archive.root):
        report = archive.recover_pending()
        assert report["recovered"] == [record_id]
        assert report["errors"] == []

    receipt = archive.get(record_id)
    assert receipt["status"] == "valid"
    assert receipt["received_at"] == received_at().astimezone(timezone.utc).isoformat()
    assert archive.read(receipt) == full_feed()
    assert row_count(archive, "outbox", record_id) == 1
    receipt_path = archive.root / "raw" / f"{record_id}.json"
    saved_receipt = receipt_path.read_bytes()
    assert not pending_files[0].exists()
    assert archive.records("TripUpdates", received_at() - timedelta(microseconds=1)) == []
    assert archive.records("TripUpdates", received_at()) == [receipt]

    with recorder_lock(archive.root):
        second_report = archive.recover_pending()
    assert second_report == {"recovered": [], "errors": []}
    assert archive.get(record_id) == receipt
    assert row_count(archive, "outbox", record_id) == 1
    assert receipt_path.read_bytes() == saved_receipt


def test_pending_capture_after_journal_before_receipt_file_finishes_without_duplication(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    stamp = received_at().astimezone(timezone.utc).isoformat()
    digest = hashlib.sha256(full_feed()).hexdigest()
    record_id = hashlib.sha256(f"TripUpdates|{stamp}|{digest}".encode()).hexdigest()
    receipt_path = archive.root / "raw" / f"{record_id}.json"
    pending_path = archive.root / "runtime" / "pending-captures" / f"{record_id}.json"
    real_atomic_write = archive_module.atomic_write

    def interrupt_receipt_publication(path, contents, *, immutable=False):
        if Path(path) == receipt_path:
            raise OSError("simulated interruption after journal commit")
        return real_atomic_write(path, contents, immutable=immutable)

    monkeypatch.setattr(archive_module, "atomic_write", interrupt_receipt_publication)
    with pytest.raises(OSError, match="after journal"):
        archive.append("TripUpdates", full_feed(), received_at(), FEEDS["TripUpdates"])
    monkeypatch.setattr(archive_module, "atomic_write", real_atomic_write)

    committed = archive.get(record_id)
    assert committed is not None
    assert not receipt_path.exists()
    assert pending_path.is_file()
    assert row_count(archive, "outbox", record_id) == 1
    before = dict(committed)

    with recorder_lock(archive.root):
        report = archive.recover_pending()
    assert report == {"recovered": [record_id], "errors": []}
    assert archive.get(record_id) == before
    assert row_count(archive, "outbox", record_id) == 1
    assert archive.read(committed) == full_feed()
    assert receipt_path.is_file()
    assert json.loads(receipt_path.read_text()) == before
    assert not pending_path.exists()


def test_interrupted_duplicate_uses_committed_annotations_and_recovers_without_conflict(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    payload = full_feed()
    original = archive.append(
        "TripUpdates",
        payload,
        received_at(),
        FEEDS["TripUpdates"],
        details={"annotation": "original"},
    )
    record_id = original["record_id"]
    receipt_path = archive.root / "raw" / f"{record_id}.json"
    receipt_bytes = receipt_path.read_bytes()
    object_path = archive.root / original["object_path"]
    object_bytes = object_path.read_bytes()
    original_commit = archive._commit_capture

    def interrupt_duplicate_after_envelope(_receipt):
        raise OSError("simulated interruption after durable duplicate envelope")

    monkeypatch.setattr(archive, "_commit_capture", interrupt_duplicate_after_envelope)
    with pytest.raises(OSError, match="duplicate envelope"):
        archive.append(
            "TripUpdates",
            payload,
            received_at(),
            FEEDS["TripUpdates"],
            details={"annotation": "changed on retry"},
        )
    monkeypatch.setattr(archive, "_commit_capture", original_commit)

    pending_path = archive.root / "runtime" / "pending-captures" / f"{record_id}.json"
    envelope = json.loads(pending_path.read_text())
    assert envelope["receipt"] == original
    assert json.loads(envelope["receipt"]["details"])["annotation"] == "original"
    assert archive.get(record_id) == original
    assert row_count(archive, "outbox", record_id) == 1
    assert receipt_path.read_bytes() == receipt_bytes
    assert object_path.read_bytes() == object_bytes

    with recorder_lock(archive.root):
        recovered = archive.recover_pending()
    assert recovered == {"recovered": [record_id], "errors": []}
    assert not pending_path.exists()
    assert archive.get(record_id) == original
    assert row_count(archive, "outbox", record_id) == 1
    assert receipt_path.read_bytes() == receipt_bytes
    assert object_path.read_bytes() == object_bytes


def test_distinct_capture_ids_publish_in_parallel_and_release_registry_entries(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    first_receipt_entered = threading.Event()
    second_receipt_entered = threading.Event()
    release_first = threading.Event()
    original_commit = archive._commit_capture
    first_digest = hashlib.sha256(full_feed("first")).hexdigest()
    second_digest = hashlib.sha256(full_feed("second")).hexdigest()

    def coordinated_commit(receipt):
        if receipt["sha256"] == first_digest:
            first_receipt_entered.set()
            if not release_first.wait(5):
                raise TimeoutError("test did not release first distinct capture")
        elif receipt["sha256"] == second_digest:
            second_receipt_entered.set()
        return original_commit(receipt)

    monkeypatch.setattr(archive, "_commit_capture", coordinated_commit)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(
            archive.append,
            "TripUpdates",
            full_feed("first"),
            received_at(),
            FEEDS["TripUpdates"],
        )
        assert first_receipt_entered.wait(2)
        second = workers.submit(
            archive.append,
            "VehiclePositions",
            full_feed("second"),
            received_at(),
            FEEDS["VehiclePositions"],
        )
        assert second_receipt_entered.wait(2), "different record IDs must not share a publication lock"
        release_first.set()
        first_result, second_result = first.result(timeout=3), second.result(timeout=3)

    assert first_result["record_id"] != second_result["record_id"]
    assert archive.get(first_result["record_id"]) == first_result
    assert archive.get(second_result["record_id"]) == second_result
    assert row_count(archive, "outbox", first_result["record_id"]) == 1
    assert row_count(archive, "outbox", second_result["record_id"]) == 1
    assert not any(key[0] == archive.root.resolve() for key in archive_module._CAPTURE_LOCKS)


def test_corrupt_valid_protobuf_claim_stays_pending_without_touching_committed_receipt(tmp_path):
    archive = Archive(tmp_path / "fixture")
    original = archive.append("TripUpdates", full_feed(), received_at(), FEEDS["TripUpdates"])
    original_id = original["record_id"]
    original_path = archive.root / "raw" / f"{original_id}.json"
    original_bytes = original_path.read_bytes()

    payload = b"\x0a\xff"  # Invalid protobuf wire data, with a matching object hash below.
    stamp = (received_at() + timedelta(seconds=1)).astimezone(timezone.utc).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    record_id = hashlib.sha256(f"TripUpdates|{stamp}|{digest}".encode()).hexdigest()
    object_path = archive.root / "raw" / "objects" / f"{digest}.gz"
    pending_path = archive.root / "runtime" / "pending-captures" / f"{record_id}.json"
    receipt = {
        "record_id": record_id,
        "feed": "TripUpdates",
        "received_at": stamp,
        "event_at": None,
        "sha256": digest,
        "gtfs_sha256": None,
        "source_url": FEEDS["TripUpdates"],
        "object_path": object_path.relative_to(archive.root).as_posix(),
        "status": "valid",
        "details": json.dumps({"entity_count": 0, "incrementality": 0}),
    }
    archive_module.atomic_write(object_path, gzip.compress(payload, mtime=0), immutable=True)
    archive_module.atomic_write(
        pending_path,
        json.dumps({"version": 1, "receipt": receipt}, sort_keys=True),
        immutable=True,
    )

    with recorder_lock(archive.root):
        report = archive.recover_pending()

    assert report["recovered"] == []
    assert report["errors"] and report["errors"][0]["error"]
    assert pending_path.exists()
    assert archive.get(record_id) is None
    assert row_count(archive, "outbox", record_id) == 0
    assert archive.get(original_id) == original
    assert row_count(archive, "outbox", original_id) == 1
    assert original_path.read_bytes() == original_bytes
    assert archive.read(original) == full_feed()


@pytest.mark.parametrize("linkage", ["missing", "future"])
def test_recovery_rejects_unavailable_or_future_gtfs_linkage(tmp_path, monkeypatch, linkage):
    archive = Archive(tmp_path / linkage)
    feed_received = received_at()
    if linkage == "future":
        schedule = archive.append(
            "GTFS",
            b"future schedule fixture",
            feed_received + timedelta(seconds=1),
            GTFS_URL,
        )
        gtfs_digest = schedule["sha256"]
    else:
        gtfs_digest = "a" * 64

    original_commit = archive._commit_capture

    def fail_before_feed_journal(_receipt):
        raise sqlite3.OperationalError("simulated interruption before feed journal")

    monkeypatch.setattr(archive, "_commit_capture", fail_before_feed_journal)
    with pytest.raises(sqlite3.OperationalError):
        archive.append(
            "TripUpdates",
            full_feed(),
            feed_received,
            FEEDS["TripUpdates"],
            gtfs_sha256=gtfs_digest,
        )
    monkeypatch.setattr(archive, "_commit_capture", original_commit)

    pending_files = list((archive.root / "runtime" / "pending-captures").glob("*.json"))
    assert len(pending_files) == 1
    pending_id = pending_files[0].stem
    with recorder_lock(archive.root):
        report = archive.recover_pending()

    assert report["recovered"] == []
    assert report["errors"]
    assert pending_files[0].exists()
    assert archive.get(pending_id) is None
    assert row_count(archive, "outbox", pending_id) == 0
    if linkage == "future":
        assert archive.get(schedule["record_id"]) == schedule


@pytest.mark.parametrize(
    "tampering",
    [
        "unsafe_path",
        "windows_path",
        "identity",
        "payload_hash",
        "event_at",
        "entity_metadata",
        "external_symlink",
    ],
)
def test_invalid_pending_evidence_stays_visible_and_does_not_rewrite_receipt(
    tmp_path, tampering
):
    archive = Archive(tmp_path / tampering)
    receipt = archive.append("TripUpdates", full_feed(), received_at(), FEEDS["TripUpdates"])
    record_id = receipt["record_id"]
    receipt_path = archive.root / "raw" / f"{record_id}.json"
    before_receipt_bytes = receipt_path.read_bytes()
    envelope = {"version": 1, "receipt": dict(receipt)}

    if tampering == "unsafe_path":
        envelope["receipt"]["object_path"] = "../outside.gz"
    elif tampering == "windows_path":
        envelope["receipt"]["object_path"] = r"C:\\outside\\payload.gz"
    elif tampering == "identity":
        envelope["receipt"]["record_id"] = "0" * 64
    elif tampering == "payload_hash":
        object_path = archive.root / receipt["object_path"]
        object_path.write_bytes(gzip.compress(b"payload changed after journal", mtime=0))
    elif tampering == "event_at":
        envelope["receipt"]["event_at"] = (
            datetime.fromisoformat(receipt["event_at"]) + timedelta(minutes=1)
        ).isoformat()
    elif tampering == "entity_metadata":
        details = json.loads(envelope["receipt"]["details"])
        details["entity_count"] = 999
        envelope["receipt"]["details"] = json.dumps(details, sort_keys=True)
    elif tampering == "external_symlink":
        object_path = archive.root / receipt["object_path"]
        external = archive.root.parent / "external-object.gz"
        external.write_bytes(object_path.read_bytes())
        object_path.unlink()
        try:
            object_path.symlink_to(external)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"external symlink unavailable on this filesystem: {exc}")

    pending_path = archive.root / "runtime" / "pending-captures" / f"{record_id}.json"
    archive_module.atomic_write(pending_path, json.dumps(envelope, sort_keys=True), immutable=True)
    with recorder_lock(archive.root):
        report = archive.recover_pending()

    assert report["recovered"] == []
    assert len(report["errors"]) == 1
    assert report["errors"][0]["pending_path"] == pending_path.relative_to(archive.root).as_posix()
    assert pending_path.exists()  # Invalid forensic evidence is retained for review.
    assert archive.get(record_id) == receipt
    assert row_count(archive, "outbox", record_id) == 1
    assert receipt_path.read_bytes() == before_receipt_bytes
