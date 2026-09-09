package com.linsight.module.aivideo.dal.mysql.node;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDeploymentDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface NodeDeploymentMapper extends BaseMapperX<NodeDeploymentDO> {
    default boolean hasActiveResource(String key, String code) {
        return selectCount(new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<NodeDeploymentDO>()
                .in(NodeDeploymentDO::getStatus, "QUEUED", "RUNNING")
                .and(q -> q.eq(key != null, NodeDeploymentDO::getResourceKey, key)
                        .or().eq(code != null, NodeDeploymentDO::getNodeCode, code))) > 0;
    }
    default boolean hasActive(Long nodeId, String host) {
        if (nodeId == null && host == null) return false;
        return selectCount(new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<NodeDeploymentDO>()
                .in(NodeDeploymentDO::getStatus, "QUEUED", "RUNNING")
                .and(q -> { if (nodeId != null) q.eq(NodeDeploymentDO::getEdgeNodeId, nodeId); if (host != null) { if (nodeId != null) q.or(); q.eq(NodeDeploymentDO::getHost, host); } })) > 0;
    }
    default NodeDeploymentDO selectByRequestId(String requestId) {
        return requestId == null ? null : selectOne(NodeDeploymentDO::getRequestId, requestId);
    }

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE ai_node_deployment SET status='FAILED', stage='INTERRUPTED', log_status=IF(log_status='LEGACY','LEGACY','COMPLETE'), message='控制面已重启，部署中断；请重新预检，远端未确认的切换将自动恢复', finish_time=NOW(), update_time=NOW() WHERE deleted=b'0' AND status IN ('QUEUED','RUNNING') AND (executor_owner IS NULL OR executor_owner <> #{owner})")
    int interruptOtherExecutors(@Param("owner") String owner);
    default List<NodeDeploymentDO> selectRecentList() {
        var page = new com.linsight.framework.common.pojo.PageParam();
        page.setPageNo(1); page.setPageSize(50);
        return selectHistoryPage(page, null).getList();
    }

    default com.linsight.framework.common.pojo.PageResult<NodeDeploymentDO> selectHistoryPage(
            com.linsight.framework.common.pojo.PageParam page, Long nodeId) {
        return selectPage(page, new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<NodeDeploymentDO>()
                .eq(nodeId != null, NodeDeploymentDO::getEdgeNodeId, nodeId)
                .select(NodeDeploymentDO::getId, NodeDeploymentDO::getHost, NodeDeploymentDO::getPort,
                        NodeDeploymentDO::getUsername, NodeDeploymentDO::getNodeCode, NodeDeploymentDO::getNodeName,
                        NodeDeploymentDO::getOperationType,
                        NodeDeploymentDO::getLogStatus, NodeDeploymentDO::getLogTruncated,
                        NodeDeploymentDO::getControlPlaneUrl, NodeDeploymentDO::getPreviousVersion,
                        NodeDeploymentDO::getTargetVersion,
                        NodeDeploymentDO::getTargetArch, NodeDeploymentDO::getOsSummary,
                        NodeDeploymentDO::getPythonVersion, NodeDeploymentDO::getRuntimePackageSha256,
                        NodeDeploymentDO::getStatus, NodeDeploymentDO::getStage, NodeDeploymentDO::getProgress,
                        NodeDeploymentDO::getMessage, NodeDeploymentDO::getDiagnosticId,
                        NodeDeploymentDO::getEdgeNodeId, NodeDeploymentDO::getCreateTime,
                        NodeDeploymentDO::getUpdateTime, NodeDeploymentDO::getFinishTime)
                .orderByDesc(NodeDeploymentDO::getId));
    }

    @Update("""
            UPDATE ai_node_deployment
            SET log_truncated = log_truncated OR CHAR_LENGTH(COALESCE(output_log, '')) + CHAR_LENGTH(#{output}) > 262144,
                output_log = RIGHT(CONCAT(COALESCE(output_log, ''), #{output}), 262144)
            WHERE id = #{id} AND deleted = b'0'
            """)
    int appendOutput(@Param("id") Long id, @Param("output") String output);
}
