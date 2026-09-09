#!/usr/bin/env python3
"""Prepare immutable Linux wheels on the build/control-plane host, never the edge.

Run with Python 3.12+ and pip installed. Does not connect to any node.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import tomllib
from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement


def target_requirements(requirements: list[str], architecture: str, python_version: str) -> list[str]:
    # pip download --platform does not change marker evaluation on the build host.
    # Evaluate direct platform requirements for the destination, then strip markers.
    environment = default_environment()
    environment.update(platform_system="Linux", platform_machine=architecture, sys_platform="linux",
                       os_name="posix", python_version=python_version,
                       python_full_version=python_version + ".0", implementation_name="cpython")
    result = []
    for value in requirements:
        requirement = Requirement(value)
        if requirement.marker is None or requirement.marker.evaluate(environment):
            requirement.marker = None
            result.append(str(requirement))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("aarch64", "x86_64"), required=True)
    parser.add_argument("--python-version", choices=("3.12", "3.13"), required=True)
    parser.add_argument("--runtime", type=Path, default=Path(__file__).resolve().parents[1] / "runtime")
    args = parser.parse_args()
    project = (args.runtime / "pyproject.toml").read_bytes()
    digest = hashlib.sha256(project).hexdigest()
    config = tomllib.loads(project.decode())
    parent = args.runtime / "deployment-wheels" / digest
    target = parent / f"{args.arch}-cp{args.python_version.replace('.', '')}"
    if target.exists():
        manifest = json.loads((target / "manifest.json").read_text())
        for name, checksum in manifest["files"].items():
            if Path(name).name != name or not name.endswith(".whl"):
                raise ValueError("Invalid wheel manifest filename")
            if hashlib.sha256((target / name).read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Wheel integrity check failed: {name}")
        print(f"Verified existing wheelhouse: {target}")
        return
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".preparing-", dir=parent) as temporary:
        staging = Path(temporary)
        requirements = target_requirements(
            config["project"]["dependencies"] + config["build-system"]["requires"],
            args.arch, args.python_version,
        )
        command = [sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
                   "--only-binary=:all:", "--python-version", args.python_version,
                   "--implementation", "cp", "--abi", "cp" + args.python_version.replace('.', ''),
                   "--abi", "abi3", "--abi", "none", "--dest", str(staging),
                   "--retries", "3", "--timeout", "30"]
        for platform in ("manylinux_2_34", "manylinux_2_28", "manylinux_2_27", "manylinux_2_26", "manylinux_2_17", "manylinux2014"):
            command.extend(["--platform", f"{platform}_{args.arch}"])
        subprocess.run(command + requirements, check=True, timeout=900)
        files = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                 for file in sorted(staging.glob("*.whl"))}
        if not files:
            raise RuntimeError("No compatible wheels downloaded")
        (staging / "manifest.json").write_text(json.dumps({
            "schemaVersion": 1, "architecture": args.arch, "pythonVersion": args.python_version,
            "pyprojectSha256": digest, "files": files,
        }, sort_keys=True, indent=2) + "\n")
        os.rename(staging, target)
        print(f"Prepared {len(files)} verified wheels: {target}")


if __name__ == "__main__":
    main()
