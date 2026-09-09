package com.linsight.module.aivideo.service.node;

import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeUpgradeCreateReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeUpgradeCommandDetailRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeUpgradeDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeUpgradeMapper;
import com.linsight.module.aivideo.framework.file.UploadContentValidator;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_UPGRADE_IN_PROGRESS;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_UPGRADE_NOT_FOUND;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_UPGRADE_PACKAGE_INVALID;

@Service
public class NodeUpgradeServiceImpl implements NodeUpgradeService {
    private static final long PACKAGE_MAX_BYTES = 64L * 1024 * 1024;
    private static final Set<String> ACTIVE_STATUSES = Set.of("QUEUED", "RUNNING", "AWAITING_ACTIVATION", "VERIFYING");

    @Resource private NodeUpgradeMapper nodeUpgradeMapper;
    @Resource private NodeService nodeService;
    @Resource private NodeCommandService nodeCommandService;
    @Resource private FileApi fileApi;
    @Resource private TransactionTemplate transactionTemplate;
    @Resource private NodeOperationService operationService;
    @Resource private com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper edgeNodeMapper;

    @Override
    public Long createUpgrade(NodeUpgradeCreateReqVO reqVO) throws IOException {
        nodeService.validateNodeAvailable(reqVO.getNodeId());
        validateActivationGuard(reqVO.getNodeId(), false);
        if (java.util.Objects.equals(reqVO.getTargetVersion(), edgeNodeMapper.selectById(reqVO.getNodeId()).getAgentVersion())) {
            throw exception(com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_UPGRADE_VERSION_UNCHANGED);
        }
        validateNoActiveUpgrade(reqVO.getNodeId());
        byte[] content = reqVO.getFile().getBytes();
        String packageName;
        try {
            packageName = UploadContentValidator.safeFileName(
                    reqVO.getFile().getOriginalFilename(), "edge-agent.tar.gz");
        } catch (IllegalArgumentException error) {
            throw exception(NODE_UPGRADE_PACKAGE_INVALID);
        }
        if (content.length == 0 || content.length > PACKAGE_MAX_BYTES
                || !(packageName.endsWith(".tar.gz") || packageName.endsWith(".tgz"))
                || !UploadContentValidator.isGzip(content)) {
            throw exception(NODE_UPGRADE_PACKAGE_INVALID);
        }
        String sha256 = DigestUtil.sha256Hex(content);
        String packageRef = fileApi.createFile(content, packageName, "ai-video/node-upgrade",
                "application/gzip");
        return operationService.exclusive("node:" + reqVO.getNodeId(), () -> {
            operationService.requireIdle(reqVO.getNodeId(), null, false);
            return createOperation(
                reqVO.getNodeId(), "UPGRADE", reqVO.getTargetVersion(), packageRef, packageName,
                sha256, reqVO.getSignature(), "UPGRADE_AGENT");
        });
    }

    @Override
    public Long createRollback(Long nodeId) {
        nodeService.validateNodeAvailable(nodeId);
        validateActivationGuard(nodeId, true);
        validateNoActiveUpgrade(nodeId);
        return operationService.exclusive("node:" + nodeId, () -> {
            operationService.requireIdle(nodeId, null, false);
            return createOperation(nodeId, "ROLLBACK", null, null, null, null, null, "ROLLBACK_AGENT");
        });
    }

    @Override
    public List<NodeUpgradeDO> getUpgradeList(Long nodeId) {
        nodeService.validateNodeExists(nodeId);
        return nodeUpgradeMapper.selectListByNode(nodeId);
    }

    @Override
    public NodeUpgradeCommandDetailRespVO getCommandDetail(String commandId, Long nodeId) {
        NodeCommandDTO command = nodeCommandService.getCommandForNode(commandId, nodeId);
        if (!Set.of("UPGRADE_AGENT", "ROLLBACK_AGENT").contains(command.getCommandType())) {
            throw exception(NODE_UPGRADE_NOT_FOUND);
        }
        NodeUpgradeDO upgrade = nodeUpgradeMapper.selectByCommandId(commandId);
        if (upgrade == null) throw exception(NODE_UPGRADE_NOT_FOUND);
        NodeUpgradeCommandDetailRespVO result = new NodeUpgradeCommandDetailRespVO();
        result.setCommandId(commandId);
        result.setCommandType(command.getCommandType());
        result.setConfigVersion(command.getConfigVersion());
        result.setTargetVersion(upgrade.getTargetVersion());
        result.setPackageName(upgrade.getPackageName());
        result.setSha256(upgrade.getSha256());
        result.setSignature(upgrade.getSignature());
        if (upgrade.getPackageRef() != null) {
            result.setPackageUrl(fileApi.presignGetUrl(upgrade.getPackageRef(), 600).getCheckedData());
        }
        return result;
    }

