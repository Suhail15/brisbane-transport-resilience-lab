"""Publish complete files atomically; immutable files never overwrite an existing path."""
from pathlib import Path
import os
import tempfile

def atomic_write(path,payload,*,immutable=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(payload,str):payload=payload.encode("utf-8")
    fd,temp=tempfile.mkstemp(prefix=".publishing-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
        if immutable:
            try:os.link(temp,path)
            except FileExistsError:
                if path.read_bytes()!=payload:raise ValueError(f"immutable file collision: {path}")
        else:os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
