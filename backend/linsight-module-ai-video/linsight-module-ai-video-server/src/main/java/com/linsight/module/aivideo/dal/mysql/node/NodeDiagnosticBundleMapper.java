package com.linsight.module.aivideo.dal.mysql.node;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.framework.tenant.core.aop.TenantIgnore;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDiagnosticBundleDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface NodeDiagnosticBundleMapper extends BaseMapperX<NodeDiagnosticBundleDO> {
    default List<NodeDiagnosticBundleDO> selectByNodeId(Long nodeId) {
        return selectList(new LambdaQueryWrapperX<NodeDiagnosticBundleDO>()
                .eq(NodeDiagnosticBundleDO::getNodeId, nodeId)
                .orderByDesc(NodeDiagnosticBundleDO::getId)
                .last("LIMIT 50"));
    }

    @TenantIgnore
    default List<NodeDiagnosticBundleDO> selectQueuedGlobal() {
        return selectList(new LambdaQueryWrapperX<NodeDiagnosticBundleDO>()
                .eq(NodeDiagnosticBundleDO::getStatus, "QUEUED")
                .orderByAsc(NodeDiagnosticBundleDO::getId)
                .last("LIMIT 10"));
    }
}
