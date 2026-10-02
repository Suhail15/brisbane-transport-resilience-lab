from __future__ import annotations
import time
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
    """Weekday 06-12 recorder. Force captures remain explicitly development-only."""
    due = {name: 0.0 for name in FEEDS}
    last_clock = utcnow()
    with httpx.Client(timeout=20, follow_redirects=True) as client, ThreadPoolExecutor(max_workers=3) as pool:
        while True:
            now = utcnow()
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
                pending = [name for name in FEEDS if time.monotonic() >= due[name]]
                futures = {name: pool.submit(fetch_feed, archive, name, digest, client) for name in pending}
                for name, future in futures.items():
                    print(future.result(), flush=True)
                    due[name] = time.monotonic() + (60 if name == "Alerts" else 30)
                try:
                    from ..db import flush_outbox
                    flush_outbox(archive)
                except Exception as exc:
                    print({"outbox_pending": True, "error": str(exc)}, flush=True)
            if once:
                return
            time.sleep(1 if force or in_window(now) else 30)
