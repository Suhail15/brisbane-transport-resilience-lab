"""A single diagnostics worker; status coalesces, observation events do not."""
from collections import deque
import json
import shutil
import threading
import time

from .files import atomic_write


class AsyncTelemetry:
    def __init__(self, archive, *, writer=atomic_write, logger=None):
        self.archive, self.writer = archive, writer
        self.logger = logger or (lambda document: print(document, flush=True))
        self.condition = threading.Condition()
        self.events = deque()
        self.latest_status = None
        self.stopping = False
        self.busy = False
        self.error = None
        self.disk = None
        self.completed = 0
        self.thread = threading.Thread(target=self._run, name="collector-telemetry", daemon=True)
        self.thread.start()

    def status(self, document):
        with self.condition:
            self.latest_status = document
            self.condition.notify()

    def log(self, document):
        with self.condition:
            self.events.append(("log", document))
            self.condition.notify()

    def gap(self, start, end, feed, reason, *, detected_at):
        with self.condition:
            self.events.append(("gap", (start, end, feed, reason, detected_at)))
            self.condition.notify()

    def health(self):
        with self.condition:
            return {"worker_alive": self.thread.is_alive(), "busy": self.busy,
                    "pending_events": len(self.events), "status_pending": self.latest_status is not None,
                    "last_error": self.error, "completed_operations": self.completed,
                    "disk": self.disk}

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.events or self.latest_status is not None or self.stopping)
                if self.events:
                    operation, document = self.events.popleft()
                elif self.latest_status is not None:
                    operation, document = "status", self.latest_status
                    self.latest_status = None
                else:
                    return
                self.busy = True
            try:
                if operation == "gap":
                    start, end, feed, reason, detected_at = document
                    self.archive.gap(start, end, feed, reason, detected_at=detected_at)
                elif operation == "log":
                    self.logger(document)
                else:
                    usage = shutil.disk_usage(self.archive.root)
                    disk = {"total_bytes": usage.total, "free_bytes": usage.free,
                            "used_fraction": usage.used / usage.total}
                    with self.condition:
                        self.disk = disk
                    self.writer(self.archive.root / "runtime" / "collector-status.json", json.dumps(document))
                with self.condition:
                    self.completed += 1
                    self.error = None
            except Exception as exc:
                with self.condition:
                    self.error = str(exc)[:500]
                    # Preserve events. A newer status may replace a failed status.
                    if operation != "status":
                        self.events.appendleft((operation, document))
                    elif self.latest_status is None:
                        self.latest_status = document
                time.sleep(1)
            finally:
                with self.condition:
                    self.busy = False
                    self.condition.notify_all()

    def wait_idle(self, timeout=5):
        with self.condition:
            return self.condition.wait_for(
                lambda: not self.busy and not self.events and self.latest_status is None, timeout)

    def close(self, timeout=30):
        with self.condition:
            self.stopping = True
            self.condition.notify()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise RuntimeError("Telemetry did not drain; retained diagnostics remain pending")
