import gzip
import json
import threading
from email.utils import format_datetime
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2
import httpx

from resilience.pipeline import collector
from resilience.pipeline.archive import Archive, FEEDS
from resilience.pipeline.collector_schedule import BRISBANE
from resilience.pipeline.collector_telemetry import AsyncTelemetry
from resilience import db as resilience_db


SERVICE_DATE = date(2026, 10, 12)


def local_at(hour, minute=0, second=0):
    return datetime.combine(SERVICE_DATE, time(hour, minute, second), BRISBANE)


def full_feed(entity_count=0):
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    for index in range(entity_count):
        message.entity.add(id=f"entity-{index}")
    return message.SerializeToString()


class ControlledFuture:
    def __init__(self):
        self.ready = False
        self.value = None

    def done(self):
        return self.ready

    def result(self):
        if not self.ready:
            raise RuntimeError("test future has not been completed")
        return self.value

    def set_result(self, value=None):
        self.value = value
        self.ready = True


class ControlledPool:
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        job = SimpleNamespace(function=function, args=args, kwargs=kwargs, future=ControlledFuture())
        self.jobs.append(job)
        return job.future


class SlowResponse:
    status_code = 200

    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class Sequence:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


def test_stalled_telemetry_coalesces_status_and_keeps_gaps_while_workers_progress(tmp_path):
    archive = Archive(tmp_path / "fixture")
    entered = threading.Event()
    release = threading.Event()
    written_statuses = []
    written_logs = []

    def stalled_writer(_path, contents):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("test did not release the simulated stalled writer")
        written_statuses.append(json.loads(contents))

    telemetry = AsyncTelemetry(archive, writer=stalled_writer, logger=written_logs.append)
    feed_pool, schedule_pool, outbox_pool, audit_pool = (
        ControlledPool(), ControlledPool(), ControlledPool(), ControlledPool()
    )
    window_start = local_at(6)
    loop = collector.CollectorLoop(
        archive,
        feed_pool,
        schedule_pool,
        outbox_pool,
        client=object(),
        audit_pool=audit_pool,
        clock=lambda: window_start,
        monotonic=lambda: 600.0,
        flush=lambda _archive: None,
        telemetry=telemetry,
    )
    gap_detected = window_start + timedelta(seconds=20)
    try:
        loop.tick(now=window_start, monotonic_now=600.0)
        assert entered.wait(2), "telemetry worker did not enter the injected stall"

        # GTFS preparation is still in flight when feed work begins. Its separate
        # worker cannot delay the three feed submissions or the bounded tick.
        loop.tick(now=window_start, monotonic_now=600.0)
        assert len(schedule_pool.jobs) == 1
        assert len(feed_pool.jobs) == 3
        assert len(outbox_pool.jobs) == 1

        for job in feed_pool.jobs:
            if job.args[1] in {"VehiclePositions", "Alerts"}:
                job.future.set_result({
                    "feed": job.args[1],
                    "status": "valid",
                    "received_at": window_start.isoformat(),
                })
        loop.tick(now=window_start + timedelta(seconds=15), monotonic_now=615.0)
        assert len(feed_pool.jobs) == 4  # TripUpdates stays in flight; VehiclePositions advances.
        assert len(schedule_pool.jobs) == 1
        assert len(outbox_pool.jobs) == 1  # A pending outbox batch is not resubmitted.

        telemetry.log({"event": "one"})
        telemetry.log({"event": "two"})
        telemetry.gap(
            window_start,
            window_start + timedelta(seconds=10),
            "TripUpdates",
            "simulated delayed persistence",
            detected_at=gap_detected,
        )
        for index in range(20):
            telemetry.status({"heartbeat_at": f"latest-{index}"})

        state = telemetry.health()
        assert state["busy"]
        assert state["pending_events"] == 5
        assert state["status_pending"]
        assert telemetry.wait_idle(timeout=0.01) is False
    finally:
        release.set()
        for job in feed_pool.jobs:
            if not job.future.done():
                job.future.set_result({
                    "feed": job.args[1],
                    "status": "valid",
                    "received_at": window_start.isoformat(),
                })
        loop.close()
        telemetry.close()

    assert len(written_statuses) <= 3  # Initial and latest snapshots only; intermediate status coalesces.
    assert telemetry.health()["pending_events"] == 0
    gaps = archive.known_gaps(gap_detected - timedelta(microseconds=1))
    assert not any(gap["reason"] == "simulated delayed persistence" for gap in gaps)
    gaps = archive.known_gaps(gap_detected)
    retained = [gap for gap in gaps if gap["reason"] == "simulated delayed persistence"]
    assert len(retained) == 1
    assert retained[0]["detected_at"] == gap_detected.astimezone(timezone.utc).isoformat()
    assert len([event for event in written_statuses if event.get("heartbeat_at") == "latest-19"]) == 1
    assert {event["event"] for event in written_logs if "event" in event} >= {"one", "two"}


