from pathlib import Path

import pytest

from edge_agent.app.upgrade.launcher import selected_executable
from edge_agent.app.upgrade.manager import UpgradeManager


def test_service_launcher_follows_current_and_rejects_escape(tmp_path: Path):
    assert selected_executable(tmp_path) is None
    release = tmp_path / "releases" / "v2"
    executable = release / "bin" / "edge-agent"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n")
    (tmp_path / "current").symlink_to(release)
    assert selected_executable(tmp_path) == executable
    (tmp_path / "current").unlink()
    (tmp_path / "current").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError):
        selected_executable(tmp_path)


@pytest.mark.parametrize("version", [".", "..", "../escape"])
def test_release_versions_cannot_escape_immutable_directory(tmp_path: Path, version: str):
    with pytest.raises(ValueError):
        UpgradeManager(tmp_path, b"x" * 32).activate(version)
