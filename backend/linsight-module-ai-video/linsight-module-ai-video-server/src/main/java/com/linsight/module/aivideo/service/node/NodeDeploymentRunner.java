package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentCreateReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDeploymentDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeDeploymentMapper;
import com.linsight.module.aivideo.framework.security.SensitiveTextRedactor;
import com.linsight.module.aivideo.integration.ssh.NodeDeploymentProperties;
import com.linsight.module.aivideo.integration.ssh.NodeSshClient;
import jakarta.annotation.Resource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

@Component
public class NodeDeploymentRunner {
    private final String executorOwner = UUID.randomUUID().toString();
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final Set<String> PACKAGE_ROOTS = Set.of("ai_runtime", "edge_agent");
    private static final String GATEWAY_CONSOLE_MANIFEST = "gateway-console/manifest.json";
    static final String MANAGED_PYTHON_VERSION = "3.12.14";
    private static final String SERVICE_DIAGNOSTIC_COMMAND = "sudo -S -p '' bash -c '"
            + "echo \"--- service state ---\"; "
            + "systemctl --no-pager --full status linsight-ai-runtime.service linsight-edge-agent.service || true; "
            + "echo \"--- recent runtime log ---\"; "
            + "journalctl --no-pager -n 80 -u linsight-ai-runtime.service || true; "
            + "echo \"--- recent agent log ---\"; "
            + "journalctl --no-pager -n 120 -u linsight-edge-agent.service || true'";

    @Resource private NodeDeploymentMapper deploymentMapper;
    @Resource private EdgeNodeMapper edgeNodeMapper;
    @Resource private NodeSshClient sshClient;
    @Resource private NodeDeploymentProperties properties;
    @Resource private NodeService nodeService;

    public String owner() { return executorOwner; }

    @org.springframework.context.event.EventListener(org.springframework.boot.context.event.ApplicationReadyEvent.class)
    public void reconcileInterrupted() { deploymentMapper.interruptOtherExecutors(executorOwner); }

    public void submissionFailed(Long id) {
        update(id, "FAILED", "REJECTED", 0, "部署队列已满，未开始执行；请稍后重新预检");
        NodeDeploymentDO failed = new NodeDeploymentDO();
        failed.setId(id);
        failed.setFinishTime(LocalDateTime.now());
        failed.setLogStatus("COMPLETE");
        deploymentMapper.updateById(failed);
    }

    @Async("nodeDeploymentTaskExecutor")
    public void run(Long deploymentId, Long tenantId, NodeDeploymentCreateReqVO request,
                    String bootstrapToken, boolean redeploy) {
        TenantUtils.execute(tenantId,
                () -> doRun(deploymentId, tenantId, request, bootstrapToken, redeploy));
    }

