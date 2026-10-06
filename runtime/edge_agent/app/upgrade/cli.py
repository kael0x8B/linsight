"""Local CLI uses the same authenticated Unix socket as the gateway entrance."""

import argparse
import base64
import json
import time
from pathlib import Path
from uuid import uuid4

from edge_agent.app.upgrade.bundle import CHUNK_SIZE
from edge_agent.app.upgrade.daemon import request


def wait(identifier: str, phases: set[str]):
    previous = None
    while True:
        status = request("status")
        if status.get("lastError"):
            raise ValueError(status["lastError"]["message"])
        job = status.get("job")
        if job and job["id"] == identifier:
            if job["phase"] != previous:
                print(job["phase"], job.get("message", ""), flush=True)
                previous = job["phase"]
            if job["phase"] in phases:
                return job
            if job["phase"] in {"FAILED", "ROLLED_BACK", "RECOVERY_FAILED"}:
                raise SystemExit(1)
        time.sleep(1)


def upload(path: Path) -> str:
    identifier = str(uuid4())
    request("upload.begin", {"id": identifier, "size": path.stat().st_size})
    offset = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            result = request(
                "upload.chunk",
                {"id": identifier, "offset": offset, "data": base64.b64encode(chunk).decode()},
            )
            offset = result["offset"]
    request("upload.finish", {"id": identifier})
    wait(identifier, {"READY"})
    return identifier


def main():
    parser = argparse.ArgumentParser(description="LInsight 盒子应用升级")
    parser.add_argument("command", choices=("check", "install", "status", "rollback"))
    parser.add_argument("package", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "status":
            print(json.dumps(request("status"), ensure_ascii=False, indent=2))
        elif args.command == "rollback":
            identifier = str(uuid4())
            request("rollback", {"id": identifier})
            wait(identifier, {"SUCCEEDED"})
        else:
            if args.package is None:
                parser.error("check/install 必须指定升级包")
            identifier = upload(args.package)
            if args.command == "install":
                request("install", {"id": identifier})
                wait(identifier, {"SUCCEEDED"})
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
