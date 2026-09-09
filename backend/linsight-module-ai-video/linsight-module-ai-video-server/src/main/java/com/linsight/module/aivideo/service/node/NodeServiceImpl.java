package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.tenant.core.aop.TenantIgnore;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeBootstrapTokenRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegisterReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegistrationRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeBootstrapTokenDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeBootstrapTokenMapper;
import com.linsight.module.aivideo.enums.node.NodeOnlineStatusEnum;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.List;
import java.util.Objects;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.*;

@Service
@Validated
public class NodeServiceImpl implements NodeService {
    @Override
    public boolean supportsModelUninstall(Long nodeId) {
        validateNodeAvailable(nodeId);
        var node = edgeNodeMapper.selectById(nodeId);
        if (node.getResourceSnapshot() == null) return false;
        return "v1".equals(JsonUtils.parseMap(node.getResourceSnapshot()).get("modelUninstall"));
    }

    @Override
    public List<NodeRuntimeSummaryDTO> getRuntimeSummaries(java.util.Collection<Long> ids) {
        if (ids.isEmpty()) return List.of();
        return edgeNodeMapper.selectBatchIds(ids).stream()
                .map(value -> new NodeRuntimeSummaryDTO(value.getId(), value.getName(), value.getStatus(),
                        value.getOnlineStatus(), value.getLastHeartbeatTime())).toList();
    }

    @Resource private NodeUpgradeActivationService activationService;

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    @Resource
    private NodeBootstrapTokenMapper nodeBootstrapTokenMapper;
    @Resource
    private EdgeNodeMapper edgeNodeMapper;

    @Override
    public NodeBootstrapTokenRespVO createBootstrapToken(String name, Integer ttlMinutes) {
        String token = randomSecret();
        LocalDateTime expireTime = LocalDateTime.now().plusMinutes(ttlMinutes);
        NodeBootstrapTokenDO tokenDO = new NodeBootstrapTokenDO();
        tokenDO.setName(name);
        tokenDO.setTokenDigest(digest(token));
        tokenDO.setExpireTime(expireTime);
        nodeBootstrapTokenMapper.insert(tokenDO);

        NodeBootstrapTokenRespVO result = new NodeBootstrapTokenRespVO();
        result.setToken(token);
        result.setExpireTime(expireTime);
        return result;
    }

    @Override
    @TenantIgnore
    @Transactional(rollbackFor = Exception.class)
    public NodeRegistrationRespVO registerNode(NodeRegisterReqVO registerReqVO, String ipAddress) {
        LocalDateTime now = LocalDateTime.now();
        NodeBootstrapTokenDO token = nodeBootstrapTokenMapper.selectByTokenDigest(
                digest(registerReqVO.getBootstrapToken()));
        if (token == null || token.getUsedTime() != null) {
            throw exception(NODE_BOOTSTRAP_TOKEN_INVALID);
        }
        if (token.getExpireTime().isBefore(now)) {
            throw exception(NODE_BOOTSTRAP_TOKEN_EXPIRED);
        }
        if (edgeNodeMapper.selectByTenantIdAndCode(token.getTenantId(), registerReqVO.getCode()) != null) {
            throw exception(NODE_CODE_DUPLICATE);
        }

        if (nodeBootstrapTokenMapper.markUsedIfAvailable(token.getId(), now) == 0) {
            throw exception(NODE_BOOTSTRAP_TOKEN_INVALID);
        }

        String credential = randomSecret();
        EdgeNodeDO node = new EdgeNodeDO();
        node.setTenantId(token.getTenantId());
        node.setCode(registerReqVO.getCode());
        node.setName(registerReqVO.getName());
        node.setAgentVersion(registerReqVO.getAgentVersion());
        node.setHostName(registerReqVO.getHostName());
        node.setIpAddress(ipAddress);
        node.setCredentialDigest(digest(credential));
        node.setOnlineStatus(NodeOnlineStatusEnum.ONLINE.getStatus());
        node.setLastHeartbeatTime(now);
        node.setHeartbeatSequence(0L);
        node.setAgentTime(now);
        node.setClockOffsetMillis(0L);
        node.setStatus(0);
        node.setCreator("node-bootstrap");
        node.setUpdater("node-bootstrap");
        edgeNodeMapper.insert(node);

        NodeRegistrationRespVO result = new NodeRegistrationRespVO();
        result.setNodeId(node.getId());
        result.setTenantId(token.getTenantId());
        result.setCredential(credential);
        return result;
    }

    @Override
    @TenantIgnore
    public boolean authenticateNode(Long nodeId, Long tenantId, String credential) {
        if (nodeId == null || tenantId == null || credential == null) {
            return false;
        }
        EdgeNodeDO node = edgeNodeMapper.selectForAuthentication(nodeId);
        return node != null && Objects.equals(node.getStatus(), 0) && tenantId.equals(node.getTenantId())
                && MessageDigest.isEqual(digest(credential).getBytes(StandardCharsets.UTF_8),
                node.getCredentialDigest().getBytes(StandardCharsets.UTF_8));
    }

