package com.linsight.module.aivideo.dal.mysql.node;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.node.NodeUpgradeDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface NodeUpgradeMapper extends BaseMapperX<NodeUpgradeDO> {
    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine = "true")
    @org.apache.ibatis.annotations.Select("SELECT * FROM ai_node_upgrade WHERE deleted=b'0' AND status IN ('QUEUED','RUNNING','AWAITING_ACTIVATION','VERIFYING') ORDER BY update_time, id LIMIT 200")
    List<NodeUpgradeDO> selectPendingGlobal();
    default NodeUpgradeDO selectByCommandId(String commandId) {
        return selectOne(NodeUpgradeDO::getCommandId, commandId);
    }

    default NodeUpgradeDO selectLatestByNode(Long nodeId) {
        return selectOne(new LambdaQueryWrapperX<NodeUpgradeDO>()
                .eq(NodeUpgradeDO::getNodeId, nodeId)
                .orderByDesc(NodeUpgradeDO::getId)
                .last("LIMIT 1"));
    }

    default List<NodeUpgradeDO> selectListByNode(Long nodeId) {
        return selectList(new LambdaQueryWrapperX<NodeUpgradeDO>()
                .eq(NodeUpgradeDO::getNodeId, nodeId)
                .orderByDesc(NodeUpgradeDO::getId)
                .last("LIMIT 50"));
    }
}
