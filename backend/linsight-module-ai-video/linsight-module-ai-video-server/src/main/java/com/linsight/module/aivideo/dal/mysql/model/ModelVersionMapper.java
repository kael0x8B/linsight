package com.linsight.module.aivideo.dal.mysql.model;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;
import java.util.Collection;

@Mapper
public interface ModelVersionMapper extends BaseMapperX<ModelVersionDO> {

    default ModelVersionDO selectByModelAndVersion(Long modelId, String version) {
        return selectOne(new LambdaQueryWrapperX<ModelVersionDO>()
                .eq(ModelVersionDO::getModelId, modelId)
                .eq(ModelVersionDO::getVersion, version));
    }

    default ModelVersionDO selectByModelAndSha256(Long modelId, String sha256) {
        return selectOne(new LambdaQueryWrapperX<ModelVersionDO>()
                .eq(ModelVersionDO::getModelId, modelId)
                .eq(ModelVersionDO::getSha256, sha256));
    }

    default List<ModelVersionDO> selectListByModelId(Long modelId) {
        return selectList(new LambdaQueryWrapperX<ModelVersionDO>()
                .eq(ModelVersionDO::getModelId, modelId)
                .orderByDesc(ModelVersionDO::getId));
    }

    default List<ModelVersionDO> selectListByModelIds(Collection<Long> modelIds) {
        return selectList(new LambdaQueryWrapperX<ModelVersionDO>()
                .in(ModelVersionDO::getModelId, modelIds)
                .orderByDesc(ModelVersionDO::getId));
    }

    default Long selectCountByModelId(Long modelId) {
        return selectCount(ModelVersionDO::getModelId, modelId);
    }

    default void supersedeCurrentPublished(Long modelId, Long exceptId) {
        update(null, new LambdaUpdateWrapper<ModelVersionDO>()
                .eq(ModelVersionDO::getModelId, modelId)
                .eq(ModelVersionDO::getPublishStatus, "PUBLISHED")
                .ne(ModelVersionDO::getId, exceptId)
                .set(ModelVersionDO::getPublishStatus, "SUPERSEDED"));
    }

}
