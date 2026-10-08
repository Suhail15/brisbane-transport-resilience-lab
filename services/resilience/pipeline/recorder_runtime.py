"""One recorder per archive; assert awake during preparation and request drain."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import threading

_LOCKED_ROOTS = set()
_LOCK_GUARD = threading.Lock()


def recorder_lock_held(root):
    with _LOCK_GUARD:
        return Path(root).resolve() in _LOCKED_ROOTS


@contextmanager
def recorder_lock(root):
    path = Path(root) / 'runtime' / 'collector.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    handle.seek(0)
    if not path.stat().st_size:
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('A collector already holds this archive lock')
    key = Path(root).resolve()
    with _LOCK_GUARD:
        _LOCKED_ROOTS.add(key)
    try:
        yield
    finally:
        with _LOCK_GUARD:
            _LOCKED_ROOTS.discard(key)
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class WindowAwake:
    def __init__(self):
        self.process = None
        self.active = False
        self.error = None
        self.restarts = 0

    def set(self, active):
        # Revalidate the owned assertion even when desired state is unchanged.
        if sys.platform == 'darwin':
            dead = self.process is not None and self.process.poll() is not None
            if dead:
                self.error = f"Owned awake assertion exited: {self.process.returncode}"
                self.process = None
                self.restarts += 1
            if active and self.process is None:
                try:
                    self.process = subprocess.Popen(
                        ['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError as exc:
                    self.error = str(exc)[:500]
                    self.active = False
                    raise
            elif not active and self.process is not None:
                self.process.terminate()
                self.process.wait(timeout=5)
                self.process = None
        elif os.name == 'nt':
            import ctypes
            if not ctypes.windll.kernel32.SetThreadExecutionState(
                    0x80000000 | (0x00000001 if active else 0)):
                self.error = 'SetThreadExecutionState failed'
                self.active = False
                raise OSError(self.error)
        self.active = active

    def health(self):
        alive = self.process is not None and self.process.poll() is None if sys.platform == 'darwin' else self.active
        return {"requested_active": self.active, "assertion_alive": alive,
                "last_error": self.error, "restart_count": self.restarts}

    def close(self):
        self.set(False)
