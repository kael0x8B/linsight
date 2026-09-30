"""Create application venvs without distro ensurepip or changes to system Python.

Only the bundled, hash-pinned pip wheel is used; bootstrap never accesses a package
index. Kept stdlib-only so node installation can run this file before Runtime exists.
"""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

PIP_WHEEL = Path(__file__).with_name("bootstrap") / "pip-25.3-py3-none-any.whl"
PIP_SHA256 = "9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd"


def create_environment(target: Path) -> None:
    """Seed only the requested application environment, including partial retries."""
    if hashlib.sha256(PIP_WHEEL.read_bytes()).hexdigest() != PIP_SHA256:
        raise ValueError("随包 pip 校验失败，未创建 Python 环境")
    target = target.absolute()
    if target.is_symlink() or target.resolve() in {
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path("/"),
    }:
        raise ValueError("不能修改当前或系统 Python 环境")
    if target.exists() and any(target.iterdir()) and not (target / "pyvenv.cfg").is_file():
        raise ValueError("目标目录非空且不是应用虚拟环境")
    venv.EnvBuilder(with_pip=False, symlinks=True).create(target)
    python = target / "bin" / "python"
    # Ignore caller Python/pip configuration, including index, target and prefix
    # overrides. -I prevents current-directory or PYTHONPATH module injection.
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("PIP_", "PYTHON"))
    }
    env["PIP_CONFIG_FILE"] = os.devnull
    seed = (
        "import pathlib,runpy,sys; "
        "target=pathlib.Path(sys.argv.pop(1)); "
        "assert sys.prefix != sys.base_prefix and pathlib.Path(sys.prefix)==target; "
        "sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('pip',run_name='__main__')"
    )
    subprocess.run(  # noqa: S603 - fixed interpreter in a verified application venv
        [
            str(python),
            "-I",
            "-c",
            seed,
            str(target),
            str(PIP_WHEEL),
            "--isolated",
            "install",
            "--no-index",
            "--no-deps",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "--ignore-installed",
            str(PIP_WHEEL),
        ],
        env=env,
        check=True,
        timeout=90,
    )
    subprocess.run(  # noqa: S603
        [str(python), "-I", "-m", "pip", "--version"],
        env=env,
        check=True,
        timeout=15,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        if args.probe:
            with tempfile.TemporaryDirectory(prefix="bootstrap-", dir=args.target) as directory:
                create_environment(Path(directory) / "venv")
        else:
            create_environment(args.target)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"LINSIGHT_ERROR=应用隔离环境准备失败：{error}") from error


if __name__ == "__main__":
    main()
