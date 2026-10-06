"""Shared mutation lease: switch waits for in-flight API mutations to finish."""

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path

LOCK = Path("/run/linsight-updater/maintenance.lock")


@contextmanager
def mutation_lease(path: Path = LOCK):
    if not path.exists():
        yield
        return
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("设备正在切换应用版本，请等待升级完成后再修改配置") from error
        yield


@contextmanager
def switching_lease(path: Path = LOCK, timeout: float = 30):
    if not path.exists():
        yield
        return
    with path.open("rb") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as error:
                if time.monotonic() >= deadline:
                    raise ValueError("仍有配置操作正在执行，请稍后重试升级") from error
                time.sleep(0.1)
        yield
