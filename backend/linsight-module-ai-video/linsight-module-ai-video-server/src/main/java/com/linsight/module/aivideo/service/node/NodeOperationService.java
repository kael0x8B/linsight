package com.linsight.module.aivideo.service.node;

import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.dal.mysql.node.*;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.function.Supplier;
import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_LIFECYCLE_IN_PROGRESS;

@Service
public class NodeOperationService {
    @Resource private NodeOperationMutexMapper mutexMapper;
    @Resource private NodeDeploymentMapper deploymentMapper;
    @Resource private NodeCommandMapper commandMapper;
    @Resource private NodeUpgradeMapper upgradeMapper;
    @Resource private EdgeNodeMapper edgeNodeMapper;
    @Resource private TransactionTemplate transactionTemplate;

    public <T> T exclusive(String key, Supplier<T> action) {
        Long tenantId = TenantContextHolder.getRequiredTenantId();
        return transactionTemplate.execute(status -> {
            mutexMapper.ensure(tenantId, key);
            mutexMapper.lock(tenantId, key);
            return action.get();
        });
    }

    public void requireIdle(Long nodeId, String host, boolean activationRestart) {
        if (deploymentMapper.hasActive(nodeId, host)) throw exception(NODE_LIFECYCLE_IN_PROGRESS);
        if (nodeId == null) return;
        var node = edgeNodeMapper.selectById(nodeId);
        if (node != null && deploymentMapper.hasActiveResource(null, node.getCode())) throw exception(NODE_LIFECYCLE_IN_PROGRESS);
        if (commandMapper.existsActiveByNode(nodeId)) throw exception(NODE_LIFECYCLE_IN_PROGRESS);
        var upgrade = upgradeMapper.selectLatestByNode(nodeId);
        if (upgrade != null && java.util.Set.of("QUEUED", "RUNNING", "AWAITING_ACTIVATION", "VERIFYING").contains(upgrade.getStatus())
                && !(activationRestart && "AWAITING_ACTIVATION".equals(upgrade.getStatus()))) {
            throw exception(NODE_LIFECYCLE_IN_PROGRESS);
        }
    }
}
