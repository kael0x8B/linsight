"""Stable systemd entry point, installed outside all application releases."""

import json
import os
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"runtime", "agent"}:
        raise SystemExit(64)
    root = Path("/opt/linsight")
    selected = (root / "current").resolve(strict=True)
    if selected.parent != root / "releases":
        raise SystemExit("Invalid release pointer")
    release = json.loads((selected / "release.json").read_text())
    os.chdir(release["runtime"])
    env = dict(os.environ, LINSIGHT_APP_RELEASE=release["id"], PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    if sys.argv[1] == "runtime":
        args = [
            release["python"],
            "-m",
            "uvicorn",
            "ai_runtime.app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "48900",
        ]
    else:
        env["LINSIGHT_AGENT_AGENT_VERSION"] = release["version"]
        args = [release["python"], "-m", "edge_agent.app.main"]
    os.execve(args[0], args, env)  # noqa: S606 - root-owned descriptor and verified release


if __name__ == "__main__":
    main()
