"""Durable full-application transactions; no control-plane connection is required."""

import errno
import fcntl
import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from edge_agent.app.upgrade.bundle import sha256, verify
from edge_agent.app.upgrade.maintenance import switching_lease

TERMINAL = {"SUCCEEDED", "FAILED", "ROLLED_BACK", "RECOVERY_FAILED"}


def atomic_json(path: Path, value: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, mode)
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read(path: Path) -> dict:
    return json.loads(path.read_text())


@contextmanager
def exclusive(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("其他部署或升级正在进行，请稍后重试") from error
        yield


class ApplicationUpdater:
    def __init__(self, root: Path, state: Path, keys: Path, lock: Path, system):
        self.root, self.state, self.keys, self.lock = root, state, keys, lock
        self.system = system
        self.state.mkdir(parents=True, exist_ok=True)
        (self.root / "releases").mkdir(parents=True, exist_ok=True)

    def current(self) -> dict:
        link = self.root / "current"
        if not link.is_symlink():
            raise ValueError("设备尚未完成首次升级迁移")
        target = link.resolve(strict=True)
        if target.parent != (self.root / "releases").resolve():
            raise ValueError("当前应用版本路径异常")
        return read(target / "release.json")

    def _save(self, job: dict, phase: str, message: str = "") -> None:
        saved = {**job, "phase": phase, "message": message, "updatedAt": time.time()}
        try:
            self._write_job(saved)
        except OSError as error:
            reserve = self.state / ".journal-reserve"
            if error.errno not in {errno.ENOSPC, errno.EDQUOT} or not reserve.exists():
                raise
            # Keep recovery journaling possible if another writer fills the device mid-switch.
            reserve.unlink()
            self._write_job(saved)
        job.update(saved)

    def _write_job(self, job):
        atomic_json(self.state / "job.json", job)
        atomic_json(self.state / "history" / f"{job['id']}.json", job)

    def _reserve_journal(self):
        reserve = self.state / ".journal-reserve"
        size = 16 * 1024**2
        with reserve.open("ab") as stream:
            os.chmod(reserve, 0o600)
            remaining = size - stream.tell()
            while remaining > 0:
                chunk = min(remaining, 1024**2)
                stream.write(b"\0" * chunk)
                remaining -= chunk
            stream.flush()
            os.fsync(stream.fileno())

    def status(self) -> dict:
        job = read(self.state / "job.json") if (self.state / "job.json").exists() else None
        previous = self.root / "previous"
        return {
            "supported": True,
            "current": self.current(),
            "job": job,
            "lastError": read(self.state / "last-error.json")
            if (self.state / "last-error.json").exists()
            else None,
            "rollbackAvailable": previous.is_symlink()
            and previous.resolve().is_dir()
            and previous.resolve() != (self.root / "current").resolve(),
        }

    def require_idle(self, allow_ready=False) -> None:
        path = self.state / "job.json"
        if path.exists() and read(path)["phase"] not in TERMINAL | (
            {"READY"} if allow_ready else set()
        ):
            raise ValueError("已有升级任务尚未完成")

    def prepare(self, job_id: str, package: Path) -> dict:
        job_id = str(UUID(job_id))
        with exclusive(self.lock):
            path = self.state / "job.json"
            if path.exists() and read(path)["id"] == job_id:
                return read(path)
            self.require_idle(allow_ready=True)
            self._reserve_journal()
            job = {
                "id": job_id,
                "action": "INSTALL",
                "createdAt": time.time(),
                "previous": self.current()["id"],
            }
            self._save(job, "VERIFYING", "正在验证发布签名和文件完整性")
            try:
                manifest = verify(package, self.keys)
                digest = sha256(package)
                release_id = manifest["version"] + "-" + digest[:12]
                job.update(
                    target=release_id,
                    version=manifest["version"],
                    notes=manifest["notes"],
                    packageSha256=digest,
                )
                if release_id == self.current()["id"]:
                    raise ValueError("该版本已在运行")
                target = self.root / "releases" / release_id
                for descriptor in (self.root / "releases").glob("*/release.json"):
                    existing = read(descriptor)
                    if (
                        existing.get("version") == manifest["version"]
                        and existing.get("packageSha256") != digest
                    ):
                        raise ValueError("相同版本号已存在不同内容，请使用新的发布版本号")
                if (target / "release.json").is_file():
                    if read(target / "release.json").get("packageSha256") != digest:
                        raise ValueError("已有版本与升级包不一致")
                    self._save(job, "READY", "已验证并准备过此版本，等待确认安装")
                    return job
                if target.exists():
                    if target.is_symlink() or target.resolve() in {
                        (self.root / "current").resolve(),
                        (self.root / "previous").resolve(),
                    }:
                        raise ValueError("不能清理当前或上一版本")
                    shutil.rmtree(target)
                self.system.preflight(manifest, package.stat().st_size, self.root)
                self._save(job, "PREPARING", "正在离线安装新版本及其依赖，原服务继续运行")
                target.mkdir()
                verify(package, self.keys, target)
                self.system.prepare_release(target, manifest)
                release = {
                    "id": release_id,
                    "version": manifest["version"],
                    "dataSchema": 1,
                    "packageSha256": digest,
                    "runtime": str(target / "runtime"),
                    "python": str(target / "venv/bin/python"),
                    "legacy": False,
                }
                atomic_json(target / "release.json", release, 0o644)
                # Persist extracted programs and dependencies before publishing READY.
                self.system.flush()
                self._save(job, "READY", "校验与准备完成，等待确认安装")
            except Exception as error:
                self._save(job, "FAILED", self.system.public_error(error))
            return job

    def _point(self, name: str, release_id: str) -> None:
        target = self.root / "releases" / release_id
        if (
            target.parent != self.root / "releases"
            or not (target / "release.json").is_file()
            or target.is_symlink()
        ):
            raise ValueError("可恢复版本目录异常")
        temporary = self.root / ("." + name + ".next")
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target)
        os.replace(temporary, self.root / name)
        sync_directory(self.root)

    def install(self, job_id: str) -> dict:
        with exclusive(self.lock), switching_lease():
            job = read(self.state / "job.json")
            if job["id"] != str(UUID(job_id)):
                raise ValueError("升级任务已变更，请刷新")
            if job["phase"] in TERMINAL:
                return job
            if job["phase"] != "READY":
                raise ValueError("升级包尚未准备完成")
            if self.current()["id"] != job["previous"]:
                raise ValueError("当前版本已变化，请重新预检")
            self._reserve_journal()
            try:
                previous = self.root / "previous"
                job["previousLink"] = previous.resolve().name if previous.is_symlink() else None
                job["baseline"] = self.system.capture()
                self._save(job, "SWITCHING", "正在切换程序，识别与预览将短暂中断")
                self.system.stop()
                self._point("current", job["target"])
                self._save(job, "CHECKING", "正在检查本机服务和任务恢复")
                self.system.start()
                self.system.wait_healthy(job["target"], job["baseline"])
                self._point("previous", job["previous"])
                self._save(job, "SUCCEEDED", "应用升级完成")
            except Exception as error:
                if job["phase"] in {"SWITCHING", "CHECKING"}:
                    self._restore(job, self.system.public_error(error))
                else:
                    self._save(job, "FAILED", self.system.public_error(error))
            return job

    def _restore(self, job: dict, reason: str) -> None:
        try:
            self._save(job, "ROLLING_BACK", reason)
        except OSError:
            # The durable SWITCHING/CHECKING record already points to the fallback.
            # A journal I/O failure must not prevent trying to restart that fallback.
            pass
        try:
            self.system.stop()
            self._point("current", job["previous"])
            self._restore_previous_pointer(job)
            self.system.start()
            self.system.wait_healthy(job["previous"], job.get("baseline", {}))
            self._save(job, "ROLLED_BACK", reason + "；已恢复上一版本")
        except Exception as error:
            self._save(
                job, "RECOVERY_FAILED", "自动恢复未通过检查：" + self.system.public_error(error)
            )

    def _restore_previous_pointer(self, job: dict):
        if job.get("previousLink"):
            self._point("previous", job["previousLink"])
        else:
            (self.root / "previous").unlink(missing_ok=True)
            sync_directory(self.root)

    def rollback(self, job_id: str) -> dict:
        with exclusive(self.lock):
            current_job = self.state / "job.json"
            if current_job.exists() and read(current_job)["id"] == str(UUID(job_id)):
                return read(current_job)
            self.require_idle(allow_ready=True)
            previous = self.root / "previous"
            if not previous.is_symlink() or not (previous / "release.json").is_file():
                raise ValueError("没有可用的上一版本")
            target = read(previous / "release.json")
            job = {
                "id": str(UUID(job_id)),
                "action": "ROLLBACK",
                "createdAt": time.time(),
                "previous": self.current()["id"],
                "target": target["id"],
                "version": target["version"],
            }
            self._save(job, "READY", "准备回退应用版本")
        return self.install(job_id)

    def recover_before_services(self) -> None:
        """Called before systemd starts either app. Never start services in this ordering gate."""
        with exclusive(self.lock):
            path = self.state / "job.json"
            if not path.exists():
                return
            job = read(path)
            if job["phase"] in {"SWITCHING", "CHECKING", "ROLLING_BACK", "RECOVERY_PENDING"}:
                self._point("current", job["previous"])
                self._restore_previous_pointer(job)
                self._save(job, "RECOVERY_PENDING", "升级曾中断，已选择旧版本，等待服务恢复检查")
            elif job["phase"] in {"VERIFYING", "PREPARING"}:
                self._save(job, "FAILED", "准备过程曾中断，原版本未切换")

    def confirm_recovery(self) -> None:
        with exclusive(self.lock):
            path = self.state / "job.json"
            if path.exists():
                job = read(path)
                if job["phase"] == "RECOVERY_PENDING":
                    try:
                        self.system.wait_healthy(job["previous"], job.get("baseline", {}))
                        self._save(job, "ROLLED_BACK", "升级中断后已恢复旧版本并通过检查")
                    except Exception as error:
                        self._save(job, "RECOVERY_FAILED", self.system.public_error(error))