def test_fetch_retries_at_most_three_times_and_keeps_a_slow_successful_full_body(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    payload = full_feed(entity_count=2500)
    received_at = datetime(2026, 10, 12, 6, 1, tzinfo=BRISBANE)

    class Client:
        def __init__(self):
            self.responses = iter([
                OSError("temporary socket reset"),
                OSError("temporary read reset"),
                SlowResponse(payload),
            ])
            self.calls = 0

        def get(self, _url):
            self.calls += 1
            response = next(self.responses)
            if isinstance(response, Exception):
                raise response
            return response

    client = Client()
    sleeps = []
    monkeypatch.setattr(collector, "utcnow", Sequence([
        received_at - timedelta(seconds=30),
        received_at - timedelta(seconds=30),
        received_at - timedelta(seconds=29),
        received_at - timedelta(seconds=28),
        received_at,
    ]))
    # The third attempt takes 21.5 seconds in this controlled clock. A returned
    # successful response is archived in full; receipt time is set at HTTP finish.
    monkeypatch.setattr(collector, "time", SimpleNamespace(
        monotonic=Sequence([0, 0, 0.1, 1.1, 1.2, 2.2, 23.7, 23.7, 23.8]),
        sleep=sleeps.append,
    ))

    result = collector.fetch_feed(archive, "TripUpdates", None, client)

    assert client.calls == 3
    assert sleeps == [1, 2]
    assert result["status"] == "valid"
    assert len(json.loads(result["details"])["attempts"]) == 3
    details = json.loads(result["details"])
    assert [attempt["attempt"] for attempt in details["attempts"]] == [1, 2, 3]
    assert details["attempts"][2]["elapsed_seconds"] == 21.5
    assert details["request_elapsed_seconds"] == 23.7
    assert datetime.fromisoformat(result["received_at"]) == received_at.astimezone(timezone.utc)
    assert archive.read(result) == payload
    assert len(archive.read(result)) == len(payload)


def test_delayed_executor_metadata_and_return_only_archive_timings_are_separate(
    tmp_path, monkeypatch
):
    archive = Archive(tmp_path / "fixture")
    phase_at = local_at(6)
    submitted_at = phase_at + timedelta(milliseconds=500)
    task_started = submitted_at + timedelta(seconds=1.25)
    received = task_started + timedelta(seconds=2)
    client = SimpleNamespace(get=lambda _url: SlowResponse(full_feed(entity_count=2)))
    monkeypatch.setattr(collector, "utcnow", Sequence([task_started, task_started, received]))
    monkeypatch.setattr(collector, "time", SimpleNamespace(
        monotonic=Sequence([101.25, 101.25, 103.25, 103.50, 107.75]),
        sleep=lambda _seconds: None,
    ))

    result = collector.fetch_feed(
        archive,
        "TripUpdates",
        None,
        client,
        dispatch={
            "phase_at": phase_at.isoformat(),
            "submitted_at": submitted_at.isoformat(),
            "submitted_monotonic": 100.0,
            "scheduler_delay_seconds": 0.5,
        },
    )

    receipt = archive.get(result["record_id"])
    metadata = json.loads(receipt["details"])
    assert metadata["phase_at"] == phase_at.isoformat()
    assert metadata["submitted_at"] == submitted_at.isoformat()
    assert metadata["scheduler_delay_seconds"] == 0.5
    assert metadata["task_started_at"] == task_started.isoformat()
    assert metadata["task_start_delay_seconds"] == 1.25
    assert "submitted_monotonic" not in metadata
    assert metadata["request_elapsed_seconds"] == 2.0
    assert metadata["schedule_lookup_seconds"] == 0.25
    assert "runtime_timing" not in receipt
    assert "persistence_elapsed_seconds" not in metadata
    assert result["runtime_timing"] == {
        "persistence_elapsed_seconds": 4.25,
        "task_elapsed_seconds": 6.5,
    }
    assert result["received_at"] == received.astimezone(timezone.utc).isoformat()


def test_retry_after_parsing_handles_finite_malformed_and_http_date():
    now = datetime(2026, 10, 12, 6, tzinfo=BRISBANE).astimezone(timezone.utc)
    response = lambda value: SimpleNamespace(headers={"Retry-After": value})

    assert collector.retry_after_seconds(response("3.5"), now) == 3.5
    assert collector.retry_after_seconds(response("NaN"), now) == 0
    assert collector.retry_after_seconds(response("infinity"), now) == 0
    assert collector.retry_after_seconds(response("not a date"), now) == 0
    future_date = format_datetime(now + timedelta(seconds=30), usegmt=True)
    assert collector.retry_after_seconds(response(future_date), now) == 30
    past_date = format_datetime(now - timedelta(seconds=2), usegmt=True)
    assert collector.retry_after_seconds(response(past_date), now) == 0


def test_exhausted_429_defers_only_its_feed_until_retry_after_deadline(tmp_path, monkeypatch):
    archive = Archive(tmp_path / "fixture")
    start = local_at(6)

    class AdvancingTime:
        def __init__(self):
            self.value = 0.0
            self.sleeps = []

        def monotonic(self):
            return self.value

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.value += seconds

    fake_time = AdvancingTime()
    monkeypatch.setattr(collector, "time", fake_time)
    monkeypatch.setattr(collector, "utcnow", lambda: start + timedelta(seconds=fake_time.value))

    class RateLimitedClient:
        def __init__(self):
            self.calls = 0

        def get(self, _url):
            self.calls += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "120"},
                request=httpx.Request("GET", FEEDS["TripUpdates"]),
            )

    client = RateLimitedClient()
    failed = collector.fetch_feed(archive, "TripUpdates", None, client)
    assert client.calls == 3
    assert fake_time.sleeps == [120, 120]
    assert failed["status"] == "failed"
    assert len(failed["attempts"]) == 3
    assert failed["retry_not_before"] == (start + timedelta(seconds=360)).timestamp()
    assert not [row for row in archive.records("TripUpdates", start + timedelta(hours=1))
                if row["status"] == "valid"]

    feed_pool, schedule_pool, outbox_pool = ControlledPool(), ControlledPool(), ControlledPool()
    loop = collector.CollectorLoop(
        archive,
        feed_pool,
        schedule_pool,
        outbox_pool,
        client=object(),
        clock=lambda: start,
        monotonic=lambda: 600.0,
        flush=lambda _archive: None,
    )
    loop.tick(now=start, monotonic_now=600.0)
    for job in feed_pool.jobs:
        if job.args[1] == "TripUpdates":
            job.future.set_result(failed)
        else:
            job.future.set_result({
                "feed": job.args[1],
                "status": "valid",
                "received_at": start.astimezone(timezone.utc).isoformat(),
            })

    loop.tick(now=start + timedelta(seconds=15), monotonic_now=615.0)
    assert len([job for job in feed_pool.jobs if job.args[1] == "TripUpdates"]) == 1
    assert len([job for job in feed_pool.jobs if job.args[1] == "VehiclePositions"]) == 2

    loop.tick(now=start + timedelta(seconds=359), monotonic_now=959.0)
    assert len([job for job in feed_pool.jobs if job.args[1] == "TripUpdates"]) == 1
    loop.tick(now=start + timedelta(seconds=360), monotonic_now=960.0)
    assert len([job for job in feed_pool.jobs if job.args[1] == "TripUpdates"]) == 2

    for job in feed_pool.jobs:
        if not job.future.done():
            job.future.set_result({
                "feed": job.args[1],
                "status": "valid",
                "received_at": (start + timedelta(seconds=361)).astimezone(timezone.utc).isoformat(),
            })
    for pool in (schedule_pool, outbox_pool):
        for job in pool.jobs:
            if not job.future.done():
                job.future.set_result({"failed": False})
    loop.close()