    @Override
    public NodeHeartbeatRespVO reportHeartbeat(Long nodeId, NodeHeartbeatReqVO heartbeatReqVO) {
        LocalDateTime now = LocalDateTime.now();
        long clockOffsetMillis = Duration.between(heartbeatReqVO.getAgentTime(), now).toMillis();
        EdgeNodeDO update = new EdgeNodeDO();
        update.setId(nodeId);
        update.setAgentVersion(heartbeatReqVO.getAgentVersion());
        update.setHostName(heartbeatReqVO.getHostName());
        update.setIpAddress(heartbeatReqVO.getIpAddress());
        update.setOnlineStatus(NodeOnlineStatusEnum.ONLINE.getStatus());
        update.setLastHeartbeatTime(now);
        update.setHeartbeatSequence(heartbeatReqVO.getSequence());
        update.setAgentTime(heartbeatReqVO.getAgentTime());
        update.setClockOffsetMillis(clockOffsetMillis);
        update.setResourceSnapshot(buildResourceSnapshot(heartbeatReqVO));
        update.setUpdater("edge-agent");
        if (edgeNodeMapper.updateHeartbeatIfNotOlder(update, heartbeatReqVO.getSequence()) == 0) {
            throw exception(NODE_HEARTBEAT_SEQUENCE_STALE);
        }
        activationService.heartbeatReceived(nodeId);

        NodeHeartbeatRespVO result = new NodeHeartbeatRespVO();
        result.setAcceptedSequence(heartbeatReqVO.getSequence());
        result.setServerTime(now);
        result.setClockOffsetMillis(clockOffsetMillis);
        return result;
    }

    @Override
    public void validateNodeAvailable(Long nodeId) {
        EdgeNodeDO node = edgeNodeMapper.selectById(nodeId);
        if (node == null || !Objects.equals(node.getStatus(), 0)
                || !Objects.equals(node.getOnlineStatus(), NodeOnlineStatusEnum.ONLINE.getStatus())) {
            throw exception(NODE_NOT_AVAILABLE);
        }
    }

    @Override
    public void validateNodeExists(Long nodeId) {
        EdgeNodeDO node = edgeNodeMapper.selectById(nodeId);
        if (node == null || !Objects.equals(node.getStatus(), 0)) {
            throw exception(NODE_NOT_AVAILABLE);
        }
    }

    @Override
    public List<EdgeNodeDO> getEnabledNodes() {
        return edgeNodeMapper.selectEnabledList();
    }

    @Override
    public List<EdgeNodeDO> getOnlineNodesGlobal() {
        return edgeNodeMapper.selectOnlineGlobal();
    }

    @Override
    public void markOfflineIfHeartbeatExpired(Long nodeId, LocalDateTime cutoff) {
        EdgeNodeDO node = edgeNodeMapper.selectById(nodeId);
        if (node == null || node.getLastHeartbeatTime() == null
                || !node.getLastHeartbeatTime().isBefore(cutoff)
                || !Objects.equals(node.getOnlineStatus(), NodeOnlineStatusEnum.ONLINE.getStatus())) {
            return;
        }
        EdgeNodeDO update = new EdgeNodeDO();
        update.setId(nodeId);
        update.setOnlineStatus(NodeOnlineStatusEnum.OFFLINE.getStatus());
        update.setUpdater("node-offline-detector");
        edgeNodeMapper.updateById(update);
    }

    private static String buildResourceSnapshot(NodeHeartbeatReqVO heartbeatReqVO) {
        Map<String, Object> resources = new LinkedHashMap<>();
        resources.put("cpuUsage", heartbeatReqVO.getCpuUsage());
        resources.put("memoryUsedBytes", heartbeatReqVO.getMemoryUsedBytes());
        resources.put("memoryTotalBytes", heartbeatReqVO.getMemoryTotalBytes());
        resources.put("diskUsedBytes", heartbeatReqVO.getDiskUsedBytes());
        resources.put("diskTotalBytes", heartbeatReqVO.getDiskTotalBytes());
        resources.put("gpuUsage", heartbeatReqVO.getGpuUsage());
        resources.put("gpuMemoryUsedBytes", heartbeatReqVO.getGpuMemoryUsedBytes());
        resources.put("gpuMemoryTotalBytes", heartbeatReqVO.getGpuMemoryTotalBytes());
        resources.put("runtimeStatus", heartbeatReqVO.getRuntimeStatus());
        resources.put("modelUninstall", heartbeatReqVO.getModelUninstall());
        resources.put("activationGuard", heartbeatReqVO.getActivationGuard());
        resources.put("agentRollbackAvailable", heartbeatReqVO.getAgentRollbackAvailable());
        resources.put("failedAgentVersion", heartbeatReqVO.getFailedAgentVersion());
        resources.put("runtimeDiagnosticId", heartbeatReqVO.getRuntimeDiagnosticId());
        return JsonUtils.toJsonString(resources);
    }

    private static String randomSecret() {
        byte[] bytes = new byte[32];
        SECURE_RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String digest(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

}
