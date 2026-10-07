"""One recorder per archive; prevent idle sleep during preparation, collection and request drain."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys

@contextmanager
def recorder_lock(root):
    path=Path(root)/'runtime'/'collector.lock';path.parent.mkdir(parents=True,exist_ok=True)
    handle=path.open('a+b');handle.seek(0)
    if not path.stat().st_size:handle.write(b'0');handle.flush();handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close();raise RuntimeError('A collector already holds this archive lock')
    try:yield
    finally:
        if os.name=='nt':
            import msvcrt
            handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()

class WindowAwake:
    def __init__(self):self.process=None;self.active=False
    def set(self,active):
        if active==self.active:return
        if sys.platform=='darwin':
            if active:self.process=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            elif self.process:self.process.terminate();self.process.wait(timeout=5);self.process=None
        elif os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000|(0x00000001 if active else 0))
        self.active=active
    def close(self):self.set(False)