    private void doRun(Long deploymentId, Long tenantId, NodeDeploymentCreateReqVO request,
                       String bootstrapToken, boolean redeploy) {
        try {
            NodeDeploymentDO record = deploymentMapper.selectById(deploymentId);
            if (record == null || !"QUEUED".equals(record.getStatus())) return;
            if ("ROLLBACK".equals(request.getAction())) {
                runSourceRollback(deploymentId, tenantId, request);
                return;
            }
            update(deploymentId, "RUNNING", "PACKAGING", 12, "正在生成 Runtime 与 Edge Agent 部署包");
            byte[] runtimePackage = buildRuntimePackage(record.getTargetArch(),
                    deploymentPythonVersion(record.getPythonVersion()));
            if (!redeploy) bootstrapToken = nodeService.createBootstrapToken(request.getNodeName(), 30).getToken();
            String runtimePackageSha256 = sha256(runtimePackage);
            recordRuntimePackageSha256(deploymentId, runtimePackageSha256);
            String runtimeKey = randomSecret();
            String remoteRoot = "/tmp/linsight-deploy-" + deploymentId;
            String trustedKey = request.getHostKeyType() + " " + request.getHostKey();
            LocalDateTime verificationStartedAt;
            update(deploymentId, "RUNNING", "CONNECTING", 22, "正在校验 SSH 主机指纹");
            EdgeNodeDO node;
            try (NodeSshClient.Connection connection = sshClient.connect(request, trustedKey)) {
                if (!request.getHostKeyFingerprint().equals(connection.hostKeyFingerprint())) {
                    throw new IllegalStateException("SSH 主机指纹与预检结果不一致");
                }
                try {
                    NodeDeploymentProbe.checkControlPlane(connection, request.getControlPlaneUrl());
                    connection.execute("umask 077; mkdir -p " + remoteRoot
                            + "; touch " + remoteRoot + "/runtime.env " + remoteRoot + "/agent.env", null);
                    update(deploymentId, "RUNNING", "UPLOADING", 38, "正在上传 Runtime 与服务配置");
                    connection.upload(runtimePackage, remoteRoot + "/runtime.zip");
                    connection.upload(recoveryScript(), remoteRoot + "/recovery.sh");
                    connection.upload(dependencyScript(), remoteRoot + "/dependencies.sh");
                    connection.upload(pythonScript(), remoteRoot + "/python.sh");
                    connection.upload(diskPressureCleanupScript(), remoteRoot + "/disk-pressure-cleanup.sh");
                    connection.upload((record.getPreviousVersion() == null ? "" : record.getPreviousVersion())
                            .getBytes(StandardCharsets.UTF_8), remoteRoot + "/previous-version");
                    connection.upload(runtimeEnv(runtimeKey, request.getControlPlaneUrl())
                            .getBytes(StandardCharsets.UTF_8), remoteRoot + "/runtime.env");
                    connection.upload(agentEnv(request, bootstrapToken, runtimeKey, runtimePackageSha256)
                                    .getBytes(StandardCharsets.UTF_8),
                            remoteRoot + "/agent.env");
                    connection.upload(installScript(request.getUsername(), remoteRoot,
                            Boolean.TRUE.equals(request.getInstallDependencies()), runtimePackageSha256)
                            .getBytes(StandardCharsets.UTF_8),
                            remoteRoot + "/install.sh");
                    update(deploymentId, "RUNNING", "INSTALLING", 55,
                            "正在安装 Python 环境与系统依赖，首次安装可能需要数分钟");
                    connection.execute("sudo -S -p '' stdbuf -oL -eL bash " + remoteRoot + "/install.sh 2>&1",
                            request.getPassword() + System.lineSeparator(),
                            new RemoteOutputObserver(deploymentId));
                    verificationStartedAt = LocalDateTime.now();
                    update(deploymentId, "RUNNING", "VERIFYING", 88,
                            "服务已启动，正在确认目标版本与 Runtime 健康心跳");
                node = waitForFreshHeartbeat(tenantId, request.getNodeCode(), verificationStartedAt,
                        "source-" + runtimePackageSha256.substring(0, 12));
                if (node == null) {
                    appendOutput(deploymentId, "[VERIFYING] 未收到目标版本且 Runtime 健康的新心跳，正在采集服务诊断日志\n");
                    connection.execute(SERVICE_DIAGNOSTIC_COMMAND,
                            request.getPassword() + System.lineSeparator(),
                            new RemoteOutputObserver(deploymentId));
                    EdgeNodeDO nodeAtHost = request.getNodeId() == null ? null : edgeNodeMapper.selectById(request.getNodeId());
                    String identityHint = nodeAtHost == null ? ""
                            : "；该地址当前仍以上报编码 " + nodeAtHost.getCode() + " 在线";
                    throw new IllegalStateException(
                            "服务已安装，但 60 秒内未收到节点 " + request.getNodeCode()
                                    + " 的目标版本健康心跳" + identityHint + "，请查看部署输出");
                }
                connection.execute("sudo -S -p '' bash -c " + NodeDeploymentProbe.quote(
                                "bash /var/lib/linsight-deployments/" + deploymentId
                                        + "/restore.sh commit " + deploymentId
                                        + " && systemctl start linsight-disk-pressure-cleanup.service"),
                        request.getPassword() + "\n",
                        new RemoteOutputObserver(deploymentId));
                } catch (Exception error) {
                    try {
                        connection.execute(SERVICE_DIAGNOSTIC_COMMAND, request.getPassword() + "\n",
                                new RemoteOutputObserver(deploymentId));
                    } catch (Exception diagnosticError) {
                        appendOutput(deploymentId, "[DIAGNOSTIC] 远端诊断不可用\n");
                    }
                    try {
                        connection.execute("sudo -S -p '' bash -c " + NodeDeploymentProbe.quote(
                                "if [ -f /var/lib/linsight-deployments/" + deploymentId + "/restore.sh ]; then bash "
                                + "/var/lib/linsight-deployments/" + deploymentId + "/restore.sh restore " + deploymentId + "; fi"),
                                request.getPassword() + "\n", new RemoteOutputObserver(deploymentId));
                    } catch (Exception recoveryError) {
                        appendOutput(deploymentId, "[RECOVERY] SSH 恢复不可达；已布置的远端看门狗将在超时后尝试恢复，请重新预检确认\n");
                    }
                    throw error;
                } finally {
                    try { connection.execute("rm -rf -- " + remoteRoot, null); }
                    catch (Exception cleanupError) { appendOutput(deploymentId, "[CLEANUP] 临时文件清理未确认\n"); }
                }
            }
            NodeDeploymentDO done = new NodeDeploymentDO();
            done.setId(deploymentId);
            done.setStatus("SUCCEEDED");
            done.setStage("COMPLETED");
            done.setProgress(100);
            done.setMessage(redeploy ? "在线升级完成，节点已恢复心跳"
                    : "部署完成，节点已注册并开始上报心跳");
            done.setEdgeNodeId(node.getId());
            done.setFinishTime(LocalDateTime.now());
            done.setLogStatus("COMPLETE");
            deploymentMapper.updateById(done);
            appendOutput(deploymentId, "[COMPLETED] " + done.getMessage() + "\n");
        } catch (Exception error) {
            NodeDeploymentDO failed = new NodeDeploymentDO();
            failed.setId(deploymentId);
            failed.setStatus("FAILED");
            failed.setStage("FAILED");
            failed.setMessage(sanitize(error));
            failed.setDiagnosticId("deployment-" + deploymentId);
            failed.setLogStatus(error.getMessage() != null && error.getMessage().contains("日志持久化失败") ? "FAILED" : "COMPLETE");
            failed.setFinishTime(LocalDateTime.now());
            deploymentMapper.updateById(failed);
            appendOutput(deploymentId, "[FAILED] " + sanitize(error) + "\n");
        } finally {
            request.setPassword(null);
        }
    }

