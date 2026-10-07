from datetime import datetime,timezone
import os
from pathlib import Path
import plistlib
import pytest
import runpy
import shutil
import subprocess
import sys
import time
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

def run_fake_macos_install(tmp_path, monkeypatch, bootstrap_results, sleep_calls, calls_out=None):
    source = Path(__file__).resolve().parents[2] / "scripts" / "install_collector.py"
    project = tmp_path / "project"
    copied_script = project / "scripts" / "install_collector.py"
    copied_script.parent.mkdir(parents=True)
    shutil.copyfile(source, copied_script)
    home = tmp_path / "home"
    calls = calls_out if calls_out is not None else []

    def fake_run(command, **kwargs):
        calls.append((list(command), kwargs))
        if command[1] == "bootout":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return bootstrap_results.pop(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", sleep_calls.append)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "argv", [str(copied_script), "--install"])
    monkeypatch.setattr(os, "getuid", lambda: 501, raising=False)
    return runpy.run_path(str(copied_script), run_name="__main__"), calls, home, project


def test_launchagent_bootstrap_retries_exit_five_once_after_half_second(tmp_path, monkeypatch):
    sleep_calls = []
    results = [
        subprocess.CompletedProcess([], 5, stdout="first output", stderr="first busy"),
        subprocess.CompletedProcess([], 0, stdout="loaded", stderr=""),
    ]

    _, calls, home, project = run_fake_macos_install(tmp_path, monkeypatch, results, sleep_calls)

    bootstrap_calls = [(command, options) for command, options in calls if command[1] == "bootstrap"]
    assert len(bootstrap_calls) == 2
    assert bootstrap_calls[0][0] == bootstrap_calls[1][0]
    assert bootstrap_calls[0][0][2] == "gui/501"
    assert bootstrap_calls[0][0][3] == str(home / "Library" / "LaunchAgents" /
                                           "au.brisbane.transport-resilience.collector.plist")
    assert all(options == {"check": False, "capture_output": True, "text": True}
               for _, options in bootstrap_calls)
    assert sleep_calls == [0.5]
    staged = plistlib.loads((project / "data" / "runtime" / "collector-launchagent.plist").read_bytes())
    assert staged["ExitTimeOut"] == 300


@pytest.mark.parametrize(
    "results, expected_calls, expected_return, expected_stdout, expected_stderr", [
    ([subprocess.CompletedProcess([], 2, stdout="details", stderr="invalid domain")],
     1, 2, "details", "invalid domain"),
    ([
        subprocess.CompletedProcess([], 5, stdout="first output", stderr="temporary busy"),
        subprocess.CompletedProcess([], 3, stdout="retry output", stderr="permanent failure"),
    ], 2, 3, "first output\nretry output", "temporary busy\npermanent failure"),
    ]
)
def test_launchagent_bootstrap_permanent_errors_propagate_captured_diagnostics(
    tmp_path, monkeypatch, results, expected_calls, expected_return,
    expected_stdout, expected_stderr
):
    sleep_calls = []
    calls = []

    with pytest.raises(subprocess.CalledProcessError) as raised:
        run_fake_macos_install(tmp_path, monkeypatch, results, sleep_calls, calls)

    # The fake runner consumes only bootstrap results; it cannot invoke launchctl.
    bootstrap_calls = [command for command, _ in calls if command[1] == "bootstrap"]
    assert len(bootstrap_calls) == expected_calls
    assert raised.value.returncode == expected_return
    assert raised.value.output == expected_stdout
    assert raised.value.stderr == expected_stderr
    assert sleep_calls == ([0.5] if expected_calls == 2 else [])
