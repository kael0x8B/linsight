package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.integration.ssh.NodeSshClient;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Only whitelisted, non-secret metadata may leave the remote credential/config files. */
final class NodeDeploymentProbe {
    private NodeDeploymentProbe() {}
    static final String RKNPU_PROBE = """
            def rknpu_available(dev_root=pathlib.Path("/dev"), drm_root=pathlib.Path("/sys/class/drm")):
                if (dev_root/"rknpu").exists():
                    return True
                # RKNPU may register a DRM render node instead of /dev/rknpu.
                # A generic GPU/display render node alone is not evidence of an NPU.
                for node in drm_root.glob("renderD*"):
                    try:
                        driver=(node/"device/uevent").read_text().splitlines()
                        if "DRIVER=RKNPU" in driver and (dev_root/"dri"/node.name).exists():
                            return True
                    except OSError:
                        continue
                return False
            """;
    static final String SCRIPT = "import pathlib\n" + RKNPU_PROBE + """
            import os, sys, json, pathlib, shutil, hashlib, subprocess, tempfile
            def emit(key, value): print(str(key)+"="+str(value))
            def env(path):
                p=pathlib.Path(path)
                return dict(line.split("=",1) for line in p.read_text().splitlines() if "=" in line and not line.startswith("#")) if p.exists() else {}
            release=env("/etc/os-release")
            memory=dict((line.split(":")[0], int(line.split()[1])//1024) for line in pathlib.Path("/proc/meminfo").read_text().splitlines() if line.startswith(("MemTotal:", "MemAvailable:")))
            emit("ARCH", os.uname().machine)
            emit("OS", release.get("PRETTY_NAME","").strip('"'))
            emit("OS_SUPPORTED", int(release.get("ID","").strip('"') in ("ubuntu","debian") and shutil.which("apt-get") is not None and pathlib.Path("/run/systemd/system").exists()))
            emit("PYTHON", ".".join(map(str,sys.version_info[:3])))
            with tempfile.TemporaryDirectory(prefix="linsight-preflight-") as temporary:
                try:
                    # Installing bundled pip on eMMC can take >20s. Preflight only
                    # tests isolation and bundled-pip availability; the installer
                    # performs the full venv/pip test before any service switch.
                    check=subprocess.run([sys.executable,"-m","venv","--without-pip",temporary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    emit("VENV", int(check.returncode == 0 and subprocess.run([temporary+"/bin/python","-c","import sys, ensurepip; assert sys.prefix != sys.base_prefix; ensurepip.version()"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode == 0))
                except subprocess.TimeoutExpired:
                    emit("VENV", 0)
            emit("FFMPEG", int(shutil.which("ffmpeg") is not None))
            emit("SUDO", int(os.geteuid()==0))
            emit("RKNPU", int(rknpu_available()))
            emit("MEMORY_MB", memory.get("MemTotal",0))
            emit("MEMORY_AVAILABLE_MB", memory.get("MemAvailable",0))
            emit("DISK_MB", shutil.disk_usage("/opt" if pathlib.Path("/opt").exists() else "/").free//1024//1024)
            identity=pathlib.Path("/var/lib/linsight/edge-agent-credential.json")
            if identity.exists():
                data=json.loads(identity.read_text())
                emit("NODE_ID", int(data["node_id"]))
                emit("TENANT_ID", int(data["tenant_id"]))
                emit("CREDENTIAL_DIGEST", hashlib.sha256(data["credential"].encode()).hexdigest())
            config=env("/etc/linsight/agent.env")
            emit("CONTROL_PLANE_URL", config.get("LINSIGHT_AGENT_CONTROL_PLANE_URL",""))
            emit("CURRENT_VERSION", config.get("LINSIGHT_AGENT_AGENT_VERSION",""))
            previous=pathlib.Path("/var/lib/linsight-deployments/source-previous")
            if previous.is_symlink() and (previous/"previous-version").is_file() and not (previous/"restored").exists():
                emit("PREVIOUS_VERSION", (previous/"previous-version").read_text().strip())
            """;

    static String inspect(NodeSshClient.Connection connection, String password) throws Exception {
        return connection.execute("timeout 25s sudo -S -p '' python3 -c " + quote(SCRIPT), password + "\n");
    }

    static void checkControlPlane(NodeSshClient.Connection connection, String url) throws Exception {
        URI uri = URI.create(url);
        if (!java.util.Set.of("http", "https").contains(uri.getScheme()) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getFragment() != null || uri.getQuery() != null) {
            throw new IllegalArgumentException("控制面地址必须为不含账号、查询参数的 HTTP(S) 服务地址");
        }
        String encoded = Base64.getEncoder().encodeToString((url.replaceAll("/+$", "")
                + "/node-api/ai-video/node/ping").getBytes(StandardCharsets.UTF_8));
        String script = "import urllib.request,json,base64; r=json.load(urllib.request.urlopen(base64.b64decode('"
                + encoded + "').decode(), timeout=10)); assert r.get('data')=='linsight-control-plane', 'not LInsight'";
        connection.execute("timeout 15s python3 -c " + quote(script), null);
    }
    static String quote(String value) { return "'" + value.replace("'", "'\"'\"'") + "'"; }
}
