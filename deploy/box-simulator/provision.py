"""Provision a disposable Linux box with real Runtime/Agent and synthetic device identity."""

import json
import os
import subprocess
import sys
from pathlib import Path

if not Path("/.dockerenv").exists() or os.environ.get("LINSIGHT_SIMULATOR") != "1":
    raise SystemExit("Only run in the dedicated disposable simulator")
sys.path.insert(0, "/simulation/linsight-bootstrap.pyz")
from edge_agent.app.upgrade.bundle import verify
from edge_agent.app.upgrade.system import LinuxSystem

root = Path("/opt/linsight")
root.mkdir()
target = root / "simulator-baseline"
target.mkdir()
manifest = verify(Path("/simulation/release.lup"), Path("/simulation/keys"), target)
LinuxSystem(Path("/simulation/provision.log")).prepare_release(target, manifest)
(root / "runtime").symlink_to(target / "runtime")
(root / "venv").symlink_to(target / "venv")
config = Path("/etc/linsight")
config.mkdir()
data = Path("/var/lib/linsight/runtime-data/gateway")
data.mkdir(parents=True)
identity = Path("/var/lib/linsight/edge-agent-credential.json")
identity.write_text(
    json.dumps(
        {
            "node_id": 1,
            "tenant_id": 1,
            "credential": "simulator-only-not-a-real-node-key",
        }
    )
)
identity.chmod(0o600)
(data / "local-password").write_text("linsight-simulator-only")
(data / "local-password").chmod(0o600)
key = "simulator-only-runtime-key-32-bytes"
(config / "runtime.env").write_text(
    f"LINSIGHT_RUNTIME_API_KEY={key}\n"
    "LINSIGHT_RUNTIME_DATA_ROOT=/var/lib/linsight/runtime-data\n"
    "LINSIGHT_RUNTIME_PLATFORM_URL=http://127.0.0.1:9\n"
    "LINSIGHT_RUNTIME_PREVIEW_ROOT=/var/lib/linsight/preview\n"
)
(config / "agent.env").write_text(
    f"LINSIGHT_AGENT_RUNTIME_API_KEY={key}\n"
    "LINSIGHT_AGENT_NODE_CODE=box-simulator\nLINSIGHT_AGENT_NODE_NAME=Box Simulator\n"
    "LINSIGHT_AGENT_CONTROL_PLANE_URL=http://127.0.0.1:9\n"
    "LINSIGHT_AGENT_RUNTIME_DATA_ROOT=/var/lib/linsight/runtime-data\n"
    "LINSIGHT_AGENT_CREDENTIAL_FILE=/var/lib/linsight/edge-agent-credential.json\n"
    "LINSIGHT_AGENT_AGENT_VERSION=legacy-simulator\n"
)
for filename, kind, command in (
    (
        "linsight-ai-runtime.service",
        "runtime",
        "uvicorn ai_runtime.app.main:create_app --factory --host 127.0.0.1 --port 48900",
    ),
    ("linsight-edge-agent.service", "agent", "edge_agent.app.main"),
):
    Path("/etc/systemd/system", filename).write_text(
        "[Unit]\nDescription=LInsight simulator application\nAfter=network.target\n"
        "[Service]\nWorkingDirectory=/opt/linsight/runtime\n"
        f"EnvironmentFile=/etc/linsight/{kind}.env\n"
        f"ExecStart=/opt/linsight/venv/bin/python -m {command}\nRestart=always\nRestartSec=3\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(
    ["systemctl", "enable", "--now", "linsight-ai-runtime", "linsight-edge-agent"],
    check=True,
)
print(json.dumps({"legacyInstalled": True, "sourceVersion": manifest["version"]}))
