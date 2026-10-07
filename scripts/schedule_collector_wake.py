#!/usr/bin/env python3
"""Prepare five owned Brisbane weekday wake events; install only on explicit request."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services"))

from resilience.pipeline.collector_schedule import BRISBANE  # noqa: E402
from resilience.pipeline.files import atomic_write  # noqa: E402

OWNER = "au.brisbane.transport-resilience.collector"
WAKE_TIME = time(5, 50)
WAKE_KIND = "wake"
PMSET = "/usr/bin/pmset"
PLAN_RELATIVE_PATH = Path("data") / "runtime" / "collector-wake-plan.json"
SCHEDULE_LINE = re.compile(
    r"^\s*(?:\[\d+\]\s*)?(?P<kind>[a-z]+)\s+at\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+by\s+"
    r"(?:'(?P<quoted_owner>[^']+)'|(?P<owner>\S+))\s*$",
    re.IGNORECASE,
)


def next_weekday_wake_events(now: datetime) -> list[dict[str, str]]:
    """Return the next five future weekday events at 05:50 Brisbane time."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(BRISBANE)
    events = []
    day = local_now.date()
    while len(events) < 5:
        event_at = datetime.combine(day, WAKE_TIME, BRISBANE)
        if day.weekday() < 5 and event_at > local_now:
            pmset_datetime = event_at.strftime("%m/%d/%y %H:%M:%S")
            events.append(
                {
                    "service_date": day.isoformat(),
                    "local_datetime": event_at.isoformat(),
                    "pmset_datetime": pmset_datetime,
                    "owner": OWNER,
                    "status": "planned",
                    "command": [PMSET, "schedule", WAKE_KIND, pmset_datetime, OWNER],
                    "admin_command": shlex.join(
                        ["sudo", PMSET, "schedule", WAKE_KIND, pmset_datetime, OWNER]
                    ),
                }
            )
        day += timedelta(days=1)
    return events


def timezone_matches_brisbane(system_zone: tzinfo, service_dates: list[date]) -> bool:
    """Check that local pmset times map to Brisbane times on every planned date."""
    for service_date in service_dates:
        local = datetime.combine(service_date, WAKE_TIME, system_zone)
        expected = datetime.combine(service_date, WAKE_TIME, BRISBANE)
        if local.utcoffset() != expected.utcoffset() or local.dst() != expected.dst():
            return False
    return True


def detect_system_timezone(localtime_path: Path = Path("/etc/localtime")) -> tzinfo:
    """Read the operating-system timezone file, ignoring process-level TZ overrides."""
    path = Path(localtime_path)
    try:
        resolved = path.resolve(strict=True)
        parts = resolved.parts
        if "zoneinfo" in parts:
            key = "/".join(parts[parts.index("zoneinfo") + 1 :])
            return ZoneInfo(key)
        with path.open("rb") as handle:
            return ZoneInfo.from_file(handle)
    except (OSError, ValueError, ZoneInfoNotFoundError) as exc:
        raise RuntimeError("could not determine the Mac timezone from /etc/localtime") from exc


def _is_matching_event(line: str, event: dict[str, str]) -> bool:
    match = SCHEDULE_LINE.match(line)
    if not match:
        return False
    owner = match.group("quoted_owner") or match.group("owner")
    if match.group("kind").casefold() != WAKE_KIND or owner != OWNER:
        return False
    try:
        month, day, year = (int(value) for value in match.group("date").split("/"))
        if len(match.group("date").split("/")[2]) == 2:
            year += 2000
        line_date = date(year, month, day)
    except ValueError:
        return False
    return (
        line_date.isoformat() == event["service_date"]
        and match.group("time") == WAKE_TIME.strftime("%H:%M:%S")
    )


def install_events(
    events: list[dict[str, str]],
    *,
    system_zone: tzinfo,
    runner=subprocess.run,
    is_admin: bool,
) -> list[dict[str, str]]:
    """Add missing owned one-time events. This never edits repeat/global schedules."""
    if not is_admin:
        raise PermissionError("--install requires administrator authorization; rerun with sudo")
    dates = [date.fromisoformat(event["service_date"]) for event in events]
    if not timezone_matches_brisbane(system_zone, dates):
        raise ValueError("Mac timezone is not Brisbane-compatible for the planned event dates")

    listing = runner(
        [PMSET, "-g", "sched"], check=True, capture_output=True, text=True
    )
    existing = getattr(listing, "stdout", "") or ""
    updated = []
    for event in events:
        item = dict(event)
        already_present = any(_is_matching_event(line, item) for line in existing.splitlines())
        if already_present:
            item["status"] = "already_scheduled"
        else:
            runner(item["command"], check=True)
            item["status"] = "installed"
        updated.append(item)
    return updated


def write_plan(repo_root: Path, plan: dict) -> Path:
    path = Path(repo_root) / PLAN_RELATIVE_PATH
    atomic_write(path, json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return path


def main(
    argv: list[str] | None = None,
    *,
    repo_root: Path | None = None,
    now: datetime | None = None,
    system_zone: tzinfo | None = None,
    runner=subprocess.run,
    platform: str | None = None,
    is_admin: bool | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="add the planned one-time events (requires sudo and a Brisbane-compatible Mac timezone)",
    )
    args = parser.parse_args(argv)

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    now = now or datetime.now(BRISBANE)
    events = next_weekday_wake_events(now)
    plan = {
        "schema_version": 1,
        "owner": OWNER,
        "timezone": "Australia/Brisbane",
        "generated_at": now.astimezone(BRISBANE).isoformat(),
        "status": "planned",
        "events": events,
    }
    path = write_plan(root, plan)
    print(f"Prepared {len(events)} owned wake events in {path}")
    for event in events:
        print(event["admin_command"])

    if not args.install:
        return 0
    if (platform or sys.platform) != "darwin":
        raise SystemExit("--install is supported only on macOS")
    if is_admin is None:
        is_admin = hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        plan["events"] = install_events(
            events,
            system_zone=system_zone or detect_system_timezone(),
            runner=runner,
            is_admin=is_admin,
        )
    except (PermissionError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
    plan["status"] = "installed"
    write_plan(root, plan)
    print("Installed or confirmed the five owned one-time events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
