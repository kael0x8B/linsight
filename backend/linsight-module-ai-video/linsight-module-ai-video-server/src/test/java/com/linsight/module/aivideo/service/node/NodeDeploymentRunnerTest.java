package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NodeDeploymentRunnerTest {
    @org.junit.jupiter.api.io.TempDir java.nio.file.Path source;

    @Test
    void sourceVersionDependsOnContentNotFileOrZipTimestamps() throws Exception {
        java.nio.file.Files.writeString(source.resolve("pyproject.toml"), "[project]\nname='test'\n");
        java.nio.file.Files.createDirectories(source.resolve("ai_runtime"));
        java.nio.file.Files.createDirectories(source.resolve("edge_agent"));
        var bootstrap = source.resolve("ai_runtime/app/core/bootstrap/pip-test.whl");
        java.nio.file.Files.createDirectories(bootstrap.getParent());
        java.nio.file.Files.writeString(bootstrap, "offline bootstrap asset");
        var module = source.resolve("edge_agent/main.py");
        java.nio.file.Files.writeString(module, "VERSION = 1\n");
        var properties = new com.linsight.module.aivideo.integration.ssh.NodeDeploymentProperties();
        properties.setRuntimeSourceDir(source.toString());
        var runner = new NodeDeploymentRunner();
        org.springframework.test.util.ReflectionTestUtils.setField(runner, "properties", properties);
        byte[] first = org.springframework.test.util.ReflectionTestUtils.invokeMethod(runner, "buildRuntimePackage");
        try (var zip = new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(first))) {
            var entries = new java.util.HashSet<String>();
            for (var entry = zip.getNextEntry(); entry != null; entry = zip.getNextEntry()) {
                entries.add(entry.getName());
            }
            assertTrue(entries.contains("ai_runtime/app/core/bootstrap/pip-test.whl"));
        }
        java.nio.file.Files.setLastModifiedTime(module, java.nio.file.attribute.FileTime.fromMillis(1000));
        byte[] second = org.springframework.test.util.ReflectionTestUtils.invokeMethod(runner, "buildRuntimePackage");
        org.junit.jupiter.api.Assertions.assertArrayEquals(first, second);
        java.nio.file.Files.writeString(module, "VERSION = 2\n");
        byte[] changed = org.springframework.test.util.ReflectionTestUtils.invokeMethod(runner, "buildRuntimePackage");
        assertFalse(NodeDeploymentRunner.sha256(first).equals(NodeDeploymentRunner.sha256(changed)));
    }

    @Test
    void installScriptMustUseDetectedPythonWithoutOverridingVendorHolds() throws Exception {
        String script = NodeDeploymentRunner.installScript(
                "linaro", "/tmp/linsight-deploy-1", true,
                "a".repeat(64));

        String dependencies = new String(NodeDeploymentRunner.dependencyScript(), java.nio.charset.StandardCharsets.UTF_8);
        assertFalse(dependencies.contains("--allow-change-held-packages"));
        assertFalse(dependencies.contains("python3-venv"));
        assertFalse(dependencies.contains("-qq"));
        assertTrue(dependencies.contains("python${python_minor}-venv"));
        assertTrue(dependencies.contains("--simulate --no-remove"));
        assertTrue(dependencies.contains("优先匹配现有 Python，不升级解释器"));
        assertTrue(dependencies.contains("candidate_version"));
        assertTrue(dependencies.contains("validate_plan"));
        assertTrue(dependencies.contains("apt-mark showhold >"));
        assertTrue(dependencies.contains("修改锁定包"));
        assertTrue(dependencies.contains("变更无关系统包"));
        assertTrue(dependencies.contains("软件源或 APT pin"));
        assertTrue(dependencies.contains("install -y \"${selected[@]}\""));
        assertTrue(dependencies.contains("仅补齐缺失项"));
        assertTrue(script.contains("bash /tmp/linsight-deploy-1/dependencies.sh install"));
        assertTrue(NodeDeploymentRunner.installScript("linaro", "/tmp/linsight-deploy-1", false, "a".repeat(64))
                .contains("bash /tmp/linsight-deploy-1/dependencies.sh check"));
        assertTrue(script.contains("environment.py /opt/linsight/venv.new"));
        assertTrue(script.contains("dependencies.sh install /opt/linsight/runtime.new/ai_runtime/app/core/environment.py"));
        assertTrue(script.indexOf("sha256sum -c -") < script.indexOf("dependencies.sh install"));
        assertTrue(script.indexOf("extractall(") < script.indexOf("dependencies.sh install"));
        assertTrue(dependencies.contains("python3 -I \"$bootstrap\" --probe"));
        assertTrue(script.contains("for attempt in 1 2 3; do"));
        assertTrue(script.contains("--retries 10 --timeout 120"));
        assertTrue(script.contains("--cache-dir /var/cache/linsight/pip"));
        assertTrue(script.contains("PIP_NO_INDEX=1 PIP_FIND_LINKS=/opt/linsight/runtime.new/deployment-wheels"));
        assertTrue(script.contains("python -m pip check"));
        assertTrue(script.contains("'/opt/linsight/runtime.new'"));
        assertFalse(script.contains("runtime.new[pytorch]"));
        assertTrue(script.indexOf("import ai_runtime.app.main, edge_agent.app.main")
                < script.indexOf("systemctl stop linsight-edge-agent.service"));
        assertTrue(dependencies.contains("跳过 APT"));
        assertTrue(script.contains("LINSIGHT_PROGRESS=70"));
        assertTrue(script.contains("sleep $((attempt * 5))"));
        assertTrue(script.contains(
                "printf '%s  %s\\n' '" + "a".repeat(64)
                        + "' '/tmp/linsight-deploy-1/runtime.zip' | sha256sum -c -"));
        assertTrue(script.contains(
                "chown -R linaro:linaro /opt/linsight/runtime.new /opt/linsight/venv.new"));
        assertTrue(script.contains("mv /opt/linsight/venv.new /opt/linsight/venv"));
        assertTrue(script.contains("ExecStart=/opt/linsight/venv/bin/python -m uvicorn"));
        assertFalse(script.contains("ExecStart=/opt/linsight/venv/bin/uvicorn"));
        assertTrue(script.contains("curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:48900/v1/health"));
        assertTrue(script.contains("timeout 45s /opt/linsight/venv.new/bin/python -c"));
        assertTrue(script.contains(
                "systemctl is-active --quiet linsight-ai-runtime.service linsight-edge-agent.service"));
        assertTrue(script.contains("recovery.sh prepare 1"));
        assertTrue(script.contains("trap 'code=$?;"));
        assertTrue(script.indexOf("recovery.sh prepare") < script.indexOf("systemctl stop linsight-edge-agent"));
        assertTrue(script.contains("PathExists=/run/linsight/node-power-request"));
        assertTrue(script.contains("linsight-node-power.path"));
        assertTrue(script.contains("case \"$action\" in"));
        assertTrue(script.contains("restart) target=reboot"));
        assertTrue(script.contains("shutdown) target=poweroff"));
        assertTrue(script.contains("NoNewPrivileges=true"));
        assertFalse(script.contains(
                "apt-get install -y -qq python3-venv ffmpeg ca-certificates curl"));
    }

    @Test
    void gatewayConsoleIsOwnedByRuntimeAndMustBeHealthyBeforeCommit() {
        String script = NodeDeploymentRunner.installScript("linaro", "/tmp/linsight-deploy-1", false, "a".repeat(64));
        assertFalse(script.contains("cat >/etc/systemd/system/linsight-local-console.service"));
        assertTrue(script.contains("systemctl disable linsight-local-console.service"));
        assertTrue(script.contains("rm -f /etc/systemd/system/linsight-local-console.service"));
        assertTrue(script.indexOf("recovery.sh prepare") < script.indexOf("systemctl disable linsight-local-console"));
        assertTrue(script.contains("http://127.0.0.1:48901/gateway-health"));
        assertTrue(script.contains("http://127.0.0.1:48901/ >/dev/null"));
        assertTrue(script.contains("\"owner\":\"runtime\""));
        assertTrue(script.indexOf("48901/gateway-health") < script.indexOf("systemctl restart linsight-edge-agent"));
    }

    @Test
    void runtimePackageDigestMustBeSha256() throws Exception {
        assertTrue(NodeDeploymentRunner.sha256("runtime-package".getBytes())
                .matches("[0-9a-f]{64}"));
        assertTrue(NodeDeploymentRunner.sha256("runtime-package".getBytes())
                .equals(NodeDeploymentRunner.sha256("runtime-package".getBytes())));
        assertFalse(NodeDeploymentRunner.sha256("runtime-package".getBytes())
                .equals(NodeDeploymentRunner.sha256("changed".getBytes())));
    }

    @Test
    void deploymentMustRequireOnlineHeartbeatFromCurrentAttempt() {
        LocalDateTime deploymentStartedAt = LocalDateTime.now();
        EdgeNodeDO node = new EdgeNodeDO();
        node.setOnlineStatus(1);
        node.setAgentVersion("source-expected");
        node.setResourceSnapshot("{\"runtimeStatus\":\"UP\"}");
        node.setLastHeartbeatTime(deploymentStartedAt.minusSeconds(1));

        assertFalse(NodeDeploymentRunner.hasFreshHeartbeat(node, deploymentStartedAt, "source-expected"));

        node.setLastHeartbeatTime(deploymentStartedAt);
        assertTrue(NodeDeploymentRunner.hasFreshHeartbeat(node, deploymentStartedAt, "source-expected"));

        node.setResourceSnapshot("{\"runtimeStatus\":\"DOWN\"}");
        assertFalse(NodeDeploymentRunner.hasFreshHeartbeat(node, deploymentStartedAt, "source-expected"));
        node.setResourceSnapshot(null);
        assertFalse(NodeDeploymentRunner.hasFreshHeartbeat(node, deploymentStartedAt, "source-expected"));
        node.setResourceSnapshot("{\"runtimeStatus\":\"UP\"}");

        node.setAgentVersion("source-old");
        assertFalse(NodeDeploymentRunner.hasFreshHeartbeat(node, deploymentStartedAt, "source-expected"));
        node.setAgentVersion("source-expected");
        node.setOnlineStatus(2);
        assertFalse(NodeDeploymentRunner.hasFreshHeartbeat(node, deploymentStartedAt, "source-expected"));
        assertFalse(NodeDeploymentRunner.hasFreshHeartbeat(null, deploymentStartedAt, "source-expected"));
    }
}
