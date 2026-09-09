package com.linsight.module.aivideo.dal.mysql.node;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.node.NodeLogDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Param;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface NodeLogMapper extends BaseMapperX<NodeLogDO> {
    default NodeLogDO selectByNodeAndEntry(Long nodeId, String entryId) {
        return selectOne(new LambdaQueryWrapperX<NodeLogDO>()
                .eq(NodeLogDO::getNodeId, nodeId)
                .eq(NodeLogDO::getEntryId, entryId));
    }

    default PageResult<NodeLogDO> selectPage(PageParam pageParam, Long nodeId, Long taskId,
                                              String component, String level, String keyword,
                                              String diagnosticId, LocalDateTime[] loggedAt) {
        return selectPage(pageParam, nodeId, taskId, component, level, keyword, diagnosticId, loggedAt, null, null);
    }

    default PageResult<NodeLogDO> selectPage(PageParam pageParam, Long nodeId, Long taskId,
                                              String component, String level, String keyword,
                                              String diagnosticId, LocalDateTime[] loggedAt,
                                              Long snapshotMaxId, Long afterId) {
        LambdaQueryWrapperX<NodeLogDO> query = new LambdaQueryWrapperX<NodeLogDO>()
                .eqIfPresent(NodeLogDO::getNodeId, nodeId)
                .leIfPresent(NodeLogDO::getId, snapshotMaxId)
                .gtIfPresent(NodeLogDO::getId, afterId)
                .eqIfPresent(NodeLogDO::getTaskId, taskId)
                .eqIfPresent(NodeLogDO::getComponent, component)
                .eqIfPresent(NodeLogDO::getLevel, level)
                .eqIfPresent(NodeLogDO::getDiagnosticId, diagnosticId)
                .betweenIfPresent(NodeLogDO::getLoggedAt, loggedAt);
        if (keyword != null && !keyword.isBlank()) {
            query.and(value -> value.like(NodeLogDO::getMessage, keyword)
                    .or().like(NodeLogDO::getContextJson, keyword));
        }
        if (afterId != null) {
            query.orderByAsc(NodeLogDO::getId);
        } else {
            query.orderByDesc(NodeLogDO::getLoggedAt).orderByDesc(NodeLogDO::getId);
        }
        return selectPage(pageParam, query);
    }

    default List<NodeLogDO> selectBefore(Long nodeId, Long id, int limit) {
        return selectList(new LambdaQueryWrapperX<NodeLogDO>()
                .eq(NodeLogDO::getNodeId, nodeId)
                .lt(NodeLogDO::getId, id)
                .orderByDesc(NodeLogDO::getId)
                .last("LIMIT " + limit));
    }

    default List<NodeLogDO> selectAfter(Long nodeId, Long id, int limit) {
        return selectList(new LambdaQueryWrapperX<NodeLogDO>()
                .eq(NodeLogDO::getNodeId, nodeId)
                .gt(NodeLogDO::getId, id)
                .orderByAsc(NodeLogDO::getId)
                .last("LIMIT " + limit));
    }

    default List<NodeLogDO> selectForDiagnostic(Long nodeId, Long taskId,
                                                 LocalDateTime rangeStart,
                                                 LocalDateTime rangeEnd) {
        return selectList(new LambdaQueryWrapperX<NodeLogDO>()
                .eq(NodeLogDO::getNodeId, nodeId)
                .eqIfPresent(NodeLogDO::getTaskId, taskId)
                .between(NodeLogDO::getLoggedAt, rangeStart, rangeEnd)
                .orderByAsc(NodeLogDO::getLoggedAt)
                .orderByAsc(NodeLogDO::getId)
                .last("LIMIT 10000"));
    }

    /** Physical retention cleanup is intentionally cross-tenant and bounded per run. */
    @InterceptorIgnore(tenantLine = "true")
    @Delete("""
            DELETE FROM ai_node_log
            WHERE level = #{level} AND logged_at < #{cutoff}
            ORDER BY logged_at, id LIMIT #{batchSize}
            """)
    int deleteExpiredGlobal(@Param("level") String level, @Param("cutoff") LocalDateTime cutoff,
                            @Param("batchSize") int batchSize);
}
