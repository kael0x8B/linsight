package com.linsight.module.aivideo.service.node;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.dal.dataobject.node.NodeUpgradeDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeUpgradeMapper;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeCommandMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.scheduling.annotation.Scheduled;
import java.time.LocalDateTime;
import java.util.Set;
import java.util.Objects;

/** Business success means the target process has reported a fresh authenticated heartbeat. */
@Service
public class NodeUpgradeActivationService {
    @Resource private NodeUpgradeMapper upgradeMapper;
    @Resource private EdgeNodeMapper nodeMapper;
    @Resource private NodeCommandMapper commandMapper;

    public void restartRequested(Long nodeId) {
        NodeUpgradeDO upgrade = upgradeMapper.selectLatestByNode(nodeId);
        if (upgrade == null || !"AWAITING_ACTIVATION".equals(upgrade.getStatus())) return;
        upgrade.setStatus("VERIFYING");
        upgrade.setStage("VERIFYING_HEARTBEAT");
        upgrade.setActivationRequestedAt(LocalDateTime.now());
        save(upgrade, Set.of("AWAITING_ACTIVATION"));
    }

    public void heartbeatReceived(Long nodeId) {
        NodeUpgradeDO upgrade = upgradeMapper.selectLatestByNode(nodeId);
        if (upgrade != null) reconcile(upgrade);
    }

    @Scheduled(fixedDelay = 30_000)
    public void reconcilePending() {
        for (NodeUpgradeDO upgrade : upgradeMapper.selectPendingGlobal()) {
            TenantUtils.execute(upgrade.getTenantId(), () -> reconcile(upgrade));
        }
    }

    private void reconcile(NodeUpgradeDO upgrade) {
        String initial = upgrade.getStatus();
        if (Set.of("QUEUED", "RUNNING").contains(initial)) {
            var command = commandMapper.selectByCommandId(upgrade.getCommandId());
            if (command != null && Set.of("EXPIRED", "FAILED").contains(command.getStatus())) {
                upgrade.setStatus(command.getStatus()); upgrade.setStage(command.getStatus());
                upgrade.setErrorMessage("升级命令未完成，请检查节点命令记录");
                upgrade.setFinishTime(LocalDateTime.now()); save(upgrade, Set.of(initial));
            }
            return;
        }
        if (!Set.of("AWAITING_ACTIVATION", "VERIFYING", "SUCCEEDED").contains(initial)) return;
        var node = nodeMapper.selectById(upgrade.getNodeId());
        LocalDateTime started = upgrade.getActivationRequestedAt();
        if (started == null) return;
        boolean fresh = node != null && node.getLastHeartbeatTime() != null
                && node.getLastHeartbeatTime().isAfter(started) && Integer.valueOf(1).equals(node.getOnlineStatus());
        var snapshot = node == null || node.getResourceSnapshot() == null ? java.util.Map.of()
                : com.linsight.framework.common.util.json.JsonUtils.parseObject(node.getResourceSnapshot(), java.util.Map.class);
        boolean runtimeHealthy = fresh && "UP".equals(snapshot.get("runtimeStatus"));
        if (fresh && upgrade.getTargetVersion() != null && Objects.equals(upgrade.getTargetVersion(), snapshot.get("failedAgentVersion"))
                && !Objects.equals(upgrade.getTargetVersion(), node.getAgentVersion())) {
            upgrade.setStatus("FAILED"); upgrade.setStage("AUTO_RESTORED");
            upgrade.setErrorMessage("目标 Agent 启动或健康确认失败，启动器已自动恢复原版本");
        } else if ("SUCCEEDED".equals(initial)) return;
        else if (runtimeHealthy && Objects.equals(upgrade.getTargetVersion(), node.getAgentVersion())) {
            upgrade.setStatus("SUCCEEDED"); upgrade.setStage("HEALTH_CONFIRMED");
        } else if ("VERIFYING".equals(initial) && started.isBefore(LocalDateTime.now().minusMinutes(5))) {
            upgrade.setStatus("FAILED"); upgrade.setStage(fresh && Objects.equals(upgrade.getPreviousVersion(), node.getAgentVersion())
                    ? "PREVIOUS_VERSION_ACTIVE" : "ACTIVATION_TIMEOUT");
            upgrade.setErrorMessage("目标版本未通过心跳确认；请检查节点当前版本和日志，不能视为升级成功");
        } else return;
        upgrade.setFinishTime(LocalDateTime.now());
        save(upgrade, Set.of(initial));
    }

    private void save(NodeUpgradeDO upgrade, Set<String> expected) {
        upgradeMapper.update(upgrade, new LambdaQueryWrapper<NodeUpgradeDO>()
                .eq(NodeUpgradeDO::getId, upgrade.getId()).in(NodeUpgradeDO::getStatus, expected));
    }
}
