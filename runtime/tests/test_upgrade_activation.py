import time
from pathlib import Path

import pytest

from edge_agent.app.upgrade.activation import acknowledge, begin, healthy, read_pending, stage
from edge_agent.app.upgrade.launcher import activate_guarded, selected_executable


def release(root: Path, version: str, script: str) -> Path:
    directory = root / "releases" / version
    executable = directory / "bin" / "edge-agent"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n" + script)
    executable.chmod(0o700)
    return directory


def test_crashed_target_restores_previous_release(tmp_path: Path):
    previous = release(tmp_path, "v1", "exit 0\n")
    target = release(tmp_path, "v2", "exit 42\n")
    stage(tmp_path, "v2", previous)
    (tmp_path / "current").symlink_to(target)
    activate_guarded(tmp_path, timeout=1)
    assert selected_executable(tmp_path).parent.parent == previous
    assert (tmp_path / "failed-activation-version").read_text() == "v2"
    assert read_pending(tmp_path) is None


def test_unresponsive_first_release_restores_source_baseline(tmp_path: Path):
    target = release(tmp_path, "v2", "sleep 10\n")
    stage(tmp_path, "v2", None)
    (tmp_path / "current").symlink_to(target)
    started = time.monotonic()
    activate_guarded(tmp_path, timeout=0.05)
    assert time.monotonic() - started < 3
    assert selected_executable(tmp_path) is None
    assert read_pending(tmp_path) is None


def test_only_target_accepted_heartbeat_acknowledges_activation(tmp_path: Path):
    stage(tmp_path, "v2", None)
    pending = begin(tmp_path)
    acknowledge(tmp_path, "v1")
    assert not healthy(tmp_path, pending)
    acknowledge(tmp_path, "v2")
    assert healthy(tmp_path, pending)


def test_valid_target_ack_commits_and_does_not_restore(tmp_path: Path):
    stage(tmp_path, "v2", None)
    pending = begin(tmp_path)
    script = f'printf v2 > "{tmp_path}/healthy-{pending["token"]}"\nsleep 0.1\n'
    target = release(tmp_path, "v2", script)
    (tmp_path / "current").symlink_to(target)
    with pytest.raises(SystemExit) as exit_status:
        activate_guarded(tmp_path, timeout=5)
    assert exit_status.value.code == 0
    assert read_pending(tmp_path) is None
    assert selected_executable(tmp_path).parent.parent == target


def test_second_install_cannot_overwrite_pending_journal(tmp_path: Path):
    stage(tmp_path, "v2", None)
    with pytest.raises(ValueError, match="awaiting activation"):
        stage(tmp_path, "v3", None)
    assert read_pending(tmp_path)["version"] == "v2"