    private static byte[] recoveryScript() throws java.io.IOException {
        try (var stream = NodeDeploymentRunner.class.getResourceAsStream("/node/deployment-recovery.sh")) {
            if (stream == null) throw new IllegalStateException("部署恢复脚本缺失");
            return stream.readAllBytes();
        }
    }

    static byte[] dependencyScript() throws java.io.IOException {
        try (var stream = NodeDeploymentRunner.class.getResourceAsStream("/node/deployment-dependencies.sh")) {
            if (stream == null) throw new IllegalStateException("部署依赖检查脚本缺失");
            return stream.readAllBytes();
        }
    }

    static byte[] pythonScript() throws java.io.IOException {
        try (var stream = NodeDeploymentRunner.class.getResourceAsStream("/node/deployment-python.sh")) {
            if (stream == null) throw new IllegalStateException("独立 Python 安装脚本缺失");
            return stream.readAllBytes();
        }
    }

    static String deploymentPythonVersion(String detectedVersion) {
        return detectedVersion != null && detectedVersion.matches("3\\.(12|13)(?:\\..*)?")
                ? detectedVersion : MANAGED_PYTHON_VERSION;
    }

    static byte[] diskPressureCleanupScript() throws java.io.IOException {
        try (var stream = NodeDeploymentRunner.class.getResourceAsStream("/node/disk-pressure-cleanup.sh")) {
            if (stream == null) throw new IllegalStateException("磁盘压力处置脚本缺失");
            return stream.readAllBytes();
        }
    }

    private void runSourceRollback(Long id, Long tenantId, NodeDeploymentCreateReqVO request) throws Exception {
        update(id, "RUNNING", "ROLLBACK", 40, "正在恢复上一份完整部署快照");
        try (var connection = sshClient.connect(request, request.getHostKeyType() + " " + request.getHostKey())) {
            String previous = connection.execute("sudo -S -p '' cat /var/lib/linsight-deployments/source-previous/previous-version",
                    request.getPassword() + "\n").trim();
            NodeDeploymentDO expected = new NodeDeploymentDO();
            expected.setId(id); expected.setTargetVersion(previous); deploymentMapper.updateById(expected);
            connection.execute("sudo -S -p '' bash -c " + NodeDeploymentProbe.quote(
                    "base=$(readlink -f /var/lib/linsight-deployments/source-previous); "
                    + "[ \"$(dirname \"$base\")\" = /var/lib/linsight-deployments ]; "
                    + "id=$(basename \"$base\"); [[ \"$id\" =~ ^[0-9]+$ ]]; bash \"$base/restore.sh\" manual \"$id\""),
                    request.getPassword() + "\n", new RemoteOutputObserver(id));
            LocalDateTime started = LocalDateTime.now();
            if (waitForFreshHeartbeat(tenantId, request.getNodeCode(), started, previous) == null) {
                throw new IllegalStateException("快照已恢复但未收到原版本新心跳，请检查节点服务");
            }
            update(id, "SUCCEEDED", "COMPLETED", 100, "完整部署已回滚，原版本心跳已确认");
            NodeDeploymentDO done = new NodeDeploymentDO();
            done.setId(id); done.setFinishTime(LocalDateTime.now()); done.setLogStatus("COMPLETE");
            deploymentMapper.updateById(done);
        }
    }

    private EdgeNodeDO waitForFreshHeartbeat(Long tenantId, String code,
                                             LocalDateTime deploymentStartedAt, String expectedVersion)
            throws InterruptedException {
        for (int index = 0; index < 30; index++) {
            EdgeNodeDO node = edgeNodeMapper.selectByTenantIdAndCode(tenantId, code);
            if (hasFreshHeartbeat(node, deploymentStartedAt, expectedVersion)) return node;
            Thread.sleep(2_000);
        }
        return null;
    }

    static boolean hasFreshHeartbeat(EdgeNodeDO node, LocalDateTime deploymentStartedAt,
                                     String expectedVersion) {
        return node != null
                && expectedVersion.equals(node.getAgentVersion())
                && Integer.valueOf(1).equals(node.getOnlineStatus())
                && node.getLastHeartbeatTime() != null
                && !node.getLastHeartbeatTime().isBefore(deploymentStartedAt)
                && hasHealthyRuntime(node.getResourceSnapshot());
    }

    private static boolean hasHealthyRuntime(String snapshot) {
        if (snapshot == null || snapshot.isBlank()) return false;
        try {
            var resources = com.linsight.framework.common.util.json.JsonUtils.parseMap(snapshot);
            return resources != null && "UP".equals(resources.get("runtimeStatus"));
        } catch (RuntimeException error) {
            return false;
        }
    }

