package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.dal.dataobject.node.NodeCommandDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeCommandMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.*;

@Service
public class NodeCommandServiceImpl implements NodeCommandService {
    private static final long SENT_RETRY_SECONDS = 30;
    private static final long RUNNING_LEASE_SECONDS = 300;
    private static final Set<String> TYPES = Set.of(
            "DEPLOY_MODEL", "UNINSTALL_MODEL", "RUN_MODEL_TEST", "VERIFY_FACE", "ENTRY_FACE", "START_TASK", "STOP_TASK",
            "UPGRADE_AGENT", "ROLLBACK_AGENT", "APPLY_TASK_SETTINGS",
            "RESTART_NODE", "SHUTDOWN_NODE");
    private static final Set<String> REPORT_STATUSES = Set.of("RUNNING", "SUCCEEDED", "FAILED");

    @Resource
    private NodeCommandMapper nodeCommandMapper;
    @Resource
    private NodeService nodeService;

    @Override
    public String createCommand(String commandId, Long nodeId, String commandType, Long aggregateId,
                                Integer configVersion, String idempotencyKey) {
        nodeService.validateNodeAvailable(nodeId);
        if (!TYPES.contains(commandType)) {
            throw exception(NODE_COMMAND_TYPE_INVALID);
        }
        NodeCommandDO existing = nodeCommandMapper.selectByIdempotencyKey(idempotencyKey);
        if (existing != null) {
            return existing.getCommandId();
        }
        NodeCommandDO command = new NodeCommandDO();
        command.setCommandId(commandId);
        command.setNodeId(nodeId);
        command.setCommandType(commandType);
        command.setAggregateId(aggregateId);
        command.setConfigVersion(configVersion);
        command.setIdempotencyKey(idempotencyKey);
        command.setStatus("QUEUED");
        command.setAttemptCount(0);
        command.setExpireTime(LocalDateTime.now().plusMinutes(30));
        if (com.linsight.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId() == null) {
            command.setCreator("system");
            command.setUpdater("system");
        }
        nodeCommandMapper.insert(command);
        return commandId;
    }

    @Override
    public List<NodeCommandDTO> getRecentCommands(Long nodeId) {
        nodeService.validateNodeExists(nodeId);
        return BeanUtils.toBean(nodeCommandMapper.selectRecentByNode(nodeId), NodeCommandDTO.class);
    }

    @Override
    public NodeCommandDTO pullCommand(Long nodeId) {
        LocalDateTime now = LocalDateTime.now();
        List<NodeCommandDO> commands = nodeCommandMapper.selectDispatchable(nodeId,
                now.minusSeconds(SENT_RETRY_SECONDS), now.minusSeconds(RUNNING_LEASE_SECONDS));
        if (commands.isEmpty()) {
            return null;
        }
        NodeCommandDO command = commands.get(0);
        if (nodeCommandMapper.markSent(command.getId(), command.getStatus(), command.getSentTime(),
                command.getUpdateTime(), now) == 0) {
            return null;
        }
        command.setStatus("SENT");
        return BeanUtils.toBean(command, NodeCommandDTO.class);
    }

    @Override
    public NodeCommandDTO reportCommand(Long nodeId, NodeCommandDTO report) {
        if (!REPORT_STATUSES.contains(report.getStatus())) {
            throw exception(NODE_COMMAND_STATUS_INVALID);
        }
        NodeCommandDO command = requireCommand(report.getCommandId(), nodeId);
        if (Set.of("SUCCEEDED", "FAILED", "EXPIRED").contains(command.getStatus())) {
            if (Objects.equals(command.getStatus(), report.getStatus())) {
                enrichReport(nodeId, report, command);
                return report;
            }
            throw exception(NODE_COMMAND_STATUS_INVALID);
        }
        command.setStatus(report.getStatus());
        command.setResultSummary(JsonUtils.toJsonString(report));
        command.setErrorCode(report.getErrorCode());
        command.setErrorMessage(report.getErrorMessage());
        if (!"RUNNING".equals(report.getStatus())) {
            command.setFinishTime(LocalDateTime.now());
        }
        command.setUpdater("edge-agent");
        nodeCommandMapper.updateById(command);
        enrichReport(nodeId, report, command);
        return report;
    }

    private static void enrichReport(Long nodeId, NodeCommandDTO report, NodeCommandDO command) {
        report.setNodeId(nodeId);
        report.setCommandType(command.getCommandType());
        report.setAggregateId(command.getAggregateId());
        report.setConfigVersion(command.getConfigVersion());
        report.setIdempotencyKey(command.getIdempotencyKey());
    }

    @Override
    public NodeCommandDTO getCommandForNode(String commandId, Long nodeId) {
        return BeanUtils.toBean(requireCommand(commandId, nodeId), NodeCommandDTO.class);
    }

    @Override
    public List<NodeCommandDTO> getExpiredCommandsGlobal() {
        return BeanUtils.toBean(nodeCommandMapper.selectExpiredGlobal(), NodeCommandDTO.class);
    }

    @Override
    public NodeCommandDTO expireCommand(Long id) {
        NodeCommandDO command = nodeCommandMapper.selectById(id);
        LocalDateTime now = LocalDateTime.now();
        if (command == null || !Set.of("QUEUED", "SENT", "RUNNING").contains(command.getStatus())
                || command.getExpireTime() == null || command.getExpireTime().isAfter(now)
                || nodeCommandMapper.markExpired(id, command.getStatus(), now) == 0) {
            return null;
        }
        command.setStatus("EXPIRED");
        command.setErrorCode("NODE_COMMAND_EXPIRED");
        command.setErrorMessage("节点命令超过执行期限");
        command.setFinishTime(now);
        NodeCommandDTO result = BeanUtils.toBean(command, NodeCommandDTO.class);
        enrichReport(command.getNodeId(), result, command);
        return result;
    }

    private NodeCommandDO requireCommand(String commandId, Long nodeId) {
        NodeCommandDO command = nodeCommandMapper.selectByCommandId(commandId);
        if (command == null || !Objects.equals(command.getNodeId(), nodeId)) {
            throw exception(NODE_COMMAND_NOT_FOUND);
        }
        return command;
    }
}