def test_outage_and_quarantined_payloads_do_not_create_valid_coverage(tmp_path):
    archive = Archive(tmp_path / "fixture")
    malformed = archive.append(
        "Alerts",
        b"not a GTFS realtime protobuf",
        local_at(6),
        FEEDS["Alerts"],
    )

    assert malformed["status"] == "quarantined"
    assert archive.records("Alerts", local_at(7))[0]["status"] == "quarantined"
    assert not archive.latest("Alerts", local_at(7))


def test_outbox_connections_are_bounded_and_cooldown_does_not_delay_feed_phases(
    tmp_path, monkeypatch
):
    connection_calls = []

    class FakeDatabaseConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

    sentinel = FakeDatabaseConnection()

    def fake_connect(url, **kwargs):
        connection_calls.append((url, kwargs))
        return sentinel

    monkeypatch.setattr(resilience_db.psycopg, "connect", fake_connect)
    assert resilience_db.outbox_connect() is sentinel
    assert connection_calls[0][1] == {
        "connect_timeout": 3,
        "options": "-c statement_timeout=3000 -c lock_timeout=1000",
    }

    # A normal persistence call continues using the library's existing defaults;
    # the short PostgreSQL limits are isolated to the outbox helper.
    resilience_db.persist_run({"run_id": "fixture-run", "status": "completed"})
    assert connection_calls[1][1] == {}
    assert connection_calls[2][1] == {}

    archive = Archive(tmp_path / "fixture")
    feed_pool, schedule_pool, outbox_pool = ControlledPool(), ControlledPool(), ControlledPool()
    start = local_at(6)
    loop = collector.CollectorLoop(
        archive,
        feed_pool,
        schedule_pool,
        outbox_pool,
        client=object(),
        clock=lambda: start,
        monotonic=lambda: 600.0,
        flush=lambda _archive: None,
    )
    loop.tick(now=start, monotonic_now=600.0)
    for job in feed_pool.jobs:
        job.future.set_result({
            "feed": job.args[1],
            "status": "valid",
            "received_at": start.astimezone(timezone.utc).isoformat(),
        })
    outbox_pool.jobs[0].future.set_result({"failed": True, "error": "simulated broker timeout"})

    failure_detected = start + timedelta(seconds=14)
    loop.tick(now=failure_detected, monotonic_now=614.0)
    assert loop.outbox_failures == 1
    assert loop.outbox_retry_at == 619.0
    loop.tick(now=start + timedelta(seconds=15), monotonic_now=615.0)
    assert len(feed_pool.jobs) == 5  # TripUpdates and VehiclePositions keep their phase.
    assert len(outbox_pool.jobs) == 1  # Five-second failed-batch cooldown is in effect.

    for job in feed_pool.jobs:
        if not job.future.done():
            job.future.set_result({
                "feed": job.args[1],
                "status": "valid",
                "received_at": (start + timedelta(seconds=16)).astimezone(timezone.utc).isoformat(),
            })
    loop.tick(now=start + timedelta(seconds=19), monotonic_now=619.0)
    assert len(outbox_pool.jobs) == 2
    outbox_pool.jobs[1].future.set_result({"failed": True, "error": "second broker timeout"})
    loop.tick(now=start + timedelta(seconds=20), monotonic_now=620.0)
    assert loop.outbox_failures == 2
    assert loop.outbox_retry_at == 630.0
    loop.tick(now=start + timedelta(seconds=29), monotonic_now=629.0)
    assert len(outbox_pool.jobs) == 2
    loop.tick(now=start + timedelta(seconds=30), monotonic_now=630.0)
    assert len(outbox_pool.jobs) == 3

    for job in feed_pool.jobs:
        if not job.future.done():
            job.future.set_result({
                "feed": job.args[1],
                "status": "valid",
                "received_at": (start + timedelta(seconds=31)).astimezone(timezone.utc).isoformat(),
            })
    if schedule_pool.jobs and not schedule_pool.jobs[0].future.done():
        schedule_pool.jobs[0].future.set_result({"sha256": "prepared"})
    outbox_pool.jobs[2].future.set_result({"failed": False, "published": 1})
    loop.close()
