from datetime import datetime,timezone
import pytest
from resilience.pipeline.recorder_runtime import recorder_lock
from resilience.pipeline.collector import in_window

def test_single_recorder_lock_and_release(tmp_path):
    with recorder_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with recorder_lock(tmp_path):pass
    with recorder_lock(tmp_path):pass

def test_recording_window_has_explicit_timezone_and_weekdays():
    assert in_window(datetime(2026,10,4,20,tzinfo=timezone.utc)) # Monday06 Brisbane
    assert not in_window(datetime(2026,10,5,2,tzinfo=timezone.utc)) # Monday12
    assert not in_window(datetime(2026,10,3,0,tzinfo=timezone.utc)) # Saturday10
