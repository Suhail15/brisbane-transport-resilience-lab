import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from google.transit import gtfs_realtime_pb2

from resilience.pipeline import collector
from resilience.pipeline.archive import Archive, FEEDS
from resilience.pipeline.collector_schedule import (
    BRISBANE,
    in_window,
    next_boundary,
    next_phase_deadline,
    preparation_active,
)
from resilience.pipeline.coverage import coverage_report


SERVICE_DATE = date(2026, 10, 12)  # Monday, Brisbane time


def local_at(day, hour, minute=0, second=0):
    return datetime.combine(day, time(hour, minute, second), BRISBANE)


def full_feed():
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    return message.SerializeToString()


def valid_result(name, received_at):
    return {
        "feed": name,
        "status": "valid",
        "received_at": received_at.astimezone(timezone.utc).isoformat(),
        "details": json.dumps({"request_started_at": received_at.isoformat(), "attempts": []}),
    }


class ControlledFuture:
    def __init__(self):
        self._done = False
        self._result = None
        self._error = None

    def done(self):
        return self._done

    def result(self):
        if not self._done:
            raise RuntimeError("test future has not been completed")
        if self._error:
            raise self._error
        return self._result

    def set_result(self, value):
        self._result, self._done = value, True

    def set_exception(self, error):
        self._error, self._done = error, True


class ControlledPool:
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        future = ControlledFuture()
        self.jobs.append(SimpleNamespace(function=function, args=args, kwargs=kwargs, future=future))
        return future

    def named(self, name):
        return [job for job in self.jobs if len(job.args) > 1 and job.args[1] == name]


def resolve_feed_jobs(pool, *, at):
    for job in pool.jobs:
        if job.future.done():
            continue
        name = job.args[1]
        job.future.set_result(valid_result(name, at))


def resolve_non_feed(pool, result=None):
    for job in pool.jobs:
        if not job.future.done():
            job.future.set_result(result)


def make_loop(archive, *, clock_at, feed_pool=None, schedule_pool=None,
              outbox_pool=None, audit_pool=None):
    feed_pool = feed_pool or ControlledPool()
    schedule_pool = schedule_pool or ControlledPool()
    outbox_pool = outbox_pool or ControlledPool()
    audit_pool = audit_pool or ControlledPool()
    loop = collector.CollectorLoop(
        archive,
        feed_pool,
        schedule_pool,
        outbox_pool,
        client=object(),
        clock=lambda: clock_at,
        flush=lambda _archive: None,
        audit_pool=audit_pool,
    )
    return loop, feed_pool, schedule_pool, outbox_pool, audit_pool


def test_fixed_phase_corrects_repeated_half_second_lateness(tmp_path):
    archive = Archive(tmp_path / "fixture")
    start = local_at(SERVICE_DATE, 6)
    loop, feed_pool, schedule_pool, _, _ = make_loop(archive, clock_at=start)

    loop.tick(now=start, monotonic_now=100.0)
    resolve_feed_jobs(feed_pool, at=start + timedelta(milliseconds=200))
    jitter = (0.5, 3.5, 0.5, 3.5, 0.5)
    for slot, lateness in enumerate(jitter, start=1):
        tick_mono = 100.0 + slot * 15 + lateness
        loop.tick(now=start + timedelta(seconds=slot * 15 + lateness), monotonic_now=tick_mono)
        assert loop.due["TripUpdates"] == 100.0 + (slot + 1) * 15
        assert len(feed_pool.named("TripUpdates")) == slot + 1
        resolve_feed_jobs(feed_pool, at=start + timedelta(seconds=slot * 15 + lateness + 0.2))

    assert next_phase_deadline(100.0, 15, 100.5) == 115.0
    assert next_phase_deadline(115.0, 15, 221.5) == 235.0
    resolve_non_feed(schedule_pool)
    resolve_feed_jobs(feed_pool, at=start + timedelta(seconds=126))
    loop.close()


