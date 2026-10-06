"""Host-driven fault test restricted to the named synthetic Docker box."""

import argparse
import json
import subprocess
import time
from pathlib import Path

BOX = "linsight-box-simulator"


def command(*args, check=True):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check
    )


def status():
    result = command("exec", BOX, "linsight-upgrade", "status")
    return json.loads(result.stdout)


parser = argparse.ArgumentParser()
parser.add_argument("fault", choices=("daemon", "container"))
parser.add_argument("--evidence", required=True, type=Path)
args = parser.parse_args()
identity = command(
    "exec", BOX, "cat", "/var/lib/linsight/edge-agent-credential.json"
).stdout
if "simulator-only-not-a-real-node-key" not in identity:
    raise SystemExit("Refusing to operate on a non-simulator identity")
before = status()
if before["job"]["phase"] != "READY":
    raise SystemExit("First run linsight-upgrade check /simulation/next.lup")
identifier = before["job"]["id"]
# Submit an existing prepared job; no file uploads race the interruption.
code = (
    "import sys;sys.path.insert(0,'/opt/linsight-updater/code');"
    "from edge_agent.app.upgrade.daemon import request;"
    f"request('install',{{'id':'{identifier}'}})"
)
command("exec", BOX, "/opt/linsight/venv/bin/python", "-c", code)
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    current = status()
    if current["job"]["phase"] == "CHECKING":
        break
    if current["job"]["phase"] not in {"READY", "SWITCHING"}:
        raise SystemExit("Missed interruption window")
    time.sleep(0.05)
else:
    raise SystemExit("No switch observed")
if args.fault == "daemon":
    command(
        "exec",
        BOX,
        "systemctl",
        "kill",
        "--signal=SIGKILL",
        "--kill-whom=main",
        "linsight-app-updater",
    )
else:
    command("kill", "--signal=KILL", BOX)
    command("start", BOX)
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    try:
        after = status()
        if after["job"]["phase"] == "ROLLED_BACK":
            assert after["current"]["id"] == before["current"]["id"]
            data = command(
                "exec",
                "-e",
                "LINSIGHT_SIMULATOR=1",
                BOX,
                "/opt/linsight/venv/bin/python",
                "/simulation/data_probe.py",
                "check",
            )
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(
                json.dumps(
                    {
                        "fault": args.fault,
                        "before": before,
                        "interrupted": current,
                        "after": after,
                        "data": json.loads(data.stdout),
                    },
                    indent=2,
                )
            )
            print(
                json.dumps(
                    {"fault": args.fault, "phase": "ROLLED_BACK", "dataUnchanged": True}
                )
            )
            break
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        pass
    time.sleep(1)
else:
    raise SystemExit("Recovery did not pass; inspect simulator services")
