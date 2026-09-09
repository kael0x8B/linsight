package com.linsight.module.aivideo.dal.mysql.node;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.node.NodeCommandDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface NodeCommandMapper extends BaseMapperX<NodeCommandDO> {
    default List<NodeCommandDO> selectRecentByNode(Long nodeId) {
        return selectList(new LambdaQueryWrapperX<NodeCommandDO>()
                .eq(NodeCommandDO::getNodeId, nodeId)
                .orderByDesc(NodeCommandDO::getId).last("LIMIT 50"));
    }

    default NodeCommandDO selectByCommandId(String commandId) {
        return selectOne(NodeCommandDO::getCommandId, commandId);
    }

    default NodeCommandDO selectByIdempotencyKey(String key) {
        return selectOne(NodeCommandDO::getIdempotencyKey, key);
    }

    default NodeCommandDO selectLatestLifecycleByNode(Long nodeId) {
        return selectOne(new LambdaQueryWrapperX<NodeCommandDO>()
                .eq(NodeCommandDO::getNodeId, nodeId)
                .in(NodeCommandDO::getCommandType, List.of("RESTART_NODE", "SHUTDOWN_NODE"))
                .orderByDesc(NodeCommandDO::getId)
                .last("LIMIT 1"));
    }

    default boolean existsActiveByNode(Long nodeId) {
        return selectCount(new LambdaQueryWrapperX<NodeCommandDO>()
                .eq(NodeCommandDO::getNodeId, nodeId)
                .in(NodeCommandDO::getStatus, List.of("QUEUED", "SENT", "RUNNING"))) > 0;
    }

    default List<NodeCommandDO> selectDispatchable(Long nodeId, LocalDateTime sentRetryBefore,
                                                   LocalDateTime runningRetryBefore) {
        return selectList(new LambdaQueryWrapperX<NodeCommandDO>()
                .eq(NodeCommandDO::getNodeId, nodeId)
                .and(wrapper -> wrapper.eq(NodeCommandDO::getStatus, "QUEUED")
                        .or(nested -> nested.eq(NodeCommandDO::getStatus, "SENT")
                                .lt(NodeCommandDO::getSentTime, sentRetryBefore))
                        .or(nested -> nested.eq(NodeCommandDO::getStatus, "RUNNING")
                                .lt(NodeCommandDO::getUpdateTime, runningRetryBefore)))
                .gt(NodeCommandDO::getExpireTime, LocalDateTime.now())
                .lt(NodeCommandDO::getAttemptCount, 5)
                .orderByAsc(NodeCommandDO::getId)
                .last("LIMIT 1"));
    }

    @InterceptorIgnore(tenantLine = "true")
    @Select("""
            SELECT * FROM ai_node_command
            WHERE deleted = b'0'
              AND status IN ('QUEUED', 'SENT', 'RUNNING')
              AND expire_time <= CURRENT_TIMESTAMP
            ORDER BY id
            LIMIT 100
            """)
    List<NodeCommandDO> selectExpiredGlobal();

    default int markExpired(Long id, String expectedStatus, LocalDateTime now) {
        return update(null, new LambdaUpdateWrapper<NodeCommandDO>()
                .eq(NodeCommandDO::getId, id)
                .eq(NodeCommandDO::getStatus, expectedStatus)
                .le(NodeCommandDO::getExpireTime, now)
                .set(NodeCommandDO::getStatus, "EXPIRED")
                .set(NodeCommandDO::getErrorCode, "NODE_COMMAND_EXPIRED")
                .set(NodeCommandDO::getErrorMessage, "节点命令超过执行期限")
                .set(NodeCommandDO::getFinishTime, now)
                .set(NodeCommandDO::getUpdater, "node-command-expiry"));
    }

    default int markSent(Long id, String expectedStatus, LocalDateTime expectedSentTime,
                         LocalDateTime expectedUpdateTime, LocalDateTime now) {
        LambdaUpdateWrapper<NodeCommandDO> update = new LambdaUpdateWrapper<NodeCommandDO>()
                .eq(NodeCommandDO::getId, id)
                .eq(NodeCommandDO::getStatus, expectedStatus)
                .set(NodeCommandDO::getStatus, "SENT")
                .set(NodeCommandDO::getSentTime, now)
                .setSql("attempt_count = attempt_count + 1");
        if ("SENT".equals(expectedStatus)) {
            update.eq(NodeCommandDO::getSentTime, expectedSentTime);
        } else if ("RUNNING".equals(expectedStatus)) {
            update.eq(NodeCommandDO::getUpdateTime, expectedUpdateTime);
        }
        return update(null, update);
    }
}
