"""Immutable content-addressed originals plus append-only receipt journal."""
from __future__ import annotations
import gzip
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from google.transit import gtfs_realtime_pb2
from .files import atomic_write

FEEDS = {name: f"https://gtfsrt.api.translink.com.au/api/realtime/SEQ/{name}" for name in ("TripUpdates", "VehiclePositions", "Alerts")}
GTFS_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"

# Only identical observations share a publication lock. References include both
# active and waiting calls, allowing entries to disappear once nobody needs them.
_CAPTURE_LOCKS = {}
_CAPTURE_LOCK_GUARD = threading.Lock()


@contextmanager
def _capture_publication_lock(root, record_id):
    key = (Path(root).resolve(), record_id)
    with _CAPTURE_LOCK_GUARD:
        entry = _CAPTURE_LOCKS.setdefault(key, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _CAPTURE_LOCK_GUARD:
            entry[1] -= 1
            if entry[1] == 0:
                del _CAPTURE_LOCKS[key]


def utcnow():
    return datetime.now(timezone.utc)

class Archive:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        (self.root / "raw" / "objects").mkdir(parents=True, exist_ok=True)
        (self.root / "runtime").mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "runtime" / "archive.sqlite"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS receipts (record_id TEXT PRIMARY KEY, feed TEXT NOT NULL, received_at TEXT NOT NULL, event_at TEXT, sha256 TEXT NOT NULL, gtfs_sha256 TEXT, source_url TEXT NOT NULL, object_path TEXT NOT NULL, status TEXT NOT NULL, details TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS receipt_time ON receipts(feed,received_at);
            CREATE TABLE IF NOT EXISTS outbox (record_id TEXT PRIMARY KEY, sent_at TEXT, attempts INTEGER DEFAULT 0, last_error TEXT);
            CREATE TABLE IF NOT EXISTS gaps (id INTEGER PRIMARY KEY, started_at TEXT, ended_at TEXT, feed TEXT, reason TEXT, detected_at TEXT);
            """)
            db.execute("BEGIN IMMEDIATE")
            if "detected_at" not in {row[1] for row in db.execute("PRAGMA table_info(gaps)")}:
                db.execute("ALTER TABLE gaps ADD COLUMN detected_at TEXT")
            db.execute("UPDATE gaps SET detected_at=? WHERE detected_at IS NULL",(utcnow().isoformat(),))
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db
    def append(self, feed, payload, received_at, source_url, gtfs_sha256=None, details=None):
        if received_at.utcoffset() is None:
            raise ValueError("receipt must be timezone aware")
        stamp = received_at.astimezone(timezone.utc).isoformat()
        digest = hashlib.sha256(payload).hexdigest()
        record_id = hashlib.sha256(f"{feed}|{stamp}|{digest}".encode()).hexdigest()
        with _capture_publication_lock(self.root, record_id):
            path = self.root / "raw" / "objects" / f"{digest}.gz"
            atomic_write(path,gzip.compress(payload,mtime=0),immutable=True)
            event_at, status = None, "valid"
            info = dict(details or {})
            if feed in FEEDS:
                try:
                    msg = gtfs_realtime_pb2.FeedMessage.FromString(payload)
                    if not msg.IsInitialized():
                        raise ValueError("missing required protobuf fields")
                    if msg.header.timestamp:
                        event_at = datetime.fromtimestamp(msg.header.timestamp, timezone.utc).isoformat()
                    info["entity_count"] = len(msg.entity)
                    info["incrementality"] = int(msg.header.incrementality)
                    if msg.header.incrementality != 0:
                        status = "quarantined"
                        info["error"] = "differential feed unsupported; full dataset required"
                except Exception as exc:
                    status = "quarantined"
                    info["error"] = str(exc)
            receipt = {"record_id": record_id, "feed": feed, "received_at": stamp,
                       "event_at": event_at, "sha256": digest, "gtfs_sha256": gtfs_sha256,
                       "source_url": source_url, "object_path": path.relative_to(self.root).as_posix(),
                       "status": status, "details": json.dumps(info, sort_keys=True)}
            # Under the same-identity lock, original committed metadata remains
            # authoritative even when a repeated caller supplies new annotations.
            receipt = self.get(record_id) or receipt
            pending = self.root / "runtime" / "pending-captures" / f"{record_id}.json"
            atomic_write(pending, json.dumps({"version": 1, "receipt": receipt}, sort_keys=True), immutable=True)
            self._commit_capture(receipt)
            receipt = self.get(record_id)
            # Receipts are immutable audit objects; replay queries use the indexed journal.
            receipt_path = self.root / "raw" / f"{record_id}.json"
            if not receipt_path.exists():
                atomic_write(receipt_path,json.dumps(receipt,indent=2),immutable=True)
            pending.unlink(missing_ok=True)
            return receipt
    def _commit_capture(self, receipt):
        """Journal-stage seam after the immutable pending envelope is durable."""
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(
                receipt[k] for k in ("record_id", "feed", "received_at", "event_at", "sha256",
                                     "gtfs_sha256", "source_url", "object_path", "status", "details")))
            db.execute("INSERT OR IGNORE INTO outbox(record_id) VALUES (?)", (receipt["record_id"],))

    def recover_pending(self):
        """Finish validated durable captures only while this process holds recorder lock."""
        from .recorder_runtime import recorder_lock_held
        if not recorder_lock_held(self.root):
            raise RuntimeError("Pending capture recovery requires the recorder lock")
        report = {"recovered": [], "errors": []}
        directory = self.root / "runtime" / "pending-captures"
        for pending in sorted(directory.glob("*.json")):
            try:
                envelope = json.loads(pending.read_text())
                if envelope.get("version") != 1:
                    raise ValueError("unsupported pending capture version")
                receipt = envelope["receipt"]
                required = {"record_id", "feed", "received_at", "event_at", "sha256",
                            "gtfs_sha256", "source_url", "object_path", "status", "details"}
                if set(receipt) != required:
                    raise ValueError("invalid pending receipt fields")
                if receipt["feed"] not in {*FEEDS, "GTFS"} or receipt["status"] not in {"valid", "quarantined"}:
                    raise ValueError("invalid pending feed/status")
                stamp = datetime.fromisoformat(receipt["received_at"])
                if stamp.utcoffset() is None or stamp.astimezone(timezone.utc).isoformat() != receipt["received_at"]:
                    raise ValueError("pending received_at must be canonical timezone-aware UTC")
                digest = receipt["sha256"]
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError("invalid pending payload hash")
                identity = hashlib.sha256(f'{receipt["feed"]}|{receipt["received_at"]}|{digest}'.encode()).hexdigest()
                if receipt["record_id"] != identity or pending.name != f"{identity}.json":
                    raise ValueError("pending identity mismatch")
                relative = receipt["object_path"]
                if (PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).is_absolute()
                        or "\\" in relative or relative != f"raw/objects/{digest}.gz"):
                    raise ValueError("unsafe pending object path")
                object_path = self.root / relative
                if (not object_path.resolve().is_relative_to(self.root.resolve())
                        or not object_path.resolve().is_relative_to((self.root / "raw" / "objects").resolve())):
                    raise ValueError("pending object escapes archive")
                payload = gzip.decompress(object_path.read_bytes())
                if hashlib.sha256(payload).hexdigest() != digest:
                    raise ValueError("pending payload hash mismatch")
                info = json.loads(receipt["details"])
                if not isinstance(info, dict):
                    raise ValueError("pending details must be an object")
                expected_url = FEEDS.get(receipt["feed"], GTFS_URL)
                if receipt["source_url"] != expected_url:
                    raise ValueError("pending source URL mismatch")
                if receipt["event_at"] is not None and datetime.fromisoformat(receipt["event_at"]).utcoffset() is None:
                    raise ValueError("pending event_at must be timezone aware")
                if receipt["feed"] in FEEDS and receipt["status"] == "valid":
                    message = gtfs_realtime_pb2.FeedMessage.FromString(payload)
                    if not message.IsInitialized() or message.header.incrementality != 0:
                        raise ValueError("pending valid receipt has invalid/non-full payload")
                    expected_event = datetime.fromtimestamp(message.header.timestamp, timezone.utc).isoformat() if message.header.timestamp else None
                    if (receipt["event_at"] != expected_event or info.get("entity_count") != len(message.entity)
                            or info.get("incrementality") != int(message.header.incrementality)):
                        raise ValueError("pending protobuf metadata mismatch")
                gtfs_digest = receipt["gtfs_sha256"]
                if gtfs_digest is not None:
                    if (not isinstance(gtfs_digest, str) or len(gtfs_digest) != 64
                            or any(c not in "0123456789abcdef" for c in gtfs_digest)):
                        raise ValueError("invalid pending GTFS hash")
                    with self.connect() as db:
                        available = db.execute(
                            "SELECT 1 FROM receipts WHERE feed='GTFS' AND status='valid' "
                            "AND sha256=? AND received_at<=? LIMIT 1",
                            (gtfs_digest, receipt["received_at"])).fetchone()
                    if available is None:
                        raise ValueError("pending GTFS receipt unavailable at original received_at")
                existing = self.get(identity)
                if existing:
                    # A committed row is authoritative, even if an envelope disagrees.
                    if any(existing[k] != receipt[k] for k in required):
                        raise ValueError("pending envelope conflicts with committed receipt")
                    receipt = existing
                else:
                    with self.connect() as db:
                        db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(
                            receipt[k] for k in ("record_id", "feed", "received_at", "event_at", "sha256",
                                                 "gtfs_sha256", "source_url", "object_path", "status", "details")))
                        db.execute("INSERT OR IGNORE INTO outbox(record_id) VALUES (?)", (identity,))
                with self.connect() as db:
                    db.execute("INSERT OR IGNORE INTO outbox(record_id) VALUES (?)", (identity,))
                # Do not overwrite existing originals; collision preserves pending evidence.
                atomic_write(self.root / "raw" / f"{identity}.json", json.dumps(receipt, indent=2), immutable=True)
                pending.unlink()
                report["recovered"].append(identity)
            except Exception as exc:
                report["errors"].append({"pending_path": pending.relative_to(self.root).as_posix(), "error": str(exc)[:500]})
        return report

    def get(self, record_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM receipts WHERE record_id=?", (record_id,)).fetchone()
        return dict(row) if row else None
    def records(self, feed=None, as_of=None):
        clauses, params = [], []
        if feed:
            clauses.append("feed=?"); params.append(feed)
        if as_of:
            clauses.append("received_at<=?"); params.append(as_of.astimezone(timezone.utc).isoformat())
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM receipts" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY received_at,record_id", params)]
    def latest(self, feed, as_of, gtfs_sha256=None):
        records = [row for row in self.records(feed, as_of) if row["status"] == "valid" and (gtfs_sha256 is None or row["gtfs_sha256"] == gtfs_sha256)]
        return records[-1] if records else None
    def read(self, receipt):
        payload = gzip.decompress((self.root / receipt["object_path"]).read_bytes())
        if hashlib.sha256(payload).hexdigest() != receipt["sha256"]:
            raise ValueError("archive hash mismatch")
        return payload
    def gap(self, start, end, feed, reason, *, detected_at=None):
        with self.connect() as db:
            db.execute("INSERT INTO gaps(started_at,ended_at,feed,reason,detected_at) VALUES (?,?,?,?,?)", (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat(), feed, reason, (detected_at or utcnow()).astimezone(timezone.utc).isoformat()))
    def known_gaps(self,as_of):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM gaps WHERE detected_at<=? ORDER BY started_at",(as_of.astimezone(timezone.utc).isoformat(),))]
    def import_bootstrap(self):
        bootstrap = self.root / "bootstrap"
        manifest = json.loads((bootstrap / "download.json").read_text())
        payload = (bootstrap / "SEQ_GTFS.zip").read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
            raise ValueError("bootstrap GTFS hash mismatch")
        return self.append("GTFS", payload, datetime.fromisoformat(manifest["received_at"]), manifest["url"], details={"kind": "source observation", "licence": "CC BY 4.0", "publisher": "Translink"})
