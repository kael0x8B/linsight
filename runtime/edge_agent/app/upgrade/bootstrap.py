"""One-time migration invoked through a trusted terminal; never replaces the legacy app."""

import argparse
import importlib.resources
import json
import os
import pwd
import shutil
import subprocess
import tempfile
from pathlib import Path

from edge_agent.app.upgrade.application import atomic_json, exclusive, read
from edge_agent.app.upgrade.bundle import VERSION, sha256, verify
from edge_agent.app.upgrade.system import SERVICES, LinuxSystem

BASE = Path("/opt/linsight-updater")
STATE = Path("/var/lib/linsight-updater")
ROOT = Path("/opt/linsight")


def show(service: str, property_name: str) -> str:
    return (
        subprocess.check_output(  # noqa: S603
            ["/usr/bin/systemctl", "show", service, f"--property={property_name}", "--value"],
            timeout=10,
        )
        .decode()
        .strip()
    )


def bootstrap(bundle: Path, public_key: Path, key_id: str, check_only=False):
    if os.geteuid() != 0 or not VERSION.fullmatch(key_id):
        raise ValueError("首次迁移需要 root 和有效的发布密钥编号")
    os.umask(0o022)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    with exclusive(Path("/run/linsight-deploy.lock")):
        journal_path = STATE / "bootstrap.json"
        journal = read(journal_path) if journal_path.exists() else None
        identity = {
            "packageSha256": sha256(bundle),
            "publicKeySha256": sha256(public_key),
            "keyId": key_id,
        }
        if journal and (journal["phase"] == "COMPLETE" or (STATE / "job.json").exists()):
            raise ValueError("设备已迁移，请使用 linsight-upgrade；安装器自身更新须单独维护")
        if journal and any(journal.get(key) != value for key, value in identity.items()):
            raise ValueError("首次迁移曾中断，请使用原升级包和原公钥继续迁移")
        if not journal and ((ROOT / "current").exists() or (STATE / "config.json").exists()):
            raise ValueError("发现已有版本管理配置，请先核对设备状态")
        system = LinuxSystem(STATE / "bootstrap.log")
        pending_timers = subprocess.check_output(  # noqa: S603
            [
                "/usr/bin/systemctl",
                "list-units",
                "--type=timer",
                "--state=active",
                "--no-legend",
                "--no-pager",
                "linsight-deploy-rollback-*.timer",
            ],
            timeout=10,
        ).strip()
        if pending_timers:
            raise ValueError("原部署尚有待确认的回滚计时器，请先完成原部署验收")
        users = [show(service, "User") or "root" for service in SERVICES]
        if users[0] != users[1]:
            raise ValueError("Runtime 与 Agent 运行用户不同，请先核对现场服务配置")
        account = pwd.getpwnam(users[0])
        for service in SERVICES:
            if show(service, "WorkingDirectory") != "/opt/linsight/runtime":
                raise ValueError("检测到自定义部署目录，首次迁移已停止，请核对适配方案")
            dropin = Path("/etc/systemd/system", service + ".d/50-application-release.conf")
            if dropin.exists() and not journal:
                raise ValueError("发现已有升级入口配置，请先检查迁移状态")
        if not (ROOT / "venv/bin/python").is_file():
            raise ValueError("原应用 Python 环境缺失")
        runtime_env, agent_env = (system._environment(service) for service in SERVICES)
        runtime_data = runtime_env.get("LINSIGHT_RUNTIME_DATA_ROOT") or runtime_env.get(
            "LINSIGHT_RUNTIME_RUNTIME_DATA_ROOT", ""
        )
        agent_data = agent_env.get("LINSIGHT_AGENT_RUNTIME_DATA_ROOT", "")
        credential = agent_env.get("LINSIGHT_AGENT_CREDENTIAL_FILE", "")
        if (
            not all(Path(value).is_absolute() for value in (runtime_data, agent_data, credential))
            or Path(runtime_data).resolve() != Path(agent_data).resolve()
            or any(
                Path(value).resolve().is_relative_to(ROOT / "releases")
                for value in (runtime_data, agent_data, credential)
            )
            or not Path(credential).is_file()
        ):
            raise ValueError("原设备数据或身份路径不是稳定的绝对路径，请核对迁移适配")
        if (
            Path("/var/lib/linsight/edge-agent/current").is_symlink()
            or Path("/var/lib/linsight/edge-agent/pending-activation.json").exists()
        ):
            raise ValueError("设备正在使用独立 Agent 签名版本，请先核对并恢复完整应用基线")
        with tempfile.TemporaryDirectory(prefix="linsight-trust-") as temporary:
            keys = Path(temporary)
            shutil.copyfile(public_key, keys / f"{key_id}.pem")
            manifest = verify(bundle, keys)
            system.preflight(manifest, bundle.stat().st_size, ROOT)
            system.capture()
            if check_only:
                return {"ready": True, "version": manifest["version"], "user": users[0]}
            payload = BASE / "bootstrap-payload"
            if not journal or journal["phase"] == "PREPARING":
                if BASE.exists():
                    if not journal or BASE.is_symlink() or (STATE / "config.json").exists():
                        raise ValueError("发现未知安装器目录，请检查首次迁移日志")
                    shutil.rmtree(BASE)
                atomic_json(journal_path, {**identity, "phase": "PREPARING"})
                BASE.mkdir(mode=0o755)
                payload.mkdir()
                verify(bundle, keys, payload)
                system.prepare_release(payload, manifest)
        # Own interpreter and wheels are outside any application release and legacy venv.
        modules = BASE / "code/edge_agent/app/upgrade"
        modules.mkdir(parents=True, exist_ok=True)
        for parent in (modules.parent, modules.parent.parent):
            (parent / "__init__.py").write_text("")
        for source in importlib.resources.files("edge_agent.app.upgrade").iterdir():
            if source.name.endswith(".py"):
                (modules / source.name).write_bytes(source.read_bytes())
        wrapper = BASE / "run.py"
        wrapper.write_text(
            "import runpy,sys\n"
            "sys.path.insert(0, '/opt/linsight-updater/code')\n"
            "module=sys.argv.pop(1)\n"
            "assert module in {'daemon','cli','launch'}\n"
            "runpy.run_module('edge_agent.app.upgrade.'+module,run_name='__main__')\n"
        )
        command = f"{payload}/venv/bin/python -I {wrapper}"
        system.flush()
        atomic_json(journal_path, {**identity, "phase": "INSTALLING"})
        keys_path = Path("/etc/linsight/upgrade-keys")
        keys_path.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(public_key, keys_path / f"{key_id}.pem")
        os.chmod(keys_path / f"{key_id}.pem", 0o644)
        state = STATE
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(state, 0o700)
        atomic_json(state / "config.json", {"uid": account.pw_uid, "gid": account.pw_gid})
        legacy = ROOT / "releases/legacy"
        legacy.mkdir(parents=True, exist_ok=True)
        env = system._environment(SERVICES[1])
        atomic_json(
            legacy / "release.json",
            {
                "id": "legacy",
                "version": env.get("LINSIGHT_AGENT_AGENT_VERSION", "legacy"),
                "runtime": str(ROOT / "runtime"),
                "python": str(ROOT / "venv/bin/python"),
                "legacy": True,
                "dataSchema": 1,
            },
            0o644,
        )
        if not (ROOT / "current").is_symlink():
            (ROOT / "current").symlink_to(legacy)
        elif (ROOT / "current").resolve() != legacy:
            raise ValueError("当前版本已变化，停止首次迁移")
        unit = Path("/etc/systemd/system/linsight-app-updater.service")
        unit.write_text(
            "[Unit]\nDescription=LInsight application update and recovery\n"
            "After=local-fs.target\n"
            "Before=linsight-ai-runtime.service linsight-edge-agent.service\n"
            "[Service]\nType=notify\nNotifyAccess=main\n"
            f"ExecStart={command} daemon\nRestart=on-failure\nRestartSec=3\n"
            "TimeoutStartSec=60\nKillMode=control-group\nUMask=0022\n"
            "[Install]\nWantedBy=multi-user.target\n"
        )
        system.flush()
        system.run(["/usr/bin/systemctl", "daemon-reload"])
        # Starting while holding the deployment lock would deadlock startup recovery.
        system.run(["/usr/bin/systemctl", "enable", unit.name])
        for service, kind in zip(SERVICES, ("runtime", "agent"), strict=True):
            dropin = Path("/etc/systemd/system", service + ".d/50-application-release.conf")
            dropin.parent.mkdir(parents=True, exist_ok=True)
            temp = dropin.with_suffix(".tmp")
            temp.write_text(
                "[Unit]\nRequires=linsight-app-updater.service\nAfter=linsight-app-updater.service\n"
                f"[Service]\nExecStart=\nExecStart={command} launch {kind}\n"
            )
            os.replace(temp, dropin)
        cli = Path("/usr/local/sbin/linsight-upgrade")
        cli.write_text(f'#!/bin/sh\nexec {command} cli "$@"\n')
        cli.chmod(0o755)
        system.flush()
        system.run(["/usr/bin/systemctl", "daemon-reload"])
    system.run(["/usr/bin/systemctl", "start", unit.name])
    atomic_json(journal_path, {**identity, "phase": "COMPLETE"})
    return {
        "ready": True,
        "version": manifest["version"],
        "message": "首次迁移完成，原服务仍在运行",
    }


def main():
    parser = argparse.ArgumentParser(description="LInsight 既有设备首次应用升级迁移")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                bootstrap(args.bundle, args.public_key, args.key_id, args.check), ensure_ascii=False
            )
        )
    except Exception as error:
        parser.exit(1, LinuxSystem.public_error(error) + "\n")


if __name__ == "__main__":
    main()