    private void update(Long id, String status, String stage, int progress, String message) {
        NodeDeploymentDO update = new NodeDeploymentDO();
        update.setId(id);
        update.setStatus(status);
        update.setStage(stage);
        update.setProgress(progress);
        update.setMessage(message);
        deploymentMapper.updateById(update);
        appendOutput(id, "[" + stage + "] " + message + "\n");
    }

    private void recordRuntimePackageSha256(Long id, String sha256) {
        NodeDeploymentDO update = new NodeDeploymentDO();
        update.setId(id);
        update.setRuntimePackageSha256(sha256);
        update.setTargetVersion("source-" + sha256.substring(0, 12));
        deploymentMapper.updateById(update);
        appendOutput(id, "[PACKAGING] Runtime 包 SHA256：" + sha256 + "\n");
    }

    private void appendOutput(Long id, String output) {
        String redacted = SensitiveTextRedactor.redactText(output);
        if (redacted == null || redacted.isEmpty()) {
            return;
        }
        String safe = redacted.replaceAll("[\\p{Cntrl}&&[^\\r\\n\\t]]", "");
        deploymentMapper.appendOutput(id, safe);
    }

    private final class RemoteOutputObserver implements java.util.function.Consumer<String> {
        private final Long deploymentId;
        private final StringBuilder pending = new StringBuilder();

        private RemoteOutputObserver(Long deploymentId) {
            this.deploymentId = deploymentId;
        }

        @Override
        public void accept(String chunk) {
            appendOutput(deploymentId, chunk);
            pending.append(chunk);
            int newline;
            while ((newline = pending.indexOf("\n")) >= 0) {
                String line = pending.substring(0, newline).trim();
                pending.delete(0, newline + 1);
                applyProgress(line);
            }
            if (pending.length() > 8192) pending.delete(0, pending.length() - 4096);
        }

        private void applyProgress(String line) {
            if (!line.startsWith("LINSIGHT_PROGRESS=")) {
                return;
            }
            int separator = line.indexOf(' ');
            if (separator <= "LINSIGHT_PROGRESS=".length()) {
                return;
            }
            String progressText = line.substring("LINSIGHT_PROGRESS=".length(), separator);
            if (!progressText.matches("\\d{1,3}")) {
                return;
            }
            int progress = Integer.parseInt(progressText);
            update(deploymentId, "RUNNING", "INSTALLING", progress,
                    line.substring(separator + 1));
        }
    }

    private byte[] buildRuntimePackage() throws Exception {
        return buildRuntimePackage(null, null);
    }