def test_missed_slots_do_not_burst_and_slow_feed_does_not_block_others(tmp_path):
    archive = Archive(tmp_path / "fixture")
    start = local_at(SERVICE_DATE, 6)
    loop, feed_pool, schedule_pool, outbox_pool, _ = make_loop(archive, clock_at=start)

    loop.tick(now=start, monotonic_now=0.0)
    # Keep TripUpdates in flight while the other workers finish normally.
    for name in ("VehiclePositions", "Alerts"):
        job = feed_pool.named(name)[0]
        job.future.set_result(valid_result(name, start + timedelta(seconds=1)))

    loop.tick(now=start + timedelta(seconds=15), monotonic_now=15.0)
    assert len(feed_pool.named("TripUpdates")) == 1
    assert len(feed_pool.named("VehiclePositions")) == 2
    feed_pool.named("VehiclePositions")[1].future.set_result(
        valid_result("VehiclePositions", start + timedelta(seconds=26))
    )

    # Skip several elapsed slots. Healthy feeds get one request each, while the
    # busy feed neither overlaps nor catches up in a burst.
    late = start + timedelta(seconds=121)
    loop.tick(now=late, monotonic_now=121.0)
    assert len(feed_pool.named("TripUpdates")) == 1
    assert len(feed_pool.named("VehiclePositions")) == 3
    assert len(feed_pool.named("Alerts")) == 2
    before = {name: len(feed_pool.named(name)) for name in FEEDS}
    loop.tick(now=late + timedelta(milliseconds=100), monotonic_now=121.1)
    assert {name: len(feed_pool.named(name)) for name in FEEDS} == before
    assert len(outbox_pool.jobs) == 1  # A pending outbox worker does not stall feed dispatch.

    feed_pool.named("TripUpdates")[0].future.set_result(
        valid_result("TripUpdates", start + timedelta(seconds=122))
    )
    feed_pool.named("VehiclePositions")[2].future.set_result(
        valid_result("VehiclePositions", start + timedelta(seconds=122))
    )
    loop.tick(now=start + timedelta(seconds=135), monotonic_now=135.0)
    assert len(feed_pool.named("TripUpdates")) == 2
    assert len(feed_pool.named("VehiclePositions")) == 4
    assert len(feed_pool.named("Alerts")) == 2
    resolve_feed_jobs(feed_pool, at=start + timedelta(seconds=136))
    resolve_non_feed(schedule_pool)
    loop.close()


@pytest.mark.parametrize(
    "feed,phase_seconds,next_phase_seconds",
    [
        ("TripUpdates", 15, 30),
        ("VehiclePositions", 15, 30),
        ("Alerts", 45, 90),
    ],
)
def test_rapid_success_after_mid_window_restart_waits_for_spacing_for_every_feed(
    tmp_path, feed, phase_seconds, next_phase_seconds
):
    archive = Archive(tmp_path / "fixture")
    start = local_at(SERVICE_DATE, 6) + timedelta(seconds=phase_seconds - 0.1)
    loop, feed_pool, schedule_pool, _, _ = make_loop(archive, clock_at=start)

    loop.tick(now=start, monotonic_now=100.0)
    assert len(feed_pool.named(feed)) == 1
    feed_pool.named(feed)[0].future.set_result(
        valid_result(feed, start + timedelta(milliseconds=50))
    )

    loop.tick(
        now=local_at(SERVICE_DATE, 6) + timedelta(seconds=phase_seconds),
        monotonic_now=100.1,
    )
    assert len(feed_pool.named(feed)) == 1

    next_mono = 100.0 + (next_phase_seconds - (phase_seconds - 0.1))
    loop.tick(
        now=local_at(SERVICE_DATE, 6) + timedelta(seconds=next_phase_seconds),
        monotonic_now=next_mono,
    )
    assert len(feed_pool.named(feed)) == 2
    assert loop.last_dispatch[feed] == pytest.approx(next_mono)

    resolve_feed_jobs(feed_pool, at=start + timedelta(seconds=next_phase_seconds + 1))
    resolve_non_feed(schedule_pool, {"sha256": "prepared"})
    loop.close()


