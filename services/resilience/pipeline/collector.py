from __future__ import annotations
import time
from datetime import datetime,timezone
from .recorder_runtime import recorder_lock,WindowAwake
from .files import atomic_write
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from zoneinfo import ZoneInfo
import httpx
from .archive import Archive, FEEDS, GTFS_URL, utcnow

BRISBANE = ZoneInfo("Australia/Brisbane")

def in_window(now):
    local = now.astimezone(BRISBANE)
    return local.weekday() < 5 and 6 <= local.hour < 12

def fetch_feed(archive, name, gtfs_digest, client):
    started = utcnow()
    for attempt in range(3):
        try:
            response = client.get(FEEDS[name])
            response.raise_for_status()
            return archive.append(name, response.content, utcnow(), FEEDS[name], gtfs_digest, {"request_started_at": started.isoformat(), "http_status": response.status_code, "development_capture": not in_window(started)})
        except (httpx.HTTPError, OSError) as exc:
            if attempt == 2:
                archive.gap(started, utcnow(), name, f"fetch failed after 3 attempts: {exc}")
                return {"feed": name, "status": "failed", "error": str(exc)}
            time.sleep(2 ** attempt)

def refresh_schedule(archive):
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(GTFS_URL); response.raise_for_status()
        return archive.append("GTFS", response.content, utcnow(), GTFS_URL, details={"licence": "CC BY 4.0", "publisher": "Translink"})

def collect(archive: Archive, *, force=False, once=False):
    with recorder_lock(archive.root):
        awake=WindowAwake()
        try:return _collect(archive,force=force,once=once,awake=awake)
        finally:awake.close()

def _collect(archive: Archive, *, force=False, once=False,awake=None):
    """Weekday 06-12 recorder. Force captures remain explicitly development-only."""
    due = {name: 0.0 for name in FEEDS}
    inflight={}
    last_clock = utcnow()
    previous=archive.latest("TripUpdates",last_clock)
    if in_window(last_clock) and (not previous or (last_clock-datetime.fromisoformat(previous["received_at"])).total_seconds()>35):
        start=datetime.combine(last_clock.astimezone(BRISBANE).date(),datetime.min.time().replace(hour=6),BRISBANE).astimezone(timezone.utc)
        archive.gap(max(start,datetime.fromisoformat(previous["received_at"])) if previous else start,last_clock,"all","Recorder startup missing preceding window receipts")
    from ..db import flush_outbox
    outbox_pool=ThreadPoolExecutor(max_workers=1);outbox_job=None
    with httpx.Client(timeout=20, follow_redirects=True) as client, ThreadPoolExecutor(max_workers=3) as pool:
        while True:
            now = utcnow()
            if awake:awake.set(in_window(now))
            atomic_write(archive.root/"runtime"/"collector-status.json",__import__("json").dumps({"pid":__import__("os").getpid(),"heartbeat_at":now.isoformat(),"window_active":in_window(now),"force":force}))
            if (now - last_clock).total_seconds() > 45 and in_window(now):
                archive.gap(last_clock, now, "all", "scheduler discontinuity, possibly laptop sleep")
            last_clock = now
            if force or in_window(now):
                schedule = archive.latest("GTFS", now)
                if not schedule or (now - __import__("datetime").datetime.fromisoformat(schedule["received_at"])).total_seconds() >= 86400:
                    try:
                        schedule = refresh_schedule(archive)
                    except Exception as exc:
                        archive.gap(now, utcnow(), "GTFS", f"schedule refresh failed: {exc}")
                digest = schedule["sha256"] if schedule else None
                for name in list(inflight):
                    if inflight[name].done():
                        print(inflight.pop(name).result(),flush=True)
                pending = [name for name in FEEDS if name not in inflight and time.monotonic() >= due[name]]

                for name in pending:
                    cadence=60 if name=="Alerts" else 30
                    # Anchor to dispatch time rather than response completion; avoid accumulating request latency.
                    dispatch=time.monotonic()
                    due[name]=max(due[name]+cadence,dispatch+cadence)
                    inflight[name]=pool.submit(fetch_feed,archive,name,digest,client)

                if outbox_job is None or outbox_job.done():
                    if outbox_job is not None:
                        try:outbox_job.result()
                        except Exception as exc:print({"outbox_pending":True,"error":str(exc)},flush=True)
                    outbox_job=outbox_pool.submit(flush_outbox,archive)
            if once:
                for future in inflight.values():print(future.result(),flush=True)
                outbox_pool.shutdown(wait=True)
                return
            time.sleep(.5 if force or in_window(now) else 30)
