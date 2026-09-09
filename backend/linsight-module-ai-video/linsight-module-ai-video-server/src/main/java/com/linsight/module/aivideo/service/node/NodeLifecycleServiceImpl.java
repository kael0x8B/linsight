package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeCommandDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeCommandMapper;
import com.linsight.module.aivideo.enums.node.NodeOnlineStatusEnum;
import com.linsight.module.aivideo.service.task.TaskService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Objects;
import java.util.UUID;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DELETE_ONLINE;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DELETE_REFERENCED;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_LIFECYCLE_IN_PROGRESS;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_NOT_AVAILABLE;

@Service
public class NodeLifecycleServiceImpl implements NodeLifecycleService {
    @Resource private EdgeNodeMapper edgeNodeMapper;
    @Resource private NodeCommandMapper nodeCommandMapper;
    @Resource private NodeCommandService nodeCommandService;
    @Resource private TaskService taskService;
    @Resource private TransactionTemplate transactionTemplate;
    @Resource private NodeOperationService operationService;
    @Resource private NodeUpgradeActivationService activationService;

    @Override
    public String restartNode(Long nodeId) {
        return createLifecycleCommand(nodeId, "RESTART_NODE");
    }

    @Override
    public String shutdownNode(Long nodeId) {
        return createLifecycleCommand(nodeId, "SHUTDOWN_NODE");
    }

    @Override
    public void deleteNode(Long nodeId) {
        operationService.exclusive("node:" + nodeId, () -> {
        EdgeNodeDO node = edgeNodeMapper.selectById(nodeId);
        if (node == null) throw exception(NODE_NOT_AVAILABLE);
        operationService.requireIdle(nodeId, node.getIpAddress(), false);
        if (Objects.equals(node.getOnlineStatus(), NodeOnlineStatusEnum.ONLINE.getStatus())) {
            throw exception(NODE_DELETE_ONLINE);
        }
        if (taskService.hasTasksForNode(nodeId)) {
            throw exception(NODE_DELETE_REFERENCED);
        }
        if (nodeCommandMapper.existsActiveByNode(nodeId)) {
            throw exception(NODE_LIFECYCLE_IN_PROGRESS);
        }
        edgeNodeMapper.deleteById(nodeId);
        return null;
        });
    }

    private String createLifecycleCommand(Long nodeId, String commandType) {
        return operationService.exclusive("node:" + nodeId, () -> {
            EdgeNodeDO node = requireNode(nodeId);
            operationService.requireIdle(nodeId, node.getIpAddress(), "RESTART_NODE".equals(commandType));
            NodeCommandDO latest = nodeCommandMapper.selectLatestLifecycleByNode(nodeId);
            int configVersion = latest == null ? 1 : latest.getConfigVersion() + 1;
            String commandId = UUID.randomUUID().toString();
            String result = nodeCommandService.createCommand(commandId, nodeId, commandType, nodeId,
                    configVersion, "node-lifecycle:" + nodeId + ":" + configVersion);
            if ("RESTART_NODE".equals(commandType)) activationService.restartRequested(nodeId);
            return result;
        });
    }

    private EdgeNodeDO requireNode(Long nodeId) {
        EdgeNodeDO node = edgeNodeMapper.selectById(nodeId);
        if (node == null || !Objects.equals(node.getStatus(), 0)) {
            throw exception(NODE_NOT_AVAILABLE);
        }
        return node;
    }
}
