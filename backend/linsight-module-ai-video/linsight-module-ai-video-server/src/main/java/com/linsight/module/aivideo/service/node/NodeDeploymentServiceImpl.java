package com.linsight.module.aivideo.service.node;

import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentConnectionReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPreflightRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDeploymentDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeDeploymentMapper;
import com.linsight.module.aivideo.integration.ssh.NodeDeploymentProperties;
import com.linsight.module.aivideo.integration.ssh.NodeSshClient;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DEPLOYMENT_DISABLED;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DEPLOYMENT_NOT_FOUND;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DEPLOYMENT_PREFLIGHT_FAILED;

@Service
public class NodeDeploymentServiceImpl implements NodeDeploymentService {

    @Resource private NodeSshClient sshClient;
    @Resource private NodeDeploymentProperties properties;
    @Resource private NodeDeploymentMapper deploymentMapper;
    @Resource private EdgeNodeMapper edgeNodeMapper;
    @Resource private NodeDeploymentRunner deploymentRunner;
    @Resource private NodeService nodeService;
    @Resource private NodeOperationService operationService;

    @Override
    public NodeDeploymentPreflightRespVO preflight(NodeDeploymentConnectionReqVO request) {
        validateEnabled();
        try (NodeSshClient.Connection connection = sshClient.connect(request, null)) {
            return inspect(connection, request);
        } catch (Exception error) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, sanitize(error));
        } finally {
            request.setPassword(null);
        }
    }

    @Override
    public Long createDeployment(NodeDeploymentCreateReqVO request) {
        validateEnabled();
        NodeDeploymentDO previous = deploymentMapper.selectByRequestId(request.getRequestId());
        if (previous != null) {
            request.setPassword(null);
            if (!java.util.Objects.equals(previous.getHost(), request.getHost())
                    || !java.util.Objects.equals(previous.getNodeCode(), request.getNodeCode())) {
                throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "幂等请求 ID 已用于其他部署");
            }
            return previous.getId();
        }
        NodeDeploymentPreflightRespVO preflight;
        try (NodeSshClient.Connection connection = sshClient.connect(request,
                request.getHostKeyType() + " " + request.getHostKey())) {
            preflight = inspect(connection, request);
            if (!request.getHostKeyFingerprint().equals(preflight.getHostKeyFingerprint())) {
                throw new IllegalStateException("SSH 主机指纹与预检结果不一致");
            }
            NodeDeploymentProbe.checkControlPlane(connection, request.getControlPlaneUrl());
        } catch (Exception error) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, sanitize(error));
        }
        if (!preflight.isSupported()) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "目标节点不满足系统、权限或资源条件，请重新预检");
        }
        if (!"ROLLBACK".equals(request.getAction()) && !preflight.isPythonSupported()
                && !Boolean.TRUE.equals(request.getInstallDependencies())) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "目标节点缺少 Python 3.12/3.13，请启用自动安装依赖");
        }
        validateExistingNodeCode(preflight, request.getNodeCode());
        boolean rollback = "ROLLBACK".equals(request.getAction());
        if (rollback && !preflight.isSourceRollbackAvailable()) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "目标没有可恢复的源码部署快照");
        }
        NodeDeploymentDO deployment = new NodeDeploymentDO();
        deployment.setHost(request.getHost());
        deployment.setPort(request.getPort());
        deployment.setUsername(request.getUsername());
        deployment.setNodeCode(request.getNodeCode());
        deployment.setNodeName(request.getNodeName());
        boolean redeploy = preflight.getExistingNodeId() != null;
        deployment.setOperationType(rollback ? "ROLLBACK" : redeploy ? "REDEPLOY" : "INITIAL");
        deployment.setEdgeNodeId(preflight.getExistingNodeId());
        request.setNodeId(preflight.getExistingNodeId());
        deployment.setRequestId(request.getRequestId());
        deployment.setExecutorOwner(deploymentRunner.owner());
        deployment.setLogStatus("COLLECTING");
        deployment.setLogTruncated(false);
        deployment.setControlPlaneUrl(request.getControlPlaneUrl());
        deployment.setPreviousVersion(preflight.getCurrentVersion());
        deployment.setTargetArch(preflight.getArchitecture());
        deployment.setOsSummary(preflight.getOsSummary());
        deployment.setPythonVersion(preflight.getPythonVersion());
        deployment.setStatus("QUEUED");
        deployment.setStage("QUEUED");
        deployment.setProgress(5);
        String queuedMessage = redeploy ? "在线升级任务已创建，等待重新部署" : "部署任务已创建，等待执行";
        deployment.setMessage(queuedMessage);
        deployment.setOutputLog("[QUEUED] " + queuedMessage + "\n");
        // Cloned gateway images can share an SSH host key. Reserve the network endpoint,
        // while the preflight fingerprint still pins the SSH connection itself.
        String key = redeploy ? "node:" + request.getNodeId() : hostResourceKey(request.getHost(), request.getPort());
        deployment.setResourceKey(key);
        Long reserved = operationService.exclusive("code:" + request.getNodeCode(), () -> operationService.exclusive(key, () -> {
            NodeDeploymentDO duplicate = deploymentMapper.selectByRequestId(request.getRequestId());
            if (duplicate != null) return duplicate.getId();
            operationService.requireIdle(request.getNodeId(), request.getHost(), false);
            if (deploymentMapper.hasActiveResource(key, request.getNodeCode())) {
                throw exception(com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_LIFECYCLE_IN_PROGRESS);
            }
            if (!redeploy && edgeNodeMapper.selectByTenantIdAndCode(
                    TenantContextHolder.getRequiredTenantId(), request.getNodeCode()) != null) {
                throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "节点编码已占用，请使用新编码或选择原节点重新部署");
            }
            deploymentMapper.insert(deployment);
            return deployment.getId();
        }));
        if (!java.util.Objects.equals(reserved, deployment.getId())) { request.setPassword(null); return reserved; }
        try {
            deploymentRunner.run(deployment.getId(), TenantContextHolder.getRequiredTenantId(), request,
                    null, redeploy);
        } catch (RuntimeException error) {
            deploymentRunner.submissionFailed(deployment.getId());
            request.setPassword(null);
        }
        return deployment.getId();
    }

    static String hostResourceKey(String host, int port) {
        String endpoint = host.trim().toLowerCase(Locale.ROOT) + ":" + port;
        try {
            return "host:" + HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(endpoint.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    @Override
    public NodeDeploymentDO getDeployment(Long id) {
        NodeDeploymentDO deployment = deploymentMapper.selectById(id);
        if (deployment == null) throw exception(NODE_DEPLOYMENT_NOT_FOUND);
        return deployment;
    }

    @Override
    public List<NodeDeploymentDO> getRecentDeployments() {
        return deploymentMapper.selectRecentList();
    }

    @Override
    public com.linsight.framework.common.pojo.PageResult<NodeDeploymentDO> getPage(
            com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPageReqVO request) {
        return deploymentMapper.selectHistoryPage(request, request.getNodeId());
    }

    private NodeDeploymentPreflightRespVO inspect(NodeSshClient.Connection connection, NodeDeploymentConnectionReqVO request) throws Exception {
        Map<String, String> values = parse(NodeDeploymentProbe.inspect(connection, request.getPassword()));
        String arch = values.getOrDefault("ARCH", "unknown");
        String python = values.getOrDefault("PYTHON", "");
        boolean pythonSupported = python.matches("3\\.(12|13)(?:\\..*)?");
        boolean architectureSupported = List.of("aarch64", "arm64", "x86_64", "amd64").contains(arch);
        List<String> warnings = new ArrayList<>();
        boolean rknpu = "1".equals(values.get("RKNPU"));
        if (!"1".equals(values.get("FFMPEG"))) warnings.add("未安装 FFmpeg，部署时将自动安装");
        if (!rknpu && ("aarch64".equals(arch) || "arm64".equals(arch))) {
            warnings.add("未发现 RKNPU 设备，本次按 ONNX Runtime CPU 模式部署");
        }
        if (rknpu) {
            warnings.add(python.startsWith("3.12.") || !pythonSupported
                    ? "已发现 RKNPU 硬件；部署将安装 RKNN SDK，加载 RKNN 模型后使用 NPU，现有 ONNX 模型继续使用 CPU"
                    : "已发现 RKNPU 硬件；RKNN SDK 需要 ARM64 Python 3.12，当前 Python 环境仅支持 CPU 模型");
        }
        if (!pythonSupported) warnings.add("当前系统 Python " + (python.isBlank() ? "未安装" : python)
                + "；启用自动安装后将独立安装 Python " + NodeDeploymentRunner.MANAGED_PYTHON_VERSION
                + "，不更改系统 python3");
        if (pythonSupported && !"1".equals(values.get("VENV"))) warnings.add("Python venv/pip 实测不可用，部署时将尝试补齐对应 Python 版本的 venv 包；不会解除系统包锁定");
        if (!"1".equals(values.get("SUDO"))) warnings.add("未发现 sudo，无法执行控制台自动安装");
        boolean osSupported = "1".equals(values.get("OS_SUPPORTED"));
        if (!osSupported) warnings.add("自动部署仅支持使用 apt 与 systemd 的 Ubuntu/Debian 系统");

        NodeDeploymentPreflightRespVO result = new NodeDeploymentPreflightRespVO();
        result.setHostKey(connection.hostKey());
        result.setHostKeyType(connection.hostKeyType());
        result.setHostKeyFingerprint(connection.hostKeyFingerprint());
        result.setArchitecture(arch);
        result.setOsSummary(values.getOrDefault("OS", "Unknown Linux"));
        result.setPythonVersion(python.isBlank() ? "未安装" : python);
        result.setPythonSupported(pythonSupported);
        result.setVenvAvailable("1".equals(values.get("VENV")));
        var wheelhouse = NodeDeploymentWheelhouse.directory(properties.resolveRuntimeSource(), arch,
                NodeDeploymentRunner.deploymentPythonVersion(python));
        result.setOfflineDependenciesAvailable(wheelhouse != null && java.nio.file.Files.isRegularFile(wheelhouse.resolve("manifest.json")));
        if (!result.isOfflineDependenciesAvailable()) warnings.add("控制面未准备此架构的离线依赖包，安装将访问外网；弱网环境建议先准备离线包");
        result.setFfmpegInstalled("1".equals(values.get("FFMPEG")));
        result.setSudoAvailable("1".equals(values.get("SUDO")));
        result.setRknpuAvailable(rknpu);
        result.setMemoryMb(parseLong(values.get("MEMORY_MB")));
        result.setMemoryAvailableMb(parseLong(values.get("MEMORY_AVAILABLE_MB")));
        result.setDiskAvailableMb(parseLong(values.get("DISK_MB")));
        result.setExecutionMode(rknpu && (python.startsWith("3.12.") || !pythonSupported)
                ? "ONNX CPU / RKNN NPU（由部署模型决定）" : "ONNX Runtime CPU");
        result.setSupported(architectureSupported && osSupported && result.isSudoAvailable()
                && result.getMemoryMb() >= 1024 && result.getMemoryAvailableMb() >= 256 && result.getDiskAvailableMb() >= 2048);
        if (result.getMemoryAvailableMb() < 256) warnings.add("可用内存不足 256 MB");
        if (result.getDiskAvailableMb() < 2048) warnings.add("可用磁盘不足 2 GB");
        result.setControlPlaneUrl(values.get("CONTROL_PLANE_URL"));
        result.setCurrentVersion(values.get("CURRENT_VERSION"));
        result.setPreviousVersion(values.get("PREVIOUS_VERSION"));
        result.setSourceRollbackAvailable(values.get("PREVIOUS_VERSION") != null && !values.get("PREVIOUS_VERSION").isBlank());
        bindIdentity(result, values, request.getNodeId());
        result.setWarnings(warnings);
        return result;
    }

    private void bindIdentity(NodeDeploymentPreflightRespVO result, Map<String, String> values, Long requestedId) {
        Long remoteId = values.containsKey("NODE_ID") ? Long.valueOf(values.get("NODE_ID")) : null;
        if (remoteId == null && requestedId == null) return;
        if (remoteId == null || (requestedId != null && !requestedId.equals(remoteId))
                || !TenantContextHolder.getRequiredTenantId().toString().equals(values.get("TENANT_ID"))) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "远端凭据身份与所选节点/租户不一致，已阻止覆盖");
        }
        EdgeNodeDO existingNode = edgeNodeMapper.selectById(remoteId);
        if (existingNode == null || !Integer.valueOf(0).equals(existingNode.getStatus())
                || !java.util.Objects.equals(existingNode.getCredentialDigest(), values.get("CREDENTIAL_DIGEST"))) {
            throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED, "远端凭据不属于有效的已注册节点，需先恢复节点身份");
        }
        result.setExistingNodeId(existingNode.getId());
        result.setExistingNodeCode(existingNode.getCode());
        result.setExistingNodeName(existingNode.getName());
        result.setCurrentVersion(existingNode.getAgentVersion());
    }

    static void validateExistingNodeCode(NodeDeploymentPreflightRespVO preflight, String requestedCode) {
        if (preflight.getExistingNodeCode() == null
                || preflight.getExistingNodeCode().equals(requestedCode)) {
            return;
        }
        throw exception(NODE_DEPLOYMENT_PREFLIGHT_FAILED,
                "目标地址已注册为节点 " + preflight.getExistingNodeCode()
                        + "，重新部署必须保持原节点编码，避免新配置与已有凭据不一致");
    }

    private static Map<String, String> parse(String output) {
        Map<String, String> values = new LinkedHashMap<>();
        for (String line : output.split("\\R")) {
            int index = line.indexOf('=');
            if (index > 0) values.put(line.substring(0, index), line.substring(index + 1).trim());
        }
        return values;
    }

    private static long parseLong(String value) {
        try { return Long.parseLong(value); } catch (Exception ignored) { return 0; }
    }

    private void validateEnabled() {
        if (!properties.isEnabled()) throw exception(NODE_DEPLOYMENT_DISABLED);
    }

    private static String sanitize(Exception error) {
        String value = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
        value = value.replaceAll("[\\r\\n]+", " ").trim();
        return value.length() > 300 ? value.substring(0, 300) : value;
    }
}