    private byte[] buildRuntimePackage(String architecture, String pythonVersion) throws Exception {
        Path source = properties.resolveRuntimeSource();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes, StandardCharsets.UTF_8)) {
            addFile(zip, source, source.resolve("pyproject.toml"));
            for (String root : PACKAGE_ROOTS.stream().sorted().toList()) {
                try (var paths = Files.walk(source.resolve(root))) {
                    paths.filter(Files::isRegularFile)
                            .filter(path -> !path.toString().contains("__pycache__"))
                            .filter(path -> !path.getFileName().toString().endsWith(".pyc"))
                            .sorted()
                            .forEach(path -> addFileUnchecked(zip, source, path));
                }
            }
            GatewayConsoleBundle gatewayConsole = requireGatewayConsoleBundle(source);
            addFile(zip, source, gatewayConsole.manifest());
            addFile(zip, source, gatewayConsole.artifact());
            addOfflinePython(zip, source, architecture);
            for (Path wheel : NodeDeploymentWheelhouse.verifiedFiles(source, architecture, pythonVersion)) {
                ZipEntry entry = new ZipEntry("deployment-wheels/" + wheel.getFileName());
                entry.setTime(0L);
                zip.putNextEntry(entry);
                Files.copy(wheel, zip);
                zip.closeEntry();
            }
        }
        return bytes.toByteArray();
    }

    private static void addOfflinePython(ZipOutputStream zip, Path source, String architecture) throws Exception {
        String target;
        String expectedSha256;
        if ("aarch64".equals(architecture) || "arm64".equals(architecture)) {
            target = "aarch64";
            expectedSha256 = "c0574c9c9fec561eb192ad510e4e79aaad039929b3531b3bb873e2f630fb14a9";
        } else if ("x86_64".equals(architecture) || "amd64".equals(architecture)) {
            target = "x86_64";
            expectedSha256 = "5eae8cf79dd47fc2496a4fccc892936be831ce7a84d984b2299dfb1cdb592682";
        } else {
            return;
        }
        Path artifact = source.resolve("deployment-python/cpython-" + MANAGED_PYTHON_VERSION
                + "+20260924-" + target + "-unknown-linux-gnu-install_only.tar.gz");
        if (!Files.exists(artifact)) return;
        if (Files.isSymbolicLink(artifact) || !Files.isRegularFile(artifact)
                || !expectedSha256.equals(sha256(Files.readAllBytes(artifact)))) {
            throw new IllegalStateException("离线 Python 安装包 SHA256 不匹配：" + artifact.getFileName());
        }
        addFile(zip, source, artifact);
    }

    private static GatewayConsoleBundle requireGatewayConsoleBundle(Path source) throws Exception {
        Path manifest = source.resolve(GATEWAY_CONSOLE_MANIFEST);
        if (!Files.isRegularFile(manifest)) {
            throw new IllegalStateException("网关控制台制品缺失，请先执行 make gateway-console");
        }
        var value = JsonUtils.parseMap(Files.readString(manifest, StandardCharsets.UTF_8));
        if (value == null || !"1.0".equals(value.get("schemaVersion"))
                || !"linsightGatewayConsole".equals(value.get("artifactType"))
                || !(value.get("artifact") instanceof java.util.Map<?, ?> artifact)) {
            throw new IllegalStateException("网关控制台 manifest 无效");
        }
        Object rawFileName = artifact.get("fileName");
        Object rawSha256 = artifact.get("sha256");
        if (!(rawFileName instanceof String fileName)
                || !fileName.matches("gateway-console-[0-9a-f]{12}\\.tar\\.gz")
                || !(rawSha256 instanceof String expectedSha256)
                || !expectedSha256.matches("[0-9a-f]{64}")) {
            throw new IllegalStateException("网关控制台 manifest 的制品字段无效");
        }
        Path bundleDirectory = manifest.getParent().toAbsolutePath().normalize();
        Path archive = bundleDirectory.resolve(fileName).normalize();
        if (!archive.getParent().equals(bundleDirectory) || !Files.isRegularFile(archive)) {
            throw new IllegalStateException("网关控制台制品文件缺失");
        }
        String actualSha256 = sha256(Files.readAllBytes(archive));
        if (!MessageDigest.isEqual(actualSha256.getBytes(StandardCharsets.US_ASCII),
                expectedSha256.getBytes(StandardCharsets.US_ASCII))) {
            throw new IllegalStateException("网关控制台制品 SHA256 不匹配");
        }
        return new GatewayConsoleBundle(manifest, archive);
    }

    private record GatewayConsoleBundle(Path manifest, Path artifact) {}

    private static void addFileUnchecked(ZipOutputStream zip, Path root, Path file) {
        try { addFile(zip, root, file); } catch (Exception error) { throw new IllegalStateException(error); }
    }

    private static void addFile(ZipOutputStream zip, Path root, Path file) throws Exception {
        ZipEntry entry = new ZipEntry(root.relativize(file).toString().replace('\\', '/'));
        entry.setTime(0L);
        zip.putNextEntry(entry);
        Files.copy(file, zip);
        zip.closeEntry();
    }

    private static String runtimeEnv(String runtimeKey, String controlPlaneUrl) {
        return "LINSIGHT_RUNTIME_API_KEY=" + runtimeKey + "\n"
                + "LINSIGHT_RUNTIME_DATA_ROOT=/var/lib/linsight/runtime-data\n"
                + "LINSIGHT_RUNTIME_PLATFORM_URL=" + controlPlaneUrl.replaceAll("/+$", "") + "\n"
                + "LINSIGHT_RUNTIME_PREVIEW_ROOT=/var/lib/linsight/preview\n";
    }

    private static String agentEnv(NodeDeploymentCreateReqVO request, String token, String runtimeKey,
                                   String runtimePackageSha256) {
        URI controlPlane = URI.create(request.getControlPlaneUrl());
        if (!("http".equals(controlPlane.getScheme()) || "https".equals(controlPlane.getScheme()))) {
            throw new IllegalArgumentException("控制面地址必须使用 HTTP 或 HTTPS");
        }
        String bootstrap = token == null ? "" : "LINSIGHT_AGENT_BOOTSTRAP_TOKEN=" + token + "\n";
        return "LINSIGHT_AGENT_CONTROL_PLANE_URL=" + request.getControlPlaneUrl().replaceAll("/+$", "") + "\n"
                + bootstrap
                + "LINSIGHT_AGENT_CREDENTIAL_FILE=/var/lib/linsight/edge-agent-credential.json\n"
                + "LINSIGHT_AGENT_NODE_CODE=" + request.getNodeCode() + "\n"
                + "LINSIGHT_AGENT_NODE_NAME=" + request.getNodeName() + "\n"
                + "LINSIGHT_AGENT_AGENT_VERSION=source-" + runtimePackageSha256.substring(0, 12) + "\n"
                + "LINSIGHT_AGENT_RUNTIME_URL=http://127.0.0.1:48900\n"
                + "LINSIGHT_AGENT_RUNTIME_API_KEY=" + runtimeKey + "\n"
                + "LINSIGHT_AGENT_RUNTIME_DATA_ROOT=/var/lib/linsight/runtime-data\n"
                + "LINSIGHT_AGENT_UPGRADE_ROOT=/var/lib/linsight/edge-agent\n"
                + "LINSIGHT_AGENT_DISK_CLEANUP_STATUS_FILE=/var/lib/linsight/disk-pressure/last-run.env\n"
                + "LINSIGHT_AGENT_EVENT_POLL_INTERVAL_SECONDS=0.5\n"
                + "LINSIGHT_AGENT_OVERLAY_POLL_INTERVAL_SECONDS=0.1\n";
    }

    static String installScript(String username, String remoteRoot, boolean installDependencies,
                                String runtimePackageSha256) {
        String dependencies = "bash " + remoteRoot + "/dependencies.sh "
                + (installDependencies ? "install" : "check")
                + " /opt/linsight/runtime.new/ai_runtime/app/core/environment.py\n";
        String id = remoteRoot.substring(remoteRoot.lastIndexOf('-') + 1);
        if (!id.matches("[0-9]+")) throw new IllegalArgumentException("Invalid deployment directory");
        String recovery = "/var/lib/linsight-deployments/" + id + "/restore.sh";
        return "#!/usr/bin/env bash\nset -euo pipefail\numask 077\n"
                + "exec 9>/run/linsight-deploy.lock\nflock -n 9 || { echo 'Another deployment is running'; exit 75; }\n"
                + "[ ! -f /var/lib/linsight-updater/config.json ] || { echo 'LINSIGHT_ERROR=该设备已启用完整应用升级，请使用应用升级包入口；保留原部署目录用于回滚'; exit 64; }\n"
                + "trap 'code=$?; if [ \"$code\" != 0 ] && [ -f " + recovery
                + " ]; then LINSIGHT_DEPLOY_LOCK_HELD=1 bash " + recovery + " restore " + id + " || true; fi' EXIT\n"
                + "echo 'LINSIGHT_PROGRESS=56 正在校验并解压 Runtime 包'\n"
                + "install -d -m 0755 /opt/linsight /etc/linsight\n"
                + "install -d -m 0755 /var/cache/linsight/pip\n"
                + "install -d -o " + username + " -g " + username + " -m 0700 /var/lib/linsight /var/lib/linsight/runtime-data /var/lib/linsight/preview\n"
                + "echo 'LINSIGHT_PROGRESS=54 正在回收可再生缓存与过期回滚快照'\n"
                + "LINSIGHT_DEPLOY_LOCK_HELD=1 bash " + remoteRoot + "/disk-pressure-cleanup.sh --force\n"
                + "available_kib=$(df -Pk / | awk 'NR==2 {print $4}')\n"
                + "[ \"$available_kib\" -ge 1572864 ] || { echo 'LINSIGHT_ERROR=安全清理后可用空间仍不足 1.5 GiB；未触碰待补传证据，请先扩容或人工核查'; exit 28; }\n"
                + "printf '%s  %s\\n' '" + runtimePackageSha256 + "' '" + remoteRoot
                + "/runtime.zip' | sha256sum -c -\n"
                + "rm -rf /opt/linsight/runtime.new\nmkdir -p /opt/linsight/runtime.new\n"
                + "python3 -c \"import zipfile; zipfile.ZipFile('" + remoteRoot + "/runtime.zip').extractall('/opt/linsight/runtime.new')\"\n"
                + "source " + remoteRoot + "/python.sh " + (installDependencies ? "install" : "check") + "\n"
                + "\"$LINSIGHT_PYTHON\" -I /opt/linsight/runtime.new/ai_runtime/app/gateway/console_artifact.py install "
                + "--bundle-dir /opt/linsight/runtime.new/gateway-console "
                + "--target /opt/linsight/runtime.new/gateway-console/current\n"
                + dependencies
                + "echo 'LINSIGHT_PROGRESS=66 正在创建隔离 Python 环境'\n"
                + "rm -rf /opt/linsight/venv.new\n"
                + "timeout 120s \"$LINSIGHT_PYTHON\" -I /opt/linsight/runtime.new/ai_runtime/app/core/environment.py /opt/linsight/venv.new\n"
                + "echo 'LINSIGHT_PROGRESS=70 正在安装 Python 依赖，网络较慢时会自动重试'\n"
                + "if [ -f /opt/linsight/runtime.new/deployment-wheels/manifest.json ]; then\n"
                + "  echo 'LINSIGHT_PROGRESS=70 正在安装随包离线 Python 依赖'\n"
                + "  echo '[DEPENDENCY] 使用随包离线依赖，不访问 PyPI'\n"
                + "  PIP_NO_INDEX=1 PIP_FIND_LINKS=/opt/linsight/runtime.new/deployment-wheels "
                + "/opt/linsight/venv.new/bin/python -m pip install --disable-pip-version-check --no-cache-dir "
                + "--progress-bar off '/opt/linsight/runtime.new' "
                + "|| { echo 'LINSIGHT_ERROR=离线依赖安装失败，原服务未切换；请检查随包 wheel 与目标平台兼容性'; exit 1; }\n"
                + "else\n"
                + "echo '[DEPENDENCY] 未准备匹配的离线依赖，使用在线安装'\n"
                + "for attempt in 1 2 3; do\n"
                + "  if /opt/linsight/venv.new/bin/python -m pip install --disable-pip-version-check "
                + "--cache-dir /var/cache/linsight/pip --progress-bar off "
                + "--retries 10 --timeout 120 '/opt/linsight/runtime.new'; then break; fi\n"
                + "  if [ \"$attempt\" = 3 ]; then echo 'LINSIGHT_ERROR=Python 依赖安装失败，已重试 3 次；原服务未切换，具体原因见上方 pip 日志'; exit 1; fi\n"
                + "  sleep $((attempt * 5))\n"
                + "done\n"
                + "fi\n"
                + "/opt/linsight/venv.new/bin/python -m pip check\n"
                // Optional model dependencies are prepared on demand in isolated profiles.
                + "timeout 45s /opt/linsight/venv.new/bin/python -c 'import ai_runtime.app.main, edge_agent.app.main' "
                + "|| { echo 'LINSIGHT_ERROR=新 Runtime/Agent 导入失败或超时，原服务未切换'; exit 1; }\n"
                + "test -s /opt/linsight/runtime.new/gateway-console/current/gateway.html\n"
                + "echo 'LINSIGHT_PROGRESS=80 正在切换 Runtime 并写入 systemd 服务'\n"
                + "chown -R " + username + ":" + username + " /opt/linsight/runtime.new /opt/linsight/venv.new\n"
                + "LINSIGHT_DEPLOY_LOCK_HELD=1 bash " + remoteRoot + "/recovery.sh prepare " + id + "\n"
                + "install -m 0600 " + remoteRoot + "/previous-version /var/lib/linsight-deployments/" + id + "/previous-version\n"
                + "systemctl stop linsight-edge-agent.service linsight-ai-runtime.service linsight-local-console.service 2>/dev/null || true\n"
                + "systemctl disable linsight-local-console.service 2>/dev/null || true\n"
                + "rm -f /etc/systemd/system/linsight-local-console.service\n"
                + "rm -rf /opt/linsight/runtime\n"
                + "mv /opt/linsight/runtime.new /opt/linsight/runtime\n"
                + "rm -rf /opt/linsight/venv\n"
                + "mv /opt/linsight/venv.new /opt/linsight/venv\n"
                + "install -m 0600 " + remoteRoot + "/runtime.env /etc/linsight/runtime.env\n"
                + "install -m 0600 " + remoteRoot + "/agent.env /etc/linsight/agent.env\n"
                + "cat >/etc/systemd/system/linsight-ai-runtime.service <<'UNIT'\n[Unit]\nDescription=LInsight AI Runtime\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser=" + username + "\nWorkingDirectory=/opt/linsight/runtime\nEnvironmentFile=/etc/linsight/runtime.env\nExecStart=/opt/linsight/venv/bin/python -m uvicorn ai_runtime.app.main:create_app --factory --host 127.0.0.1 --port 48900\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=true\n\n[Install]\nWantedBy=multi-user.target\nUNIT\n"
                + "cat >/usr/local/sbin/linsight-accelerator-metrics-permissions <<'SCRIPT'\n#!/usr/bin/env bash\nset -u\nload=/sys/kernel/debug/rknpu/load\nif test -e \"$load\"; then\n  chgrp " + username + " /sys/kernel/debug /sys/kernel/debug/rknpu \"$load\" 2>/dev/null && chmod g+x /sys/kernel/debug /sys/kernel/debug/rknpu 2>/dev/null && chmod g+r \"$load\" 2>/dev/null || echo 'LINSIGHT_WARNING=无法授权 Edge Agent 读取 RKNPU 负载' >&2\nfi\nexit 0\nSCRIPT\n"
                + "chmod 0755 /usr/local/sbin/linsight-accelerator-metrics-permissions\n"
                + "cat >/etc/systemd/system/linsight-accelerator-metrics-permissions.service <<'UNIT'\n[Unit]\nDescription=Grant LInsight access to accelerator utilization only\nBefore=linsight-edge-agent.service\n\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/linsight-accelerator-metrics-permissions\nNoNewPrivileges=true\nPrivateTmp=true\n\n[Install]\nWantedBy=multi-user.target\nUNIT\n"
                + "install -m 0755 " + remoteRoot + "/disk-pressure-cleanup.sh /usr/local/sbin/linsight-disk-pressure-cleanup\n"
                + "printf 'LINSIGHT_DISK_CLEANUP_TRIGGER_PERCENT=80\\nLINSIGHT_DISK_CLEANUP_CRITICAL_PERCENT=90\\n' >/etc/linsight/disk-pressure.env\n"
                + "chmod 0600 /etc/linsight/disk-pressure.env\n"
                + "cat >/etc/systemd/system/linsight-disk-pressure-cleanup.service <<'UNIT'\n[Unit]\nDescription=LInsight bounded disk pressure remediation\nAfter=local-fs.target\n\n[Service]\nType=oneshot\nEnvironmentFile=/etc/linsight/disk-pressure.env\nExecStart=/usr/local/sbin/linsight-disk-pressure-cleanup\nNoNewPrivileges=true\nProtectSystem=full\nReadWritePaths=/opt/linsight /var/cache/linsight /var/lib/linsight-deployments /var/lib/linsight/edge-agent /var/lib/linsight/disk-pressure /tmp\nNice=10\nIOSchedulingClass=idle\nUNIT\n"
                + "cat >/etc/systemd/system/linsight-disk-pressure-cleanup.timer <<'UNIT'\n[Unit]\nDescription=Check LInsight edge disk pressure every 15 minutes\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\nRandomizedDelaySec=60\nPersistent=true\nUnit=linsight-disk-pressure-cleanup.service\n\n[Install]\nWantedBy=timers.target\nUNIT\n"
                + "cat >/etc/systemd/system/linsight-edge-agent.service <<'UNIT'\n[Unit]\nDescription=LInsight Edge Agent\nAfter=network-online.target linsight-ai-runtime.service linsight-accelerator-metrics-permissions.service\nWants=network-online.target linsight-accelerator-metrics-permissions.service\nRequires=linsight-ai-runtime.service\n\n[Service]\nType=simple\nUser=" + username + "\nWorkingDirectory=/opt/linsight/runtime\nEnvironmentFile=/etc/linsight/agent.env\nEnvironmentFile=-/etc/linsight/agent-upgrade.env\nExecStart=/opt/linsight/venv/bin/python -m edge_agent.app.upgrade.launcher\nRestart=always\nRestartSec=3\nNoNewPrivileges=true\n\n[Install]\nWantedBy=multi-user.target\nUNIT\n"
                + "install -d -o " + username + " -g " + username + " -m 0700 /run/linsight /var/lib/linsight/edge-agent\n"
                + "rm -f /var/lib/linsight/edge-agent/current /var/lib/linsight/edge-agent/pending-activation.json /var/lib/linsight/edge-agent/failed-activation-version\n"
                + "printf 'd /run/linsight 0700 " + username + " " + username
                + " -\\n' >/etc/tmpfiles.d/linsight.conf\n"
                + "cat >/usr/local/sbin/linsight-node-power <<'SCRIPT'\n#!/usr/bin/env bash\nset -euo pipefail\nrequest=/run/linsight/node-power-request\naction=$(tr -d '\\r\\n' <\"$request\")\nrm -f -- \"$request\"\ncase \"$action\" in\n  restart) target=reboot ;;\n  shutdown) target=poweroff ;;\n  *) exit 64 ;;\nesac\n/usr/bin/systemd-run --quiet --unit=linsight-node-${action}-$(date +%s) --on-active=15s /usr/bin/systemctl \"$target\"\nSCRIPT\n"
                + "chmod 0755 /usr/local/sbin/linsight-node-power\n"
                + "cat >/etc/systemd/system/linsight-node-power.service <<'UNIT'\n[Unit]\nDescription=LInsight requested node lifecycle action\n\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/linsight-node-power\nNoNewPrivileges=true\nProtectSystem=strict\nReadWritePaths=/run/linsight\nPrivateTmp=true\nUNIT\n"
                + "cat >/etc/systemd/system/linsight-node-power.path <<'UNIT'\n[Unit]\nDescription=Watch for LInsight node lifecycle requests\n\n[Path]\nPathExists=/run/linsight/node-power-request\nUnit=linsight-node-power.service\n\n[Install]\nWantedBy=multi-user.target\nUNIT\n"
                + "echo 'LINSIGHT_PROGRESS=84 正在启动 Runtime 与 Edge Agent'\n"
                + "systemctl daemon-reload\nsystemctl enable --now linsight-ai-runtime.service linsight-accelerator-metrics-permissions.service linsight-edge-agent.service linsight-node-power.path linsight-disk-pressure-cleanup.timer\n"
                + "echo 'LINSIGHT_PROGRESS=86 正在执行本机健康检查'\n"
                + "for i in $(seq 1 30); do curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:48900/v1/health >/dev/null 2>&1 && break; "
                + "echo \"[HEALTH] 等待 Runtime 就绪 ($i/30)\"; sleep 2; done\n"
                + "curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:48900/v1/health >/dev/null "
                + "|| { echo 'LINSIGHT_ERROR=Runtime 健康检查超时或失败，正在恢复原部署'; exit 1; }\n"
                + "curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:48901/gateway-health "
                + "| grep -Fq '\"owner\":\"runtime\"' "
                + "|| { echo 'LINSIGHT_ERROR=Runtime 内置管理入口未就绪，正在恢复原部署'; exit 1; }\n"
                + "curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:48901/ >/dev/null "
                + "|| { echo 'LINSIGHT_ERROR=本地管理页面不可访问，正在恢复原部署'; exit 1; }\n"
                + "systemctl is-active --quiet linsight-ai-runtime.service linsight-edge-agent.service\n"
                + "for i in $(seq 1 30); do [ -s /var/lib/linsight/edge-agent-credential.json ] && break; sleep 2; done\n"
                + "[ -s /var/lib/linsight/edge-agent-credential.json ]\n"
                + "sed -i '/^LINSIGHT_AGENT_BOOTSTRAP_TOKEN=/d' /etc/linsight/agent.env\n"
                + "systemctl restart linsight-edge-agent.service\n";
    }

    private static String randomSecret() {
        byte[] bytes = new byte[32];
        SECURE_RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static String sha256(byte[] value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    }

    private static String sanitize(Exception error) {
        String value = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
        value = SensitiveTextRedactor.redactText(value).replaceAll("[\\r\\n]+", " ").trim();
        return value.length() > 500 ? value.substring(0, 500) : value;
    }
}
