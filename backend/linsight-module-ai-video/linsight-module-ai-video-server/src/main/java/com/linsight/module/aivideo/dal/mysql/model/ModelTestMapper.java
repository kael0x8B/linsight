package com.linsight.module.aivideo.dal.mysql.model;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.model.ModelTestDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface ModelTestMapper extends BaseMapperX<ModelTestDO> {
    default ModelTestDO selectByCommandId(String commandId) {
        return selectOne(ModelTestDO::getCommandId, commandId);
    }
    default List<ModelTestDO> selectListByVersion(Long versionId) {
        return selectList(new LambdaQueryWrapperX<ModelTestDO>()
                .eq(ModelTestDO::getModelVersionId, versionId)
                .orderByDesc(ModelTestDO::getId));
    }
    default boolean existsSucceededByVersionAndNode(Long versionId, Long nodeId) {
        return selectCount(new LambdaQueryWrapperX<ModelTestDO>()
                .eq(ModelTestDO::getModelVersionId, versionId)
                .eq(ModelTestDO::getNodeId, nodeId)
                .eq(ModelTestDO::getStatus, "SUCCEEDED")) > 0;
    }
}
