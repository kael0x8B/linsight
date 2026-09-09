#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

from edge_agent.app.upgrade.manager import ReleaseManifest, UpgradeManager


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install or roll back a verified Edge Agent release"
    )
    parser.add_argument("command", choices=("install", "rollback", "status"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    key = os.environ.get("LINSIGHT_AGENT_UPGRADE_SIGNING_KEY", "").encode()
    manager = UpgradeManager(args.root, key)
    if args.command == "install":
        if args.package is None or args.manifest is None:
            parser.error("install requires --package and --manifest")
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        manager.install(args.package, ReleaseManifest(**value))
    elif args.command == "rollback":
        manager.rollback()
    print(json.dumps({"currentVersion": manager.current_version()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
