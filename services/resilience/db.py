"""Operational PostGIS store and a durable archive-reference outbox."""
import json
from datetime import datetime, timezone
import psycopg
from confluent_kafka import Producer
from .settings import settings

DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS source_receipts (record_id text PRIMARY KEY, feed text NOT NULL, received_at timestamptz NOT NULL, event_at timestamptz, sha256 text NOT NULL, manifest jsonb NOT NULL);
CREATE INDEX IF NOT EXISTS source_receipts_asof ON source_receipts(feed,received_at);
CREATE TABLE IF NOT EXISTS snapshots (snapshot_id text PRIMARY KEY, snapshot_at timestamptz NOT NULL, document jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS stops (stop_id text PRIMARY KEY, name text NOT NULL, geometry geometry(Point,4326) NOT NULL);
CREATE INDEX IF NOT EXISTS stops_geometry ON stops USING gist(geometry);
CREATE TABLE IF NOT EXISTS walking_links (link_id text PRIMARY KEY, from_stop_id text NOT NULL, to_stop_id text NOT NULL, length_m double precision NOT NULL, geometry geometry(LineString,4326) NOT NULL, osm_node_ids jsonb NOT NULL);
CREATE INDEX IF NOT EXISTS walking_geometry ON walking_links USING gist(geometry);
CREATE TABLE IF NOT EXISTS experiment_runs (run_id text PRIMARY KEY, status text NOT NULL, document jsonb NOT NULL);
"""

def initialize():
    with psycopg.connect(settings.database_url) as db:
        db.execute(DDL)

def persist_snapshot(snapshot):
    initialize()
    with psycopg.connect(settings.database_url) as db:
        db.execute("INSERT INTO snapshots VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING", (snapshot.metadata.snapshot_id, snapshot.metadata.snapshot_at, snapshot.model_dump_json()))
        for stop in snapshot.stops:
            db.execute("INSERT INTO stops VALUES (%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326)) ON CONFLICT(stop_id) DO UPDATE SET name=excluded.name,geometry=excluded.geometry", (stop.stop_id,stop.name,stop.longitude,stop.latitude))
        for link in snapshot.walking_links:
            geometry = json.dumps({"type":"LineString","coordinates":link.geometry})
            db.execute("INSERT INTO walking_links VALUES (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s::jsonb) ON CONFLICT DO NOTHING", (link.link_id,link.from_stop_id,link.to_stop_id,link.length_m,geometry,json.dumps(link.osm_node_ids)))

def persist_run(run):
    initialize()
    with psycopg.connect(settings.database_url) as db:
        db.execute("INSERT INTO experiment_runs VALUES (%s,%s,%s::jsonb) ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,document=excluded.document", (run["run_id"],run["status"],json.dumps(run)))

def flush_outbox(archive):
    initialize()
    producer = Producer({"bootstrap.servers":settings.broker,"message.timeout.ms":3000,"socket.timeout.ms":3000,"enable.idempotence":True})
    sent = 0
    with archive.connect() as journal:
        rows = journal.execute("SELECT r.* FROM receipts r JOIN outbox o USING(record_id) WHERE o.sent_at IS NULL ORDER BY received_at LIMIT 100").fetchall()
    for row in rows:
        receipt = dict(row)
        try:
            with psycopg.connect(settings.database_url, connect_timeout=3) as db:
                db.execute("INSERT INTO source_receipts VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING", (receipt["record_id"],receipt["feed"],receipt["received_at"],receipt["event_at"],receipt["sha256"],json.dumps(receipt)))
            errors = []
            producer.produce("resilience.source-references.v1", key=receipt["record_id"], value=json.dumps(receipt), on_delivery=lambda err,msg: errors.append(str(err)) if err else None)
            remaining = producer.flush(4)
            if remaining or errors: raise RuntimeError(str(errors or "broker delivery timed out"))
            with archive.connect() as journal:
                journal.execute("UPDATE outbox SET sent_at=?,attempts=attempts+1,last_error=NULL WHERE record_id=?", (datetime.now(timezone.utc).isoformat(),receipt["record_id"]))
            sent += 1
        except Exception as exc:
            with archive.connect() as journal:
                journal.execute("UPDATE outbox SET attempts=attempts+1,last_error=? WHERE record_id=?", (str(exc),receipt["record_id"]))
            break
    return {"published":sent,"remaining":len(rows)-sent,"delivery":"at least once; consumer deduplicates record_id"}
