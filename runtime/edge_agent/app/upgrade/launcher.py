"""Systemd entry point: execute the selected verified release, or the source baseline."""

import os
import subprocess
import time
from pathlib import Path

from edge_agent.app.upgrade.activation import begin, finish, healthy, restore


def selected_executable(root: Path) -> Path | None:
    current = root / "current"
    if not current.is_symlink():
        return None
    release = current.resolve(strict=True)
    release.relative_to((root / "releases").resolve())
    executable = release / "bin" / "edge-agent"
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("selected Agent release has no regular executable")
    return executable


def activate_guarded(root: Path, timeout: float = 120) -> bool:
    """Restore on failure; after health confirmation, exit with the candidate process."""
    pending = begin(root)
    if pending is None:
        return False
    child = None
    try:
        executable = selected_executable(root)
        if executable is None or executable.parent.parent.name != pending["version"]:
            raise ValueError("activation journal does not match selected release")
        env = dict(
            os.environ,
            LINSIGHT_AGENT_AGENT_VERSION=pending["version"],
            LINSIGHT_AGENT_ACTIVATION_GUARD="v1",
        )
        child = subprocess.Popen([str(executable)], env=env, start_new_session=True)  # noqa: S603
        while time.time() - pending["startedAt"] < timeout:
            if healthy(root, pending):
                finish(root, pending)
                raise SystemExit(child.wait())
            if child.poll() is not None:
                break
            time.sleep(0.25)
    except (OSError, ValueError):
        pass
    finally:
        # No journal means health was acknowledged; do not roll back a committed version.
        if (root / "pending-activation.json").exists():
            if child is not None and child.poll() is None:
                import signal

                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            restore(root, pending)
    return False


def main() -> None:
    root = Path(os.environ.get("LINSIGHT_AGENT_UPGRADE_ROOT", "/var/lib/linsight/edge-agent"))
    os.environ["LINSIGHT_AGENT_ACTIVATION_GUARD"] = "v1"
    activate_guarded(root)
    executable = selected_executable(root)
    if executable is not None:
        os.environ["LINSIGHT_AGENT_AGENT_VERSION"] = executable.parent.parent.name
        os.execv(str(executable), [str(executable)])  # noqa: S606 - verified local release
    from edge_agent.app.main import main as run_agent

    run_agent()


if __name__ == "__main__":
    main()
