import hashlib
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from ai_runtime.app.core import environment


def test_bundled_seed_has_release_hash():
    assert hashlib.sha256(environment.PIP_WHEEL.read_bytes()).hexdigest() == environment.PIP_SHA256


def test_real_offline_seed_without_ensurepip_and_partial_retry(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("ensurepip must not be used")

    monkeypatch.setattr(venv.EnvBuilder, "_setup_pip", forbidden)
    monkeypatch.setenv("PIP_TARGET", str(tmp_path / "forbidden-target"))
    monkeypatch.setenv("PIP_PREFIX", str(tmp_path / "forbidden-prefix"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "forbidden-pythonpath"))
    target = tmp_path / "app"
    # Reproduce the partial directory left behind by a failed distro venv.
    venv.EnvBuilder(with_pip=False).create(target)
    environment.create_environment(target)
    environment.create_environment(target)
    result = subprocess.run(  # noqa: S603 - interpreter created inside pytest tmp_path
        [str(target / "bin/python"), "-I", "-c",
         "import pip,sys; print(sys.prefix); print(pip.__file__)"],
        check=True, capture_output=True, text=True,
    )
    assert all(str(target) in line for line in result.stdout.splitlines())
    assert not (tmp_path / "forbidden-target").exists()
    assert not (tmp_path / "forbidden-prefix").exists()


@pytest.mark.parametrize("contents", [None, b"corrupted wheel"])
def test_missing_or_corrupt_seed_fails_before_creating_environment(tmp_path, monkeypatch, contents):
    wheel = tmp_path / "pip.whl"
    if contents is not None:
        wheel.write_bytes(contents)
    monkeypatch.setattr(environment, "PIP_WHEEL", wheel)
    with pytest.raises((OSError, ValueError)):
        environment.create_environment(tmp_path / "app")
    assert not (tmp_path / "app").exists()


def test_refuses_system_current_and_unrelated_directories(tmp_path):
    for target in (Path(sys.prefix), Path(sys.base_prefix), Path("/")):
        with pytest.raises(ValueError):
            environment.create_environment(target)
    (tmp_path / "user-file").write_text("preserve")
    with pytest.raises(ValueError):
        environment.create_environment(tmp_path)
    assert (tmp_path / "user-file").read_text() == "preserve"
    link = tmp_path / "link"
    link.symlink_to(sys.prefix)
    with pytest.raises(ValueError):
        environment.create_environment(link)
