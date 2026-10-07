"""Pure Brisbane window and fixed-phase polling helpers."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

BRISBANE = ZoneInfo("Australia/Brisbane")
POLL_SECONDS = {"TripUpdates": 25, "VehiclePositions": 25, "Alerts": 55}
MIN_DISPATCH_SECONDS = {name: cadence - 5 for name, cadence in POLL_SECONDS.items()}
POLICY = "collector-v2"


def in_window(now):
    local = now.astimezone(BRISBANE)
    return local.weekday() < 5 and 6 <= local.hour < 12


def preparation_active(now):
    local = now.astimezone(BRISBANE)
    return local.weekday() < 5 and time(5, 50) <= local.time().replace(tzinfo=None) < time(12)


def window_start(now):
    return datetime.combine(now.astimezone(BRISBANE).date(), time(6), BRISBANE)


def next_phase_deadline(deadline, cadence, now):
    """Advance from the original phase to the first slot strictly after now."""
    return deadline + (max(0, int((now - deadline) // cadence)) + 1) * cadence


def next_boundary(now):
    local = now.astimezone(BRISBANE)
    for days in range(8):
        day = local.date() + timedelta(days=days)
        if day.weekday() >= 5:
            continue
        for boundary in (time(5, 50), time(6), time(12)):
            candidate = datetime.combine(day, boundary, BRISBANE)
            if candidate > local:
                return candidate