    @Override
    public void applyCommandReport(NodeCommandDTO report) {
        if (!Set.of("UPGRADE_AGENT", "ROLLBACK_AGENT").contains(report.getCommandType())) return;
        NodeUpgradeDO upgrade = nodeUpgradeMapper.selectByCommandId(report.getCommandId());
        if (upgrade == null) throw exception(NODE_UPGRADE_NOT_FOUND);
        // Duplicate or late command reports must not undo a heartbeat-confirmed outcome.
        if (!Set.of("QUEUED", "RUNNING").contains(upgrade.getStatus())) return;
        upgrade.setStatus(report.getStatus());
        upgrade.setStage(report.getStage());
        upgrade.setDiagnosticId(report.getDiagnosticId());
        upgrade.setErrorCode(report.getErrorCode());
        upgrade.setErrorMessage(report.getErrorMessage());
        if (report.getResult() != null) {
            upgrade.setResultSummary(JsonUtils.toJsonString(report.getResult()));
        }
        if ("SUCCEEDED".equals(report.getStatus())) {
            upgrade.setStatus("AWAITING_ACTIVATION");
            upgrade.setStage("AWAITING_ACTIVATION");
            upgrade.setActivationRequestedAt(LocalDateTime.now());
            if (report.getResult() != null && report.getResult().get("currentVersion") instanceof String version) {
                if ("ROLLBACK".equals(upgrade.getAction())) upgrade.setTargetVersion(version);
                else if (!java.util.Objects.equals(upgrade.getTargetVersion(), version)) {
                    upgrade.setStatus("FAILED");
                    upgrade.setStage("VERSION_MISMATCH");
                    upgrade.setErrorMessage("节点报告版本与请求目标版本不一致，未确认升级");
                    upgrade.setFinishTime(LocalDateTime.now());
                }
            }
        } else if (Set.of("FAILED", "EXPIRED").contains(report.getStatus())) {
            upgrade.setFinishTime(LocalDateTime.now());
        }
        upgrade.setUpdater("edge-agent");
        nodeUpgradeMapper.update(upgrade, new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<NodeUpgradeDO>()
                .eq(NodeUpgradeDO::getId, upgrade.getId()).in(NodeUpgradeDO::getStatus, "QUEUED", "RUNNING"));
    }

    private Long createOperation(Long nodeId, String action, String targetVersion,
                                 String packageRef, String packageName, String sha256,
                                 String signature, String commandType) {
        NodeUpgradeDO latest = nodeUpgradeMapper.selectLatestByNode(nodeId);
        int configVersion = latest == null ? 1 : latest.getConfigVersion() + 1;
        String commandId = UUID.randomUUID().toString();
        NodeUpgradeDO upgrade = new NodeUpgradeDO();
        upgrade.setNodeId(nodeId);
        upgrade.setAction(action);
        upgrade.setTargetVersion(targetVersion);
        upgrade.setPackageRef(packageRef);
        upgrade.setPackageName(packageName);
        upgrade.setSha256(sha256);
        upgrade.setSignature(signature);
        upgrade.setCommandId(commandId);
        upgrade.setConfigVersion(configVersion);
        upgrade.setStatus("QUEUED");
        upgrade.setPreviousVersion(edgeNodeMapper.selectById(nodeId).getAgentVersion());
        nodeUpgradeMapper.insert(upgrade);
        nodeCommandService.createCommand(commandId, nodeId, commandType, upgrade.getId(),
                configVersion, "node-upgrade:" + nodeId + ":" + configVersion);
        return upgrade.getId();
    }

    private void validateNoActiveUpgrade(Long nodeId) {
        NodeUpgradeDO latest = nodeUpgradeMapper.selectLatestByNode(nodeId);
        if (latest != null && ACTIVE_STATUSES.contains(latest.getStatus())) {
            throw exception(NODE_UPGRADE_IN_PROGRESS);
        }
    }

    private void validateActivationGuard(Long nodeId, boolean rollback) {
        var node = edgeNodeMapper.selectById(nodeId);
        var snapshot = node == null || node.getResourceSnapshot() == null ? null
                : JsonUtils.parseObject(node.getResourceSnapshot(), java.util.Map.class);
        if (snapshot == null || !"v1".equals(snapshot.get("activationGuard"))) {
            throw exception(com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_UPGRADE_GUARD_REQUIRED);
        }
        if (rollback && !Boolean.TRUE.equals(snapshot.get("agentRollbackAvailable"))) {
            throw exception(com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_UPGRADE_ROLLBACK_UNAVAILABLE);
        }
    }
}
