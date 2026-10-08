from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .archive import Archive, FEEDS, GTFS_URL, utcnow
from .collector_schedule import (
    BRISBANE, POLICY, POLL_SECONDS, MIN_DISPATCH_SECONDS, in_window, next_boundary,
    next_phase_deadline, preparation_active, window_start,
)
from .files import atomic_write
from .recorder_runtime import recorder_lock, WindowAwake
from .collector_telemetry import AsyncTelemetry


def latest_schedule(archive, as_of):
    # Bounded indexed lookup; a pending/uncommitted download is unavailable.
    with archive.connect() as db:
        row = db.execute(
            "SELECT * FROM receipts WHERE feed='GTFS' AND status='valid' "
            "AND received_at<=? ORDER BY received_at DESC LIMIT 1",
            (as_of.astimezone(timezone.utc).isoformat(),),
        ).fetchone()
    return dict(row) if row else None


def feed_client():
    return httpx.Client(timeout=20, follow_redirects=True,
                        limits=httpx.Limits(max_connections=3, max_keepalive_connections=3,
                                            keepalive_expiry=90))


def retry_after_seconds(response, now):
    value = getattr(response, "headers", {}).get("Retry-After") if response is not None else None
    if value is None:
        return 0.0
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds >= 0 else 0.0
    except (ValueError, TypeError):
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.utcoffset() is None:
                return 0.0
            return max(0.0, (deadline.astimezone(timezone.utc) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0


def fetch_feed(archive, name, gtfs_digest, client, *, dispatch=None, telemetry=None):
    started = utcnow()
    started_mono = time.monotonic()
    timing = dict(dispatch or {})
    if "submitted_monotonic" in timing:
        timing["task_start_delay_seconds"] = max(0, started_mono - timing.pop("submitted_monotonic"))
    timing["task_started_at"] = started.isoformat()
    attempts = []
    for attempt in range(3):
        attempted_at = utcnow()
        attempt_mono = time.monotonic()
        try:
            response = client.get(FEEDS[name])
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            elapsed = time.monotonic() - attempt_mono
            retry_delay = max(2 ** attempt, retry_after_seconds(getattr(exc, "response", None), attempted_at))
            attempts.append({"attempt": attempt + 1, "started_at": attempted_at.isoformat(),
                             "elapsed_seconds": elapsed, "retry_after_seconds": retry_delay,
                             "error": str(exc)[:500]})
            if attempt == 2:
                ended = utcnow()
                reason = f"fetch failed after 3 attempts: {str(exc)[:500]}"
                if telemetry:
                    telemetry.gap(started, ended, name, reason, detected_at=ended)
                else:
                    archive.gap(started, ended, name, reason, detected_at=ended)
                return {"feed": name, "status": "failed", "error": str(exc)[:500],
                        "request_started_at": started.isoformat(), "attempts": attempts,
                        "request_elapsed_seconds": time.monotonic() - started_mono,
                        "retry_not_before": (ended.timestamp() + retry_after_seconds(getattr(exc, "response", None), ended)),
                        "collector_policy": POLICY, "poll_interval_seconds": POLL_SECONDS[name],
                        "minimum_dispatch_spacing_seconds": MIN_DISPATCH_SECONDS[name]}
            time.sleep(retry_delay)
            continue
        received = utcnow()
        http_finished_mono = time.monotonic()
        attempts.append({"attempt": attempt + 1, "started_at": attempted_at.isoformat(),
                         "elapsed_seconds": http_finished_mono - attempt_mono,
                         "http_status": response.status_code})
        schedule = latest_schedule(archive, received)
        persistence_started_mono = time.monotonic()
        receipt = archive.append(name, response.content, received, FEEDS[name],
                              schedule["sha256"] if schedule else None,
                              {**timing, "request_started_at": started.isoformat(),
                               "request_elapsed_seconds": http_finished_mono - started_mono,
                               "schedule_lookup_seconds": persistence_started_mono - http_finished_mono,
                               "attempts": attempts, "http_status": response.status_code,
                               "collector_policy": POLICY, "poll_interval_seconds": POLL_SECONDS[name],
                               "minimum_dispatch_spacing_seconds": MIN_DISPATCH_SECONDS[name],
                               "development_capture": not in_window(started) or not in_window(received)})
        completed_mono = time.monotonic()
        # Return-only diagnostics: immutable receipt metadata never gains later knowledge.
        return {**receipt, "runtime_timing": {
            "persistence_elapsed_seconds": completed_mono - persistence_started_mono,
            "task_elapsed_seconds": completed_mono - started_mono}}


def refresh_schedule(archive):
    started = utcnow()
    started_mono = time.monotonic()
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(GTFS_URL)
        response.raise_for_status()
        received = utcnow()
        return archive.append("GTFS", response.content, received, GTFS_URL,
                              details={"licence": "CC BY 4.0", "publisher": "Translink",
                                       "request_started_at": started.isoformat(),
                                       "request_elapsed_seconds": time.monotonic() - started_mono,
                                       "collector_policy": POLICY})


def audit_window(archive, service_date):
    from .coverage import coverage_report
    report = coverage_report(archive)
    path = archive.root / "runtime" / f"coverage-{service_date}.json"
    atomic_write(path, json.dumps(report, indent=2))
    return {"coverage_report": str(path), "service_date": service_date,
            "complete_weekday_windows": report["complete_weekday_windows"]}


class CollectorLoop:
    """Finite tick seam: workers do I/O; the scheduler only drains and dispatches."""
    def __init__(self, archive, feed_pool, schedule_pool, outbox_pool, client, *,
                 audit_pool=None, awake=None, force=False, clock=utcnow,
                 monotonic=time.monotonic, flush=None, telemetry=None):
        if flush is None:
            from ..db import flush_outbox
            flush = flush_outbox
        self.telemetry = telemetry or AsyncTelemetry(archive)
        self.owns_telemetry = telemetry is None
        self.archive, self.feed_pool, self.schedule_pool = archive, feed_pool, schedule_pool
        self.outbox_pool, self.audit_pool, self.client = outbox_pool, audit_pool or outbox_pool, client
        self.awake, self.force, self.clock, self.monotonic, self.flush = awake, force, clock, monotonic, flush
        self.inflight, self.due, self.feed_health = {}, {}, {}
        self.dispatch_times = {}
        self.last_dispatch = {}
        self.last_valid_receipts = {}
        self.last_valid_gaps = {}
        with archive.connect() as db:
            for name in FEEDS:
                row = db.execute("SELECT received_at FROM receipts WHERE feed=? AND status='valid' "
                                 "AND received_at<=? ORDER BY received_at DESC LIMIT 1",
                                 (name, clock().astimezone(timezone.utc).isoformat())).fetchone()
                if row:
                    self.last_valid_receipts[name] = row[0]
        self.schedule_job = self.outbox_job = self.audit_job = None
        self.schedule = latest_schedule(archive, clock())
        self.refresh_retry_at = 0.0
        self.prepared_day = self.active_day = None
        self.pending_audits = []
        initial_local = clock().astimezone(BRISBANE)
        if initial_local.weekday() < 5 and initial_local.hour >= 12:
            self.pending_audits.append(initial_local.date().isoformat())
        self.last_clock = clock()
        self.last_status = float('-inf')
        self.schedule_error = None
        self.outbox_retry_at = 0.0
        self.outbox_failures = 0
        self.outbox_health = {}
        self.retry_not_before = {}
        if in_window(self.last_clock):
            start = window_start(self.last_clock).astimezone(timezone.utc)
            with archive.connect() as db:
                previous = db.execute("SELECT received_at FROM receipts WHERE feed='TripUpdates' AND status='valid' "
                                      "AND received_at<=? ORDER BY received_at DESC LIMIT 1",
                                      (self.last_clock.astimezone(timezone.utc).isoformat(),)).fetchone()
            previous_time = datetime.fromisoformat(previous[0]).astimezone(timezone.utc) if previous else start
            gap_start = max(start, previous_time)
            if (self.last_clock - gap_start).total_seconds() > 35:
                self.telemetry.gap(gap_start, self.last_clock, "all",
                            "Recorder startup missing preceding window receipts", detected_at=self.last_clock)

    def _drain(self, now, mono):
        for name in list(self.inflight):
            future = self.inflight[name]
            if not future.done():
                continue
            self.inflight.pop(name)
            self.dispatch_times.pop(name, None)
            try:
                result = future.result()
                details = json.loads(result.get("details", "{}"))
                if result.get("status") == "valid" and result.get("received_at"):
                    previous = self.last_valid_receipts.get(name)
                    received = result["received_at"]
                    if previous and received >= previous:
                        self.last_valid_gaps[name] = max(0, (datetime.fromisoformat(received) -
                                                           datetime.fromisoformat(previous)).total_seconds())
                    if previous is None or received >= previous:
                        self.last_valid_receipts[name] = received
                self.retry_not_before[name] = result.get("retry_not_before", 0)
                self.feed_health[name] = {"runtime_timing": result.get("runtime_timing", {}),
                    "phase_at": details.get("phase_at"), "submitted_at": details.get("submitted_at"),
                    "scheduler_delay_seconds": details.get("scheduler_delay_seconds"),
                    "task_start_delay_seconds": details.get("task_start_delay_seconds"),
                    "status": result.get("status"),
                    "received_at": result.get("received_at"),
                    "request_started_at": details.get("request_started_at", result.get("request_started_at")),
                    "request_elapsed_seconds": details.get("request_elapsed_seconds", result.get("request_elapsed_seconds")),
                    "attempts": details.get("attempts", result.get("attempts", [])),
                    "error": result.get("error")}
            except Exception as exc:
                self.feed_health[name] = {"status": "failed", "error": str(exc)[:500]}
                self.telemetry.gap(now, now, name, f"feed worker failed: {str(exc)[:500]}", detected_at=now)
            self.telemetry.log({"feed": name, **self.feed_health[name]})
        if self.schedule_job is not None and self.schedule_job.done():
            try:
                self.schedule = self.schedule_job.result()
                self.schedule_error = None
            except Exception as exc:
                self.schedule_error = str(exc)[:500]
                self.telemetry.gap(self.refresh_started, now, "GTFS", f"schedule refresh failed: {self.schedule_error}", detected_at=now)
                self.refresh_retry_at = mono + 300
                self.telemetry.log({"schedule_refresh_failed": self.schedule_error})
            self.schedule_job = None
        for attr in ("outbox_job", "audit_job"):
            future = getattr(self, attr)
            if future is not None and future.done():
                try:
                    result = future.result()
                    if attr == "audit_job":
                        self.telemetry.log(result)
                    else:
                        self.outbox_health = result or {}
                        if self.outbox_health.get("failed"):
                            self.outbox_failures += 1
                            self.outbox_retry_at = mono + min(300, 5 * 2 ** min(self.outbox_failures - 1, 6))
                        else:
                            self.outbox_failures = 0
                            self.outbox_retry_at = mono + 5
                except Exception as exc:
                    self.telemetry.log({"worker": attr, "error": str(exc)[:500]})
                    if attr == "outbox_job":
                        self.outbox_failures += 1
                        self.outbox_retry_at = mono + min(300, 5 * 2 ** min(self.outbox_failures - 1, 6))
                        self.outbox_health = {"failed": True, "error": str(exc)[:500]}
                setattr(self, attr, None)

    def tick(self, now=None, monotonic_now=None):
        controlled_tick = now is not None or monotonic_now is not None
        now = self.clock() if now is None else now
        mono = self.monotonic() if monotonic_now is None else monotonic_now
        active, preparing = in_window(now), preparation_active(now)
        if self.awake:
            try:
                self.awake.set(preparing or bool(self.inflight))
            except (OSError, subprocess.SubprocessError) as exc:
                self.telemetry.log({"awake_error": str(exc)[:500]})
        self._drain(now, mono)
        if (now - self.last_clock).total_seconds() > 45 and active:
            self.telemetry.gap(self.last_clock, now, "all", "scheduler discontinuity, possibly laptop sleep", detected_at=now)
        self.last_clock = now
        day = now.astimezone(BRISBANE).date().isoformat()
        if self.active_day and (not active or self.active_day != day):
            self.pending_audits.append(self.active_day)
            self.active_day = None
            self.due.clear()
        if active and self.active_day != day:
            self.active_day = day
            # Map 06:00 wall boundary to monotonic phase, including a mid-window restart.
            phase = mono - (now - window_start(now)).total_seconds()
            self.due = {name: phase for name in FEEDS}
        if self.force and not self.due:
            self.due = {name: mono for name in FEEDS}
        if preparing or self.force:
            stale = not self.schedule or (now - datetime.fromisoformat(self.schedule["received_at"])).total_seconds() >= 86400
            warmup = preparing and self.prepared_day != day
            if self.schedule_job is None and mono >= self.refresh_retry_at and (stale or warmup or self.schedule_error):
                self.refresh_started = now
                self.schedule_job = self.schedule_pool.submit(refresh_schedule, self.archive)
                self.prepared_day = day
        if active or self.force:
            for name in FEEDS:
                # Recheck actual time after any preceding work and before admission.
                # Explicit tick snapshots remain deterministic for fault tests.
                submitted_at = now if controlled_tick else self.clock()
                submitted_mono = mono if controlled_tick else self.monotonic()
                if submitted_mono >= self.due[name]:
                    phase_deadline = self.due[name] + int((submitted_mono - self.due[name]) // POLL_SECONDS[name]) * POLL_SECONDS[name]
                    # Consume every elapsed slot even if busy or now outside window.
                    self.due[name] = next_phase_deadline(self.due[name], POLL_SECONDS[name], submitted_mono)
                    # A delayed/initial dispatch near the next phase must not burst.
                    spaced = name not in self.last_dispatch or submitted_mono - self.last_dispatch[name] >= MIN_DISPATCH_SECONDS[name]
                    eligible = self.force or in_window(submitted_at)
                    if (eligible and name not in self.inflight and spaced
                            and submitted_at.timestamp() >= self.retry_not_before.get(name, 0)):
                        digest = self.schedule["sha256"] if self.schedule else None
                        phase_at = datetime.fromtimestamp(now.timestamp() - (mono - phase_deadline), timezone.utc)
                        dispatch = {"phase_at": phase_at.isoformat(), "submitted_at": submitted_at.isoformat(),
                                    "submitted_monotonic": submitted_mono,
                                    "scheduler_delay_seconds": max(0, submitted_mono - phase_deadline)}
                        self.inflight[name] = self.feed_pool.submit(fetch_feed, self.archive, name, digest, self.client,
                                                                  dispatch=dispatch, telemetry=self.telemetry)
                        self.dispatch_times[name] = {"started_at": submitted_at.isoformat(), "monotonic": submitted_mono}
                        self.last_dispatch[name] = submitted_mono
            if self.outbox_job is None and mono >= self.outbox_retry_at:
                self.outbox_job = self.outbox_pool.submit(self.flush, self.archive)
        if self.pending_audits and not self.inflight and self.audit_job is None:
            completed_day = self.pending_audits.pop(0)
            if not (self.archive.root / "runtime" / f"coverage-{completed_day}.json").exists():
                self.audit_job = self.audit_pool.submit(audit_window, self.archive, completed_day)
        if mono - self.last_status >= 5 or not active:
            health = {}
            for name in FEEDS:
                valid_at = self.last_valid_receipts.get(name)
                age = max(0, (now - datetime.fromisoformat(valid_at)).total_seconds()) if valid_at else None
                limit = 65 if name == "Alerts" else 35
                inflight_age = max(0, mono - self.dispatch_times[name]["monotonic"]) if name in self.dispatch_times else None
                warning = None
                if active or self.force:
                    if age is None:
                        warning = "no_valid_receipt"
                    elif age > limit:
                        warning = "valid_receipt_age_exceeds_limit"
                    if inflight_age is not None and inflight_age > limit:
                        warning = "inflight_elapsed_exceeds_limit"
                health[name] = {**self.feed_health.get(name, {}),
                    "last_valid_received_at": valid_at, "receipt_age_seconds": age,
                    "last_valid_inter_receipt_gap_seconds": self.last_valid_gaps.get(name),
                    "max_allowed_gap_seconds": limit, "warning": warning}
            available_schedule = self.schedule if self.schedule and datetime.fromisoformat(self.schedule["received_at"]) <= now else None
            status = {"pid": os.getpid(), "heartbeat_at": now.isoformat(),
                      "window_active": active, "preparation_active": preparing, "force": self.force,
                      "collector_policy": POLICY, "poll_intervals_seconds": POLL_SECONDS,
                      "minimum_dispatch_spacing_seconds": MIN_DISPATCH_SECONDS,
                      "telemetry": self.telemetry.health(),
                      "awake": self.awake.health() if self.awake and hasattr(self.awake, "health") else None,
                      "workers": {"feed_pending": len(self.inflight), "schedule_pending": self.schedule_job is not None,
                                  "outbox_pending": self.outbox_job is not None, "audit_pending": self.audit_job is not None},
                      "outbox": {**self.outbox_health, "consecutive_failures": self.outbox_failures,
                                 "retry_in_seconds": max(0, self.outbox_retry_at - mono)},
                      "schedule_refresh_pending": self.schedule_job is not None,
                      "available_gtfs_sha256": available_schedule["sha256"] if available_schedule else None,
                      "schedule_refresh_error": self.schedule_error,
                      "inflight_feeds": list(self.inflight),
                      "inflight_requests": {name: {"dispatched_at": value["started_at"],
                          "elapsed_seconds": max(0, mono - value["monotonic"])}
                          for name, value in self.dispatch_times.items()}, "feeds": health}
            self.telemetry.status(status)
            self.last_status = mono
        boundary_wait = (next_boundary(now) - now).total_seconds()
        return min(.5 if active or self.force or self.inflight else 30, max(0, boundary_wait))

    def close(self):
        # Do not cancel or lose responses already dispatched at the window boundary.
        for future in self.inflight.values():
            try:
                future.result()
            except Exception:
                pass  # _drain records worker failures and still processes other feeds.
        if self.schedule_job is not None:
            try:
                self.schedule_job.result()
            except Exception:
                pass  # _drain records the refresh failure with its real end time.
        self._drain(self.clock(), self.monotonic())
        if self.owns_telemetry:
            self.telemetry.close()


def collect(archive: Archive, *, force=False, once=False):
    with recorder_lock(archive.root):
        recovery = archive.recover_pending()
        print({"pending_capture_recovery": recovery}, flush=True)
        awake = WindowAwake()
        stop_event = threading.Event()
        previous_term = None
        if threading.current_thread() is threading.main_thread():
            previous_term = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, lambda signum, frame: stop_event.set())
        try:
            return _collect(archive, force=force, once=once, awake=awake, stop_event=stop_event)
        finally:
            awake.close()
            if previous_term is not None:
                signal.signal(signal.SIGTERM, previous_term)


def _collect(archive: Archive, *, force=False, once=False, awake=None, stop_event=None):
    stop_event = stop_event or threading.Event()
    with feed_client() as client, \
            ThreadPoolExecutor(max_workers=3) as feed_pool, \
            ThreadPoolExecutor(max_workers=1) as schedule_pool, \
            ThreadPoolExecutor(max_workers=1) as outbox_pool, \
            ThreadPoolExecutor(max_workers=1) as audit_pool:
        loop = CollectorLoop(archive, feed_pool, schedule_pool, outbox_pool, client,
                             audit_pool=audit_pool, awake=awake, force=force)
        try:
            while not stop_event.is_set():
                delay = loop.tick()
                if once:
                    return
                stop_event.wait(delay)
        finally:
            loop.close()
