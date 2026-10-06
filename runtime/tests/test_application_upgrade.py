import base64
import errno
import hashlib
import zipfile
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from edge_agent.app.upgrade.application import ApplicationUpdater, atomic_json, exclusive, read
from edge_agent.app.upgrade.bundle import canonical, verify
from edge_agent.app.upgrade.daemon import UpgradeControl
from edge_agent.app.upgrade.maintenance import mutation_lease, switching_lease


class PowerLoss(BaseException):
    pass


class Host:
    fail_prepare = False
    fail_check = False
    power_loss = False
    stops = 0
    checks = []

    def preflight(self, *_):
        pass

    def prepare_release(self, *_):
        if self.fail_prepare:
            raise ValueError("依赖检查失败")

    def flush(self):
        pass

    def capture(self):
        return {"tasks": [{"id": 11, "enabled": False, "revision": 3, "healthy": False}]}

    def stop(self):
        self.stops += 1

    def start(self):
        if self.power_loss:
            raise PowerLoss()

    def wait_healthy(self, version, baseline):
        self.checks.append(version)
        if version != "legacy" and self.fail_check:
            raise ValueError("任务恢复失败")

    @staticmethod
    def public_error(error):
        return str(error)


@pytest.fixture
def setup(tmp_path):
    key = Ed25519PrivateKey.generate()
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "test.pem").write_bytes(
        key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    root = tmp_path / "app"
    legacy = root / "releases/legacy"
    legacy.mkdir(parents=True)
    atomic_json(legacy / "release.json", {"id": "legacy", "version": "old"})
    (root / "current").symlink_to(legacy)
    system = Host()
    updater = ApplicationUpdater(root, tmp_path / "state", keys, tmp_path / "lock", system)
    return updater, key


def package(tmp_path, key, version="1.2.0", extra=None):
    contents = {
        "payload/python.tar.gz": b"python",
        "payload/runtime/pyproject.toml": b"project",
        "payload/runtime/ai_runtime/app/main.py": b"runtime",
        "payload/runtime/edge_agent/app/main.py": b"agent",
        "payload/runtime/gateway-console/manifest.json": b"{}",
        "payload/wheels/test.whl": b"wheel",
    }
    contents.update(extra or {})
    manifest = {
        "schemaVersion": 1,
        "artifactType": "linsight-box",
        "version": version,
        "keyId": "test",
        "architecture": "aarch64",
        "devices": ["generic"],
        "minGlibc": "2.34",
        "dataSchema": 1,
        "minUpdater": 1,
        "pythonVersion": "3.12",
        "notes": "test",
        "files": {
            name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in contents.items()
        },
    }
    target = tmp_path / f"{version}.lup"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", canonical(manifest))
        archive.writestr("manifest.sig", key.sign(canonical(manifest)))
        for name, data in contents.items():
            archive.writestr(name, data)
    return target


def test_signed_install_and_manual_rollback_preserve_data(setup, tmp_path):
    updater, key = setup
    data = tmp_path / "events.sqlite3"
    data.write_bytes(b"unacknowledged events and identity")
    identifier = str(uuid4())
    prepared = updater.prepare(identifier, package(tmp_path, key))
    assert prepared["phase"] == "READY"
    assert updater.system.stops == 0
    assert updater.current()["id"] == "legacy"
    assert updater.install(identifier)["phase"] == "SUCCEEDED"
    assert updater.status()["rollbackAvailable"]
    stops = updater.system.stops
    assert updater.install(identifier)["phase"] == "SUCCEEDED"
    assert updater.system.stops == stops
    rollback_id = str(uuid4())
    assert updater.rollback(rollback_id)["phase"] == "SUCCEEDED"
    assert updater.current()["id"] == "legacy"
    assert updater.rollback(rollback_id)["phase"] == "SUCCEEDED"
    assert updater.current()["id"] == "legacy"
    assert data.read_bytes() == b"unacknowledged events and identity"


def test_prepare_failure_never_stops_existing_services(setup, tmp_path):
    updater, key = setup
    updater.system.fail_prepare = True
    result = updater.prepare(str(uuid4()), package(tmp_path, key))
    assert result["phase"] == "FAILED"
    assert updater.system.stops == 0
    assert updater.current()["id"] == "legacy"


def test_health_failure_restores_the_entire_application(setup, tmp_path):
    updater, key = setup
    identifier = str(uuid4())
    updater.prepare(identifier, package(tmp_path, key))
    updater.system.fail_check = True
    assert updater.install(identifier)["phase"] == "ROLLED_BACK"
    assert updater.current()["id"] == "legacy"
    assert not updater.status()["rollbackAvailable"]


def test_power_loss_recovery_precedes_service_start(setup, tmp_path):
    updater, key = setup
    identifier = str(uuid4())
    updater.prepare(identifier, package(tmp_path, key))
    updater.system.power_loss = True
    with pytest.raises(PowerLoss):
        updater.install(identifier)
    assert updater.current()["id"] != "legacy"
    updater.recover_before_services()
    assert updater.current()["id"] == "legacy"
    assert read(updater.state / "job.json")["phase"] == "RECOVERY_PENDING"
    updater.system.power_loss = False
    updater.confirm_recovery()
    assert read(updater.state / "job.json")["phase"] == "ROLLED_BACK"


def test_foreign_signature_and_traversal_rejected_before_extracting(setup, tmp_path):
    updater, key = setup
    with pytest.raises(ValueError, match="签名"):
        verify(package(tmp_path, Ed25519PrivateKey.generate()), updater.keys)
    with pytest.raises(ValueError, match="路径"):
        verify(package(tmp_path, key, extra={"payload/../../escaped": b"bad"}), updater.keys)
    assert not (tmp_path / "escaped").exists()


def test_unsigned_extra_file_and_duplicate_members_are_rejected(setup, tmp_path):
    updater, key = setup
    target = package(tmp_path, key)
    with zipfile.ZipFile(target, "a") as archive:
        archive.writestr("payload/backdoor.py", b"unlisted")
    with pytest.raises(ValueError, match="清单"):
        verify(target, updater.keys)
    target = package(tmp_path, key, "2.0")
    with pytest.warns(UserWarning), zipfile.ZipFile(target, "a") as archive:
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(ValueError, match="重复"):
        verify(target, updater.keys)


def test_shared_deployment_lock_blocks_upgrade(setup, tmp_path):
    updater, key = setup
    with exclusive(updater.lock), pytest.raises(ValueError, match="其他部署"):
        updater.prepare(str(uuid4()), package(tmp_path, key))
    assert updater.system.stops == 0


def test_chunk_retries_are_idempotent_and_resumable(setup):
    updater, _ = setup
    control = UpgradeControl(updater)
    identifier = str(uuid4())
    assert control.invoke("upload.begin", {"id": identifier, "size": 6})["offset"] == 0
    chunk = {"id": identifier, "offset": 0, "data": base64.b64encode(b"abc").decode()}
    assert control.invoke("upload.chunk", chunk)["offset"] == 3
    assert control.invoke("upload.chunk", chunk)["offset"] == 3
    # New control process recovers its offset from the durable file.
    control = UpgradeControl(updater)
    assert control.invoke("upload.begin", {"id": identifier, "size": 6})["offset"] == 3
    with pytest.raises(ValueError, match="完整"):
        control.invoke("upload.finish", {"id": identifier})
    with pytest.raises(ValueError, match="不一致"):
        control.invoke("upload.chunk", {**chunk, "data": base64.b64encode(b"xyz").decode()})
    with pytest.raises(ValueError):
        control.invoke("install", {"id": identifier, "command": "shell"})


def test_switching_excludes_mutations(tmp_path):
    lock = tmp_path / "maintenance.lock"
    lock.touch()
    with switching_lease(lock), pytest.raises(ValueError, match="切换"):
        with mutation_lease(lock):
            pytest.fail("Mutation ran during switch")
    with mutation_lease(lock):
        pass


def test_inflight_mutation_timeout_leaves_old_services_running(tmp_path):
    lock = tmp_path / "maintenance.lock"
    lock.touch()
    with mutation_lease(lock), pytest.raises(ValueError, match="配置操作"):
        with switching_lease(lock, timeout=0):
            pytest.fail("Switch started while a mutation was running")


def test_failed_prepare_can_retry_and_ready_candidate_can_be_reused(setup, tmp_path):
    updater, key = setup
    bundle = package(tmp_path, key)
    updater.system.fail_prepare = True
    assert updater.prepare(str(uuid4()), bundle)["phase"] == "FAILED"
    updater.system.fail_prepare = False
    assert updater.prepare(str(uuid4()), bundle)["phase"] == "READY"
    # CLI check followed by install uploads the same immutable package under a new id.
    identifier = str(uuid4())
    assert updater.prepare(identifier, bundle)["phase"] == "READY"
    assert updater.install(identifier)["phase"] == "SUCCEEDED"


def test_worker_rejection_is_visible_to_disconnected_clients(setup):
    updater, _ = setup
    control = UpgradeControl(updater)

    def rejected():
        raise ValueError("其他部署正在执行")

    control._start(rejected)
    control.worker.join(timeout=2)
    assert control.invoke("status", {})["lastError"]["message"] == "其他部署正在执行"


def test_recovery_preserves_existing_fallback_pointer(setup, tmp_path):
    updater, key = setup
    first = str(uuid4())
    updater.prepare(first, package(tmp_path, key, "first"))
    updater.install(first)
    old_current = updater.current()["id"]
    second = str(uuid4())
    updater.prepare(second, package(tmp_path, key, "second"))
    updater.system.power_loss = True
    with pytest.raises(PowerLoss):
        updater.install(second)
    updater.recover_before_services()
    assert updater.current()["id"] == old_current
    assert (updater.root / "previous").resolve().name == "legacy"


def test_journal_reserve_allows_rollback_state_when_disk_fills(setup, tmp_path, monkeypatch):
    updater, key = setup
    identifier = str(uuid4())
    updater.prepare(identifier, package(tmp_path, key))
    original = updater._write_job
    failed = False

    def disk_full_once(job):
        nonlocal failed
        if job["phase"] == "CHECKING" and not failed:
            failed = True
            raise OSError(errno.ENOSPC, "disk full")
        return original(job)

    monkeypatch.setattr(updater, "_write_job", disk_full_once)
    updater.system.fail_check = True
    assert updater.install(identifier)["phase"] == "ROLLED_BACK"
    assert updater.current()["id"] == "legacy"
    assert not (updater.state / ".journal-reserve").exists()


def test_commit_journal_io_failure_restores_application(setup, tmp_path, monkeypatch):
    updater, key = setup
    identifier = str(uuid4())
    updater.prepare(identifier, package(tmp_path, key))
    original = updater._write_job

    def fail_commit(job):
        if job["phase"] in {"SUCCEEDED", "ROLLING_BACK"}:
            raise OSError(errno.EIO, "journal write failure")
        return original(job)

    monkeypatch.setattr(updater, "_write_job", fail_commit)
    assert updater.install(identifier)["phase"] == "ROLLED_BACK"
    assert updater.current()["id"] == "legacy"
