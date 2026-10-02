"""Immutable content-addressed originals plus append-only receipt journal."""
from __future__ import annotations
import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from google.transit import gtfs_realtime_pb2
from .files import atomic_write

FEEDS = {name: f"https://gtfsrt.api.translink.com.au/api/realtime/SEQ/{name}" for name in ("TripUpdates", "VehiclePositions", "Alerts")}
GTFS_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"

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
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)", (record_id, feed, stamp, event_at, digest, gtfs_sha256, source_url, str(path.relative_to(self.root)), status, json.dumps(info, sort_keys=True)))
            db.execute("INSERT OR IGNORE INTO outbox(record_id) VALUES (?)", (record_id,))
        receipt = self.get(record_id)
        # Receipts are immutable audit objects; replay queries use the indexed journal.
        receipt_path = self.root / "raw" / f"{record_id}.json"
        if not receipt_path.exists():
            atomic_write(receipt_path,json.dumps(receipt,indent=2),immutable=True)
        return receipt
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
    def gap(self, start, end, feed, reason):
        with self.connect() as db:
            db.execute("INSERT INTO gaps(started_at,ended_at,feed,reason,detected_at) VALUES (?,?,?,?,?)", (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat(), feed, reason, utcnow().isoformat()))
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