def test_preparation_window_edges_noon_drain_and_weekday_boundaries(tmp_path):
    archive = Archive(tmp_path / "fixture")
    prewarm = local_at(SERVICE_DATE, 5, 50)
    loop, feed_pool, schedule_pool, outbox_pool, audit_pool = make_loop(archive, clock_at=prewarm)

    loop.tick(now=prewarm, monotonic_now=0.0)
    assert len(schedule_pool.jobs) == 1
    assert not feed_pool.jobs
    loop.tick(now=prewarm + timedelta(minutes=9, seconds=59), monotonic_now=599.0)
    assert not feed_pool.jobs

    window_start = local_at(SERVICE_DATE, 6)
    loop.tick(now=window_start, monotonic_now=600.0)
    assert {name: len(feed_pool.named(name)) for name in FEEDS} == {
        "TripUpdates": 1,
        "VehiclePositions": 1,
        "Alerts": 1,
    }
    assert all(job.args[2] is None for job in feed_pool.jobs)
    assert len(outbox_pool.jobs) == 1

    noon = local_at(SERVICE_DATE, 12)
    loop.tick(now=noon, monotonic_now=22_200.0)
    assert {name: len(feed_pool.named(name)) for name in FEEDS} == {
        "TripUpdates": 1,
        "VehiclePositions": 1,
        "Alerts": 1,
    }
    resolve_feed_jobs(feed_pool, at=noon + timedelta(milliseconds=500))
    loop.tick(now=noon + timedelta(seconds=1), monotonic_now=22_201.0)
    assert loop.feed_health.keys() == FEEDS.keys()
    assert len(audit_pool.jobs) == 1
    assert audit_pool.jobs[0].args[1] == SERVICE_DATE.isoformat()

    resolve_non_feed(schedule_pool, {"sha256": "prepared-after-dispatch"})
    loop.close()

    assert preparation_active(prewarm)
    assert not preparation_active(prewarm - timedelta(seconds=1))
    assert not preparation_active(noon)
    assert in_window(window_start)
    assert not in_window(noon)
    assert next_boundary(prewarm - timedelta(seconds=30)) == prewarm
    assert next_boundary(prewarm) == window_start
    friday_noon = local_at(date(2026, 10, 9), 12)
    assert next_boundary(friday_noon) == local_at(date(2026, 10, 12), 5, 50)
    sunday = local_at(date(2026, 10, 11), 10)
    assert next_boundary(sunday) == local_at(date(2026, 10, 12), 5, 50)


@pytest.mark.parametrize("force,expected_jobs", [(False, 0), (True, 3)])
def test_submit_boundary_rechecks_noon_but_preserves_forced_development_capture(
    tmp_path, force, expected_jobs
):
    archive = Archive(tmp_path / f"fixture-{force}")
    before_noon = local_at(SERVICE_DATE, 11, 59, 59)
    after_noon = local_at(SERVICE_DATE, 12, 0, 1)

    class BoundaryClock:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            call = self.calls
            self.calls += 1
            if call < 7:  # Constructor snapshots, then tick's observed 11:59:59 time.
                return before_noon
            return after_noon + timedelta(seconds=call - 7)

    feed_pool, schedule_pool, outbox_pool = ControlledPool(), ControlledPool(), ControlledPool()
    loop = collector.CollectorLoop(
        archive,
        feed_pool,
        schedule_pool,
        outbox_pool,
        client=object(),
        force=force,
        clock=BoundaryClock(),
        monotonic=lambda: 100.0,
        flush=lambda _archive: None,
    )
    loop.tick()

    assert len(feed_pool.jobs) == expected_jobs
    if force:
        assert all(job.kwargs["dispatch"]["submitted_at"] >= after_noon.isoformat()
                   for job in feed_pool.jobs)

    for job in feed_pool.jobs:
        job.future.set_result({
            "feed": job.args[1],
            "status": "valid",
            "received_at": after_noon.astimezone(timezone.utc).isoformat(),
        })
    for pool in (schedule_pool, outbox_pool):
        for job in pool.jobs:
            job.future.set_result({"sha256": "prepared"})
    loop.close()


