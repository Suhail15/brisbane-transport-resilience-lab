from datetime import date, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import TZPATH, ZoneInfo

import pytest

from scripts import schedule_collector_wake as wake


def test_default_run_prepares_five_future_weekdays_without_os_calls(tmp_path, capsys):
    now = datetime(2026, 10, 7, 12, 5, tzinfo=ZoneInfo("Australia/Brisbane"))
    calls = []

    def forbidden_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run must not invoke an operating-system command")

    assert wake.main([], repo_root=tmp_path, now=now, runner=forbidden_runner) == 0
    plan_path = tmp_path / "data" / "runtime" / "collector-wake-plan.json"
    assert plan_path.is_file()
    assert "data/runtime" in plan_path.as_posix()
    assert not (tmp_path / "data" / "collector-wake-plan.json").exists()
    assert calls == []

    plan = json.loads(plan_path.read_text())
    assert plan["status"] == "planned"
    assert plan["timezone"] == "Australia/Brisbane"
    assert [event["service_date"] for event in plan["events"]] == [
        "2026-10-08",
        "2026-10-09",
        "2026-10-12",
        "2026-10-13",
        "2026-10-14",
    ]
    assert all(event["owner"] == wake.OWNER for event in plan["events"])
    assert all("05:50:00" in event["local_datetime"] for event in plan["events"])
    output = capsys.readouterr().out
    assert "sudo /usr/bin/pmset schedule wake" in output
    assert output.count("sudo /usr/bin/pmset schedule wake") == 5
    assert all(event["command"][2] == "wake" for event in plan["events"])


def test_install_requires_admin_and_brisbane_timezone_before_any_command():
    events = wake.next_weekday_wake_events(
        datetime(2026, 10, 7, 12, 5, tzinfo=ZoneInfo("Australia/Brisbane"))
    )
    calls = []

    def fake_runner(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="")

    with pytest.raises(PermissionError, match="administrator"):
        wake.install_events(
            events,
            system_zone=ZoneInfo("Australia/Brisbane"),
            runner=fake_runner,
            is_admin=False,
        )
    assert calls == []

    with pytest.raises(ValueError, match="Brisbane-compatible"):
        wake.install_events(
            events,
            system_zone=ZoneInfo("Australia/Sydney"),
            runner=fake_runner,
            is_admin=True,
        )
    assert calls == []


def test_install_adds_individual_owned_events_and_preserves_existing_schedule():
    events = wake.next_weekday_wake_events(
        datetime(2026, 10, 7, 12, 5, tzinfo=ZoneInfo("Australia/Brisbane"))
    )
    existing_output = (
        "Scheduled power events:\n"
        "wake at 10/08/26 05:50:00 by 'unrelated.user.schedule'\n"
        "wake at 10/09/2026 05:50:00 by 'au.brisbane.transport-resilience.collector'\n"
        "wakeorpoweron at 10/12/26 05:50:00 by 'au.brisbane.transport-resilience.collector'\n"
        "wake at 10/07/26 07:00:00 by 'unrelated.user.schedule'\n"
        "wake at 10/14/26 05:50:00 by 'au.brisbane.transport-resilience.collector'\n"
    )
    calls = []

    def fake_runner(args, **kwargs):
        calls.append(list(args))
        if args == [wake.PMSET, "-g", "sched"]:
            return SimpleNamespace(stdout=existing_output)
        return SimpleNamespace(stdout="")

    installed = wake.install_events(
        events,
        system_zone=ZoneInfo("Australia/Brisbane"),
        runner=fake_runner,
        is_admin=True,
    )

    assert [event["status"] for event in installed] == [
        "installed",
        "already_scheduled",
        "installed",
        "installed",
        "already_scheduled",
    ]
    assert calls[0] == [wake.PMSET, "-g", "sched"]
    assert calls[1:] == [events[index]["command"] for index in (0, 2, 3)]
    assert all(command[1] == "schedule" and command[2] == "wake" for command in calls[1:])
    assert not any("cancel" in command or "repeat" in command for command in calls)
    assert all(event["owner"] == wake.OWNER for event in installed)


def test_system_timezone_comes_from_localtime_file_not_process_tz(tmp_path, monkeypatch):
    source = next(
        (
            Path(root) / "Australia" / "Sydney"
            for root in TZPATH
            if (Path(root) / "Australia" / "Sydney").is_file()
        ),
        None,
    )
    if source is None:
        pytest.skip("system IANA timezone file is unavailable")
    localtime_file = tmp_path / "localtime"
    localtime_file.write_bytes(source.read_bytes())
    monkeypatch.setenv("TZ", "Australia/Brisbane")

    detected = wake.detect_system_timezone(localtime_file)

    assert not wake.timezone_matches_brisbane(
        detected,
        [date(2026, 10, 8), date(2026, 10, 12)],
    )
    with pytest.raises(RuntimeError, match="could not determine"):
        wake.detect_system_timezone(tmp_path / "missing-localtime")
