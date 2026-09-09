import asyncio
from pathlib import Path

import pytest

from edge_agent.app.command.lifecycle import NodeLifecycleController


def test_duplicate_command_after_restart_does_not_publish_another_host_action(tmp_path: Path):
    request = tmp_path / 'node-power-request'
    journal = tmp_path / 'persistent-journal'
    asyncio.run(NodeLifecycleController(request, journal).schedule('restart', 'command-1'))
    request.unlink()  # systemd consumed the first request
    result = asyncio.run(NodeLifecycleController(request, journal).schedule('restart', 'command-1'))
    assert result['duplicate'] is True
    assert not request.exists()
    with pytest.raises(ValueError):
        asyncio.run(NodeLifecycleController(request, journal).schedule('shutdown', 'command-1'))


def test_failed_submission_can_be_retried_without_touching_symlink_target(tmp_path: Path):
    request = tmp_path / 'missing' / 'node-power-request'
    controller = NodeLifecycleController(request, tmp_path / 'journal')
    with pytest.raises(OSError):
        asyncio.run(controller.schedule('shutdown', 'command-2'))
    request.parent.mkdir()
    target = tmp_path / 'untouched'
    target.write_text('keep')
    request.symlink_to(target)
    asyncio.run(controller.schedule('shutdown', 'command-2'))
    assert target.read_text() == 'keep'
    assert not request.is_symlink()
    assert request.read_text() == 'shutdown\n'


def test_invalid_action_is_rejected_before_publishing(tmp_path: Path):
    request = tmp_path / 'request'
    with pytest.raises(ValueError):
        asyncio.run(NodeLifecycleController(request).schedule('reboot; arbitrary', 'command-3'))
    assert not request.exists()