def test_restarted_loop_anchors_phases_and_journals_only_elapsed_missing_time(tmp_path):
    archive = Archive(tmp_path / "fixture")
    yesterday = local_at(SERVICE_DATE, 11, 59, 50)
    archive.append("TripUpdates", full_feed(), yesterday, FEEDS["TripUpdates"])
    next_day = date(2026, 10, 13)
    start = local_at(next_day, 6)
    loop, feed_pool, schedule_pool, _, _ = make_loop(archive, clock_at=start)

    loop.tick(now=start, monotonic_now=50_000.0)

    assert loop.active_day == next_day.isoformat()
    assert loop.due == {
        "TripUpdates": 50_015.0,
        "VehiclePositions": 50_015.0,
        "Alerts": 50_045.0,
    }
    assert not any(
        "Recorder startup missing preceding window receipts" in gap["reason"]
        for gap in archive.known_gaps(start + timedelta(minutes=1))
    )
    resolve_feed_jobs(feed_pool, at=start + timedelta(milliseconds=200))
    resolve_non_feed(schedule_pool, {"sha256": "prepared"})
    loop.close()

    late_start = start + timedelta(minutes=1)
    late_loop, _, _, _, _ = make_loop(archive, clock_at=late_start)
    late_loop.close()  # Drain the asynchronous startup-gap event before inspecting the journal.
    startup_gaps = [
        gap
        for gap in archive.known_gaps(late_start + timedelta(minutes=1))
        if "Recorder startup missing preceding window receipts" in gap["reason"]
    ]
    assert len(startup_gaps) == 1
    assert (
        datetime.fromisoformat(startup_gaps[0]["ended_at"])
        - datetime.fromisoformat(startup_gaps[0]["started_at"])
    ).total_seconds() == 60
    late_loop.close()


