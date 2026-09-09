package com.linsight.module.aivideo.dal.mysql.model;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDeploymentDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;
import java.util.Collection;

@Mapper
public interface ModelDeploymentMapper extends BaseMapperX<ModelDeploymentDO> {
    default ModelDeploymentDO selectByVersionAndNode(Long versionId, Long nodeId) {
        return selectOne(new LambdaQueryWrapperX<ModelDeploymentDO>()
                .eq(ModelDeploymentDO::getModelVersionId, versionId)
                .eq(ModelDeploymentDO::getNodeId, nodeId)
                .orderByDesc(ModelDeploymentDO::getConfigVersion)
                .last("LIMIT 1"));
    }
    default ModelDeploymentDO selectByCommandId(String commandId) {
        return selectOne(ModelDeploymentDO::getCommandId, commandId);
    }
    default List<ModelDeploymentDO> selectListByVersion(Long versionId) {
        return selectList(new LambdaQueryWrapperX<ModelDeploymentDO>()
                .eq(ModelDeploymentDO::getModelVersionId, versionId)
                .orderByDesc(ModelDeploymentDO::getId));
    }

    default List<ModelDeploymentDO> selectListByVersions(Collection<Long> versionIds) {
        return selectList(new LambdaQueryWrapperX<ModelDeploymentDO>()
                .in(ModelDeploymentDO::getModelVersionId, versionIds)
                .orderByDesc(ModelDeploymentDO::getId));
    }
}