class Sequence:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class Response:
    status_code = 200

    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_metadata_preserves_measured_failure_and_v3_counterfactual_margin(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    first_start = local_at(SERVICE_DATE, 6)
    # Counterfactual collector-v3 phase: the observed 7 October HTTP durations
    # are replayed at 15 seconds; this does not rewrite the measured old receipts.
    second_start = first_start + timedelta(seconds=15)
    client = FakeClient([Response(full_feed()), Response(full_feed())])
    monkeypatch.setattr(
        collector,
        "utcnow",
        Sequence(
            [
                first_start,
                first_start,
                first_start + timedelta(seconds=0.274174),
                second_start,
                second_start,
                first_start + timedelta(seconds=22.066556),
            ]
        ),
    )
    monotonic = Sequence([
        100.0, 100.0, 100.274174, 100.274174, 100.274174,
        200.0, 200.0, 207.066556, 207.066556, 207.066556,
    ])
    monkeypatch.setattr(collector, "time", SimpleNamespace(monotonic=monotonic, sleep=lambda _s: None))

    first = collector.fetch_feed(archive, "TripUpdates", None, client)
    second = collector.fetch_feed(archive, "TripUpdates", None, client)
    first_received = datetime.fromisoformat(first["received_at"])
    second_received = datetime.fromisoformat(second["received_at"])
    first_details = json.loads(first["details"])
    second_details = json.loads(second["details"])

    assert client.urls == [FEEDS["TripUpdates"], FEEDS["TripUpdates"]]
    assert second_details["collector_policy"] == "collector-v3"
    assert second_details["poll_interval_seconds"] == 15
    assert [attempt["attempt"] for attempt in second_details["attempts"]] == [1]
    assert second_details["request_started_at"] == second_start.isoformat()
    assert second_details["attempts"][0]["started_at"] == second_start.isoformat()
    assert first_details["request_elapsed_seconds"] == pytest.approx(0.274174)
    assert second_details["request_elapsed_seconds"] == pytest.approx(7.066556)
    assert (second_received - first_received).total_seconds() == pytest.approx(21.792382)

    # Keep the measured 7 October failure and both approved counterfactual margins
    # distinct. The measured old 30.190457s dispatch spacing exceeded the strict
    # 35s ceiling after the observed latency grew from 0.274174s to 7.066556s.
    measured_old_gap = 30.190457 + 7.066556 - 0.274174
    v2_counterfactual_gap = 25 + 7.066556 - 0.274174
    v3_counterfactual_gap = 15 + 7.066556 - 0.274174
    assert measured_old_gap == pytest.approx(36.982839)
    assert measured_old_gap > 35
    assert v2_counterfactual_gap == pytest.approx(31.792382)
    assert v3_counterfactual_gap == pytest.approx(21.792382)

    # A 3.5s late worker still has margin with v3; severe 13.5s lateness remains
    # visible as a strict-ceiling violation instead of being called healthy.
    assert v3_counterfactual_gap + 3.5 < 35
    assert v3_counterfactual_gap + 13.5 > 35

    trip_updates = coverage_report(archive)["windows"][0]["feeds"]["TripUpdates"]
    assert trip_updates["max_allowed_gap_seconds"] == 35
    assert not any(
        datetime.fromisoformat(gap["start"]) == first_received
        and datetime.fromisoformat(gap["end"]) == second_received
        for gap in trip_updates["gaps"]
    )
    assert not trip_updates["complete"]  # Two receipts cannot make a six-hour morning complete.


def test_outage_previous_day_receipt_and_malformed_payload_do_not_pass_coverage(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    previous_weekday = local_at(date(2026, 10, 9), 6)
    archive.append("TripUpdates", full_feed(), previous_weekday, FEEDS["TripUpdates"])

    current_start = local_at(SERVICE_DATE, 6)
    failing_client = FakeClient([httpx.ConnectError("offline")] * 3)
    monkeypatch.setattr(
        collector,
        "utcnow",
        Sequence([current_start, current_start, current_start, current_start, current_start]),
    )
    monkeypatch.setattr(
        collector,
        "time",
        SimpleNamespace(
            monotonic=Sequence([10, 10, 10.1, 10.1, 10.2, 10.2, 10.3, 10.3]),
            sleep=lambda _s: None,
        ),
    )
    failed = collector.fetch_feed(archive, "TripUpdates", None, failing_client)
    assert failed["status"] == "failed"
    assert len(failed["attempts"]) == 3
    current_trip_updates = [
        row
        for row in archive.records("TripUpdates", current_start + timedelta(hours=1))
        if datetime.fromisoformat(row["received_at"]) >= current_start.astimezone(timezone.utc)
    ]
    assert not current_trip_updates
    assert archive.known_gaps(current_start + timedelta(hours=1))

    malformed = archive.append(
        "Alerts", b"not a protobuf", current_start, FEEDS["Alerts"]
    )
    assert malformed["status"] == "quarantined"
    report = coverage_report(archive)
    monday = next(window for window in report["windows"] if window["service_date"] == SERVICE_DATE.isoformat())
    assert report["complete_weekday_windows"] == 0
    assert monday["feeds"]["TripUpdates"]["receipts"] == 0
    assert monday["feeds"]["TripUpdates"]["max_allowed_gap_seconds"] == 35
    assert monday["feeds"]["VehiclePositions"]["max_allowed_gap_seconds"] == 35
    assert monday["feeds"]["Alerts"]["receipts"] == 0
    assert monday["feeds"]["Alerts"]["max_allowed_gap_seconds"] == 65
    assert archive.root == tmp_path / "fixture"
